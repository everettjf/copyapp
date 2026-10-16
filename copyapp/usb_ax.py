"""USB Accessibility Audit fallback for observing and activating named elements."""

from typing import Any, Dict, List

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit


async def usb_ax(udid: str, action: str, caption: str = "") -> Dict[str, Any]:
    if action not in ("observe", "press"):
        raise ValueError("unsupported USB accessibility action")
    if action == "press" and not caption:
        raise ValueError("press requires an exact accessibility caption")
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with AccessibilityAudit(device) as audit:
            elements = [element async for element in audit.iter_elements()]
            if action == "observe":
                return {"source": "USB Accessibility Audit", "elements": [
                    element.to_dict() for element in elements
                ]}
            matches: List[Any] = [element for element in elements if element.caption == caption]
            if len(matches) != 1 or matches[0].element is None:
                raise ValueError(f"expected exactly one current element with caption {caption!r}; found {len(matches)}")
            await audit.perform_press(matches[0].element.identifier)
            return {
                "source": "USB Accessibility Audit", "requested": "press",
                "caption": caption,
                "note": "Activation request sent; observe the screen again to verify its effect.",
            }
    finally:
        await device.close()
