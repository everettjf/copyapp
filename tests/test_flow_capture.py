import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from copyapp.flow_capture import (ObserverGroup, capture_flow, validate_flow_pair,
                                  validate_flow_trace_pair)
from copyapp.flow_trace import FlowTrace
from copyapp.verify import verify_case


class FlowCaptureTest(unittest.TestCase):
    def test_observer_group_finishes_all_children_after_one_cleanup_error(self):
        calls = []

        class Observer:
            def __init__(self, name, fail=False):
                self.name = name
                self.fail = fail

            def start(self, udid, bundle):
                calls.append((self.name, "start", udid, bundle))

            def begin_step(self, index, action):
                calls.append((self.name, "begin", index, action))

            def end_step(self):
                calls.append((self.name, "end"))
                if self.fail:
                    raise RuntimeError("first end failed")

            def finish(self):
                calls.append((self.name, "finish"))

        group = ObserverGroup([Observer("methods", True), Observer("network")])
        group.start("device", "com.example.app")
        group.begin_step(3, "tap_label")
        with self.assertRaisesRegex(RuntimeError, "first end failed"):
            group.end_step()
        group.finish()
        self.assertIn(("network", "end"), calls)
        self.assertIn(("network", "finish"), calls)

    def test_network_capture_preserves_child_and_status_in_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.json"
            script.write_text(json.dumps({"bundle_id": "com.example.app",
                                          "schema_version": 1}))

            def play(_udid, _backend, _script, target, **kwargs):
                self.assertIsNotNone(kwargs["trace_observer"])
                target.mkdir()
                (target / "playbook.json").write_bytes(script.read_bytes())
                path = target / "manifest.json"
                path.write_text(json.dumps({"status": "complete",
                                            "finished_at": "2026-10-15T12:00:00+00:00"}))
                network = target.parent / "network"
                network.mkdir()
                (network / "hook.js").write_text("hook")
                (network / "network.json").write_text("{}")
                (network / "manifest.json").write_text("{}")
                return path, True

            def view(_udid, _bundle, target, **_kwargs):
                target.mkdir()
                path = target / "manifest.json"
                path.write_text(json.dumps({"status": "complete", "node_count": 1,
                                            "window_count": 1,
                                            "started_at": "2026-10-15T12:00:01+00:00"}))
                return path, True

            with patch("copyapp.flow_capture.run_playbook", side_effect=play), \
                 patch("copyapp.flow_capture.capture_view_tree", side_effect=view), \
                 patch("copyapp.flow_capture.verify_case", return_value=True), \
                 patch("copyapp.flow_capture.validate_flow_pair"), \
                 patch("copyapp.flow_capture.validate_network_trace_files",
                       return_value={"events": [{}]}) as validate:
                path, complete = capture_flow("device", "ios-mcp", script,
                                              root / "flow", network=True)
            self.assertTrue(complete)
            parent = json.loads(path.read_text())
            self.assertEqual(parent["network_status"], "complete")
            self.assertEqual(parent["network_event_count"], 1)
            self.assertIn("network/network.json",
                          {item["path"] for item in parent["evidence"]})
            validate.assert_called_once()

    def test_trace_counts_follow_action_steps_and_reject_wrong_static_binary(self):
        play = {"steps": [{"index": 1, "action": "observe"},
                          {"index": 2, "action": "tap"},
                          {"index": 3, "action": "swipe"}]}
        with tempfile.TemporaryDirectory() as directory, patch("copyapp.flow_trace.time.sleep"):
            recorder = FlowTrace(Path(directory) / "trace", ["Demo::pressed:"])
            recorder.record.update({"bundle_id": "com.example.app",
                                    "device_id_sha256_prefix": "device", "attached_at": "now",
                                    "methods": [{"class": "Demo", "selector": "pressed:",
                                                 "status": "hooked"}]})
            for index, action in ((2, "tap"), (3, "swipe")):
                recorder.begin_step(index, action)
                recorder._on_message({"payload": {"type": "method_hit", "index": 0}}, None)
                recorder._on_message({"payload": {"type": "static_hit", "index": 0}}, None)
                recorder.end_step()
            recorder.finish()
            trace = json.loads((recorder.output / "trace.json").read_text())
            self.assertEqual([step["call_counts"] for step in trace["steps"]], [[1], [1]])
            validate_flow_trace_pair(play, trace, "com.example.app", "device")
            trace["steps"][1]["index"] = 4
            with self.assertRaisesRegex(ValueError, "action steps"):
                validate_flow_trace_pair(play, trace, "com.example.app", "device")
            trace["steps"][1]["index"] = 3
            trace["static_binary_sha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "another binary"):
                validate_flow_trace_pair(play, trace, "com.example.app", "device", {"a" * 64})

    def test_selected_raw_argument_is_bound_to_same_tap_and_both_hooks(self):
        play = {"steps": [{"index": 1, "action": "tap_label"}]}
        with tempfile.TemporaryDirectory() as directory, patch("copyapp.flow_trace.time.sleep"):
            recorder = FlowTrace(Path(directory) / "trace", ["Demo::buttonPressed:"],
                                 arg2_u32_methods=["Demo::buttonPressed:"])
            recorder.record.update({"bundle_id": "com.example.app",
                                    "device_id_sha256_prefix": "device", "attached_at": "now",
                                    "methods": [{"class": "Demo", "selector": "buttonPressed:",
                                                 "status": "hooked"}]})
            recorder.begin_step(1, "tap_label")
            recorder._on_message({"payload": {"type": "method_hit", "index": 0,
                                              "arg2_u32": 18}}, None)
            recorder._on_message({"payload": {"type": "static_hit", "index": 0,
                                              "arg2_u32": 18}}, None)
            recorder.end_step()
            recorder.finish()
            trace = json.loads((recorder.output / "trace.json").read_text())
            self.assertEqual([hit["value"] for hit in trace["steps"][0]["arg2_u32_hits"]],
                             [18, 18])
            validate_flow_trace_pair(play, trace, "com.example.app", "device")
            trace["steps"][0]["arg2_u32_hits"].pop()
            with self.assertRaisesRegex(ValueError, "raw argument count"):
                validate_flow_trace_pair(play, trace, "com.example.app", "device")

    def test_branch_hit_counts_are_bound_to_selected_step(self):
        play = {"steps": [{"index": 1, "action": "tap"}]}
        with tempfile.TemporaryDirectory() as directory, patch("copyapp.flow_trace.time.sleep"):
            recorder = FlowTrace(Path(directory) / "trace", ["Demo::pressed:"])
            recorder.branch_offsets = [0xeb5c]
            recorder.branch_counts = [0]
            recorder.record.update({"bundle_id": "com.example.app",
                "device_id_sha256_prefix": "device", "attached_at": "now",
                "methods": [{"class": "Demo", "selector": "pressed:", "status": "hooked"}],
                "branch_requested_offsets": ["0xeb5c"],
                "static_entries": [{"module_path": "/App.app/App"}],
                "branch_entries": [{"index": 0, "module_offset": "0xeb5c",
                                    "module_path": "/App.app/App"}]})
            recorder.begin_step(1, "tap")
            recorder._on_message({"payload": {"type": "branch_hit", "index": 0}}, None)
            recorder.end_step()
            recorder.finish()
            trace = json.loads((recorder.output / "trace.json").read_text())
            self.assertEqual(trace["steps"][0]["branch_call_counts"], [1])
            validate_flow_trace_pair(play, trace, "com.example.app", "device")
            trace["steps"][0]["branch_call_counts"] = [2]
            with self.assertRaisesRegex(ValueError, "branch step counts"):
                validate_flow_trace_pair(play, trace, "com.example.app", "device")

    def test_branch_return_is_bound_to_selected_offset_and_tap(self):
        play = {"steps": [{"index": 1, "action": "tap"}]}
        with tempfile.TemporaryDirectory() as directory, patch("copyapp.flow_trace.time.sleep"):
            recorder = FlowTrace(Path(directory) / "trace", ["Demo::pressed:"])
            recorder.branch_offsets = [0x200, 0x300]
            recorder.branch_return_u32_offsets = [0x300]
            recorder.branch_counts = [0, 0]
            recorder.record.update({"bundle_id": "com.example.app",
                "device_id_sha256_prefix": "device", "attached_at": "now",
                "methods": [{"class": "Demo", "selector": "pressed:", "status": "hooked"}],
                "branch_requested_offsets": ["0x200", "0x300"],
                "branch_return_u32_offsets": ["0x300"],
                "static_entries": [{"module_path": "/Demo.app/Demo"}],
                "branch_entries": [
                    {"index": 0, "module_offset": "0x200", "module_path": "/Demo.app/Demo"},
                    {"index": 1, "module_offset": "0x300", "module_path": "/Demo.app/Demo"}]})
            recorder.begin_step(1, "tap")
            recorder._on_message({"payload": {"type": "branch_hit", "index": 1}}, None)
            recorder._on_message({"payload": {"type": "branch_return_u32",
                                              "index": 1, "value": 0}}, None)
            recorder.end_step()
            recorder.finish()
            trace = json.loads((recorder.output / "trace.json").read_text())
            self.assertEqual(trace["steps"][0]["branch_return_u32_hits"],
                             [{"index": 1, "value": 0}])
            validate_flow_trace_pair(play, trace, "com.example.app", "device")
            trace["steps"][0]["branch_return_u32_hits"][0]["index"] = 0
            with self.assertRaisesRegex(ValueError, "raw branch returns"):
                validate_flow_trace_pair(play, trace, "com.example.app", "device")

    def test_branch_register_records_only_selected_app_pointer_offsets(self):
        play = {"steps": [{"index": 1, "action": "tap"}]}
        with tempfile.TemporaryDirectory() as directory, patch("copyapp.flow_trace.time.sleep"):
            recorder = FlowTrace(Path(directory) / "trace", ["Demo::pressed:"])
            recorder.branch_offsets = [0x400]
            recorder.branch_registers = [(0x400, "x19")]
            recorder.branch_counts = [0]
            recorder.record.update({"bundle_id": "com.example.app",
                "device_id_sha256_prefix": "device", "attached_at": "now",
                "methods": [{"class": "Demo", "selector": "pressed:", "status": "hooked"}],
                "static_entries": [{"module_path": "/Demo.app/Demo"}],
                "branch_requested_offsets": ["0x400"],
                "branch_registers": [{"offset": "0x400", "register": "x19"}],
                "branch_entries": [{"index": 0, "module_offset": "0x400",
                                    "module_path": "/Demo.app/Demo"}]})
            recorder.begin_step(1, "tap")
            recorder._on_message({"payload": {"type": "branch_hit", "index": 0}}, None)
            recorder._on_message({"payload": {"type": "branch_register", "index": 0,
                                              "register": "x19", "status": "app_image",
                                              "target_offset": "0x2ff218"}}, None)
            recorder.end_step()
            recorder.finish()
            trace = json.loads((recorder.output / "trace.json").read_text())
            self.assertEqual(trace["steps"][0]["branch_register_hits"],
                             [{"index": 0, "register": "x19", "status": "app_image",
                               "target_offset": "0x2ff218"}])
            validate_flow_trace_pair(play, trace, "com.example.app", "device")
            trace["steps"][0]["branch_register_hits"][0]["register"] = "x20"
            with self.assertRaisesRegex(ValueError, "register pointer bindings"):
                validate_flow_trace_pair(play, trace, "com.example.app", "device")

    def test_pair_requires_same_identity_and_prompt_no_launch_scan(self):
        play = {"status": "complete", "bundle_id": "com.example.app",
                "device_id_sha256_prefix": "device", "ui_backend": "ios-mcp",
                "finished_at": "2026-10-15T12:00:00+00:00"}
        views = {"status": "complete", "bundle_id": "com.example.app",
                 "device_id_sha256_prefix": "device", "ui_backend": "ios-mcp",
                 "launch_requested": False, "frontmost_before": "com.example.app",
                 "frontmost_after": "com.example.app",
                 "started_at": "2026-10-15T12:00:08+00:00"}
        validate_flow_pair(play, views, "com.example.app", "device", "ios-mcp")
        views["started_at"] = "2026-10-15T12:02:00+00:00"
        with self.assertRaisesRegex(ValueError, "within 60 seconds"):
            validate_flow_pair(play, views, "com.example.app", "device", "ios-mcp")
        views["started_at"] = "2026-10-15T12:00:08+00:00"
        views["launch_requested"] = True
        with self.assertRaisesRegex(ValueError, "identity"):
            validate_flow_pair(play, views, "com.example.app", "device", "ios-mcp")

    def test_failed_playbook_is_retained_and_view_scan_is_not_attempted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.json"
            script.write_text(json.dumps({"bundle_id": "com.example.app",
                                          "scenario_id": "tap", "schema_version": 1}))
            output = root / "flow"

            def failed_playbook(_udid, _backend, _script, target, **_kwargs):
                target.mkdir()
                (target / "playbook.json").write_text(script.read_text())
                manifest = target / "manifest.json"
                manifest.write_text(json.dumps({"status": "failed",
                                                "error": {"message": "target left foreground"},
                                                "evidence": []}))
                return manifest, False

            with patch("copyapp.flow_capture.run_playbook", side_effect=failed_playbook), \
                    patch("copyapp.flow_capture.capture_view_tree") as scan:
                manifest, complete = capture_flow("device", "ios-mcp", script, output)
            self.assertFalse(complete)
            scan.assert_not_called()
            record = json.loads(manifest.read_text())
            self.assertEqual(record["error"]["stage"], "playbook")
            self.assertTrue((output / "playbook/manifest.json").is_file())
            self.assertTrue(verify_case(output))

    def test_ictrl_keeps_one_tunnel_for_playbook_and_view_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "script.json"
            script.write_text(json.dumps({"bundle_id": "com.example.app",
                                          "scenario_id": "tap", "schema_version": 1}))

            def play(_udid, _backend, _script, target, **_kwargs):
                target.mkdir()
                (target / "playbook.json").write_bytes(script.read_bytes())
                path = target / "manifest.json"
                path.write_text(json.dumps({"status": "complete",
                                            "finished_at": "2026-10-15T12:00:00+00:00"}))
                return path, True

            def view(_udid, _bundle, target, **_kwargs):
                target.mkdir()
                path = target / "manifest.json"
                path.write_text(json.dumps({"status": "complete", "node_count": 1,
                                            "window_count": 1,
                                            "started_at": "2026-10-15T12:00:01+00:00"}))
                return path, True

            with patch("copyapp.flow_capture.ictrl_tunnel", return_value=nullcontext(22224)) as tunnel, \
                 patch("copyapp.flow_capture.run_playbook", side_effect=play) as replay, \
                 patch("copyapp.flow_capture.capture_view_tree", side_effect=view) as scan, \
                 patch("copyapp.flow_capture.validate_flow_pair"), \
                 patch("copyapp.flow_capture.verify_case", return_value=True):
                _, complete = capture_flow("device", "ictrl", script, root / "flow")
            self.assertTrue(complete)
            tunnel.assert_called_once()
            self.assertEqual(replay.call_args.kwargs["port"], 22224)
            self.assertEqual(scan.call_args.kwargs["port"], 22224)
            self.assertFalse(scan.call_args.kwargs["launch"])


if __name__ == "__main__":
    unittest.main()
