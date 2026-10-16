import asyncio
import json
import os
import plistlib
import tempfile
import unittest
from contextlib import contextmanager
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from copyapp.ictrl_setup import _bundle_from_ipa, _pair, setup_ictrl
from copyapp.verify import verify_case


BUNDLE = "com.example.ictrl.uitests.xctrunner"
UDID = "00008020-000D650434B8003A"


@contextmanager
def fake_forward(*args, **kwargs):
    yield 33224


def make_ipa(path: Path, minimum: str) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("Payload/iCTRLUITests-Runner.app/Info.plist",
                         plistlib.dumps({"CFBundleIdentifier": BUNDLE,
                                         "MinimumOSVersion": minimum}))


class ICtrlSetupTest(unittest.TestCase):
    def test_pair_shows_only_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "ictrl"
            fake.write_text("#!/bin/sh\n"
                            "echo 'key fingerprint: ab12cd34  (verify it matches the on-device prompt)' >&2\n"
                            "echo 'waiting for Allow on the device…' >&2\n"
                            "echo 'paired — tok=SECRET123 (key cached)'\n")
            os.chmod(fake, 0o700)
            display = StringIO()
            with patch("copyapp.ictrl_setup._paired_health", return_value=True), \
                 redirect_stdout(display):
                _pair(33224, fake)
            self.assertIn("ab12cd34", display.getvalue())
            self.assertNotIn("SECRET123", display.getvalue())

    def test_ipa_bundle_and_minimum_are_strictly_read(self):
        with tempfile.TemporaryDirectory() as directory:
            ipa = Path(directory) / "runner.ipa"
            make_ipa(ipa, "16.0")
            self.assertEqual(_bundle_from_ipa(ipa), (BUNDLE, "16.0"))

    def test_existing_runner_uses_health_without_install_or_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "ictrl"
            client.write_bytes(b"cli")
            with patch("copyapp.ictrl_setup._device", return_value={
                    "ProductVersion": "16.1.1", "UniqueDeviceID": UDID}), \
                 patch("copyapp.ictrl_setup.configured_ictrl_runner_bundle", return_value=BUNDLE), \
                 patch("copyapp.ictrl_setup._build_client", return_value=client), \
                 patch("copyapp.ictrl_setup._installed_app", return_value={"Path": "/app"}), \
                 patch("copyapp.ictrl_setup._usb_forward", side_effect=fake_forward), \
                 patch("copyapp.ictrl_setup._launch_runner"), \
                 patch("copyapp.ictrl_setup._paired_health", return_value=True), \
                 patch("copyapp.ictrl_setup._build_runner") as build, \
                 patch("copyapp.ictrl_setup.install_trollstore_ipa") as install, \
                 patch("copyapp.ictrl_setup._pair") as pair:
                path, ready = setup_ictrl(UDID, root / "case")
            self.assertTrue(ready)
            self.assertEqual(json.loads(path.read_text())["status"], "ready")
            self.assertTrue(verify_case(root / "case"))
            build.assert_not_called()
            install.assert_not_called()
            pair.assert_not_called()

    def test_new_runner_installs_and_pairs_after_minimum_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "ictrl"
            client.write_bytes(b"cli")
            ipa = root / "runner.ipa"
            make_ipa(ipa, "16.0")
            identity = root / "id"
            known_hosts = root / "known_hosts"
            identity.touch()
            known_hosts.touch()
            with patch("copyapp.ictrl_setup._device", return_value={
                    "ProductVersion": "16.1.1", "UniqueDeviceID": UDID}), \
                 patch("copyapp.ictrl_setup.configured_ictrl_runner_bundle", return_value=None), \
                 patch("copyapp.ictrl_setup._build_client", return_value=client), \
                 patch("copyapp.ictrl_setup._installed_app", side_effect=[{}, {"Path": "/app"}]) as installed, \
                 patch("copyapp.ictrl_setup._usb_forward", side_effect=fake_forward), \
                 patch("copyapp.ictrl_setup._launch_runner"), \
                 patch("copyapp.ictrl_setup._paired_health", side_effect=[False, True]), \
                 patch("copyapp.ictrl_setup._save_bundle") as save, \
                 patch("copyapp.ictrl_setup.install_trollstore_ipa") as install, \
                 patch("copyapp.ictrl_setup._pair") as pair:
                path, ready = setup_ictrl(UDID, root / "case", ssh_identity=identity,
                                          ssh_known_hosts=known_hosts, runner_ipa=ipa)
            self.assertTrue(ready)
            self.assertTrue(verify_case(root / "case"))
            self.assertIn("pairing_approved", json.loads(path.read_text())["stages"])
            self.assertEqual((root / "case" / "iCTRLUITests-Runner.ipa").read_bytes(),
                             ipa.read_bytes())
            manifest = json.loads((root / "case" / "manifest.json").read_text())
            self.assertIn("iCTRLUITests-Runner.ipa",
                          [item["path"] for item in manifest["evidence"]])
            save.assert_called_once_with(UDID, BUNDLE)
            self.assertEqual(installed.call_args_list[0].args, (UDID, BUNDLE))
            install.assert_called_once()
            pair.assert_called_once()

    def test_reinstall_same_bundle_stops_old_process_and_launches_new_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "ictrl"
            client.write_bytes(b"cli")
            ipa = root / "runner.ipa"
            make_ipa(ipa, "16.0")
            identity = root / "id"
            known_hosts = root / "known_hosts"
            identity.touch()
            known_hosts.touch()
            with patch("copyapp.ictrl_setup._device", return_value={
                    "ProductVersion": "16.1.1", "UniqueDeviceID": UDID}), \
                 patch("copyapp.ictrl_setup.configured_ictrl_runner_bundle", return_value=BUNDLE), \
                 patch("copyapp.ictrl_setup._build_client", return_value=client), \
                 patch("copyapp.ictrl_setup._installed_app", return_value={"Path": "/app"}), \
                 patch("copyapp.ictrl_setup._usb_forward", side_effect=fake_forward), \
                 patch("copyapp.ictrl_setup.install_trollstore_ipa"), \
                 patch("copyapp.ictrl_setup._stop_runner") as stop, \
                 patch("copyapp.ictrl_setup._launch_runner") as launch, \
                 patch("copyapp.ictrl_setup._paired_health", return_value=True), \
                 patch("copyapp.ictrl_setup._save_bundle"):
                path, ready = setup_ictrl(UDID, root / "case", ssh_identity=identity,
                                          ssh_known_hosts=known_hosts, runner_ipa=ipa,
                                          reinstall=True)
            self.assertTrue(ready)
            self.assertTrue(verify_case(root / "case"))
            self.assertIn("runner_reinstalled", json.loads(path.read_text())["stages"])
            stop.assert_called_once_with(UDID, BUNDLE)
            self.assertTrue(launch.call_args.kwargs["force"])

    def test_rejects_runner_for_newer_ios_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "ictrl"
            client.write_bytes(b"cli")
            ipa = root / "runner.ipa"
            make_ipa(ipa, "17.0")
            with patch("copyapp.ictrl_setup._device", return_value={
                    "ProductVersion": "16.1.1", "UniqueDeviceID": UDID}), \
                 patch("copyapp.ictrl_setup._build_client", return_value=client), \
                 patch("copyapp.ictrl_setup._installed_app", return_value={}), \
                 patch("copyapp.ictrl_setup.install_trollstore_ipa") as install:
                path, ready = setup_ictrl(UDID, root / "case", runner_ipa=ipa)
            self.assertFalse(ready)
            self.assertIn("needs iOS 17.0", json.loads(path.read_text())["error"]["message"])
            self.assertTrue(verify_case(root / "case"))
            install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
