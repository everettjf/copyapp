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
        async with DvtProvider(device) as provider, ProcessControl(provider) as control:
            await control.launch(bundle, kill_existing=True)
    finally:
        await device.close()


if __name__ == "__main__":
    if (len(sys.argv) != 3 or
            not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", sys.argv[1]) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", sys.argv[2])):
        raise SystemExit("usage: python -m copyapp.dvt_launch UDID BUNDLE_ID")
    asyncio.run(launch(sys.argv[1], sys.argv[2]))
