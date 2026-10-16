"""Read-only app bundle snapshot through an already installed AFC2 service."""

import hashlib
import json
import posixpath
from pathlib import Path
from typing import Any, Dict, List, Tuple
from zipfile import ZIP_DEFLATED, ZipFile

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ipa import analyze_ipa, write_ipa_report


MAX_FILES = 10000
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_SINGLE_FILE = 250 * 1024 * 1024


def _safe_name(value: str) -> bool:
    return value not in ("", ".", "..") and "/" not in value and "\\" not in value


async def _walk(afc: AfcService, root: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    files: List[Dict[str, Any]] = []
    skipped: List[str] = []
    pending = [(root, "")]
    total = 0
    while pending:
        remote, relative = pending.pop()
        for name in sorted(await afc.listdir(remote)):
            if not _safe_name(name):
                raise ValueError(f"invalid bundle entry name: {name!r}")
            child = posixpath.join(remote, name)
            rel = posixpath.join(relative, name)
            metadata = await afc.stat(child)
            kind = metadata.get("st_ifmt")
            if kind == "S_IFDIR":
                pending.append((child, rel))
            elif kind == "S_IFREG":
                size = int(metadata.get("st_size", 0))
                total += size
                if size > MAX_SINGLE_FILE or total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES:
                    raise ValueError("app bundle exceeds acquisition limits")
                files.append({"remote": child, "relative": rel, "size": size})
            else:
                skipped.append(rel)
    return sorted(files, key=lambda item: item["relative"]), skipped


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def acquire_bundle(udid: str, bundle_id: str, output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle_id])
        if bundle_id not in apps:
            raise ValueError(f"app not installed: {bundle_id}")
        app = apps[bundle_id]
        remote_root = str(app.get("Path") or "")
        if not remote_root.startswith("/") or not remote_root.endswith(".app"):
            raise ValueError("installation record has no usable .app path")
        async with AfcService(device, service_name="com.apple.afc2") as afc:
            files, skipped = await _walk(afc, remote_root)
            output.mkdir(parents=True, exist_ok=True)
            local_root = output / "bundle" / posixpath.basename(remote_root)
            for item in files:
                destination = local_root / item["relative"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                await afc.pull(item["remote"], str(destination), progress_bar=False)
                if destination.stat().st_size != item["size"]:
                    raise IOError(f"size changed during copy: {item['relative']}")
                item["sha256"] = _sha256_file(destination)
        snapshot = output / "bundle-snapshot.ipa"
        with ZipFile(snapshot, "w", ZIP_DEFLATED) as archive:
            for item in files:
                local = local_root / item["relative"]
                archive.write(local, "Payload/" + local_root.name + "/" + item["relative"])
        manifest = {
            "schema_version": 1, "source": "USB AFC2 read-only app bundle snapshot",
            "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
            "bundle_id": bundle_id, "installed_version": app.get("CFBundleShortVersionString"),
            "installed_build": app.get("CFBundleVersion"),
            "remote_bundle_path": remote_root, "files": files, "skipped_non_regular": skipped,
            "snapshot_sha256": _sha256_file(snapshot),
            "note": "Repacked snapshot for analysis; not asserted to be an installable original IPA.",
        }
        (output / "acquisition.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        static = analyze_ipa(snapshot)
        if static["bundle_id"] != bundle_id:
            raise ValueError("acquired Info.plist bundle id differs from installation record")
        write_ipa_report(static, output / "static")
        return output / "static" / "ipa-report.md"
    finally:
        await device.close()
