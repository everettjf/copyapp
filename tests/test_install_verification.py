import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from copyapp.install import install_trollstore_ipa, install_usb_ipa
from copyapp.verify import sha256_file, verify_case


class InstallationVerificationTest(unittest.TestCase):
    def test_trollstore_install_owns_exact_device_forward(self):
        udid = "00008020-000D650434B8003A"
        ipa = Path("fixture.ipa")
        out = Path("install")
        identity = Path("id_ed25519")
        known_hosts = Path("xr_known_hosts")
        with patch("copyapp.install.exact_ssh_tunnel") as tunnel, \
             patch("copyapp.install._install_trollstore_ipa_via_ssh",
                   return_value=out / "install.json") as install:
            result = install_trollstore_ipa(udid, ipa, out, 22316,
                                            identity, known_hosts)
        tunnel.assert_called_once_with(udid, 22316, identity, known_hosts)
        install.assert_called_once_with(udid, ipa, out, 22316, identity, known_hosts)
        self.assertEqual(result, out / "install.json")

    def test_rechecks_ipa_bytes_and_recorded_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ipa = root / "app.ipa"
            ipa.write_bytes(b"saved package")
            digest = sha256_file(ipa)
            case = root / "install"
            case.mkdir()
            record = {"schema_version": 1, "status": "installed",
                      "device_id": "00008020-000D650434B8003A",
                      "ipa": str(ipa), "ipa_sha256": digest,
                      "staged_sha256": digest, "helper_exit_code": 0,
                      "bundle_id": "com.copyapp.example", "version": "1.0", "build": "1"}
            (case / "install.json").write_text(json.dumps(record))
            package = {"bundle_id": "com.copyapp.example", "version": "1.0",
                       "build": "1"}
            with patch("copyapp.ipa.analyze_ipa", return_value=package):
                self.assertTrue(verify_case(case))
                ipa.write_bytes(b"changed package")
                self.assertFalse(verify_case(case))

    def test_usb_install_checks_exact_device_and_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ipa = root / "app.ipa"
            ipa.write_bytes(b"signed package")
            bundle = "com.copyapp.example"
            udid = "00008020-000D650434B8003A"
            package = {"ipa_sha256": sha256_file(ipa), "bundle_id": bundle,
                       "version": "1.0", "build": "1"}
            device = MagicMock()
            device.get_value = AsyncMock(return_value={"UniqueDeviceID": udid})
            device.close = AsyncMock()
            proxy = MagicMock()
            proxy.install_from_local = AsyncMock()
            proxy.get_apps = AsyncMock(return_value={bundle: {
                "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1",
                "ProfileValidated": True, "Path": "/Applications/Example.app"}})
            service = MagicMock()
            service.__aenter__ = AsyncMock(return_value=proxy)
            service.__aexit__ = AsyncMock(return_value=None)
            with patch("copyapp.install.analyze_ipa", return_value=package), \
                 patch("copyapp.install.create_using_usbmux", new=AsyncMock(return_value=device)), \
                 patch("copyapp.install.InstallationProxyService", return_value=service):
                result = install_usb_ipa(udid, ipa, root / "install")
            record = json.loads(result.read_text())
            self.assertEqual(record["transport"], "usb")
            self.assertEqual(record["status"], "installed")
            self.assertTrue(record["installed_profile_validated"])
            proxy.install_from_local.assert_awaited_once_with(ipa)
            device.close.assert_awaited_once()
            with patch("copyapp.ipa.analyze_ipa", return_value=package):
                self.assertTrue(verify_case(result.parent))
                record["installed_profile_validated"] = False
                result.write_text(json.dumps(record))
                self.assertFalse(verify_case(result.parent))


if __name__ == "__main__":
    unittest.main()
