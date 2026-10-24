"""Use developer services on one verified USB device.

iOS 17 moved developer services behind Remote Service Discovery. On macOS,
pymobiledevice3's native transport can use the paired remoted tunnel after the
matching Developer Disk Image has been mounted.
"""

import asyncio
import re
import sys
import tempfile
from pathlib import Path

from pymobiledevice3.services.screenshot import ScreenshotService
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl
from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo


async def exact_device_screenshot(udid: str) -> tuple[bytes, str]:
    """Capture through developer services after rechecking the USB identity."""
    from pymobiledevice3.lockdown import create_using_usbmux

    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("screenshot USB identity differs from requested device")
        return await take_screenshot(device, udid, str(values.get("ProductVersion", "")))
    finally:
        await device.close()


async def list_directory(device, udid: str, ios_version: str, path: str) -> tuple[list[str], str]:
    """List a device directory through the developer transport for this iOS release."""
    major = int(ios_version.split(".", 1)[0]) if re.match(r"^\d+", ios_version) else 0
    if major < 17 or sys.platform != "darwin":
        async with DvtProvider(device) as dvt, DeviceInfo(dvt) as info:
            return await info.ls(path), "lockdown"
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid USB device UDID")
    if not path.startswith("/") or "\n" in path or "\r" in path:
        raise ValueError("invalid absolute device path")
    command = [sys.executable, "-m", "pymobiledevice3", "developer", "dvt",
               "ls", "--native", "--udid", udid, path]
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError("native RSD directory listing timed out") from exc
    if process.returncode != 0:
        raise RuntimeError("native RSD directory listing failed: " +
                           stderr.decode(errors="replace").strip()[-250:])
    entries = stdout.decode(errors="replace").splitlines()
    if any(not item.startswith(path.rstrip("/") + "/") for item in entries):
        raise RuntimeError("native RSD returned a path outside the requested directory")
    return entries, "native_rsd"


async def take_screenshot(device, udid: str, ios_version: str) -> tuple[bytes, str]:
    """Use native RSD on macOS/iOS 17+, or lockdown on earlier systems."""
    major = int(ios_version.split(".", 1)[0]) if re.match(r"^\d+", ios_version) else 0
    if major < 17 or sys.platform != "darwin":
        async with ScreenshotService(device) as screen:
            picture = await screen.take_screenshot()
        if not picture:
            raise RuntimeError("lockdown returned an empty screenshot")
        return picture, "lockdown"
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid USB device UDID")
    with tempfile.TemporaryDirectory(prefix="copyapp-screen-") as temporary:
        output = Path(temporary) / "screenshot.png"
        command = [sys.executable, "-m", "pymobiledevice3", "developer", "dvt",
                   "screenshot", "--native", "--udid", udid, str(output)]
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=45)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("native RSD screenshot timed out") from exc
        if process.returncode != 0 or not output.is_file():
            detail = stderr.decode(errors="replace").strip()[-250:]
            raise RuntimeError("native RSD screenshot failed: " + detail)
        picture = output.read_bytes()
        if not picture.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8")):
            raise RuntimeError("native RSD returned a non-image screenshot")
        return picture, "native_rsd"


async def launch_app(device, udid: str, ios_version: str, bundle: str) -> str:
    """Launch through the iOS 17 native RSD route or the older lockdown DVT route."""
    major = int(ios_version.split(".", 1)[0]) if re.match(r"^\d+", ios_version) else 0
    if major < 17 or sys.platform != "darwin":
        async with DvtProvider(device) as dvt, ProcessControl(dvt) as control:
            await control.launch(bundle, kill_existing=False)
        return "lockdown"
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid USB device UDID")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid bundle ID")
    command = [sys.executable, "-m", "pymobiledevice3", "developer", "dvt",
               "launch", "--native", "--udid", udid, "--no-kill-existing", bundle]
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=45)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError("native RSD App launch timed out") from exc
    if process.returncode != 0:
        raise RuntimeError("native RSD App launch failed: " +
                           stderr.decode(errors="replace").strip()[-250:])
    return "native_rsd"
