"""Remember a verified SSH route separately for each exact USB phone."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional


PROFILE_PATH = Path("cases/ssh/profiles.json")


def _device_key(udid: str) -> str:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    return hashlib.sha256(udid.encode()).hexdigest()


def load_ssh_profile(udid: str, path: Path = PROFILE_PATH) -> Optional[dict]:
    """Return a locally verified route, or None when no profile exists."""
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid SSH profile file")
    item = data.get(_device_key(udid))
    if item is None:
        return None
    if not isinstance(item, dict) or not isinstance(item.get("ssh_port"), int):
        raise ValueError("invalid SSH profile record")
    if not 1 <= item["ssh_port"] <= 65535:
        raise ValueError("invalid SSH profile port")
    for name in ("ssh_identity", "ssh_known_hosts"):
        if not isinstance(item.get(name), str) or not item[name]:
            raise ValueError("invalid SSH profile path")
    return item


def save_ssh_profile(udid: str, port: int, identity: Path, known_hosts: Path,
                     path: Path = PROFILE_PATH) -> Path:
    """Persist only after SSH has authenticated the requested device UDID."""
    key = _device_key(udid)
    if not 1 <= port <= 65535:
        raise ValueError("invalid SSH profile port")
    if not identity.is_file() or not known_hosts.is_file():
        raise FileNotFoundError("verified SSH files are missing")
    data: dict[str, Any] = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("invalid SSH profile file")
    data[key] = {"ssh_port": port,
                 "ssh_identity": str(identity.resolve()),
                 "ssh_known_hosts": str(known_hosts.resolve())}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".profiles-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return path


def apply_ssh_profile(args: Any, argv: list[str], path: Path = PROFILE_PATH) -> None:
    """Fill omitted SSH flags; an explicit command-line value always wins."""
    udid = getattr(args, "udid", None)
    if not udid or not any(hasattr(args, name) for name in
                           ("ssh_port", "ssh_identity", "ssh_known_hosts")):
        return
    profile = load_ssh_profile(udid, path)
    if profile is None:
        return
    for name in ("ssh_port", "ssh_identity", "ssh_known_hosts"):
        if not hasattr(args, name):
            continue
        flag = "--" + name.replace("_", "-")
        if any(value == flag or value.startswith(flag + "=") for value in argv):
            continue
        value = profile[name]
        setattr(args, name, Path(value) if name != "ssh_port" else value)


def remember_verified_doctor_case(case: Path, port: int, identity: Path,
                                  known_hosts: Path, path: Path = PROFILE_PATH) -> bool:
    """Save settings only when doctor authenticated the exact requested phone."""
    record = json.loads((case / "device.json").read_text(encoding="utf-8"))
    if record.get("probes", {}).get("ssh_mobile", {}).get("status") != "available":
        return False
    udid = record.get("device", {}).get("UniqueDeviceID")
    if not isinstance(udid, str):
        return False
    save_ssh_profile(udid, port, identity, known_hosts, path)
    return True
