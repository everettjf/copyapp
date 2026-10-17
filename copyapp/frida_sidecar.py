"""Provision and use a version-pinned Frida server on RootHide without replacing its package."""

import atexit
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from copyapp.source_root import source_root


VERSION = "17.23.3"
PACKAGE_SHA256 = "6bf24760fe29fdeb786af71ec689dac333f7dda8aa1fe93ed3dff594bf23531b"
PACKAGE_URL = ("https://github.com/frida/frida/releases/download/" + VERSION +
               "/frida_" + VERSION + "_iphoneos-arm64.deb")
DEVICE_PORT = 27043
REMOTE_DIR = "/rootfs/var/mobile/Media/copyapp-frida-" + VERSION
CONFIG = source_root() / "toolchains" / "frida-sidecars.json"
_forwards: Dict[str, subprocess.Popen] = {}
_devices: Dict[str, Any] = {}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_config() -> Dict[str, Any]:
    if not CONFIG.is_file():
        return {}
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid Frida sidecar configuration")
    return data


def configured_sidecar(udid: str) -> Optional[Dict[str, Any]]:
    item = _read_config().get(udid)
    if item is None:
        return None
    if not isinstance(item, dict) or item.get("version") != VERSION or item.get("device_port") != DEVICE_PORT:
        raise ValueError("invalid Frida sidecar entry for device")
    return item


def _save_config(udid: str, identity: Path, known_hosts: Path) -> None:
    data = _read_config()
    data[udid] = {"version": VERSION, "device_port": DEVICE_PORT,
                  "remote_dir": REMOTE_DIR,
                  "ssh_identity": str(identity.resolve()),
                  "ssh_known_hosts": str(known_hosts.resolve())}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temp = CONFIG.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(CONFIG)


def _port() -> int:
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        return int(reserved.getsockname()[1])


def _pinned_alias(known_hosts: Path) -> str:
    for line in known_hosts.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        for host in line.split()[0].split(","):
            if re.fullmatch(r"\[127\.0\.0\.1\]:\d{1,5}", host):
                return host
    raise ValueError("pinned known-hosts file lacks a 127.0.0.1 USB SSH entry")


def _ssh_args(port: int, identity: Path, known_hosts: Path):
    from copyapp.ssh_acquire import _ssh_argv

    argv = _ssh_argv(port, identity, known_hosts, "mobile")
    argv[-1:-1] = ["-o", "HostKeyAlias=" + _pinned_alias(known_hosts)]
    return argv


def _close_forward(udid: str) -> None:
    process = _forwards.pop(udid, None)
    _devices.pop(udid, None)
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


@atexit.register
def _close_all() -> None:
    for udid in list(_forwards):
        _close_forward(udid)


def _connect(udid: str):
    import frida

    if frida.__version__ != VERSION:
        raise RuntimeError(f"RootHide Frida sidecar needs host frida=={VERSION}; found {frida.__version__}")
    cached = _devices.get(udid)
    if cached is not None and _forwards[udid].poll() is None:
        try:
            cached.enumerate_processes()
            return cached
        except Exception:
            _close_forward(udid)
    host_port = _port()
    process = subprocess.Popen([sys.executable, "-m", "pymobiledevice3", "usbmux",
                                "forward", str(host_port), str(DEVICE_PORT), "--serial", udid],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Frida sidecar USB forward exited")
            try:
                with socket.create_connection(("127.0.0.1", host_port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.15)
        else:
            raise TimeoutError("Frida sidecar USB forward is not reachable")
        device = frida.get_device_manager().add_remote_device(f"127.0.0.1:{host_port}")
        device.enumerate_processes()
        _forwards[udid] = process
        _devices[udid] = device
        return device
    except Exception:
        process.terminate()
        process.wait(timeout=3)
        raise


def _ssh_run(udid: str, identity: Path, known_hosts: Path, command: str) -> subprocess.CompletedProcess:
    from copyapp.usb_tunnel import ssh_tunnel

    with ssh_tunnel(udid, _port()) as port:
        result = subprocess.run(_ssh_args(port, identity, known_hosts) + [command],
                                capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("RootHide SSH command failed: " + result.stderr[-350:])
    return result


def _start(udid: str, identity: Path, known_hosts: Path) -> None:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    # The SSH namespace uses /rootfs for the real Media directory; the daemon
    # sees the same files at /var/mobile/Media after its RootHide environment is set.
    command = (f'test -x {REMOTE_DIR}/server && '
               f'test -f {REMOTE_DIR}/frida-agent.dylib && '
               f'CRYPTEX_MOUNT_PATH="$(jbroot)" nohup {REMOTE_DIR}/server '
               f'-l 127.0.0.1:{DEVICE_PORT} -C '
               f'> {REMOTE_DIR}/server.log 2>&1 < /dev/null &')
    _ssh_run(udid, identity, known_hosts, command)


def sidecar_device(udid: str):
    import frida

    entry = configured_sidecar(udid)
    if entry is None:
        raise RuntimeError("Frida sidecar is not configured for this device")
    if frida.__version__ != VERSION:
        raise RuntimeError(f"RootHide Frida sidecar needs host frida=={VERSION}; found {frida.__version__}")
    try:
        return _connect(udid)
    except Exception:
        _close_forward(udid)
        _start(udid, Path(entry["ssh_identity"]), Path(entry["ssh_known_hosts"]))
        deadline = time.monotonic() + 12
        last_error: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                return _connect(udid)
            except Exception as exc:
                last_error = exc
                time.sleep(0.4)
        raise RuntimeError("Frida sidecar did not become available") from last_error


def _package_bytes(path: Optional[Path]) -> bytes:
    if path is not None:
        data = path.read_bytes()
    else:
        with urllib.request.urlopen(PACKAGE_URL, timeout=45) as response:
            data = response.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024 or _sha256(data) != PACKAGE_SHA256:
        raise ValueError("official Frida package SHA-256 mismatch")
    return data


def _ar_member(archive: bytes, wanted: bytes) -> bytes:
    if not archive.startswith(b"!<arch>\n"):
        raise ValueError("invalid Debian package archive")
    offset = 8
    while offset + 60 <= len(archive):
        header = archive[offset:offset + 60]
        if header[58:60] != b"`\n":
            raise ValueError("invalid Debian archive member")
        name = header[:16].strip().rstrip(b"/")
        size = int(header[48:58].strip())
        start = offset + 60
        end = start + size
        if end > len(archive):
            raise ValueError("truncated Debian archive member")
        if name == wanted:
            return archive[start:end]
        offset = end + (size % 2)
    raise ValueError("Debian package data archive missing")


def _binaries(package: bytes) -> Dict[str, bytes]:
    payload = _ar_member(package, b"data.tar.xz")
    wanted = {"./var/jb/usr/sbin/frida-server": "server",
              "./var/jb/usr/lib/frida-1.0/frida-agent.dylib": "frida-agent.dylib"}
    result: Dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as archive:
        for member in archive:
            destination = wanted.get(member.name)
            if destination is None:
                continue
            if not member.isfile() or member.size > 50 * 1024 * 1024:
                raise ValueError("unexpected Frida binary in official package")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Frida binary body missing")
            result[destination] = source.read()
    if set(result) != set(wanted.values()):
        raise ValueError("official Frida package lacks server or agent")
    return result


def setup_roothide_sidecar(udid: str, output: Path, identity: Path,
                           known_hosts: Path, package_path: Optional[Path] = None) -> Path:
    """Stage an official version-pinned sidecar, then verify the exact USB phone."""
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    from copyapp.usb_tunnel import ssh_tunnel
    import frida

    if frida.__version__ != VERSION:
        raise RuntimeError(f"install host frida=={VERSION} before setting up this sidecar")
    package = _package_bytes(package_path)
    binaries = _binaries(package)
    marker = _ssh_run(udid, identity, known_hosts,
                      "deviceinfo uniqueid; command -v jbroot; test -d /rootfs/var/mobile/Media")
    marker_lines = marker.stdout.splitlines()
    if len(marker_lines) < 2 or marker_lines[0].strip() != udid or not marker_lines[1].endswith("/jbroot"):
        raise RuntimeError("the named phone did not report the expected RootHide SSH namespace")
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        for name, data in binaries.items():
            (directory / name).write_bytes(data)
        with ssh_tunnel(udid, _port()) as port:
            ssh = _ssh_args(port, identity, known_hosts)
            result = subprocess.run(ssh + [f"mkdir -p {REMOTE_DIR}"],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError("cannot create RootHide sidecar directory: " + result.stderr[-300:])
            scp = ["scp", "-P", str(port), "-i", str(identity),
                   "-o", f"UserKnownHostsFile={known_hosts}",
                   "-o", "HostKeyAlias=" + _pinned_alias(known_hosts),
                   "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes",
                   "-o", "IdentitiesOnly=yes"]
            for name in binaries:
                result = subprocess.run(scp + [str(directory / name),
                                                f"mobile@127.0.0.1:{REMOTE_DIR}/{name}.new"],
                                        capture_output=True, text=True, timeout=120)
                if result.returncode:
                    raise RuntimeError("Frida sidecar transfer failed: " + result.stderr[-300:])
            result = subprocess.run(ssh + [f"chmod 700 {REMOTE_DIR}/server.new; "
                                           f"{REMOTE_DIR}/server.new --version"],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode or result.stdout.strip() != VERSION:
                raise RuntimeError("staged Frida server did not report the pinned version")
            result = subprocess.run(ssh + [f"mv -f {REMOTE_DIR}/frida-agent.dylib.new "
                                           f"{REMOTE_DIR}/frida-agent.dylib && "
                                           f"mv -f {REMOTE_DIR}/server.new {REMOTE_DIR}/server"],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError("cannot activate staged Frida binaries: " + result.stderr[-300:])
    _close_forward(udid)
    try:
        _connect(udid)
    except Exception:
        _start(udid, identity, known_hosts)
    deadline = time.monotonic() + 12
    while True:
        try:
            device = _connect(udid)
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.4)
    _save_config(udid, identity, known_hosts)
    output.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "kind": "frida_roothide_sidecar",
              "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
              "version": VERSION, "package_sha256": PACKAGE_SHA256,
              "server_sha256": _sha256(binaries["server"]),
              "agent_sha256": _sha256(binaries["frida-agent.dylib"]),
              "process_count": len(device.enumerate_processes()),
              "remote_port": DEVICE_PORT, "status": "ready"}
    (output / "setup.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    manifest = {"schema_version": 1, "kind": "frida_roothide_sidecar",
                "status": "complete", "device_id_sha256_prefix": report["device_id_sha256_prefix"],
                "evidence": [{"id": "setup", "kind": "json", "path": "setup.json",
                              "sha256": hashlib.sha256((output / "setup.json").read_bytes()).hexdigest()}]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output
