"""Keep the two Copy APP USB forwards alive in one foreground command."""

import asyncio
import re
import socket
import subprocess
import sys
import tempfile
import time


def _check_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("forward port must be between 1 and 65535")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def run_tunnels(udid: str, ssh_port: int = 22222, mcp_port: int = 22223,
                ssh_only: bool = False, mcp_only: bool = False) -> int:
    """Forward SSH and iOS MCP over USB until Ctrl-C or one forward exits."""
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if ssh_only and mcp_only:
        raise ValueError("choose at most one of --ssh-only and --mcp-only")
    endpoints = []
    if not mcp_only:
        endpoints.append(("SSH", ssh_port, 22))
    if not ssh_only:
        endpoints.append(("iOS MCP", mcp_port, 8090))
    if len({local for _, local, _ in endpoints}) != len(endpoints):
        raise ValueError("SSH and iOS MCP host ports must differ")
    for _, local, _ in endpoints:
        _check_port(local)
    from pymobiledevice3.usbmux import list_devices
    devices = asyncio.run(list_devices())
    if not any(item.serial == udid and
               str(getattr(item, "connection_type", "")).lower().endswith("usb")
               for item in devices):
        raise ValueError("the exact requested UDID is not connected over USB")
    processes = []
    with tempfile.TemporaryFile() as child_log:
        try:
            for name, local, remote in endpoints:
                argv = [sys.executable, "-m", "pymobiledevice3", "usbmux", "forward",
                        str(local), str(remote), "--serial", udid]
                process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                           stdout=child_log, stderr=child_log)
                processes.append((name, local, remote, process))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if any(process.poll() is not None for _, _, _, process in processes):
                    child_log.seek(0)
                    detail = child_log.read()[-800:].decode(errors="replace")
                    raise RuntimeError("a USB forward exited: " + detail)
                try:
                    for _, local, _, _ in processes:
                        with socket.create_connection(("127.0.0.1", local), timeout=0.2):
                            pass
                    break
                except (ConnectionRefusedError, TimeoutError, OSError):
                    time.sleep(0.1)
            else:
                raise TimeoutError("USB forwards did not open their localhost ports")
            print(f"Copy APP USB forwards for {udid}:", flush=True)
            for name, local, remote, _ in processes:
                print(f"  {name}: 127.0.0.1:{local} -> device:{remote}", flush=True)
            print("Keep this terminal open; press Ctrl-C to stop both forwards.", flush=True)
            while True:
                for name, _, _, process in processes:
                    if process.poll() is not None:
                        child_log.seek(0)
                        detail = child_log.read()[-800:].decode(errors="replace")
                        raise RuntimeError(f"{name} USB forward exited: {detail}")
                time.sleep(0.5)
        except KeyboardInterrupt:
            return 0
        finally:
            for _, _, _, process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
