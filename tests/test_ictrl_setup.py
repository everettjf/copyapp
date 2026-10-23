import asyncio
import json
import os
import plistlib
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from copyapp.ictrl_setup import _bundle_from_ipa, _ensure_developer_image, _pair, setup_ictrl
from copyapp.usb_tunnel import ictrl_xcuitest_session
from copyapp.verify import verify_case


BUNDLE = "com.example.ictrl.uitests.xctrunner"
UDID = "00008020-000D650434B8003A"


@contextmanager
def fake_forward(*args, **kwargs):
    yield 33224


@contextmanager
def fake_xcuitest(*args, **kwargs):
    class Process:
        def poll(self):
            return None

    yield Process()


def make_ipa(path: Path, minimum: str) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("Payload/iCTRLUITests-Runner.app/Info.plist",
                         plistlib.dumps({"CFBundleIdentifier": BUNDLE,
                                         "MinimumOSVersion": minimum}))


class ICtrlSetupTest(unittest.TestCase):
    def test_usb_only_runner_failure_never_falls_back_to_trollstore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "ictrl"
            client.write_bytes(b"cli")
            ipa = root / "runner.ipa"
            make_ipa(ipa, "16.0")
            identity, hosts = root / "id", root / "known_hosts"
            identity.touch()
            hosts.touch()
            with patch("copyapp.ictrl_setup._device", return_value={
                    "ProductVersion": "26.0.1", "UniqueDeviceID": UDID}), \
                 patch("copyapp.ictrl_setup._build_client", return_value=client), \
                 patch("copyapp.ictrl_setup.configured_ictrl_runner_bundle", return_value=None), \
                 patch("copyapp.ictrl_setup._installed_app", return_value={}), \
                 patch("copyapp.ictrl_setup._install_usb_ipa", side_effect=RuntimeError("bad signature")), \
                 patch("copyapp.ictrl_setup.install_trollstore_ipa") as trollstore, \
                 patch("copyapp.ictrl_setup._usb_forward") as forward:
                path, ready = setup_ictrl(UDID, root / "case", ssh_identity=identity,
                                          ssh_known_hosts=hosts, runner_ipa=ipa, transport="usb")
            self.assertFalse(ready)
            self.assertIn("USB-only", json.loads(path.read_text())["error"]["message"])
            trollstore.assert_not_called()
            forward.assert_not_called()

    def test_xcuitest_one_shot_pairing_is_explicit(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch("copyapp.usb_tunnel.subprocess.Popen", return_value=process) as launch, \
             patch("copyapp.usb_tunnel.subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
            with ictrl_xcuitest_session(UDID, BUNDLE, auto_approve_first_pair=True):
                pass
        command = launch.call_args.args[0]
        self.assertEqual(command[-3:], ["--env", "ICTRL_ALLOW_AUTH_ONCE=1", BUNDLE])
        process.terminate.assert_called_once()

    def test_ios26_xcuitest_uses_userspace_tunnel(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch("copyapp.usb_tunnel.subprocess.Popen", return_value=process) as launch, \
             patch("copyapp.usb_tunnel.subprocess.run", return_value=subprocess.CompletedProcess([], 0)):
            with ictrl_xcuitest_session(UDID, BUNDLE, ios_version="26.0.1"):
                pass
        command = launch.call_args.args[0]
        self.assertIn("--userspace", command)
        self.assertNotIn("--native", command)

    def test_owned_runner_stops_before_testmanager_disconnect_even_on_failure(self):
        events = []
        process = MagicMock()
        process.poll.return_value = None
        process.terminate.side_effect = lambda: events.append("disconnect")

        def stop(command, **kwargs):
            self.assertEqual(command[-3:], ["copyapp.ictrl_runner_stop", UDID, BUNDLE])
            events.append("stop runner")
            return subprocess.CompletedProcess(command, 0)

        with patch("copyapp.usb_tunnel.subprocess.Popen", return_value=process), \
             patch("copyapp.usb_tunnel.subprocess.run", side_effect=stop):
            with self.assertRaisesRegex(RuntimeError, "capture failed"):
                with ictrl_xcuitest_session(UDID, BUNDLE, ios_version="17.3.1"):
                    raise RuntimeError("capture failed")
        self.assertEqual(events, ["stop runner", "disconnect"])

    def test_runner_stop_failure_still_closes_host_and_is_reported(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch("copyapp.usb_tunnel.subprocess.Popen", return_value=process), \
             patch("copyapp.usb_tunnel.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(RuntimeError, "could not stop the owned"):
                with ictrl_xcuitest_session(UDID, BUNDLE, ios_version="17.3.1"):
                    pass
        process.terminate.assert_called_once()

    def test_ios26_mounts_developer_image_before_xcuitest(self):
        with patch("copyapp.ictrl_setup.subprocess.run") as run:
            run.return_value.returncode = 0
            _ensure_developer_image(UDID, "26.0.1")
        command = run.call_args.args[0]
        self.assertEqual(command[-4:], ["auto-mount", "--userspace", "--udid", UDID])

    def test_older_ios_does_not_mount_developer_image_in_setup(self):
        with patch("copyapp.ictrl_setup.subprocess.run") as run:
            _ensure_developer_image(UDID, "17.3.1")
        run.assert_not_called()

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

    def test_existing_supplied_runner_is_registered_for_future_tunnels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "ictrl"
            client.write_bytes(b"cli")
            ipa = root / "runner.ipa"
            make_ipa(ipa, "16.0")
            with patch("copyapp.ictrl_setup._device", return_value={
                    "ProductVersion": "16.1.1", "UniqueDeviceID": UDID}), \
                 patch("copyapp.ictrl_setup.configured_ictrl_runner_bundle", return_value=None), \
                 patch("copyapp.ictrl_setup._build_client", return_value=client), \
                 patch("copyapp.ictrl_setup._installed_app", return_value={"Path": "/app"}), \
                 patch("copyapp.ictrl_setup._usb_forward", side_effect=fake_forward), \
                 patch("copyapp.ictrl_setup._launch_runner"), \
                 patch("copyapp.ictrl_setup._paired_health", return_value=True), \
                 patch("copyapp.ictrl_setup._save_bundle") as save:
                path, ready = setup_ictrl(UDID, root / "case", runner_ipa=ipa)
            self.assertTrue(ready)
            self.assertIn("runner_registered", json.loads(path.read_text())["stages"])
            save.assert_called_once_with(UDID, BUNDLE)

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
                 patch("copyapp.ictrl_setup._install_usb_ipa", side_effect=RuntimeError("unsigned IPA")), \
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

    def test_signed_runner_installs_over_usb_without_ssh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "ictrl"
            client.write_bytes(b"cli")
            ipa = root / "runner.ipa"
            make_ipa(ipa, "16.0")
            with patch("copyapp.ictrl_setup._device", return_value={
                    "ProductVersion": "17.3.1", "UniqueDeviceID": UDID}), \
                 patch("copyapp.ictrl_setup.configured_ictrl_runner_bundle", return_value=None), \
                 patch("copyapp.ictrl_setup._build_client", return_value=client), \
                 patch("copyapp.ictrl_setup._installed_app", side_effect=[{}, {"Path": "/app"}]), \
                 patch("copyapp.ictrl_setup._install_usb_ipa") as usb_install, \
                 patch("copyapp.ictrl_setup._usb_forward", side_effect=fake_forward), \
                 patch("copyapp.ictrl_setup.ictrl_xcuitest_session", side_effect=fake_xcuitest), \
                 patch("copyapp.ictrl_setup._runner_ready", return_value=True), \
                 patch("copyapp.ictrl_setup._paired_health", return_value=True), \
                 patch("copyapp.ictrl_setup._save_bundle"), \
                 patch("copyapp.ictrl_setup.install_trollstore_ipa") as trollstore_install:
                path, ready = setup_ictrl(UDID, root / "case", runner_ipa=ipa)
            self.assertTrue(ready)
            self.assertIn("runner_usb_installed", json.loads(path.read_text())["stages"])
            self.assertIn("xcuitest_session_started", json.loads(path.read_text())["stages"])
            usb_install.assert_awaited_once()
            trollstore_install.assert_not_called()

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
                 patch("copyapp.ictrl_setup._install_usb_ipa", side_effect=RuntimeError("unsigned IPA")), \
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
