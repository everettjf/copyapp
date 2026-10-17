"""Subprocess entry for one Instruments app launch.

The parent owns the timeout. Instruments teardown has blocked cancellation on
the XR, so this work must be isolated in a process that can be stopped.
"""

import asyncio
import re
import sys


async def launch(udid: str, bundle: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl

    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("lockdown device identity does not match requested UDID")
        version = str(values.get("ProductVersion", ""))
        major = version.split(".", 1)[0]
        if sys.platform == "darwin" and major.isdigit() and int(major) >= 17:
            # Lockdown DVT is unavailable on iOS 17+. Use the exact device's
            # native RSD transport and retain kill-existing fresh-launch semantics.
            await device.close()
            device = None
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pymobiledevice3", "developer", "dvt",
                "launch", "--native", "--udid", udid, "--kill-existing", bundle,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            if process.returncode:
                detail = (stderr or stdout).decode(errors="replace").strip()[-300:]
                raise RuntimeError(f"native RSD fresh launch failed: {detail}")
            return
        async with DvtProvider(device) as provider, ProcessControl(provider) as control:
            await control.launch(bundle, kill_existing=True)
    finally:
        if device is not None:
            await device.close()


if __name__ == "__main__":
    if (len(sys.argv) != 3 or
            not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", sys.argv[1]) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", sys.argv[2])):
        raise SystemExit("usage: python -m copyapp.dvt_launch UDID BUNDLE_ID")
    asyncio.run(launch(sys.argv[1], sys.argv[2]))
