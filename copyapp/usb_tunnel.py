"""Own a short-lived USB mux port forward for one named iOS device."""

import asyncio
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Iterator, Optional

from copyapp.ios_mcp import IOSMCPClient
from copyapp.ictrl import ICtrlClient, DEFAULT_CLIENT


@contextmanager
def ssh_tunnel(udid: str, port: int = 22222) -> Iterator[int]:
    """Forward SSH for one exact USB device while a probe is running."""
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if not 1 <= port <= 65535:
        raise ValueError("invalid SSH host port")
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", port))
    command = [sys.executable, "-m", "pymobiledevice3", "usbmux", "forward",
               str(port), "22", "--serial", udid]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("USB SSH forward exited before it was ready")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    pass
                break
            except (ConnectionRefusedError, TimeoutError, OSError):
                time.sleep(0.1)
        else:
            raise TimeoutError("USB SSH forward did not become reachable")
        yield port
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def configured_ictrl_runner_bundle(udid: str) -> Optional[str]:
    """Read the Bundle ID installed by setup for this exact device."""
    config = Path(__file__).resolve().parents[1] / "toolchains" / "ictrl-runners.json"
    if config.is_file():
        try:
            value = json.loads(config.read_text()).get(udid)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", value):
                return value
        except (OSError, ValueError):
            pass
    return None


def ictrl_runner_bundle(udid: str) -> str:
    bundle = configured_ictrl_runner_bundle(udid)
    if bundle is None:
        raise FileNotFoundError("iCTRL runner is not configured for this device; run copyapp setup ictrl")
    return bundle


async def _ios_version(udid: str) -> str:
    from pymobiledevice3.lockdown import create_using_usbmux

    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("USB runner target identity does not match requested UDID")
        return str(values.get("ProductVersion", ""))
    finally:
        await device.close()


@contextmanager
def ictrl_xcuitest_session(udid: str, bundle: str,
                          log_path: Optional[Path] = None) -> Iterator[subprocess.Popen]:
    """Keep iOS 17+ testmanagerd attached while the iCTRL service is in use."""
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid runner Bundle ID")
    command = [sys.executable, "-m", "pymobiledevice3", "developer", "dvt",
               "xcuitest", "--native", "--udid", udid, bundle]
    log_file = log_path.open("w+b") if log_path is not None else tempfile.TemporaryFile(mode="w+b")
    with log_file as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            yield process
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


async def _launch_ictrl_runner(udid: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from copyapp.device_developer import launch_app

    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("USB runner target identity does not match requested UDID")
        await launch_app(device, udid, str(values.get("ProductVersion", "")),
                         ictrl_runner_bundle(udid))
    finally:
        await device.close()


@contextmanager
def ictrl_tunnel(udid: str, client: Path = DEFAULT_CLIENT) -> Iterator[int]:
    """Launch the paired runner and forward its encrypted UI protocol."""
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if not client.is_file():
        raise FileNotFoundError(f"iCTRL client not found: {client}")
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    command = [sys.executable, "-m", "pymobiledevice3", "usbmux", "forward",
               str(port), "8200", "--serial", udid]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    try:
        rpc = ICtrlClient(port=port, client=client)

        def runner_ready() -> bool:
            if process.poll() is not None:
                raise RuntimeError("USB mux forward exited before iCTRL was reachable")
            try:
                rpc._run("call", "logs", json.dumps({"max_elements": 1}), timeout=2)
                return True
            except Exception:
                return False

        # A prior capture may have left the runner active. Avoid an Instruments
        # relaunch in that case: it can block indefinitely on this device.
        ready = False
        probe_deadline = time.monotonic() + 3
        while time.monotonic() < probe_deadline:
            if runner_ready():
                ready = True
                break
            time.sleep(0.2)
        version = asyncio.run(_ios_version(udid)) if not ready else ""
        major = int(version.split(".", 1)[0]) if version[:1].isdigit() else 0
        session = (ictrl_xcuitest_session(udid, ictrl_runner_bundle(udid))
                   if not ready and major >= 17 else nullcontext(None))
        with session as test_process:
            if not ready and test_process is None:
                try:
                    subprocess.run([sys.executable, "-m", "copyapp.ictrl_runner_launch", udid],
                                   capture_output=True, text=True, check=True, timeout=30)
                except subprocess.TimeoutExpired as exc:
                    raise TimeoutError("launching the iCTRL runner timed out") from exc
            deadline = time.monotonic() + (60 if test_process is not None else 15)
            while time.monotonic() < deadline:
                if runner_ready():
                    break
                if test_process is not None and test_process.poll() is not None:
                    raise RuntimeError("iCTRL XCTest session exited before its UI service became reachable")
                time.sleep(0.3)
            else:
                raise TimeoutError("paired iCTRL runner did not become reachable on the named USB device")
            yield port
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


@contextmanager
def ios_mcp_tunnel(udid: str) -> Iterator[int]:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    command = [sys.executable, "-m", "pymobiledevice3", "usbmux", "forward",
               str(port), "8090", "--serial", udid]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("USB mux forward exited before iOS MCP was reachable")
            try:
                IOSMCPClient(port=port, timeout=0.5).health()
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise TimeoutError("iOS MCP did not become reachable through the named USB device")
        yield port
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
