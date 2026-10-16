"""Select the requested USB phone when Frida sees several connected devices."""

import frida


def get_usb_device(udid: str, timeout: float = 5):
    if not udid:
        raise ValueError("Frida USB selection requires a device UDID")
    device = frida.get_device(udid, timeout=timeout)
    if device.id != udid or device.type != "usb":
        raise RuntimeError("Frida device is not the requested USB device")
    return device
