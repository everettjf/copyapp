import asyncio
import json
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from copyapp.install import (_install_trollstore_ipa_via_ssh,
                             _stop_stale_mobile_processes, install_trollstore_ipa,
                             install_usb_ipa)
from copyapp.verify import sha256_file, verify_case


class InstallationVerificationTest(unittest.TestCase):
    def test_trollstore_timeout_records_observed_old_version_without_retry(self):
        udid = "00008020-000D650434B8003A"
        bundle = "com.copyapp.example"
        helper = ("/var/containers/Bundle/Application/"
                  "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA/TrollStore.app/trollstorehelper")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ipa = root / "app.ipa"
            ipa.write_bytes(b"new package")
            package = {"ipa_sha256": sha256_file(ipa), "bundle_id": bundle,
                       "version": "2.0", "build": "2", "executable": "Example"}

            def run(argv, **_kwargs):
                command = argv[-1]
                if command == "deviceinfo uniqueid":
                    return subprocess.CompletedProcess(argv, 0, (udid + "\n").encode())
                if command.startswith("find "):
                    return subprocess.CompletedProcess(argv, 0, (helper + "\n").encode())
                if command.startswith("sha256sum "):
                    return subprocess.CompletedProcess(argv, 0,
                                                       (package["ipa_sha256"] + "  app.ipa\n").encode())
                if command.startswith("rm -f ") or argv[0] == "scp":
                    return subprocess.CompletedProcess(argv, 0, b"")
                raise AssertionError(command)

            with patch("copyapp.install.analyze_ipa", return_value=package), \
                 patch("copyapp.install._ssh_argv", return_value=["ssh"]), \
                 patch("copyapp.install._stop_running_app", return_value={"status": "requested"}), \
                 patch("copyapp.install._stop_stale_mobile_processes",
                       return_value={"status": "clear", "count": 0}), \
                 patch("copyapp.install.subprocess.run", side_effect=run), \
                 patch("copyapp.install.run_root_command",
                       side_effect=TimeoutError("helper uncertain")) as helper_run, \
                 patch("copyapp.install._installed_app", new=AsyncMock(return_value={
                     "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1",
                     "Path": "/Applications/Example.app"})):
                with self.assertRaises(TimeoutError):
                    _install_trollstore_ipa_via_ssh(udid, ipa, root / "install", 22316,
                                                   root / "identity", root / "known_hosts")
            record = json.loads((root / "install/install.json").read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["installed_after_timeout"]["version"], "1.0")
            self.assertEqual(record["installed_after_timeout"]["build"], "1")
            self.assertTrue((root / "install/input.ipa").is_file())
            helper_run.assert_called_once()

    def test_stale_process_cleanup_checks_each_bundle_id_before_killing(self):
        suffix = "/CopyAppClock.app/CopyAppClock"
        app_a = "/var/containers/Bundle/Application/AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA" + suffix
        app_b = "/var/containers/Bundle/Application/BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB" + suffix
        udid = "00008020-000D650434B8003A"
        device = MagicMock(id=udid, type="usb")
        device.enumerate_processes.return_value = [
            MagicMock(pid=101, parameters={"path": app_a}),
            MagicMock(pid=102, parameters={"path": app_b}),
        ]
        frida = MagicMock()
        frida.get_device_manager.return_value.get_device.return_value = device

        def fake_run(argv, **_kwargs):
            command = argv[-1]
            if command.startswith("cat "):
                bundle = "com.copyapp.clock.currentauto" if "AAAAAAAA" in command else "com.other.clock"
                return subprocess.CompletedProcess(argv, 0, plistlib.dumps({"CFBundleIdentifier": bundle}))
            raise AssertionError(command)

        with patch.dict(sys.modules, {"frida": frida}), \
             patch("copyapp.install.subprocess.run", side_effect=fake_run), \
             patch("copyapp.install.time.sleep"):
            result = _stop_stale_mobile_processes(udid, ["ssh", "mobile@phone"],
                                                  "com.copyapp.clock.currentauto", "CopyAppClock")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["count"], 1)
        device.kill.assert_called_once_with(101)

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
                 patch("copyapp.install._stop_running_app", return_value={
                     "status": "requested", "backend": "ictrl", "bundle_id": bundle}), \
                 patch("copyapp.install.create_using_usbmux", new=AsyncMock(return_value=device)), \
                 patch("copyapp.install.InstallationProxyService", return_value=service):
                result = install_usb_ipa(udid, ipa, root / "install")
            record = json.loads(result.read_text())
            self.assertEqual(record["transport"], "usb")
            self.assertEqual(record["status"], "installed")
            self.assertTrue(record["installed_profile_validated"])
            self.assertEqual(record["preinstall_termination"]["bundle_id"], bundle)
            saved_ipa = (root / "install" / "input.ipa").resolve()
            self.assertEqual(record["ipa"], str(saved_ipa))
            proxy.install_from_local.assert_awaited_once_with(saved_ipa)
            device.close.assert_awaited_once()
            with patch("copyapp.ipa.analyze_ipa", return_value=package):
                self.assertTrue(verify_case(result.parent))
                ipa.write_bytes(b"source rebuilt later")
                self.assertTrue(verify_case(result.parent))
                record["installed_profile_validated"] = False
                result.write_text(json.dumps(record))
                self.assertFalse(verify_case(result.parent))

    def test_usb_install_timeout_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ipa = root / "app.ipa"
            ipa.write_bytes(b"signed package")
            package = {"ipa_sha256": sha256_file(ipa), "bundle_id": "com.copyapp.example",
                       "version": "1.0", "build": "1"}
            device = MagicMock()
            device.get_value = AsyncMock(return_value={"UniqueDeviceID": "00008020-000D650434B8003A"})
            device.close = AsyncMock()
            proxy = MagicMock()
            proxy.install_from_local = AsyncMock(side_effect=asyncio.TimeoutError())
            service = MagicMock()
            service.__aenter__ = AsyncMock(return_value=proxy)
            service.__aexit__ = AsyncMock(return_value=None)
            with patch("copyapp.install.analyze_ipa", return_value=package), \
                 patch("copyapp.install._stop_running_app", return_value={"status": "unavailable"}), \
                 patch("copyapp.install.create_using_usbmux", new=AsyncMock(return_value=device)), \
                 patch("copyapp.install.InstallationProxyService", return_value=service):
                with self.assertRaises(asyncio.TimeoutError):
                    install_usb_ipa("00008020-000D650434B8003A", ipa, root / "install")
            record = json.loads((root / "install" / "install.json").read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["error"]["type"], "TimeoutError")


if __name__ == "__main__":
    unittest.main()
