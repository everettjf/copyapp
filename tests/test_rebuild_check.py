import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.rebuild_check import _final_view_check, _identity, _preflight, check_final_view, rebuild_check
from copyapp.verify import sha256_file, verify_case


class RebuildCheckTest(unittest.TestCase):
    def test_system_app_identity_allows_absent_marketing_version(self):
        identity = _identity({"CFBundleVersion": "1.0", "Path": "/Applications/Clock.app"},
                             "com.apple.mobiletimer")
        self.assertEqual(identity["version"], None)
        self.assertEqual(identity["build"], "1.0")
        with self.assertRaisesRegex(ValueError, "identity is incomplete"):
            _identity({"Path": "/Applications/Clock.app"}, "com.apple.mobiletimer")

    def test_final_view_accepts_visible_table_cell_label(self):
        with tempfile.TemporaryDirectory() as temp:
            flow = Path(temp)
            (flow / "view-tree").mkdir()
            (flow / "manifest.json").write_text("{}")
            (flow / "view-tree/view-tree.json").write_text(json.dumps({"nodes": [
                {"id": 0, "parent": None, "class_name": "UIWindow",
                 "frame": {"x": 0, "y": 0, "width": 414, "height": 896},
                 "hidden": False, "alpha": 1},
                {"id": 1, "parent": 0, "class_name": "UITableViewLabel",
                 "text": "When Timer Ends",
                 "frame": {"x": 20, "y": 532, "width": 250, "height": 52},
                 "hidden": False, "alpha": 1}
            ]}))
            result = check_final_view(flow, {"text": "When Timer Ends",
                "region_points": [0, 0, 414, 896]})
            self.assertTrue(result["passed"])
            self.assertEqual(result["matches"][0]["class_name"], "UITableViewLabel")

    def test_final_view_accepts_clock_time_view_only_in_selected_region(self):
        with tempfile.TemporaryDirectory() as temp:
            flow = Path(temp)
            (flow / "view-tree").mkdir()
            (flow / "manifest.json").write_text("{}")
            (flow / "view-tree/view-tree.json").write_text(json.dumps({"nodes": [
                {"id": 0, "parent": None, "class_name": "UIWindow",
                 "frame": {"x": 0, "y": 0, "width": 414, "height": 896}},
                {"id": 1, "parent": 0, "class_name": "MTUITimeView", "text": "00:00.00",
                 "frame": {"x": 0, "y": 200, "width": 414, "height": 106}},
                {"id": 2, "parent": 0, "class_name": "MTUITimeView", "text": "00:00.00",
                 "frame": {"x": 550, "y": 313, "width": 136, "height": 30}},
            ]}))
            result = check_final_view(flow, {"text": "00:00.00",
                "region_points": [0, 190, 414, 325]})
            self.assertTrue(result["passed"])
            self.assertEqual([item["node_id"] for item in result["matches"]], [1])

    def test_screenshot_ocr_final_view_checks_region_and_saved_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            flow = Path(temp)
            play = flow / "playbook"
            play.mkdir()
            (flow / "manifest.json").write_text("{}")
            screenshot = play / "step-02-screenshot.jpg"
            screenshot.write_bytes(b"saved screenshot")
            manifest = {"status": "complete", "screen": {"width": 414, "height": 896},
                "steps": [{"action": "screenshot",
                "evidence_path": screenshot.name, "sha256": sha256_file(screenshot)}]}
            (play / "manifest.json").write_text(json.dumps(manifest))
            assertion = {"source": "screenshot_ocr", "text": "15",
                         "region_points": [0, 200, 414, 380]}
            observed = {"image": {"width": 828, "height": 1792},
                        "texts": [{"text": "15", "confidence": 0.9,
                          "rect": {"x": 640, "y": 560, "width": 140, "height": 100}}]}
            with patch("copyapp.rebuild_check.recognize_screenshot", return_value=observed):
                self.assertTrue(check_final_view(flow, assertion)["passed"])
                outside = dict(assertion, region_points=[0, 0, 414, 200])
                self.assertFalse(check_final_view(flow, outside)["passed"])
                screenshot.write_bytes(b"changed screenshot")
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    check_final_view(flow, assertion)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.udid = "test-device"
        self.original = "com.example.original"
        self.rebuilt = "dev.example.rebuilt"
        self.spec = self.root / "feature-spec.json"
        self.spec.write_text(json.dumps({"schema_version": 1,
            "target_bundle_id": self.original, "rebuilt_bundle_id": self.rebuilt,
            "flows": [{"id": "add"}]}))
        self.scripts = []
        for bundle, name in ((self.original, "original"), (self.rebuilt, "rebuilt")):
            path = self.root / f"{name}.json"
            path.write_text(json.dumps({"schema_version": 1,
                "scenario_id": "addition", "bundle_id": bundle,
                "fresh_launch": True,
                "steps": [{"action": "screenshot", "stable": True,
                           "ready_contains": "ready"},
                          {"action": "tap_label", "label": "add"},
                          {"action": "screenshot", "stable": True,
                           "ready_contains": "result"}]}))
            self.scripts.append(path)

    def _run(self, udid, backend, script, output):
        plan = json.loads(script.read_text())
        output.mkdir(parents=True)
        (output / "playbook.json").write_bytes(script.read_bytes())
        bundle = plan["bundle_id"]
        evidence = [{"path": "playbook.json",
                     "sha256": sha256_file(output / "playbook.json")}]
        steps = []
        for index, requested in enumerate(plan["steps"], 1):
            item = {"index": index, "action": requested["action"],
                    "frontmost": bundle, "duration_ms": 5}
            if requested["action"] == "screenshot":
                image = output / f"step-{index:02d}-screenshot.jpg"
                Image.new("RGB", (20, 30), "#303030").save(image)
                digest = sha256_file(image)
                item.update({"evidence_path": image.name, "sha256": digest,
                             "stability": {"stable": True},
                             "ready_contains": requested["ready_contains"],
                             "ready_found": True})
                evidence.append({"path": image.name, "sha256": digest})
            steps.append(item)
        record = {"schema_version": 1, "status": "complete", "bundle_id": bundle,
                  "scenario_id": plan["scenario_id"], "ui_backend": backend,
                  "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                  "screen": {"width": 20, "height": 30, "coordinate_space": "points"},
                  "steps": steps, "evidence": evidence}
        manifest = output / "manifest.json"
        manifest.write_text(json.dumps(record))
        return manifest, True

    def test_rejects_different_gesture_before_device_access(self):
        clone = json.loads(self.scripts[1].read_text())
        clone["steps"][1]["label"] = "subtract"
        self.scripts[1].write_text(json.dumps(clone))
        with patch("copyapp.rebuild_check._installed_app") as device:
            with self.assertRaisesRegex(ValueError, "tap labels differ"):
                rebuild_check(self.udid, self.spec,
                              [("add", *self.scripts)], self.root / "out")
        device.assert_not_called()

    def test_rejects_different_swipe_before_device_access(self):
        for path, end_x in zip(self.scripts, (100, 120)):
            plan = json.loads(path.read_text())
            plan["steps"][1] = {"action": "swipe", "from_x": 300,
                                 "from_y": 280, "to_x": end_x, "to_y": 280}
            path.write_text(json.dumps(plan))
        with patch("copyapp.rebuild_check._installed_app") as device:
            with self.assertRaisesRegex(ValueError, "gesture parameters differ"):
                rebuild_check(self.udid, self.spec,
                              [("add", *self.scripts)], self.root / "out")
        device.assert_not_called()

    def test_rejects_different_exact_observation_labels_before_device_access(self):
        for path, label in zip(self.scripts, ("Stop", "Start")):
            plan = json.loads(path.read_text())
            plan["steps"].insert(1, {"action": "observe", "exact_labels": [label]})
            path.write_text(json.dumps(plan))
        with patch("copyapp.rebuild_check._installed_app") as device:
            with self.assertRaisesRegex(ValueError, "exact observation labels differ"):
                rebuild_check(self.udid, self.spec,
                              [("add", *self.scripts)], self.root / "out")
        device.assert_not_called()

    def test_rejects_different_screenshot_visual_labels_before_device_access(self):
        for path, label in zip(self.scripts, ("Stop", "Start")):
            plan = json.loads(path.read_text())
            next(step for step in plan["steps"] if step["action"] == "screenshot")[
                "ready_ocr_labels"] = [label]
            path.write_text(json.dumps(plan))
        with patch("copyapp.rebuild_check._installed_app") as device:
            with self.assertRaisesRegex(ValueError, "screenshot visual labels differ"):
                rebuild_check(self.udid, self.spec,
                              [("add", *self.scripts)], self.root / "out")
        device.assert_not_called()

    def test_rejects_different_label_region_before_device_access(self):
        original = json.loads(self.scripts[0].read_text())
        clone = json.loads(self.scripts[1].read_text())
        original["steps"][1]["region_points"] = [0, 10, 20, 30]
        clone["steps"][1]["region_points"] = [0, 0, 20, 10]
        self.scripts[0].write_text(json.dumps(original))
        self.scripts[1].write_text(json.dumps(clone))
        with patch("copyapp.rebuild_check._installed_app") as device:
            with self.assertRaisesRegex(ValueError, "tap label regions differ"):
                rebuild_check(self.udid, self.spec,
                              [("add", *self.scripts)], self.root / "out")
        device.assert_not_called()

    def test_rejects_provisional_feature_spec_before_device_access(self):
        spec = json.loads(self.spec.read_text())
        spec["review_status"] = "needs_semantic_review"
        self.spec.write_text(json.dumps(spec))
        with patch("copyapp.rebuild_check._installed_app") as device:
            with self.assertRaisesRegex(ValueError, "invalid rebuild feature spec"):
                rebuild_check(self.udid, self.spec,
                              [("add", *self.scripts)], self.root / "out")
        device.assert_not_called()
        spec.pop("review_status")
        spec["flows"][0]["review_status"] = "needs_semantic_review"
        self.spec.write_text(json.dumps(spec))
        with patch("copyapp.rebuild_check._installed_app") as device:
            with self.assertRaisesRegex(ValueError, "invalid rebuild feature spec"):
                rebuild_check(self.udid, self.spec,
                              [("add", *self.scripts)], self.root / "out")
        device.assert_not_called()

    def test_runs_and_binds_pair_to_installed_versions(self):
        async def installed(udid, bundle):
            return {"CFBundleShortVersionString": "1.0", "CFBundleVersion": "7",
                    "Path": f"/Applications/{bundle}.app"}

        with patch("copyapp.rebuild_check._installed_app", side_effect=installed), \
             patch("copyapp.rebuild_check.run_playbook", side_effect=self._run) as worker:
            manifest, complete = rebuild_check(self.udid, self.spec,
                                               [("add", *self.scripts)], self.root / "out")
        self.assertTrue(complete)
        self.assertEqual(worker.call_count, 2)
        record = json.loads(manifest.read_text())
        self.assertEqual(record["installed_apps"][1]["build"], "7")
        self.assertEqual(record["flows"][0]["screenshot_pairs"], 2)
        self.assertTrue(verify_case(self.root / "out"))

    def test_resume_keeps_verified_original_without_new_touch(self):
        async def installed(udid, bundle):
            return {"CFBundleShortVersionString": "1.0", "CFBundleVersion": "7",
                    "Path": f"/Applications/{bundle}.app"}

        calls = []

        def first(udid, backend, script, output):
            calls.append(script)
            if script == self.scripts[1].resolve():
                output.mkdir(parents=True)
                (output / "playbook.json").write_bytes(script.read_bytes())
                (output / "manifest.json").write_text(json.dumps({"status": "failed"}))
                return output / "manifest.json", False
            return self._run(udid, backend, script, output)

        with patch("copyapp.rebuild_check._installed_app", side_effect=installed), \
             patch("copyapp.rebuild_check.run_playbook", side_effect=first):
            _, complete = rebuild_check(self.udid, self.spec,
                                        [("add", *self.scripts)], self.root / "out")
        self.assertFalse(complete)
        self.assertEqual(calls, [script.resolve() for script in self.scripts])
        self.assertTrue(verify_case(self.root / "out"))
        with patch("copyapp.rebuild_check._installed_app", side_effect=installed), \
             patch("copyapp.rebuild_check.run_playbook", side_effect=self._run) as worker:
            _, complete = rebuild_check(self.udid, self.spec,
                                        [("add", *self.scripts)], self.root / "out",
                                        resume=True)
        self.assertTrue(complete)
        worker.assert_called_once()
        self.assertEqual(worker.call_args.args[2], self.scripts[1].resolve())
        self.assertTrue(verify_case(self.root / "out"))

    def test_final_text_requires_one_visible_label_in_display_region(self):
        case = self.root / "flow"
        (case / "view-tree").mkdir(parents=True)
        (case / "manifest.json").write_text("{}")
        nodes = [
            {"id": 0, "parent": None, "class_name": "UIView", "hidden": False,
             "alpha": 1, "frame": {"x": 0, "y": 0, "width": 414, "height": 896}},
            {"id": 1, "parent": 0, "class_name": "UILabel", "text": "9",
             "hidden": False, "alpha": 1,
             "frame": {"x": 320, "y": 200, "width": 60, "height": 100}},
            {"id": 2, "parent": 0, "class_name": "UIButtonLabel", "text": "9",
             "hidden": False, "alpha": 1,
             "frame": {"x": 250, "y": 450, "width": 20, "height": 30}},
            {"id": 3, "parent": 0, "class_name": "UIButtonLabel", "text": "AC",
             "hidden": False, "alpha": 1,
             "frame": {"x": 35, "y": 360, "width": 45, "height": 30}},
        ]
        tree = case / "view-tree/view-tree.json"
        tree.write_text(json.dumps({"nodes": nodes}))
        assertion = {"text": "9", "region_points": [0, 150, 414, 341]}
        check = _final_view_check(case, assertion, self.root / "state.json")
        self.assertTrue(check["passed"])
        self.assertEqual([item["node_id"] for item in check["matches"]], [1])
        assertion["also"] = [{"text": "AC", "region_points": [0, 341, 110, 430]}]
        check = _final_view_check(case, assertion, self.root / "state-also.json")
        self.assertTrue(check["passed"])
        self.assertEqual(check["also_checks"][0]["matches"][0]["node_id"], 3)
        nodes[3]["text"] = "C"
        tree.write_text(json.dumps({"nodes": nodes}))
        self.assertFalse(_final_view_check(case, assertion,
                                            self.root / "state-wrong-control.json")["passed"])
        nodes[1]["hidden"] = True
        tree.write_text(json.dumps({"nodes": nodes}))
        self.assertFalse(_final_view_check(case, assertion,
                                            self.root / "state-hidden.json")["passed"])

    def test_final_view_can_require_dialog_label_to_be_absent(self):
        assertion = {"text": "Home", "region_points": [0, 0, 414, 896],
                     "absent": [{"text": "Cancel", "region_points": [0, 300, 414, 600]}]}
        spec = json.loads(self.spec.read_text())
        spec["flows"][0]["final_view"] = assertion
        self.spec.write_text(json.dumps(spec))
        _preflight(self.spec, [("add", *self.scripts)])

        case = self.root / "dismissed"
        (case / "view-tree").mkdir(parents=True)
        (case / "manifest.json").write_text("{}")
        nodes = [
            {"id": 0, "parent": None, "class_name": "UIView", "hidden": False,
             "alpha": 1, "frame": {"x": 0, "y": 0, "width": 414, "height": 896}},
            {"id": 1, "parent": 0, "class_name": "UILabel", "text": "Home",
             "hidden": False, "alpha": 1,
             "frame": {"x": 20, "y": 100, "width": 100, "height": 30}},
            {"id": 2, "parent": 0, "class_name": "UIButtonLabel", "text": "Cancel",
             "hidden": True, "alpha": 1,
             "frame": {"x": 50, "y": 480, "width": 100, "height": 30}},
        ]
        tree = case / "view-tree/view-tree.json"
        tree.write_text(json.dumps({"nodes": nodes}))
        result = _final_view_check(case, assertion, self.root / "dismissed.json")
        self.assertTrue(result["passed"])
        self.assertTrue(result["absent_checks"][0]["passed"])
        nodes[2]["hidden"] = False
        tree.write_text(json.dumps({"nodes": nodes}))
        self.assertFalse(_final_view_check(case, assertion,
                                            self.root / "dialog-visible.json")["passed"])

        spec["flows"][0]["final_view"]["absent"][0]["region_points"] = [10, 10, 10, 20]
        self.spec.write_text(json.dumps(spec))
        with self.assertRaisesRegex(ValueError, "invalid final view assertion"):
            _preflight(self.spec, [("add", *self.scripts)])


if __name__ == "__main__":
    unittest.main()
