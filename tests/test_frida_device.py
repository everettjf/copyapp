import unittest
from types import SimpleNamespace
from unittest.mock import patch

from copyapp.frida_device import get_usb_device


class FridaDeviceTest(unittest.TestCase):
    def test_selects_requested_usb_device_by_id(self):
        phone = SimpleNamespace(id="requested-udid", type="usb")
        with patch("frida.get_device", return_value=phone) as lookup:
            self.assertIs(get_usb_device("requested-udid"), phone)
        lookup.assert_called_once_with("requested-udid", timeout=5)

    def test_rejects_non_usb_or_wrong_device(self):
        for device in (SimpleNamespace(id="requested-udid", type="remote"),
                       SimpleNamespace(id="other-udid", type="usb")):
            with self.subTest(device=device), patch("frida.get_device", return_value=device):
                with self.assertRaisesRegex(RuntimeError, "requested USB device"):
                    get_usb_device("requested-udid")


if __name__ == "__main__":
    unittest.main()
