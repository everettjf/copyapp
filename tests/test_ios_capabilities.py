import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from copyapp.ios_capabilities import capability_plan, collect_capabilities, _root_spawn_probe
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.verify import verify_case


UDID = "00008030-000E45AE0C42402E"


def baseline():
    return {"device": {"UniqueDeviceID": UDID, "ProductVersion": "26.0.1"},
            "probes": {name: {"status": "available"} for name in
                       ("usb_lockdown", "usb_screenshot", "ictrl")},
            "host": {name: {"status": "available"} for name in
                     ("xcode", "development_signing")}}


class IosCapabilitiesTest(unittest.TestCase):
    def test_standard_analysis_and_rebuild_do_not_require_a_package_or_jailbreak(self):
        result = capability_plan(baseline(), "standard")
        self.assertEqual(result["ui_backend"], "ictrl")
        self.assertTrue(result["operations"]["analyze"]["ready_for_attempt"])
        self.assertTrue(result["operations"]["rebuild"]["ready_for_attempt"])
        self.assertFalse(result["operations"]["trace"]["ready_for_attempt"])

    def test_explicit_deep_operation_cannot_silently_become_ui_success(self):
        result = capability_plan(baseline(), "enhanced")
        self.assertFalse(result["operations"]["analyze"]["ready_for_attempt"])
        self.assertIn("ssh_mobile", result["operations"]["analyze"]["missing"])
        self.assertIn("frida_usb", result["operations"]["trace"]["missing"])

    def test_auto_uses_observed_services_not_a_jailbreak_marker(self):
        record = baseline()
        record["probes"]["rootless_marker"] = {"status": "observed", "roothide_namespace": True}
        self.assertEqual(capability_plan(record, "auto")["selected_mode"], "standard")
        for name in ("ssh_mobile", "ios_mcp"):
            record["probes"][name] = {"status": "available"}
        result = capability_plan(record, "auto")
        self.assertEqual(result["selected_mode"], "enhanced")
        self.assertEqual(result["ui_backend"], "ios-mcp")
        self.assertFalse(result["operations"]["trace"]["ready_for_attempt"])

    def test_standard_rebuild_needs_development_signing_not_just_ldid(self):
        record = baseline()
        record["host"] = {"xcode": {"status": "available"}, "ldid": {"status": "available"}}
        result = capability_plan(record, "standard")
        self.assertTrue(result["operations"]["analyze"]["ready_for_attempt"])
        self.assertEqual(result["operations"]["rebuild"]["missing"], ["development_signing"])

    def test_mobile_full_frida_allows_tracing_but_not_device_decryption(self):
        data = baseline()
        for name in ("ssh_mobile", "frida_usb", "ios_mcp"):
            data["probes"][name] = {"status": "available"}
        data["probes"]["frida_root_spawn"] = {"status": "unavailable", "effective_uid": 501}
        result = capability_plan(data, "auto")
        self.assertEqual(result["selected_mode"], "enhanced")
        for name in ("analyze", "trace", "sandbox"):
            self.assertTrue(result["operations"][name]["ready_for_attempt"])
        self.assertEqual(result["operations"]["decrypt-device"]["missing"], ["frida_root_spawn"])
        # Historical cases retain their original readiness meaning.
        old = capability_plan(data, "auto", version=1)
        self.assertNotIn("capability_model_version", old)
        self.assertTrue(old["operations"]["decrypt-device"]["ready_for_attempt"])

    def test_root_probe_kills_suspended_child_without_running_it_and_records_mobile_uid(self):
        from contextlib import nullcontext
        device = Mock(id=UDID, type="usb")
        device.spawn.return_value = 123
        with patch("copyapp.usb_tunnel.exact_ssh_tunnel", return_value=nullcontext(1234)), \
                patch("copyapp.ssh_acquire._ssh_argv", return_value=[]), \
                patch("copyapp.root_bridge.resolve_jailbreak_executable", return_value="/var/jb/bin/sh"), \
                patch("frida.get_device_manager") as manager, \
                patch("copyapp.root_bridge._spawned_effective_uid", return_value=501):
            manager.return_value.get_device.return_value = device
            result = _root_spawn_probe(UDID, 1234, Path("key"), Path("hosts"))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["effective_uid"], 501)
        self.assertTrue(result["suspended_child_stopped"])
        device.resume.assert_not_called()
        device.spawn.assert_called_once_with(["/var/jb/bin/sh", "-c", ":"])
        device.kill.assert_called_once_with(123)

    def test_root_probe_cleanup_failure_prevents_root_readiness(self):
        from contextlib import nullcontext
        device = Mock(id=UDID, type="usb")
        device.spawn.return_value = 123
        device.kill.side_effect = RuntimeError("stop failed")
        with patch("copyapp.usb_tunnel.exact_ssh_tunnel", return_value=nullcontext(1234)), \
                patch("copyapp.ssh_acquire._ssh_argv", return_value=[]), \
                patch("copyapp.root_bridge.resolve_jailbreak_executable", return_value="/var/jb/bin/sh"), \
                patch("frida.get_device_manager") as manager, \
                patch("copyapp.root_bridge._spawned_effective_uid", return_value=0):
            manager.return_value.get_device.return_value = device
            result = _root_spawn_probe(UDID, 1234, Path("key"), Path("hosts"))
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["suspended_child_stopped"])
        device.resume.assert_not_called()

    def test_standard_doctor_never_calls_jailbreak_collectors(self):
        from copyapp.doctor import run_doctor
        record = baseline()

        async def usb(_udid, _out, probes, _evidence, survey_only):
            self.assertTrue(survey_only)
            probes.update({key: record["probes"][key] for key in ("usb_lockdown", "usb_screenshot")})
            return record["device"]

        with tempfile.TemporaryDirectory() as directory, \
                patch("copyapp.doctor._usb_probes", side_effect=usb), \
                patch("copyapp.doctor._host_probes", return_value={
                    **record["host"], "xcodegen": {"status": "available"},
                    "ldid": {"status": "available"}, "theos": {"status": "available"},
                    "codex_cli": {"status": "available"}}), \
                patch("copyapp.doctor._ictrl_probe", return_value={"status": "available"}), \
                patch("copyapp.doctor._ssh_probe") as ssh, \
                patch("copyapp.doctor._frida_probe") as frida, \
                patch("copyapp.doctor._ios_mcp_probe") as mcp:
            root = Path(directory) / "doctor"
            run_doctor(UDID, root, standard_only=True)
            data = read_json(root / "device.json")
            self.assertEqual(data["probes"]["ssh_mobile"]["status"], "not_probed")
            self.assertNotIn("theos_tweak", [step["for"] for step in data["next_steps"]])
            ssh.assert_not_called()
            frida.assert_not_called()
            mcp.assert_not_called()

    def test_v2_case_binds_capability_plan_and_cannot_fall_back_to_report_index(self):
        def doctor(_udid, out, *_args, **kwargs):
            self.assertTrue(kwargs["standard_only"])
            out.mkdir()
            data = baseline()
            for key in ("ssh_mobile", "frida_usb", "ios_mcp"):
                data["probes"][key] = {"status": "not_probed"}
            write_json(out / "device.json", data)
            write_json(out / "manifest.json", {"kind": "device_doctor", "evidence": []})

        with tempfile.TemporaryDirectory() as directory, \
                patch("copyapp.ios_capabilities.run_doctor", side_effect=doctor), \
                patch("copyapp.ios_capabilities._root_spawn_probe") as root_probe, \
                redirect_stdout(io.StringIO()):
            root = Path(directory) / "case"
            collect_capabilities(UDID, root, "standard")
            root_probe.assert_not_called()
            self.assertTrue(verify_case(root))
            saved = read_json(root / "capabilities.json")
            saved["operations"]["trace"]["ready_for_attempt"] = True
            write_json(root / "capabilities.json", saved)
            write_json(root / "report-index.json", {"artifacts": {}})
            seal_case(root, "ios_capabilities", status="complete", requested_mode="standard",
                      selected_mode="standard", device_id_sha256_prefix="7982b33dd7a5e62e")
            self.assertFalse(verify_case(root))

    def test_root_readiness_rejects_wrong_device_or_missing_stop_and_retains_v1_cases(self):
        from copyapp.ios_capabilities import _root_spawn_valid
        data = baseline()
        for name in ("ssh_mobile", "frida_usb"):
            data["probes"][name] = {"status": "available"}
        probe = {"status": "available", "device_id": UDID, "effective_uid": 0,
                 "identity_verified": True, "suspended_child_stopped": True}
        self.assertTrue(_root_spawn_valid(probe, UDID, "enhanced", data["probes"]))
        for replacement in ({"device_id": "another-phone"}, {"effective_uid": 501},
                            {"effective_uid": False}, {"suspended_child_stopped": False}):
            self.assertFalse(_root_spawn_valid({**probe, **replacement}, UDID, "enhanced", data["probes"]))
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            write_json(root / "baseline/device.json", data)
            write_json(root / "baseline/manifest.json", {"kind": "device_doctor", "evidence": []})
            write_json(root / "capabilities.json", {**data, **capability_plan(data, "enhanced", version=1)})
            seal_case(root, "ios_capabilities", status="complete", requested_mode="enhanced",
                      selected_mode="enhanced", device_id_sha256_prefix="7982b33dd7a5e62e")
            self.assertTrue(verify_case(root))
            # A retained new probe cannot be reclassified as an older model.
            write_json(root / "root-spawn.json", probe)
            seal_case(root, "ios_capabilities", status="complete", requested_mode="enhanced",
                      selected_mode="enhanced", device_id_sha256_prefix="7982b33dd7a5e62e")
            self.assertFalse(verify_case(root))

    def test_unknown_ios_kind_and_unlisted_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            (root / "report.md").write_text("placeholder")
            seal_case(root, "ios_future_kind", status="complete")
            self.assertFalse(verify_case(root))
            (root / "unexpected.txt").write_text("unlisted")
            self.assertFalse(verify_case(root))

    def test_onboarding_standard_does_not_generate_ssh_keys(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from copyapp.onboarding import run_onboarding

        def collect(_udid, out, *_args):
            out.mkdir()
            write_json(out / "capabilities.json", {**capability_plan(baseline(), "standard")})

        with tempfile.TemporaryDirectory() as directory, \
                patch("copyapp.onboarding.list_devices", new=AsyncMock(return_value=[
                    SimpleNamespace(serial=UDID, connection_type="USB")])), \
                patch("copyapp.ios_capabilities.collect_capabilities", side_effect=collect), \
                patch("copyapp.onboarding._prepare_ssh_key") as keygen, \
                redirect_stdout(io.StringIO()):
            _, ready = run_onboarding(output=Path(directory) / "case", stage="rebuild", mode="standard")
            self.assertTrue(ready)
            keygen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
