import tempfile
import unittest
from pathlib import Path

from copyapp.frida_sidecar import _package_bytes, _pinned_alias


class FridaSidecarTest(unittest.TestCase):
    def test_pinned_alias_requires_a_loopback_usb_host_entry(self):
        with tempfile.TemporaryDirectory() as root:
            known_hosts = Path(root) / "known_hosts"
            known_hosts.write_text("[127.0.0.1]:22222 ssh-ed25519 AAAA\n")
            self.assertEqual(_pinned_alias(known_hosts), "[127.0.0.1]:22222")
            known_hosts.write_text("example.com ssh-ed25519 AAAA\n")
            with self.assertRaisesRegex(ValueError, "pinned known-hosts"):
                _pinned_alias(known_hosts)

    def test_unpinned_package_is_rejected_before_phone_transfer(self):
        with tempfile.TemporaryDirectory() as root:
            package = Path(root) / "frida.deb"
            package.write_bytes(b"untrusted package")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                _package_bytes(package)


if __name__ == "__main__":
    unittest.main()
