import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from copyapp.usb_tunnel import exact_ssh_tunnel


class ExactSshTunnelTest(unittest.TestCase):
    def test_existing_forward_must_report_requested_udid(self):
        with patch("copyapp.usb_tunnel.socket.create_connection", return_value=MagicMock()), \
                patch("copyapp.ssh_acquire._ssh_argv", return_value=["ssh", "phone"]), \
                patch("copyapp.usb_tunnel.ssh_tunnel") as new_tunnel, \
                patch("copyapp.usb_tunnel.subprocess.run", return_value=
                      subprocess.CompletedProcess([], 0, "another-phone\n", "")):
            with self.assertRaisesRegex(RuntimeError, "requested USB device"):
                with exact_ssh_tunnel("requested-phone", 22222,
                                      Path("key"), Path("hosts")):
                    pass
        new_tunnel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
