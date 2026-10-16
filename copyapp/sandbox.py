"""Metadata-only inventory of an installed app's data container over USB SSH."""

import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ssh_acquire import _ssh_argv


MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 10000
CONTAINER_PATTERN = re.compile(
    r"^/(?:private/)?var/mobile/Containers/Data/Application/[0-9A-Fa-f-]{36}$"
)


def _read_remote_index(argv: List[str], path: str, depth: int) -> List[Dict[str, Any]]:
    if not CONTAINER_PATTERN.fullmatch(path):
        raise ValueError("installation record has no valid app data-container path")
    if not 1 <= depth <= 12:
        raise ValueError("sandbox depth must be between 1 and 12")
    command = (
        "PATH=/var/jb/usr/bin:/usr/bin:/bin:$PATH; find " + shlex.quote(path) +
        " -maxdepth " + str(depth) + " -printf '%P\\0%y\\0%s\\0%T@\\0'"
    )
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(argv + [command], stdout=subprocess.PIPE, stderr=errors)
        try:
            assert process.stdout is not None
            raw = process.stdout.read(MAX_INDEX_BYTES + 1)
            if len(raw) > MAX_INDEX_BYTES:
                raise ValueError("sandbox metadata index exceeds limit")
            if process.wait(timeout=30) != 0:
                errors.seek(0)
                raise RuntimeError("SSH find failed: " + errors.read(512).decode(errors="replace"))
        except Exception:
            process.kill()
            process.wait()
            raise
    fields = raw.split(b"\0")
    if fields[-1] != b"" or (len(fields) - 1) % 4:
        raise ValueError("malformed remote sandbox index")
    items: List[Dict[str, Any]] = []
    for pos in range(0, len(fields) - 1, 4):
        relative, kind, size, modified = (os.fsdecode(x) for x in fields[pos:pos + 4])
        if not relative:
            continue
        normalized = PurePosixPath(relative)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("unsafe path in remote sandbox index")
        items.append({"relative": relative, "kind": kind, "size": int(size),
                      "modified_epoch": float(modified)})
        if len(items) > MAX_ENTRIES:
            raise ValueError("too many sandbox entries")
    return sorted(items, key=lambda item: item["relative"])


async def index_sandbox_ssh(udid: str, bundle_id: str, output: Path, port: int,
                            identity: Path, known_hosts: Path, user: str,
                            depth: int = 8) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id):
        raise ValueError("invalid bundle id")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite sandbox index: {output}")
    argv = _ssh_argv(port, identity, known_hosts, user)
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle_id])
        if bundle_id not in apps:
            raise ValueError(f"app not installed: {bundle_id}")
        app = apps[bundle_id]
        path = str(app.get("Container") or "")
        items = _read_remote_index(argv, path, depth)
        index = {
            "schema_version": 1,
            "source": "read-only SSH find metadata through USB tunnel",
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
            "bundle_id": bundle_id,
            "container_path_sha256_prefix": hashlib.sha256(path.encode()).hexdigest()[:16],
            "installed_version": app.get("CFBundleShortVersionString"),
            "installed_build": app.get("CFBundleVersion"),
            "depth_limit": depth,
            "entries": items,
            "note": "No file contents were copied. Path inventory may be incomplete beyond depth limit.",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        return output
    finally:
        await device.close()
