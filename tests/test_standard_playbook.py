import asyncio
import io
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from PIL import Image

from copyapp.experiment import ExperimentUI
from copyapp.ios_cases import read_json, write_json
from copyapp.playbook import _check_standard_launch_frame, run_playbook


UDID = "00008030-000E45AE0C42402E"
BUNDLE = "com.example.original"


class StandardPlaybookTest(unittest.TestCase):
    def test_standard_route_owns_xctest_without_opening_mcp_identity_tunnel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.json"
            write_json(script, {"schema_version": 1, "bundle_id": BUNDLE, "scenario_id": "read",
                                "steps": [{"action": "observe"}]})
            with patch("copyapp.playbook.ictrl_tunnel", return_value=nullcontext(1234)) as tunnel, \
                    patch("copyapp.playbook.ios_mcp_tunnel") as mcp, \
                    patch("copyapp.playbook._run_steps"):
                _, complete = run_playbook(UDID, "ictrl", script, root / "case", mode="standard")
            self.assertTrue(complete)
            self.assertTrue(tunnel.call_args.kwargs["require_xctest"])
            self.assertEqual(tunnel.call_args.kwargs["log_path"], root / "case/xcuitest.log")
            mcp.assert_not_called()

    def test_standard_mode_rejects_jailbreak_backend_and_runtime_observer_before_touching_phone(self):
        with patch("copyapp.playbook.ictrl_tunnel") as tunnel:
            for backend, observer in [("ios-mcp", None), ("ictrl", Mock())]:
                with self.assertRaisesRegex(ValueError, "standard playbooks"):
                    run_playbook(UDID, backend, Path("missing"), Path("missing"),
                                 trace_observer=observer, mode="standard")
            tunnel.assert_not_called()

    def test_standard_screenshot_uses_exact_usb_device_without_runner_capture(self):
        ui = ExperimentUI.__new__(ExperimentUI)
        ui.backend, ui.standard_mode, ui.device_udid = "ictrl", True, UDID
        ui.client = Mock()
        with tempfile.TemporaryDirectory() as directory, \
                patch("copyapp.device_developer.exact_device_screenshot",
                      new=AsyncMock(return_value=(b"image", "native_rsd"))) as capture:
            path = Path(directory) / "screen.jpg"
            ui.screenshot(path)
            self.assertEqual(path.read_bytes(), b"image")
            self.assertEqual(ui.last_screenshot_source, "usb_native_rsd")
            capture.assert_awaited_once_with(UDID)
        ui.client.screenshot.assert_not_called()

    def test_launch_recovery_preserves_black_frame_and_never_repeats_flow_actions(self):
        class UI:
            client = Mock()
            last_screenshot_source = "usb_native_rsd"

            def __init__(self):
                self.count = 0
                self.launch = Mock()

            def screenshot(self, path):
                self.count += 1
                Image.new("RGB", (30, 30), "black" if self.count == 1 else "white").save(path)

            def frontmost(self):
                return BUNDLE

        ui = UI()
        with tempfile.TemporaryDirectory() as directory:
            root, record = Path(directory), {"evidence": []}
            _check_standard_launch_frame(ui, BUNDLE, root, record)
            self.assertTrue((root / "standard-launch-initial.jpg").is_file())
            self.assertTrue(record["standard_launch_frames"][0]["near_uniform_black"])
            self.assertFalse(record["standard_launch_frames"][1]["near_uniform_black"])
            self.assertEqual(record["fresh_launch_render_recovery"], "home_then_xctest_activate")
        ui.client.call_ui.assert_called_once_with("home")
        ui.launch.assert_called_once_with(BUNDLE)


if __name__ == "__main__":
    unittest.main()
