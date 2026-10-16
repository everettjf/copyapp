"""Own a short-lived USB mux port forward for one named iOS device."""

import asyncio
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from copyapp.ios_mcp import IOSMCPClient
from copyapp.ictrl import ICtrlClient, DEFAULT_CLIENT


ICTRL_RUNNER_BUNDLE = "com.openminis.ypv49m8592.ictrl.uitests.xctrunner"


async def _launch_ictrl_runner(udid: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl

    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with DvtProvider(device) as provider, ProcessControl(provider) as control:
            await control.launch(ICTRL_RUNNER_BUNDLE, kill_existing=False)
    finally:
        await device.close()


@contextmanager
def ictrl_tunnel(udid: str, client: Path = DEFAULT_CLIENT) -> Iterator[int]:
    """Launch the paired runner and forward its encrypted UI protocol."""
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if not client.is_file():
        raise FileNotFoundError(f"iCTRL client not found: {client}")
    asyncio.run(_launch_ictrl_runner(udid))
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    command = [sys.executable, "-m", "pymobiledevice3", "usbmux", "forward",
               str(port), "8200", "--serial", udid]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("USB mux forward exited before iCTRL was reachable")
            try:
                ICtrlClient(port=port, client=client).call_ui("logs", {"max_elements": 1})
                break
            except Exception:
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
