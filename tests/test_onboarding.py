import tempfile
import unittest
import os
import json
import socket
from contextlib import nullcontext, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from copyapp.doctor import _frida_probe, _next_steps, _ssh_probe, run_doctor
from copyapp.onboarding import _choose_device, _prepare_ssh_key, run_onboarding
from copyapp.tunnels import _check_port, run_tunnels


UDID = "00008020-000D650434B8003A"
OTHER = "00008122-001461960A8A801C"


class OnboardingTest(unittest.TestCase):
    def test_multiple_devices_require_an_exact_udid(self):
        devices = [SimpleNamespace(serial=UDID, connection_type="USB"),
                   SimpleNamespace(serial=OTHER, connection_type="USB")]
        with self.assertRaisesRegex(ValueError, "multiple USB devices"):
            _choose_device(devices, None)
        self.assertEqual(_choose_device(devices, UDID), UDID)
        with self.assertRaisesRegex(ValueError, "not connected"):
            _choose_device(devices, "wrong")

    def test_key_creation_never_overwrites_an_existing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ssh" / "id_ed25519"
            self.assertTrue(_prepare_ssh_key(path))
            original = path.read_bytes()
            self.assertTrue((path.parent / "id_ed25519.pub").is_file())
            self.assertFalse(_prepare_ssh_key(path))
            self.assertEqual(path.read_bytes(), original)
            existing_parent = Path(directory) / "existing"
            existing_parent.mkdir(mode=0o755)
            before = os.stat(existing_parent).st_mode & 0o777
            _prepare_ssh_key(existing_parent / "id")
            self.assertEqual(os.stat(existing_parent).st_mode & 0o777, before)

    def test_doctor_steps_are_ordered_and_do_not_require_optional_tweak_build(self):
        probes = {name: {"status": "available"} for name in
                  ("usb_lockdown", "usb_screenshot", "ssh_mobile", "frida_usb",
                   "ios_mcp", "ictrl")}
        host = {name: {"status": "available"} for name in
                ("xcode", "xcodegen", "ldid", "codex_cli")}
        host["theos"] = {"status": "not_configured"}
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / "id"
            known_hosts = Path(directory) / "known_hosts"
            self.assertEqual(_next_steps(UDID, probes, host, identity, known_hosts), [])
            probes["ssh_mobile"] = {"status": "not_configured"}
            steps = _next_steps(UDID, probes, host, identity, known_hosts)
            self.assertEqual([step["for"] for step in steps],
                             ["ssh_mobile", "ssh_mobile"])
            self.assertIn("fingerprint", steps[1]["action"])
            probes["ssh_mobile"] = {"status": "identity_mismatch"}
            steps = _next_steps(UDID, probes, host, identity, known_hosts)
            self.assertEqual(len(steps), 1)
            self.assertIn("different phone", steps[0]["action"])

    def test_doctor_distinguishes_another_phones_pinned_host_key(self):
        with tempfile.TemporaryDirectory() as directory:
            identity = Path(directory) / "id"
            known_hosts = Path(directory) / "known_hosts"
            identity.write_text("test key")
            known_hosts.write_text("test host key")
            failed = SimpleNamespace(returncode=255, stdout="",
                                     stderr="REMOTE HOST IDENTIFICATION HAS CHANGED!")
            with patch("copyapp.doctor._ssh_argv", return_value=["ssh"]), \
                 patch("copyapp.doctor.subprocess.run", return_value=failed):
                probe = _ssh_probe(UDID, 22316, identity, known_hosts)
            self.assertEqual(probe["status"], "host_key_mismatch")
            probes = {name: {"status": "available"} for name in
                      ("usb_lockdown", "usb_screenshot", "frida_usb",
                       "ios_mcp", "ictrl")}
            probes["ssh_mobile"] = probe
            host = {name: {"status": "available"} for name in
                    ("xcode", "xcodegen", "ldid", "codex_cli")}
            steps = _next_steps(UDID, probes, host, identity, known_hosts, 22316)
            self.assertEqual(len(steps), 1)
            self.assertIn("separate file", steps[0]["action"])
            self.assertIn("22316", steps[0]["action"])

    def test_doctor_reports_optional_developer_filesystem_gap(self):
        probes = {name: {"status": "available"} for name in
                  ("usb_lockdown", "usb_screenshot", "ssh_mobile", "frida_usb",
                   "ios_mcp", "ictrl")}
        probes["dvt_filesystem"] = {"status": "unavailable",
                                    "error_type": "ConnectionTerminatedError"}
        host = {name: {"status": "available"} for name in
                ("xcode", "xcodegen", "ldid", "codex_cli")}
        with tempfile.TemporaryDirectory() as directory:
            steps = _next_steps(UDID, probes, host, Path(directory) / "id",
                                Path(directory) / "known_hosts")
        self.assertEqual([step["for"] for step in steps], ["dvt_filesystem_optional"])
        self.assertIn("SSH-backed analysis", steps[0]["action"])

    def test_development_signing_is_a_rebuild_route_without_ldid(self):
        probes = {name: {"status": "available"} for name in
                  ("usb_lockdown", "usb_screenshot", "ssh_mobile", "frida_usb",
                   "ios_mcp", "ictrl")}
        host = {name: {"status": "available"} for name in
                ("xcode", "xcodegen", "codex_cli", "development_signing")}
        host["ldid"] = {"status": "not_configured"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steps = _next_steps(UDID, probes, host, root / "id", root / "known_hosts")
            self.assertNotIn("signing_rebuild", [step["for"] for step in steps])
            def fake_doctor(_udid, output, *_args, **_kwargs):
                output.mkdir()
                (output / "report.md").write_text("report")
                (output / "device.json").write_text(json.dumps({
                    "probes": probes, "host": host, "next_steps": steps,
                }))
                return output / "report.md", True
            device = SimpleNamespace(serial=UDID, connection_type="USB")
            display = StringIO()
            with patch("copyapp.onboarding.list_devices", new=AsyncMock(return_value=[device])), \
                 patch("copyapp.onboarding.run_doctor", side_effect=fake_doctor), \
                 patch("copyapp.onboarding._prepare_ssh_key", return_value=False), \
                 redirect_stdout(display):
                _, ready = run_onboarding(output=root / "rebuild", stage="rebuild")
            self.assertTrue(ready)
            self.assertIn("no persistent tunnel is required", display.getvalue())
            host["development_signing"] = {"status": "not_configured"}
            steps = _next_steps(UDID, probes, host, root / "id", root / "known_hosts")
            self.assertIn("signing_rebuild", [step["for"] for step in steps])

    def test_roothide_inventory_requires_configured_sidecar_for_analysis(self):
        probes = {name: {"status": "available"} for name in
                  ("usb_screenshot", "ssh_mobile", "ios_mcp")}
        probes["rootless_marker"] = {"roothide_namespace": True}
        probes["frida_usb"] = {"status": "available", "transport": "usb"}
        host = {"xcode": {"status": "available"},
                "xcodegen": {"status": "available"},
                "ldid": {"status": "available"}}
        device = SimpleNamespace(serial=UDID, connection_type="USB")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def fake_doctor(_udid, output, *_args, **_kwargs):
                output.mkdir()
                (output / "report.md").write_text("report")
                (output / "device.json").write_text(json.dumps({
                    "probes": probes, "host": host,
                    "next_steps": [{"for": "frida_roothide", "action": "configure sidecar"}],
                }))
                return output / "report.md", True
            display = StringIO()
            with patch("copyapp.onboarding.list_devices", new=AsyncMock(return_value=[device])), \
                 patch("copyapp.onboarding.run_doctor", side_effect=fake_doctor), \
                 redirect_stdout(display):
                _, ready = run_onboarding(output=root / "before", stage="analyze",
                                          prepare_ssh=False)
            self.assertFalse(ready)
            self.assertIn("configure sidecar", display.getvalue())
            probes["frida_usb"]["transport"] = "usb_roothide_sidecar"
            with patch("copyapp.onboarding.list_devices", new=AsyncMock(return_value=[device])), \
                 patch("copyapp.onboarding.run_doctor", side_effect=fake_doctor), \
                 redirect_stdout(StringIO()):
                _, ready = run_onboarding(output=root / "after", stage="analyze",
                                          prepare_ssh=False)
            self.assertTrue(ready)

    def test_doctor_detects_roothide_even_when_dvt_marker_was_observed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "doctor"
            async def fake_usb(_udid, _output, probes, _evidence, _survey_only):
                probes.update({"usb_lockdown": {"status": "available"},
                               "usb_screenshot": {"status": "available"},
                               "rootless_marker": {"status": "observed",
                                                   "var_jb_readable": True}})
                return {"UniqueDeviceID": UDID}
            host = {name: {"status": "available"} for name in
                    ("xcode", "xcodegen", "ldid", "codex_cli", "theos")}
            with patch("copyapp.doctor._usb_probes", side_effect=fake_usb), \
                 patch("copyapp.doctor.socket.create_connection", side_effect=OSError), \
                 patch("copyapp.doctor.ssh_tunnel", return_value=nullcontext(22222)), \
                 patch("copyapp.doctor._ssh_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._roothide_marker_probe", return_value={
                     "status": "observed", "roothide_namespace": True}), \
                 patch("copyapp.doctor._frida_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._ios_mcp_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._ictrl_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._host_probes", return_value=host):
                run_doctor(UDID, output)
            record = json.loads((output / "device.json").read_text())
            self.assertTrue(record["probes"]["rootless_marker"]["var_jb_readable"])
            self.assertTrue(record["probes"]["rootless_marker"]["roothide_namespace"])
            self.assertIn("frida_roothide", [s["for"] for s in record["next_steps"]])

    def test_doctor_ssh_marker_does_not_report_stale_dvt_error(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "doctor"
            async def fake_usb(_udid, _output, probes, _evidence, _survey_only):
                probes.update({"usb_lockdown": {"status": "available"},
                               "usb_screenshot": {"status": "available"},
                               "rootless_marker": {"status": "unavailable",
                                                   "error_type": "RuntimeError",
                                                   "reason": "native RSD directory listing failed"}})
                return {"UniqueDeviceID": UDID}
            host = {name: {"status": "available"} for name in
                    ("xcode", "xcodegen", "ldid", "codex_cli", "theos")}
            with patch("copyapp.doctor._usb_probes", side_effect=fake_usb), \
                 patch("copyapp.doctor.socket.create_connection", side_effect=OSError), \
                 patch("copyapp.doctor.ssh_tunnel", return_value=nullcontext(22222)), \
                 patch("copyapp.doctor._ssh_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._roothide_marker_probe", return_value={
                     "status": "observed", "roothide_namespace": True}), \
                 patch("copyapp.doctor._frida_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._ios_mcp_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._ictrl_probe", return_value={"status": "available"}), \
                 patch("copyapp.doctor._host_probes", return_value=host):
                run_doctor(UDID, output)
            record = json.loads((output / "device.json").read_text())
            marker = record["probes"]["rootless_marker"]
            self.assertEqual(marker["status"], "observed")
            self.assertTrue(marker["roothide_namespace"])
            self.assertEqual(marker["dvt_marker_status"], "unavailable")
            self.assertNotIn("reason", marker)
            self.assertNotIn("error_type", marker)
            self.assertNotIn("native RSD directory listing failed", (output / "report.md").read_text())

    def test_frida_inventory_does_not_claim_jailed_access_is_ready(self):
        device = SimpleNamespace(id=UDID, type="usb",
                                 query_system_parameters=lambda: {"access": "jailed"},
                                 enumerate_processes=lambda **kwargs: ["SpringBoard"])
        manager = SimpleNamespace(enumerate_devices=lambda: [device])
        with patch("frida.get_device_manager", return_value=manager):
            result = _frida_probe(UDID)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["access"], "jailed")
        device.query_system_parameters = lambda: {"access": "full"}
        with patch("frida.get_device_manager", return_value=manager):
            result = _frida_probe(UDID)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["access"], "full")

    def test_tunnel_rejects_colliding_ports_before_spawning(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            run_tunnels(UDID, 22222, 22222)

    def test_tunnel_reports_an_occupied_host_port(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(ValueError, f"local port {port} is already in use"):
                _check_port(port)

    def test_tunnel_refuses_a_missing_exact_device(self):
        with patch("pymobiledevice3.usbmux.list_devices",
                   new=AsyncMock(return_value=[])), \
             patch("copyapp.tunnels._check_port"), \
             self.assertRaisesRegex(ValueError, "not connected over USB"):
            run_tunnels(UDID, 33551, 33552)

    def test_onboard_prints_only_the_selected_stage_repairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = []
            def fake_doctor(udid, output, *args, **kwargs):
                stages.append(kwargs.get("survey_only"))
                output.mkdir()
                (output / "report.md").write_text("report")
                (output / "device.json").write_text(json.dumps({
                    "probes": {"usb_screenshot": {"status": "available"},
                               "ssh_mobile": {"status": "not_configured"},
                               "frida_usb": {"status": "not_configured"},
                               "ios_mcp": {"status": "not_configured"}},
                    "host": {"xcode": {"status": "available"},
                             "xcodegen": {"status": "available"},
                             "ldid": {"status": "available"}},
                    "next_steps": [{"for": "ssh_mobile", "action": "configure SSH"}],
                }))
                return output / "report.md", True
            display = StringIO()
            device = SimpleNamespace(serial=UDID, connection_type="USB")
            with patch("copyapp.onboarding.list_devices", new=AsyncMock(return_value=[device])), \
                 patch("copyapp.onboarding.run_doctor", side_effect=fake_doctor), \
                 patch("copyapp.onboarding._prepare_ssh_key") as keygen, \
                 redirect_stdout(display):
                _, ready = run_onboarding(output=root / "survey")
            self.assertTrue(ready)
            keygen.assert_not_called()
            self.assertEqual(stages, [True])
            self.assertNotIn("configure SSH", display.getvalue())
            display = StringIO()
            with patch("copyapp.onboarding.list_devices", new=AsyncMock(return_value=[device])), \
                 patch("copyapp.onboarding.run_doctor", side_effect=fake_doctor), \
                 patch("copyapp.onboarding._prepare_ssh_key", return_value=True) as keygen, \
                 redirect_stdout(display):
                _, ready = run_onboarding(output=root / "analyze", stage="analyze",
                                          ssh_identity=root / "id_ed25519")
            self.assertFalse(ready)
            keygen.assert_called_once_with(root / "id_ed25519")
            self.assertEqual(stages, [True, False])
            self.assertIn("configure SSH", display.getvalue())

    def test_survey_doctor_skips_deep_channels_and_repair_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "survey"
            async def fake_usb(udid, case, probes, evidence, survey_only):
                self.assertTrue(survey_only)
                probes.update({"usb_lockdown": {"status": "available"},
                               "usb_screenshot": {"status": "available"},
                               "dvt_filesystem": {"status": "not_probed"},
                               "rootless_marker": {"status": "not_probed"}})
                return {"UniqueDeviceID": udid}
            host = {name: {"status": "not_configured"} for name in
                    ("xcode", "xcodegen", "ldid", "codex_cli", "claude_cli", "theos")}
            with patch("copyapp.doctor._usb_probes", side_effect=fake_usb), \
                 patch("copyapp.doctor._host_probes", return_value=host), \
                 patch("copyapp.doctor.ssh_tunnel") as ssh_tunnel, \
                 patch("copyapp.doctor._frida_probe") as frida_probe, \
                 patch("copyapp.doctor._ios_mcp_probe") as ios_mcp_probe:
                report, connected = run_doctor(UDID, output, survey_only=True)
            self.assertTrue(connected)
            self.assertTrue(report.is_file())
            ssh_tunnel.assert_not_called()
            frida_probe.assert_not_called()
            ios_mcp_probe.assert_not_called()
            record = json.loads((output / "device.json").read_text())
            self.assertEqual(record["next_steps"], [])
            self.assertEqual(record["probes"]["ssh_mobile"]["status"], "not_probed")


if __name__ == "__main__":
    unittest.main()
