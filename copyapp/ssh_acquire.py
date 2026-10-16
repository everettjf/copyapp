"""Read-only acquisition of one installed app bundle over a USB-forwarded SSH port."""

import hashlib
import json
import posixpath
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ipa import analyze_ipa, write_ipa_report
from copyapp.objc import ObjCIndexError, index_objc, write_objc_report


MAX_FILES = 10000
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_SINGLE_FILE = 250 * 1024 * 1024
MAX_TAR_BYTES = MAX_TOTAL_BYTES + 32 * 1024 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ssh_argv(port: int, identity: Path, known_hosts: Path, user: str) -> List[str]:
    if not (1 <= port <= 65535):
        raise ValueError("invalid SSH port")
    if user not in ("root", "mobile"):
        raise ValueError("SSH user must be root or mobile")
    if not identity.is_file() or not known_hosts.is_file():
        raise FileNotFoundError("SSH identity or pinned known-hosts file missing")
    return [
        "ssh", "-p", str(port), "-i", str(identity),
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes", "-o", "ConnectTimeout=10",
        f"{user}@127.0.0.1",
    ]


def _stream_tar(argv: List[str], remote_path: str, destination: Path) -> None:
    parent, basename = posixpath.split(remote_path)
    command = "PATH=/var/jb/usr/bin:/usr/bin:/bin:$PATH; tar -C " + shlex.quote(parent) + " -cf - " + shlex.quote(basename)
    with destination.open("wb") as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(argv + [command], stdout=subprocess.PIPE, stderr=errors)
        total = 0
        try:
            assert process.stdout is not None
            while chunk := process.stdout.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_TAR_BYTES:
                    raise ValueError("remote tar exceeds acquisition limit")
                output.write(chunk)
            if process.wait(timeout=30) != 0:
                errors.seek(0)
                raise RuntimeError("SSH tar failed: " + errors.read(512).decode(errors="replace"))
        except Exception:
            process.kill()
            process.wait()
            raise


def _extract_regular_files(archive_path: Path, app_name: str, output: Path) -> tuple:
    local_root = output / "bundle" / app_name
    files: List[Dict[str, Any]] = []
    skipped: List[str] = []
    seen = set()
    total = 0
    with tarfile.open(archive_path, "r:") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != app_name:
                raise ValueError("unsafe path in remote tar")
            if member.isdir():
                continue
            relative = PurePosixPath(*path.parts[1:])
            if not relative.parts:
                raise ValueError("invalid app bundle file path")
            if not member.isfile():
                skipped.append(str(relative))
                continue
            if str(relative) in seen:
                raise ValueError("duplicate path in remote tar")
            seen.add(str(relative))
            total += member.size
            if member.size > MAX_SINGLE_FILE or total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES:
                raise ValueError("app bundle exceeds acquisition limits")
            destination = local_root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise IOError("missing file body in remote tar")
            digest = hashlib.sha256()
            copied = 0
            with source, destination.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    digest.update(chunk)
                    target.write(chunk)
            if copied != member.size:
                raise IOError("truncated file in remote tar")
            files.append({"relative": str(relative), "size": member.size, "sha256": digest.hexdigest()})
    return local_root, sorted(files, key=lambda item: item["relative"]), skipped


def _write_snapshot(local_root: Path, app_name: str, files: List[Dict[str, Any]],
                    snapshot: Path) -> None:
    with ZipFile(snapshot, "w", ZIP_DEFLATED) as archive:
        for item in files:
            entry = ZipInfo("Payload/" + app_name + "/" + item["relative"],
                            date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            with (local_root / item["relative"]).open("rb") as source, archive.open(entry, "w") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)


async def acquire_bundle_ssh(udid: str, bundle_id: str, output: Path, port: int,
                             identity: Path, known_hosts: Path, user: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id):
        raise ValueError("invalid bundle id")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    argv = _ssh_argv(port, identity, known_hosts, user)
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle_id])
        if bundle_id not in apps:
            raise ValueError(f"app not installed: {bundle_id}")
        app = apps[bundle_id]
        remote_path = str(app.get("Path") or "")
        if not remote_path.startswith("/") or not remote_path.endswith(".app") or "\n" in remote_path:
            raise ValueError("installation record has no usable .app path")
        app_name = posixpath.basename(remote_path)
        output.mkdir(parents=True, exist_ok=True)
        tar_path = output / "bundle-transport.tar"
        try:
            _stream_tar(argv, remote_path, tar_path)
            local_root, files, skipped = _extract_regular_files(tar_path, app_name, output)
        finally:
            tar_path.unlink(missing_ok=True)
        snapshot = output / "bundle-snapshot.ipa"
        _write_snapshot(local_root, app_name, files, snapshot)
        manifest = {
            "schema_version": 1, "source": "USB-forwarded SSH read-only app bundle snapshot",
            "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
            "bundle_id": bundle_id, "installed_version": app.get("CFBundleShortVersionString"),
            "installed_build": app.get("CFBundleVersion"), "remote_bundle_path": remote_path,
            "files": files, "skipped_non_regular": skipped,
            "snapshot_sha256": _sha256_file(snapshot),
            "note": "Repacked snapshot for analysis; not asserted to be an installable original IPA.",
        }
        (output / "acquisition.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        static = analyze_ipa(snapshot)
        if static["bundle_id"] != bundle_id:
            raise ValueError("acquired Info.plist bundle id differs from installation record")
        write_ipa_report(static, output / "static")
        main_path = "Payload/" + app_name + "/" + static["executable"]
        main = next((item for item in static["binaries"] if item["path"] == main_path), None)
        if main and not main.get("encrypted_on_disk") and "status" not in main:
            try:
                write_objc_report(index_objc(local_root / static["executable"]), output / "static")
            except ObjCIndexError as exc:
                (output / "static" / "objc-status.json").write_text(json.dumps({
                    "status": "unsupported", "reason": str(exc)
                }, ensure_ascii=False, indent=2) + "\n")
        return output / "static" / "ipa-report.md"
    finally:
        await device.close()
