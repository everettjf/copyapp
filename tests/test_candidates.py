import hashlib
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.candidates import build_candidates
from copyapp.verify import verify_case


class CandidatesTest(unittest.TestCase):
    @staticmethod
    def _minimal_macho():
        data = bytearray(104)
        data[:4] = b"\xcf\xfa\xed\xfe"
        struct.pack_into("<II", data, 16, 1, 72)
        struct.pack_into("<II", data, 32, 0x19, 72)
        struct.pack_into("<QQQQ", data, 56, 0x100000000, 0x1000, 0, len(data))
        return bytes(data)

    def test_exact_binary_and_completed_experiment_yield_only_observed_instance_method(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "App.app" / "App"
            binary.parent.mkdir()
            binary.write_bytes(self._minimal_macho())
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            index = root / "objc-index.json"
            index.write_text(json.dumps({"schema_version": 1, "binary_sha256": digest,
                                         "image_base": "0x100000000",
                                         "classes": [{"name": "View", "instance_methods": [
                                             {"selector": "tap:", "imp": "0x100001000"}],
                                             "class_methods": [{"selector": "shared", "imp": "0x100002000"}]}]}))
            experiment = root / "experiment"
            experiment.mkdir()
            before, after = b"before", b"after"
            (experiment / "before.jpg").write_bytes(before)
            (experiment / "after.jpg").write_bytes(after)
            udid = "00008020-1111111111111111"
            experiment_data = {
                "status": "complete", "bundle_id": "com.example.app",
                "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                "frontmost_before": "com.example.app", "frontmost_after": "com.example.app",
                "requested_methods": ["View::tap:", "View::shared"],
                "methods": [{"class": "View", "selector": "tap:", "status": "hooked", "imp": "0x1234",
                             "imp_stripped": "0x100131000", "module_base": "0x100130000",
                             "module_offset": "0x1000", "module_path": "/Applications/App.app/App"},
                            {"class": "View", "selector": "shared", "status": "hooked", "imp": "0x5678"}],
                "call_counts": [1, 1],
                "screenshot_before_sha256": hashlib.sha256(before).hexdigest(),
                "screenshot_after_sha256": hashlib.sha256(after).hexdigest(),
            }
            (experiment / "experiment.json").write_text(json.dumps(experiment_data))
            result, ok = build_candidates(udid, "com.example.app", binary, index,
                                          [experiment], root / "output")
            self.assertTrue(ok)
            summary = json.loads(result.read_text())
            self.assertEqual(summary["candidates"][0]["static_address"], "0x100001000")
            self.assertEqual(summary["candidates"][0]["observations"][0]["binding"]["status"], "offset_match")
            self.assertEqual(len(summary["candidates"]), 1)
            self.assertEqual(summary["unresolved"][0]["selector"], "shared")
            self.assertTrue(verify_case(root / "output"))

            experiment_data["methods"][0]["module_offset"] = "0x2000"
            (experiment / "experiment.json").write_text(json.dumps(experiment_data))
            mismatched, has_candidates = build_candidates(udid, "com.example.app", binary, index,
                                                          [experiment], root / "mismatch")
            self.assertFalse(has_candidates)
            rejected = json.loads(mismatched.read_text())
            self.assertEqual(rejected["unresolved"][0]["binding"]["status"], "mismatch")
            self.assertTrue(verify_case(root / "mismatch"))

            conflict_exp = root / "conflict-experiment"
            shutil.copytree(experiment, conflict_exp)
            experiment_data["methods"][0]["module_offset"] = "0x1000"
            (experiment / "experiment.json").write_text(json.dumps(experiment_data))
            conflict_path, conflict_ok = build_candidates(udid, "com.example.app", binary,
                                                          index, [experiment, conflict_exp],
                                                          root / "conflicting")
            self.assertFalse(conflict_ok)
            self.assertEqual(json.loads(conflict_path.read_text())["candidates"], [])

            # A framework can swizzle the live IMP. A separately observed app
            # entry restores the static link while retaining the mismatch.
            experiment_data["methods"][0]["module_path"] = "/System/Library/AccessibilityBundles/App.axbundle/App"
            experiment_data["methods"][0]["module_offset"] = "0x5300"
            experiment_data["methods"][0]["module_base"] = "0x100130000"
            experiment_data["methods"][0]["imp_stripped"] = "0x100135300"
            experiment_data["static_binary_sha256"] = digest
            experiment_data["static_requested_offsets"] = ["0x1000", "0x2000"]
            experiment_data["static_call_counts"] = [1, 0]
            experiment_data["static_entries"] = [
                {"index": 0, "class": "View", "selector": "tap:", "status": "hooked",
                 "address": "0x100131000", "module_base": "0x100130000",
                 "module_offset": "0x1000", "module_path": "/Applications/App.app/App"},
                {"index": 1, "class": "View", "selector": "shared", "status": "hooked",
                 "address": "0x100132000", "module_base": "0x100130000",
                 "module_offset": "0x2000", "module_path": "/Applications/App.app/App"},
            ]
            (experiment / "experiment.json").write_text(json.dumps(experiment_data))
            direct, direct_ok = build_candidates(udid, "com.example.app", binary, index,
                                                 [experiment], root / "direct")
            self.assertTrue(direct_ok)
            observation = json.loads(direct.read_text())["candidates"][0]["observations"][0]
            self.assertEqual(observation["binding"]["status"], "mismatch")
            self.assertEqual(observation["static_entry"]["status"], "direct_static_entry")
            self.assertTrue(verify_case(root / "direct"))

            experiment_data["static_entries"][0]["module_offset"] = "0x1004"
            (experiment / "experiment.json").write_text(json.dumps(experiment_data))
            with self.assertRaisesRegex(ValueError, "static entry does not match"):
                build_candidates(udid, "com.example.app", binary, index,
                                 [experiment], root / "invalid-direct")

    def test_binary_hash_mismatch_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "App"
            binary.write_bytes(b"different")
            index = root / "objc-index.json"
            index.write_text(json.dumps({"schema_version": 1, "binary_sha256": "0" * 64,
                                         "classes": []}))
            with self.assertRaises(ValueError):
                build_candidates("device", "com.example.app", binary, index,
                                 [root / "nonexistent"], root / "output")
            self.assertFalse((root / "output").exists())

    def test_traced_flow_yields_step_attributed_static_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "App.app" / "App"
            binary.parent.mkdir()
            binary.write_bytes(self._minimal_macho())
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            index = root / "objc-index.json"
            index.write_text(json.dumps({"schema_version": 1, "binary_sha256": digest,
                "image_base": "0x100000000", "classes": [{"name": "View",
                "instance_methods": [{"selector": "tap:", "imp": "0x100001000"}]}]}))
            flow = root / "flow"
            (flow / "playbook").mkdir(parents=True)
            (flow / "view-tree").mkdir()
            (flow / "trace").mkdir()
            (flow / "manifest.json").write_text("{}")
            (flow / "trace/trace.json").write_text("{}")
            udid = "device"
            trace = {"methods": [{"class": "View", "selector": "tap:",
                                   "status": "hooked", "imp": "0xdead",
                                   "imp_stripped": "0x100135300", "module_base": "0x100130000",
                                   "module_offset": "0x5300",
                                   "module_path": "/System/Library/AccessibilityBundles/App.axbundle/App"}],
                     "static_binary_sha256": digest,
                     "static_requested_offsets": ["0x1000"],
                     "static_entries": [{"index": 0, "class": "View", "selector": "tap:",
                                         "status": "hooked", "address": "0x100131000",
                                         "module_base": "0x100130000", "module_offset": "0x1000",
                                         "module_path": "/Applications/App.app/App"}],
                     "steps": [{"index": 2, "action": "tap", "call_counts": [1],
                                "static_call_counts": [1]},
                               {"index": 3, "action": "tap_label", "call_counts": [1],
                                "static_call_counts": [1]}]}
            validated = {"trace": trace,
                         "files": ["manifest.json", "trace/trace.json"]}
            with patch("copyapp.candidates._validate_flow_capture", return_value=validated) as check:
                path, ok = build_candidates(udid, "com.example.app", binary, index,
                                            [flow], root / "output")
            check.assert_called_once_with(flow, "com.example.app",
                                          hashlib.sha256(udid.encode()).hexdigest()[:16],
                                          {digest})
            self.assertTrue(ok)
            result = json.loads(path.read_text())
            self.assertEqual(result["experiment_count"], 1)
            self.assertEqual(result["observation_count"], 2)
            observations = result["candidates"][0]["observations"]
            self.assertEqual([item["step_index"] for item in observations], [2, 3])
            self.assertTrue(all(item["static_entry"]["calls"] == 1 for item in observations))
            self.assertEqual(observations[0]["binding"]["status"], "mismatch")
            self.assertTrue(verify_case(root / "output"))


if __name__ == "__main__":
    unittest.main()
