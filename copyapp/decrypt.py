"""Recover an installed app's encrypted main Mach-O range from its own process.

The output is an analysis copy. Replacing encrypted bytes invalidates the
original code signature and does not produce an installable App Store IPA.
"""

import asyncio
import hashlib
import json
import plistlib
import posixpath
import re
import shlex
import struct
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ipa import MACHO64_LE, MAX_BINARY, inspect_macho
from copyapp.ssh_acquire import _ssh_argv
from copyapp.usb_tunnel import ios_mcp_tunnel
from copyapp.ios_mcp import IOSMCPClient, IOSMCPError


CHUNK = 64 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cryptid_offset(data: bytes) -> int:
    if len(data) < 32 or data[:4] != MACHO64_LE:
        raise ValueError("this recovery path requires a thin arm64 Mach-O")
    ncmds, sizeofcmds = struct.unpack_from("<II", data, 16)
    if ncmds > 10000 or 32 + sizeofcmds > len(data):
        raise ValueError("invalid Mach-O load commands")
    cursor = 32
    result = None
    for _ in range(ncmds):
        if cursor + 8 > 32 + sizeofcmds:
            raise ValueError("truncated Mach-O load command")
        cmd, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > 32 + sizeofcmds:
            raise ValueError("invalid Mach-O load command size")
        if (cmd & 0x7fffffff) == 0x2c:
            if size < 24 or result is not None:
                raise ValueError("invalid or duplicate LC_ENCRYPTION_INFO_64")
            result = cursor + 16
        cursor += size
    if result is None:
        raise ValueError("main binary has no LC_ENCRYPTION_INFO_64")
    return result


async def _installed_main(udid: str, bundle: str) -> tuple:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle])
        if bundle not in apps:
            raise ValueError("target app is not installed")
        info = apps[bundle]
        root = str(info.get("Path") or "")
        executable = str(info.get("CFBundleExecutable") or "")
        if not root.startswith("/") or not root.endswith(".app") or "\n" in root:
            raise ValueError("invalid installed app path")
        if not re.fullmatch(r"[A-Za-z0-9_. -]+", executable):
            raise ValueError("invalid installed executable name")
        return posixpath.join(root, executable), executable, info
    finally:
        await device.close()


def _copy_disk_binary(ssh: list, remote_path: str, destination: Path) -> str:
    command = "cat " + shlex.quote(remote_path)
    digest = hashlib.sha256()
    with destination.open("wb") as target, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(ssh + [command], stdout=subprocess.PIPE, stderr=errors)
        total = 0
        try:
            assert process.stdout is not None
            while chunk := process.stdout.read(CHUNK):
                total += len(chunk)
                if total > MAX_BINARY:
                    raise ValueError("main binary exceeds transfer limit")
                digest.update(chunk)
                target.write(chunk)
            if process.wait(timeout=20) != 0:
                errors.seek(0)
                raise RuntimeError("SSH binary read failed: " + errors.read(300).decode(errors="replace"))
        except Exception:
            process.kill()
            process.wait()
            raise
    return digest.hexdigest()


def decrypt_main(udid: str, bundle: str, output: Path, ssh_port: int,
                 identity: Path, known_hosts: Path, user: str = "mobile") -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid bundle ID")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    ssh = _ssh_argv(ssh_port, identity, known_hosts, user)
    remote_path, executable, app = asyncio.run(_installed_main(udid, bundle))
    output.mkdir(parents=True, exist_ok=True)
    disk_path = output / "encrypted-main.bin"
    disk_sha = _copy_disk_binary(ssh, remote_path, disk_path)
    disk = disk_path.read_bytes()
    static = inspect_macho(disk)
    encryption = static["encryption_info"]
    if not encryption or encryption["cryptid"] == 0 or encryption["cryptsize"] == 0:
        raise ValueError("main binary is not marked encrypted on disk")
    cryptoff = encryption["cryptoff"]
    cryptsize = encryption["cryptsize"]
    if cryptoff + cryptsize > len(disk) or cryptsize > MAX_BINARY:
        raise ValueError("encrypted range exceeds file or size limit")
    cryptid_offset = _cryptid_offset(disk)
    if struct.unpack_from("<I", disk, cryptid_offset)[0] != encryption["cryptid"]:
        raise ValueError("cryptid load-command offset mismatch")

    import frida
    device = frida.get_usb_device(timeout=5)
    if device.id != udid:
        raise RuntimeError("Frida device does not match requested UDID")
    with ios_mcp_tunnel(udid) as port:
        client = IOSMCPClient(port=port)
        client.initialize()
        try:
            client.call_ui("launch_app", {"bundle_id": bundle})
        except IOSMCPError:
            # A system permission alert can own the foreground while the app
            # process has already started. Runtime memory is still testable.
            pass
        time.sleep(1)
        app_process = next((item for item in device.enumerate_applications(scope="full")
                            if item.identifier == bundle), None)
        if app_process is None or not app_process.pid:
            raise RuntimeError("target app is not running after launch")
        session = device.attach(app_process.pid)
        try:
            script = session.create_script("""
const moduleName = %s;
rpc.exports = {
  info() { const m=Process.getModuleByName(moduleName);
           return {name:m.name, path:m.path, base:m.base.toString(), size:m.size}; },
  read(offset, size) { const m=Process.getModuleByName(moduleName);
                       if (size < 1 || size > 65536 || offset < 0 || offset + size > m.size)
                         throw new Error('read outside module bounds');
                       return m.base.add(offset).readByteArray(size); }
};
""" % json.dumps(executable))
            script.load()
            try:
                module = script.exports_sync.info()
                if posixpath.basename(module["path"]) != executable:
                    raise RuntimeError("running module executable name mismatch")
                if cryptoff + cryptsize > module["size"]:
                    raise ValueError("encrypted file range is outside running module")
                header_size = min(4096, cryptoff)
                runtime_header = script.exports_sync.read(0, header_size)
                if runtime_header != disk[:header_size]:
                    raise RuntimeError("runtime module base does not match disk file offsets")
                recovered = bytearray()
                for offset in range(cryptoff, cryptoff + cryptsize, CHUNK):
                    size = min(CHUNK, cryptoff + cryptsize - offset)
                    chunk = script.exports_sync.read(offset, size)
                    if len(chunk) != size:
                        raise IOError("short runtime memory read")
                    recovered.extend(chunk)
            finally:
                script.unload()
        finally:
            session.detach()

    changed = sum(a != b for a, b in zip(disk[cryptoff:cryptoff + cryptsize], recovered))
    if changed == 0:
        raise RuntimeError("runtime encrypted range equals disk; no decrypted bytes proven")
    output_bytes = bytearray(disk)
    output_bytes[cryptoff:cryptoff + cryptsize] = recovered
    struct.pack_into("<I", output_bytes, cryptid_offset, 0)
    decrypted = output / "decrypted-main.bin"
    decrypted.write_bytes(output_bytes)
    post = inspect_macho(output_bytes)
    if post["encryption_status"] != "cryptid_zero" or post["uuid"] != static["uuid"]:
        raise RuntimeError("decrypted output failed Mach-O header verification")
    if output_bytes[cryptoff:cryptoff + cryptsize] != recovered:
        raise RuntimeError("decrypted output range differs from runtime bytes")
    record: Dict[str, Any] = {
        "schema_version": 1,
        "source": "installed file plus Frida runtime memory of the same process",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device_id_sha256_prefix": _sha256(udid.encode())[:16],
        "bundle_id": bundle,
        "installed_version": app.get("CFBundleShortVersionString"),
        "executable": executable,
        "macho_uuid": static["uuid"],
        "encrypted_file_sha256": disk_sha,
        "encrypted_region_sha256": _sha256(disk[cryptoff:cryptoff + cryptsize]),
        "runtime_region_sha256": _sha256(recovered),
        "decrypted_file_sha256": _sha256(output_bytes),
        "cryptoff": cryptoff,
        "cryptsize": cryptsize,
        "changed_region_bytes": changed,
        "cryptid_before": encryption["cryptid"],
        "cryptid_after": post["encryption_info"]["cryptid"],
        "runtime_header_matches_disk": True,
        "scope": "main executable only; frameworks and extensions not yet recovered",
        "note": "Analysis copy only. Original code signature is invalid after replacing encrypted bytes; no installability claim.",
    }
    manifest = output / "decryption.json"
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def decrypt_extension(udid: str, bundle: str, appex: str, output: Path,
                      ssh_port: int, identity: Path, known_hosts: Path,
                      user: str = "mobile") -> Path:
    """Recover one already running app extension selected by its bundle folder."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid bundle ID")
    if not re.fullmatch(r"[A-Za-z0-9_. -]+", appex):
        raise ValueError("invalid extension name")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    ssh = _ssh_argv(ssh_port, identity, known_hosts, user)
    main_path, _, app = asyncio.run(_installed_main(udid, bundle))
    app_root = posixpath.dirname(main_path)
    extension_root = posixpath.join(app_root, "PlugIns", appex + ".appex")
    plist_path = posixpath.join(extension_root, "Info.plist")
    plist = subprocess.run(ssh + ["cat " + shlex.quote(plist_path)], capture_output=True,
                           timeout=20, check=True).stdout
    if len(plist) > 1024 * 1024:
        raise ValueError("extension Info.plist exceeds 1 MiB")
    info = plistlib.loads(plist)
    executable = str(info.get("CFBundleExecutable") or "")
    if not re.fullmatch(r"[A-Za-z0-9_. -]+", executable):
        raise ValueError("invalid extension executable")
    relative = posixpath.join("PlugIns", appex + ".appex", executable)
    remote_path = posixpath.join(extension_root, executable)

    output.mkdir(parents=True, exist_ok=True)
    disk_path = output / "encrypted-extension.bin"
    disk_sha = _copy_disk_binary(ssh, remote_path, disk_path)
    disk = disk_path.read_bytes()
    static = inspect_macho(disk)
    encryption = static["encryption_info"]
    if not encryption or encryption["cryptid"] == 0 or encryption["cryptsize"] == 0:
        raise ValueError("extension binary is not marked encrypted on disk")
    start, size = encryption["cryptoff"], encryption["cryptsize"]
    if start + size > len(disk) or size > MAX_BINARY:
        raise ValueError("encrypted range exceeds extension file or size limit")
    patch_offset = _cryptid_offset(disk)

    import frida
    device = frida.get_device_manager().get_device(udid, timeout=5)
    if device.id != udid or device.type != "usb":
        raise RuntimeError("Frida device does not match requested USB UDID")
    norm = lambda path: path.removeprefix("/private")
    process = next((p for p in device.enumerate_processes(scope="full")
                    if norm(str((p.parameters or {}).get("path") or "")) == norm(remote_path)), None)
    if process is None:
        raise RuntimeError("extension process is not running; activate it through its system extension point")
    session = device.attach(process.pid)
    try:
        script = session.create_script("""
const moduleName = %s;
rpc.exports = {
  info() { const m=Process.getModuleByName(moduleName);
           return {name:m.name, path:m.path, base:m.base.toString(), size:m.size}; },
  read(offset, size) { const m=Process.getModuleByName(moduleName);
                       if (size < 1 || size > 65536 || offset < 0 || offset + size > m.size)
                         throw new Error('read outside module bounds');
                       return m.base.add(offset).readByteArray(size); }
};
""" % json.dumps(executable))
        script.load()
        try:
            module = script.exports_sync.info()
            if norm(module["path"]) != norm(remote_path) or start + size > module["size"]:
                raise RuntimeError("runtime extension module identity or bounds mismatch")
            header_size = min(4096, start)
            if script.exports_sync.read(0, header_size) != disk[:header_size]:
                raise RuntimeError("runtime extension header differs from installed file")
            recovered_region = bytearray()
            for offset in range(start, start + size, CHUNK):
                chunk = script.exports_sync.read(offset, min(CHUNK, start + size - offset))
                recovered_region.extend(chunk)
        finally:
            script.unload()
    finally:
        session.detach()

    changed = sum(a != b for a, b in zip(disk[start:start + size], recovered_region))
    if changed == 0 or len(recovered_region) != size:
        raise RuntimeError("extension runtime region was not recovered")
    restored = bytearray(disk)
    restored[start:start + size] = recovered_region
    struct.pack_into("<I", restored, patch_offset, 0)
    after = inspect_macho(restored)
    if after["encryption_status"] != "cryptid_zero" or after["uuid"] != static["uuid"]:
        raise RuntimeError("restored extension Mach-O failed header verification")
    (output / "decrypted-extension.bin").write_bytes(restored)
    record = {
        "schema_version": 1,
        "source": "installed extension file plus Frida memory of its system-hosted process",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device_id_sha256_prefix": _sha256(udid.encode())[:16],
        "bundle_id": bundle,
        "installed_version": app.get("CFBundleShortVersionString"),
        "extension_bundle_id": info.get("CFBundleIdentifier"),
        "executable": executable,
        "relative_path": relative,
        "macho_uuid": static["uuid"],
        "encrypted_file_sha256": disk_sha,
        "encrypted_region_sha256": _sha256(disk[start:start + size]),
        "runtime_region_sha256": _sha256(recovered_region),
        "decrypted_file_sha256": _sha256(restored),
        "cryptoff": start,
        "cryptsize": size,
        "changed_region_bytes": changed,
        "cryptid_before": encryption["cryptid"],
        "cryptid_after": 0,
        "runtime_header_matches_disk": True,
        "process_pid": process.pid,
        "note": "Analysis copy only; original code signature is invalid after patching.",
    }
    manifest = output / "decryption.json"
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return manifest
