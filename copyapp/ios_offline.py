"""Pinned FairPlay host adapter with independent whole-package structural audit."""

import io
import re
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional
from zipfile import BadZipFile, ZipFile

from copyapp.decrypt_package import _canonicalize_analysis_ipa, _verify_changed_binaries
from copyapp.decrypt_verify import inspect_decrypted_ipa
from copyapp.ipa import ARM64_CPU, MACHO64_LE
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.ios_packages import package_index, verified_package
from copyapp.source_root import source_root
from copyapp.verify import sha256_file, verify_case


FAIRPLAY_REVISION = "1bad106ee1698c6d9c483f67d898183ffa4c6eb3"
FAIRPLAY_FILES = {
    "decrypt.py": "6ebf98ae86ca9560c124b77c3b66cd4cc78f5947575d6c437223d3ff7edf3c18",
    "core.py": "40aeae1fa24afd31a4dc86978be90af554f85dcfb057cd7c059ec0fcc5df4a99",
    "transform.c": "7677b61dc8b53666adcb22020d5433b2d40305c97827d30fdef78a8a9f46ed6b",
    "transform_const_data.bin": "32e3e80b03b078ec545df0506527925584e740d9e05e044cd111f9e8a9b2cdd9",
}
ERRORS = {"credential_unavailable", "tool_unavailable_or_modified", "transform_build_failed",
          "decoder_failed", "decoder_timeout", "package_audit_failed", "unsupported_binary_inventory",
          "credential_mismatch", "unsupported_license_format", "decoder_dependency_unavailable"}


def _credential(store: Path, reference: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", reference):
        raise ValueError("credential reference must be an opaque local identifier")
    candidate = store / (reference + ".bin")
    if (not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size != 16 or
            store.resolve() not in candidate.resolve().parents):
        raise ValueError("matching credential is not available in the local credential store")
    return candidate.resolve(strict=True)


def _prepare_tool(source: Path, output: Path) -> dict:
    for name, expected in FAIRPLAY_FILES.items():
        path = source / name
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected:
            raise ValueError("FairPlay source differs from the reviewed pinned revision")
    output.mkdir()
    for name in FAIRPLAY_FILES:
        shutil.copyfile(source / name, output / name)
    result = subprocess.run(["cc", "-std=c11", "-O2", "-o", str(output / "transform"),
                             str(output / "transform.c")], capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError("transform_build_failed")
    return {"name": "EthanArbuckle/fairplay-decrypt", "revision": FAIRPLAY_REVISION,
            "sources": dict(FAIRPLAY_FILES), "transform_sha256": sha256_file(output / "transform"),
            "python_version": sys.version.split()[0]}


def _inventory(source: Path, index: dict) -> list[dict]:
    if (not index.get("binaries") or index.get("unsupported_binaries") or
            any(item.get("status") for item in index["binaries"])):
        raise ValueError("unsupported_binary_inventory")
    encrypted = [item for item in index["binaries"] if item.get("encrypted_on_disk")]
    with ZipFile(source) as archive:
        for item in index["binaries"]:
            # The byte-range audit currently supports thin ARM64 only. Never
            # accept a partly checked FAT package just because its selected
            # ARM64 slice is clear; another slice may still be encrypted.
            with archive.open(item["path"]) as stream:
                if stream.read(4) != MACHO64_LE or item.get("cpu_type") != ARM64_CPU:
                    raise ValueError("unsupported_binary_inventory")
    return encrypted


def audit_offline_package(source: Path, recovered: Path, index: dict) -> tuple[list, dict]:
    with ZipFile(source) as before, ZipFile(recovered) as after:
        names = before.namelist()
        other = after.namelist()
        if len(other) != len(set(other)) or set(names) != set(other):
            raise ValueError("offline decoder changed the package member list")
    check = inspect_decrypted_ipa(recovered, index["bundle_id"])
    if not check["header_check_passed"]:
        raise ValueError("some package binaries remain encrypted or unreadable")
    changed = _verify_changed_binaries(source, recovered, index)
    # Recheck every resource and unencrypted member, not only the decoder's list.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="copyapp-offline-audit-") as temporary:
        _canonicalize_analysis_ipa(source, recovered, Path(temporary) / "audit.ipa",
                                   {item["path"] for item in changed})
    check["source"] = "analysis.ipa"
    return changed, check


def decrypt_offline(package: Path, output: Path, tool_dir: Optional[Path] = None,
                      credential_ref: Optional[str] = None,
                      credential_store: Optional[Path] = None,
                      timeout: int = 600) -> tuple[Path, bool]:
    if output.exists():
        raise FileExistsError(output)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("decoder timeout must be 1–3600 seconds")
    index = verified_package(package)
    output.mkdir(parents=True)
    shutil.copytree(package, output / "source")
    source = output / "source/input.ipa"
    record = {"status": "failed", "bundle_id": index["bundle_id"],
              "source_manifest_sha256": sha256_file(package / "manifest.json"),
              "source_ipa_sha256": index["ipa_sha256"], "credential_ref": None,
              "strategy": "fairplay_offline", "plaintext_validation": "not_verified",
              "error": "unsupported_binary_inventory"}
    try:
        encrypted = _inventory(source, index)
        if not encrypted:
            shutil.copyfile(source, output / "analysis.ipa")
            record["strategy"] = "source_already_unencrypted"
        else:
            record["error"] = "credential_unavailable"
            if credential_ref is None:
                raise ValueError("credential_unavailable")
            store = credential_store if credential_store is not None else source_root() / "cases/credentials/fairplay"
            credential = _credential(store, credential_ref)
            record["credential_ref"] = credential_ref
            record["error"] = "tool_unavailable_or_modified"
            if tool_dir is None:
                tool_dir = source_root() / "toolchains/fairplay-decrypt-src"
            try:
                record["tool"] = _prepare_tool(tool_dir, output / "tool")
            except (RuntimeError, subprocess.TimeoutExpired):
                record["error"] = "transform_build_failed"
                raise
            record["error"] = "decoder_failed"
            command = [sys.executable, "-B", "-E", str((output / "tool/decrypt.py").resolve()),
                       str(source.resolve()), str((output / "analysis.ipa").resolve()),
                       "--credential", str(credential)]
            try:
                result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                record["error"] = "decoder_timeout"
                raise
            record["exit_code"] = result.returncode
            if result.returncode:
                diagnostic = result.stderr + result.stdout
                if b"credential does not decode this SINF priv record" in diagnostic:
                    record["error"] = "credential_mismatch"
                elif b"unsupported SUPF format" in diagnostic or b"unsupported SINF" in diagnostic:
                    record["error"] = "unsupported_license_format"
                elif b"No module named 'cryptography'" in diagnostic:
                    record["error"] = "decoder_dependency_unavailable"
                raise ValueError("decoder_failed")
        record["error"] = "package_audit_failed"
        changed, check = audit_offline_package(source, output / "analysis.ipa", index)
        write_json(output / "decryption-check.json", check)
        record.update(status="complete", recovered_binaries=changed,
                      analysis_ipa_sha256=sha256_file(output / "analysis.ipa"),
                      plaintext_validation="structural_only" if encrypted else "source_unchanged")
        record.pop("error")
        recovered_index = package_index(output / "analysis.ipa")
        recovered_index["source"] = "analysis.ipa"
        write_json(output / "package-index.json", recovered_index)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, BadZipFile):
        record.update(status="failed", plaintext_validation="not_verified")
        if record.get("error") not in ERRORS:
            record["error"] = "package_audit_failed"
    write_json(output / "offline.json", record)
    (output / "report.md").write_text(
        "# Offline iOS package recovery\n\n"
        f"Status: `{record['status']}`. Strategy: `{record['strategy']}`.\n\n"
        f"Plaintext validation: `{record['plaintext_validation']}`.\n\n"
        "The source package, full binary inventory and byte-range/resource audit are retained. "
        "Structural success does not certify correct plaintext, runtime identity, semantic interpretation "
        "or installability. Compare matching binaries with independently verified device recovery when available. "
        "The local credential contents and raw decoder account/session output are never retained.\n",
        encoding="utf-8")
    path = seal_case(output, "ios_offline_package", status=record["status"], bundle_id=index["bundle_id"])
    return path, record["status"] == "complete"


def validate_offline(root: Path, manifest: dict) -> bool:
    record = read_json(root / "offline.json")
    index = verified_package(root / "source")
    if (record.get("status") != manifest.get("status") or
            record.get("bundle_id") != manifest.get("bundle_id") or
            record["bundle_id"] != index["bundle_id"] or
            record.get("source_manifest_sha256") != sha256_file(root / "source/manifest.json") or
            record.get("source_ipa_sha256") != index["ipa_sha256"]):
        return False
    if record["status"] == "failed":
        return record.get("error") in ERRORS and record.get("plaintext_validation") == "not_verified"
    if record["status"] != "complete":
        return False
    encrypted = _inventory(root / "source/input.ipa", index)
    if encrypted:
        tool = record.get("tool", {})
        if (record.get("strategy") != "fairplay_offline" or record.get("exit_code") != 0 or
                record.get("plaintext_validation") != "structural_only" or
                not isinstance(record.get("credential_ref"), str) or
                not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", record["credential_ref"]) or
                tool.get("revision") != FAIRPLAY_REVISION or tool.get("sources") != FAIRPLAY_FILES or
                tool.get("transform_sha256") != sha256_file(root / "tool/transform") or
                any(sha256_file(root / "tool" / name) != digest for name, digest in FAIRPLAY_FILES.items())):
            return False
    elif (record.get("strategy") != "source_already_unencrypted" or
          record.get("plaintext_validation") != "source_unchanged" or
          record.get("credential_ref") is not None or
          sha256_file(root / "analysis.ipa") != index["ipa_sha256"]):
        return False
    changed, check = audit_offline_package(root / "source/input.ipa", root / "analysis.ipa", index)
    actual_index = package_index(root / "analysis.ipa")
    actual_index["source"] = "analysis.ipa"
    return (record.get("recovered_binaries") == changed and
            record.get("analysis_ipa_sha256") == sha256_file(root / "analysis.ipa") and
            read_json(root / "decryption-check.json") == check and
            read_json(root / "package-index.json") == actual_index)
