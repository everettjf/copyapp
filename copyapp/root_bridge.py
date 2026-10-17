"""One-shot root command through an already paired, USB-connected Frida server.

Frida starts the command on the *named* device. The existing mobile SSH channel
only retrieves its bounded output and exit status; it never gains root login.
"""

import json
import re
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

from copyapp.ssh_acquire import _ssh_argv


MAX_OUTPUT = 1024 * 1024


def _spawned_effective_uid(device: Any, pid: int) -> int:
    """Verify privilege in the suspended child before calling it a root command."""
    observed: Dict[str, Any] = {}
    ready = threading.Event()

    def on_message(message: Dict[str, Any], _data: Any) -> None:
        if message.get("type") == "send" and isinstance(message.get("payload"), int):
            observed["uid"] = message["payload"]
        else:
            observed["error"] = message.get("description", "invalid Frida UID response")
        ready.set()

    session = device.attach(pid)
    try:
        script = session.create_script(
            "const symbol = Module.getGlobalExportByName ? "
            "Module.getGlobalExportByName('geteuid') : "
            "Module.getExportByName(null, 'geteuid'); "
            "send((new NativeFunction(symbol, 'uint', []))());")
        script.on("message", on_message)
        script.load()
        if not ready.wait(3):
            raise RuntimeError("Frida child did not report its effective UID")
        if "error" in observed:
            raise RuntimeError("Frida child UID probe failed: " + str(observed["error"]))
        return observed["uid"]
    finally:
        session.detach()


def resolve_jailbreak_executable(ssh: List[str], logical_path: str) -> str:
    """Resolve one trusted tool in rootless or RootHide's randomized root."""
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", logical_path) or ".." in logical_path.split("/"):
        raise ValueError("invalid jailbreak executable path")
    rootless = "/var/jb" + logical_path
    script = (f"if test -x {shlex.quote(rootless)}; then printf '%s\\n' "
              f"{shlex.quote(rootless)}; elif command -v jbroot >/dev/null 2>&1; "
              f"then jbroot {shlex.quote(logical_path)}; else exit 1; fi")
    result = subprocess.run(ssh + [script], capture_output=True, timeout=10,
                            check=True)
    path = result.stdout.decode().strip()
    if (not re.fullmatch(r"/[A-Za-z0-9_./-]+", path) or
            ".." in path.split("/") or "//" in path):
        raise RuntimeError("device returned an invalid jailbreak executable path")
    return path


def run_root_command(udid: str, command: List[str], output: Path, ssh_port: int,
                     identity: Path, known_hosts: Path, timeout: int = 60) -> Dict[str, Any]:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if not command or not command[0].startswith("/") or any("\x00" in arg for arg in command):
        raise ValueError("command must start with an absolute executable path and contain no NUL")
    if not 1 <= timeout <= 3600:
        raise ValueError("timeout must be between 1 and 3600 seconds")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")

    import frida

    ssh = _ssh_argv(ssh_port, identity, known_hosts, "mobile")
    device = frida.get_device_manager().get_device(udid, timeout=5)
    if device.id != udid or device.type != "usb":
        raise RuntimeError("Frida did not resolve the named USB device")
    ssh_identity = subprocess.run(ssh + ["deviceinfo uniqueid"], capture_output=True,
                                  timeout=10, check=True).stdout.decode().strip()
    if ssh_identity != udid:
        raise RuntimeError("SSH and Frida are connected to different devices")
    shell_path = resolve_jailbreak_executable(ssh, "/bin/sh")
    nonce = uuid.uuid4().hex
    remote_base = f"/var/mobile/Media/copyapp-root-{nonce}"
    log = remote_base + ".log"
    status = remote_base + ".status"
    # The shell program is fixed. Command arguments are passed as argv after
    # the shell's $0, so their contents cannot become shell syntax.
    shell = ("PATH=/var/jb/usr/bin:/var/jb/bin:/usr/bin:/bin; umask 022; "
             f'"$@" > {shlex.quote(log)} 2>&1; code=$?; '
             f'printf "%s\\n" "$code" > {shlex.quote(status)}')
    pid = device.spawn([shell_path, "-c", shell, "copyapp-root"] + command)
    try:
        effective_uid = _spawned_effective_uid(device, pid)
        if effective_uid != 0:
            raise RuntimeError(
                f"Frida spawned effective UID {effective_uid}; root-run requires UID 0. "
                "Use a root-capable Frida server; the mobile RootHide server is insufficient.")
    except Exception:
        try:
            device.kill(pid)
        except Exception:
            pass
        raise
    device.resume(pid)

    deadline = time.monotonic() + timeout
    exit_code = None
    try:
        while time.monotonic() < deadline:
            check = subprocess.run(ssh + ["cat " + shlex.quote(status)],
                                   capture_output=True, timeout=10)
            if check.returncode == 0:
                value = check.stdout.strip()
                if not re.fullmatch(rb"[0-9]{1,3}", value):
                    raise RuntimeError("invalid root command exit status")
                exit_code = int(value)
                break
            time.sleep(0.25)
        if exit_code is None:
            try:
                device.kill(pid)
            except Exception:
                pass
            raise TimeoutError(f"root command exceeded {timeout}s; process {pid} stopped")

        captured = subprocess.run(
            ssh + ["head -c " + str(MAX_OUTPUT + 1) + " " + shlex.quote(log)],
            capture_output=True, timeout=15, check=True,
        ).stdout
        truncated = len(captured) > MAX_OUTPUT
        output.mkdir(parents=True, exist_ok=True)
        (output / "output.txt").write_bytes(captured[:MAX_OUTPUT])
        result = {
            "schema_version": 1,
            "device_id": udid,
            "transport": "named USB Frida spawn; paired mobile SSH result retrieval",
            "command": command,
            "pid": pid,
            "exit_code": exit_code,
            "output_truncated": truncated,
            "remote_log": log,
            "remote_status": status,
        }
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        # Only the two files created for this invocation are removed.
        try:
            subprocess.run(ssh + ["rm -f " + shlex.quote(log) + " " + shlex.quote(status)],
                           capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
