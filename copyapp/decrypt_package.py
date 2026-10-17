"""Bounded, independently checked whole-bundle decryption on a named USB device."""

import asyncio
import hashlib
import json
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import tempfile
import uuid
from copy import copy
from pathlib import Path
from zipfile import ZipFile

from copyapp.decrypt import _cryptid_offset, _installed_main
from copyapp.decrypt_verify import inspect_decrypted_ipa, write_decryption_check
from copyapp.ipa import analyze_ipa, inspect_macho, write_ipa_report
from copyapp.objc import ObjCIndexError, index_objc, write_objc_report
from copyapp.root_bridge import MAX_OUTPUT, run_root_command, resolve_jailbreak_executable
from copyapp.ssh_acquire import _ssh_argv


PINNED_HELPER_SHA256 = "8fe2ace941132c29d19480adba554ebd71d2a1ea27a2c7c6ee1eb648a504151b"
CASE_EVIDENCE_NAMES = (
    "analysis.ipa", "decryption.json", "check/decryption-check.json",
    "check/decryption-check.md", "device-run/result.json",
    "device-run/output.txt", "static/manifest.json",
    "static/ipa-index.json", "static/ipa-report.md",
    "static/objc-index.json", "static/objc-report.md", "static/objc-status.json",
)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_roothide_ssh(ssh: list) -> bool:
    result = subprocess.run(ssh + ["test -d /rootfs/var/mobile/Media && "
                                   "command -v jbroot >/dev/null 2>&1"],
                            capture_output=True, timeout=10)
    return result.returncode == 0


def _run_roothide_helper(ssh: list, udid: str, command: list,
                         output: Path) -> dict:
    """Run the pinned helper from mobile's RootHide namespace, with a bound."""
    process = subprocess.run(ssh + [shlex.join(command)], capture_output=True,
                             timeout=140)
    captured = process.stdout + process.stderr
    output.mkdir(parents=True, exist_ok=True)
    (output / "output.txt").write_bytes(captured[:MAX_OUTPUT])
    result = {"schema_version": 1, "device_id": udid,
              "transport": "named USB mobile SSH in RootHide namespace",
              "command": command, "exit_code": process.returncode,
              "output_truncated": len(captured) > MAX_OUTPUT}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def _verify_changed_binaries(snapshot: Path, result: Path, source_index: dict) -> list:
    records = []
    with ZipFile(snapshot) as before_zip, ZipFile(result) as after_zip:
        for binary in source_index["binaries"]:
            if not binary.get("encrypted_on_disk"):
                continue
            path = binary["path"]
            before = before_zip.read(path)
            after = after_zip.read(path)
            if len(before) != len(after):
                raise ValueError(f"decrypted binary size changed: {path}")
            before_info, after_info = inspect_macho(before), inspect_macho(after)
            crypt = before_info["encryption_info"]
            start, size = crypt["cryptoff"], crypt["cryptsize"]
            patch = _cryptid_offset(before)
            expected = bytearray(before)
            expected[start:start + size] = after[start:start + size]
            expected[patch:patch + 4] = after[patch:patch + 4]
            if expected != after or before_info["uuid"] != after_info["uuid"]:
                raise ValueError(f"unexpected executable changes outside encrypted region: {path}")
            if after_info["encryption_status"] != "cryptid_zero":
                raise ValueError(f"executable remains encrypted: {path}")
            changed = sum(a != b for a, b in zip(before[start:start + size], after[start:start + size]))
            if changed == 0:
                raise ValueError(f"no encrypted code bytes changed: {path}")
            records.append({
                "path": path,
                "uuid": before_info["uuid"],
                "cryptoff": start,
                "cryptsize": size,
                "changed_encrypted_bytes": changed,
                "encrypted_sha256": hashlib.sha256(before).hexdigest(),
                "decrypted_sha256": hashlib.sha256(after).hexdigest(),
                "only_cryptid_and_encrypted_region_changed": True,
            })
    return records


def _same_member_bytes(left, right) -> bool:
    while True:
        a = left.read(1024 * 1024)
        b = right.read(1024 * 1024)
        if a != b:
            return False
        if not a:
            return True


def _canonicalize_analysis_ipa(snapshot: Path, recovered: Path, output: Path,
                               replaced_paths: set) -> None:
    """Keep the source archive layout while inserting verified decrypted code.

    The device helper may timestamp recovered ZIP entries at run time. This
    rebuild gives identical source and recovered bytes an identical IPA hash,
    and rejects changes to members outside the declared encrypted binaries.
    """
    if output.exists():
        raise FileExistsError(output)
    with ZipFile(snapshot) as source, ZipFile(recovered) as device, ZipFile(output, "w") as target:
        source_infos = source.infolist()
        device_infos = device.infolist()
        source_names = [item.filename for item in source_infos]
        device_names = [item.filename for item in device_infos]
        source_set, device_set = set(source_names), set(device_names)
        omitted = source_set - device_set
        # The pinned helper drops FairPlay SC_Info receipts while repacking.
        # Keep that precise omission, but reject any lost app resource.
        expected_omissions = all(name.startswith("Payload/") and "/SC_Info/" in name
                                 for name in omitted)
        if (len(source_names) != len(set(source_names)) or
                len(device_names) != len(set(device_names)) or
                device_set - source_set or not expected_omissions or
                not replaced_paths.issubset(device_set)):
            raise ValueError("decrypted IPA member list differs from source snapshot")
        for info in source_infos:
            if info.filename in omitted:
                continue
            device_info = device.getinfo(info.filename)
            if info.is_dir() != device_info.is_dir():
                raise ValueError(f"decrypted IPA member type changed: {info.filename}")
            if info.is_dir():
                target.writestr(copy(info), b"")
                continue
            if info.filename not in replaced_paths:
                with source.open(info) as before, device.open(device_info) as after:
                    if not _same_member_bytes(before, after):
                        raise ValueError(f"decrypted IPA changed unencrypted member: {info.filename}")
            with (device.open(device_info) if info.filename in replaced_paths
                  else source.open(info)) as data, target.open(copy(info), "w") as sink:
                shutil.copyfileobj(data, sink, length=1024 * 1024)


def _write_case_manifest(output: Path, snapshot: Path, record: dict) -> Path:
    manifest = {
        "schema_version": 1, "kind": "decrypted_package", "status": "complete",
        "bundle_id": record["bundle_id"],
        "device_id_sha256_prefix": record["device_id_sha256_prefix"],
        "source_snapshot": str(snapshot.resolve(strict=True)),
        "source_snapshot_sha256": record["source_snapshot_sha256"],
        "analysis_ipa_sha256": record["analysis_ipa_sha256"],
        "evidence": [{"path": name, "sha256": _hash_file(output / name)}
                     for name in CASE_EVIDENCE_NAMES if (output / name).is_file()],
    }
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def validate_decrypt_package_case(output: Path, manifest: dict) -> bool:
    """Recompute the source-to-analysis byte audit for a standalone case."""
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "decrypted_package" or
            manifest.get("status") != "complete"):
        return False
    evidence_paths = [item["path"] for item in manifest["evidence"]]
    required = set(CASE_EVIDENCE_NAMES[:9])
    if (len(evidence_paths) != len(set(evidence_paths)) or
            not required.issubset(set(evidence_paths)) or
            set(evidence_paths) != {name for name in CASE_EVIDENCE_NAMES
                                    if (output / name).is_file()} or
            not ({"static/objc-index.json", "static/objc-report.md"}.issubset(
                set(evidence_paths)) or "static/objc-status.json" in evidence_paths)):
        return False
    snapshot = Path(manifest["source_snapshot"]).resolve(strict=True)
    candidate = (output / "analysis.ipa").resolve(strict=True)
    if snapshot == candidate or output.resolve() in snapshot.parents:
        return False
    record = json.loads((output / "decryption.json").read_text(encoding="utf-8"))
    device_run = json.loads((output / "device-run/result.json").read_text(
        encoding="utf-8"))
    run_command = device_run.get("command")
    if (record.get("schema_version") != 1 or
            record.get("bundle_id") != manifest.get("bundle_id") or
            record.get("device_id_sha256_prefix") !=
            manifest.get("device_id_sha256_prefix") or
            _hash_file(snapshot) != record.get("source_snapshot_sha256") or
            record.get("source_snapshot_sha256") !=
            manifest.get("source_snapshot_sha256") or
            _hash_file(candidate) != record.get("analysis_ipa_sha256") or
            record.get("analysis_ipa_sha256") != manifest.get("analysis_ipa_sha256") or
            record.get("helper_sha256") != PINNED_HELPER_SHA256 or
            record.get("all_macho_headers_decrypted") is not True or
            device_run.get("exit_code") != 0 or
            hashlib.sha256(device_run["device_id"].encode()).hexdigest()[:16] !=
            record.get("device_id_sha256_prefix") or
            not isinstance(run_command, list) or
            len(run_command) < 5 or
            "decrypt" not in run_command or
            record["bundle_id"] not in run_command):
        return False
    source_index = analyze_ipa(snapshot)
    static_index = analyze_ipa(candidate)
    if (source_index.get("bundle_id") != record["bundle_id"] or
            source_index.get("version") != record.get("installed_version") or
            source_index.get("build") != record.get("installed_build") or
            static_index != json.loads((output / "static/ipa-index.json").read_text(
                encoding="utf-8")) or
            static_index.get("ipa_sha256") != record["analysis_ipa_sha256"]):
        return False
    check = inspect_decrypted_ipa(candidate, record["bundle_id"])
    saved_check = json.loads((output / "check/decryption-check.json").read_text(
        encoding="utf-8"))
    saved_source = Path(saved_check["source"])
    source_matches = (saved_source.resolve() == candidate if saved_source.is_absolute()
                      else ".." not in saved_source.parts and bool(saved_source.parts) and
                      candidate.parts[-len(saved_source.parts):] == saved_source.parts)
    if not source_matches:
        return False
    check["source"] = saved_check["source"]
    if (not check["header_check_passed"] or
            check["checked_binaries"] != record.get("checked_macho_count") or
            check != saved_check):
        return False
    changed = _verify_changed_binaries(snapshot, candidate, source_index)
    if changed != record.get("recovered_binaries"):
        return False
    if not changed and not inspect_decrypted_ipa(snapshot, record["bundle_id"])["header_check_passed"]:
        return False
    with tempfile.TemporaryDirectory(prefix="copyapp-decrypt-verify-") as scratch:
        expected = Path(scratch) / "analysis.ipa"
        _canonicalize_analysis_ipa(snapshot, candidate, expected,
                                   {item["path"] for item in changed})
        if _hash_file(expected) != record["analysis_ipa_sha256"]:
            return False
        objc_path = output / "static/objc-index.json"
        if objc_path.is_file():
            main = Path(scratch) / "main"
            with ZipFile(candidate) as archive, archive.open(check["main_path"]) as src, main.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            objc = index_objc(main)
            if (objc != json.loads(objc_path.read_text(encoding="utf-8")) or
                    record.get("objc_class_count") != len(objc["classes"]) or
                    record.get("objc_method_count") != sum(
                        len(item.get("instance_methods", [])) + len(item.get("class_methods", []))
                        for item in objc["classes"])):
                return False
        elif record.get("objc_class_count") is not None or record.get("objc_method_count") is not None:
            return False
    return True


def decrypt_package(udid: str, bundle: str, snapshot: Path, helper: Path,
                    output: Path, ssh_port: int, identity: Path,
                    known_hosts: Path) -> Path:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid bundle ID")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    if _hash_file(helper) != PINNED_HELPER_SHA256:
        raise ValueError("helper does not match reviewed pinned build")
    source_index = analyze_ipa(snapshot)
    if source_index["bundle_id"] != bundle:
        raise ValueError("snapshot bundle ID differs from requested app")
    main_path, _, app = asyncio.run(_installed_main(udid, bundle))
    app_root = posixpath.dirname(main_path)
    if source_index["version"] != app.get("CFBundleShortVersionString"):
        raise ValueError("snapshot and installed app versions differ")
    if source_index["build"] != app.get("CFBundleVersion"):
        raise ValueError("snapshot and installed app builds differ")

    ssh = _ssh_argv(ssh_port, identity, known_hosts, "mobile")
    actual_udid = subprocess.run(ssh + ["deviceinfo uniqueid"], capture_output=True,
                                 timeout=10, check=True).stdout.decode().strip()
    if actual_udid != udid:
        raise RuntimeError("SSH is connected to a different device")
    nonce = uuid.uuid4().hex[:16]
    remote_helper = f"/var/mobile/Media/copyapp-helper-{nonce}"
    remote_ipa = f"/var/mobile/Media/copyapp-analysis-{nonce}.ipa"
    roothide = _is_roothide_ssh(ssh)
    ssh_helper = "/rootfs" + remote_helper if roothide else remote_helper
    ssh_ipa = "/rootfs" + remote_ipa if roothide else remote_ipa
    output.mkdir(parents=True, exist_ok=True)
    try:
        scp = ["scp", "-P", str(ssh_port), "-i", str(identity),
               "-o", f"UserKnownHostsFile={known_hosts}",
               "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes"]
        subprocess.run(scp + [str(helper), f"mobile@127.0.0.1:{ssh_helper}"],
                       capture_output=True, timeout=30, check=True)
        remote_hash = subprocess.run(ssh + ["sha256sum " + shlex.quote(ssh_helper)],
                                     capture_output=True, timeout=10, check=True).stdout.decode().split()[0]
        if remote_hash != PINNED_HELPER_SHA256:
            raise RuntimeError("staged helper hash mismatch")
        if roothide:
            command = ["/usr/bin/timeout", "-s", "TERM", "120", ssh_helper,
                       "-v", "decrypt", bundle, app_root, remote_ipa]
            run = _run_roothide_helper(ssh, udid, command, output / "device-run")
        else:
            timeout_executable = resolve_jailbreak_executable(ssh, "/usr/bin/timeout")
            command = [timeout_executable, "-s", "TERM", "120", remote_helper,
                       "-v", "decrypt", bundle, app_root, remote_ipa]
            run = run_root_command(udid, command, output / "device-run", ssh_port,
                                   identity, known_hosts, timeout=140)
        if run["exit_code"] != 0:
            raise RuntimeError(f"device helper exited {run['exit_code']}; inspect device-run/output.txt")
        candidate = (output / "analysis.ipa").resolve()
        subprocess.run(scp + [f"mobile@127.0.0.1:{ssh_ipa}", str(candidate)],
                       capture_output=True, timeout=120, check=True)
        remote_ipa_hash = subprocess.run(ssh + ["sha256sum " + shlex.quote(ssh_ipa)],
                                         capture_output=True, timeout=10, check=True).stdout.decode().split()[0]
        if _hash_file(candidate) != remote_ipa_hash:
            raise RuntimeError("analysis IPA transfer hash mismatch")
        check = inspect_decrypted_ipa(candidate, bundle)
        write_decryption_check(check, output / "check")
        if not check["header_check_passed"]:
            raise RuntimeError("package-wide Mach-O check failed; inspect check/decryption-check.json")
        changed = _verify_changed_binaries(snapshot, candidate, source_index)
        normalized = output / "analysis-canonical.ipa"
        _canonicalize_analysis_ipa(snapshot, candidate, normalized,
                                   {item["path"] for item in changed})
        os.replace(normalized, candidate)
        check = inspect_decrypted_ipa(candidate, bundle)
        write_decryption_check(check, output / "check")
        if not check["header_check_passed"]:
            raise RuntimeError("canonical analysis IPA failed package-wide Mach-O check")
        static_index = analyze_ipa(candidate)
        write_ipa_report(static_index, output / "static")
        objc_classes = None
        objc_methods = None
        try:
            with tempfile.TemporaryDirectory(dir=output) as scratch:
                main_file = Path(scratch) / "main-mach-o"
                with ZipFile(candidate) as archive, archive.open(check["main_path"]) as source, main_file.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                objc = index_objc(main_file)
                write_objc_report(objc, output / "static")
                objc_classes = len(objc["classes"])
                objc_methods = sum(len(item.get("instance_methods", [])) + len(item.get("class_methods", []))
                                   for item in objc["classes"])
        except ObjCIndexError as exc:
            (output / "static" / "objc-status.json").write_text(
                json.dumps({"status": "unsupported", "reason": str(exc)}, ensure_ascii=False, indent=2) + "\n")
        manifest = {
            "schema_version": 1,
            "bundle_id": bundle,
            "installed_version": app.get("CFBundleShortVersionString"),
            "installed_build": app.get("CFBundleVersion"),
            "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
            "source_snapshot_sha256": source_index["ipa_sha256"],
            "helper_source": "londek/ipadecrypt@2fa69244cc6e580cd05f781db57912c79a4c3197",
            "helper_sha256": PINNED_HELPER_SHA256,
            "device_ipa_sha256": remote_ipa_hash,
            "analysis_ipa_sha256": _hash_file(candidate),
            "checked_macho_count": check["checked_binaries"],
            "recovered_binaries": changed,
            "objc_class_count": objc_classes,
            "objc_method_count": objc_methods,
            "all_macho_headers_decrypted": True,
            "note": ("No encrypted Mach-O required recovery; no App code bytes changed. "
                     "Installability is not asserted." if not changed else
                     "Analysis IPA only. Its modified code signatures are invalid; "
                     "installability is not asserted."),
        }
        path = output / "decryption.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        _write_case_manifest(output, snapshot, manifest)
        return path
    finally:
        try:
            subprocess.run(ssh + ["rm -f " + shlex.quote(ssh_helper) + " " + shlex.quote(ssh_ipa)],
                           capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass
