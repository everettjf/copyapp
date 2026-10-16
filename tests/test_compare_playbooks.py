import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from copyapp.compare_playbooks import _color_match_check, _load_run, _pulse_check, compare_playbooks
from copyapp.verify import sha256_file, verify_case


class ComparePlaybooksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self._run("original", "com.example.original", (10, 20, 30))
        self.rebuilt = self._run("rebuilt", "dev.example.rebuilt", (20, 30, 40))

    def _run(self, name, bundle, color):
        root = self.root / name
        root.mkdir()
        plan = {"schema_version": 1, "scenario_id": "bearing-lock",
                "bundle_id": bundle, "steps": [
                    {"action": "screenshot", "stable": True, "ready_contains": "heading"},
                    {"action": "tap", "x": 20, "y": 30},
                    {"action": "screenshot", "stable": True, "ready_contains": "heading"}]}
        (root / "playbook.json").write_text(json.dumps(plan))
        evidence = [{"path": "playbook.json", "sha256": sha256_file(root / "playbook.json")}]
        steps = []
        for index, action in enumerate(("screenshot", "tap", "screenshot"), 1):
            item = {"index": index, "action": action, "frontmost": bundle,
                    "duration_ms": 30}
            if action == "screenshot":
                path = root / f"step-{index:02d}-screenshot.jpg"
                Image.new("RGB", (40, 60), color).save(path)
                item.update({"evidence_path": path.name, "sha256": sha256_file(path)})
                item.update({"stability": {"stable": True},
                             "ready_contains": "heading", "ready_found": True})
                evidence.append({"path": path.name, "sha256": item["sha256"]})
            steps.append(item)
        manifest = {"schema_version": 1, "scenario_id": "bearing-lock",
                    "bundle_id": bundle, "status": "complete", "ui_backend": "ios-mcp",
                    "device_id_sha256_prefix": "device01",
                    "screen": {"width": 40, "height": 60, "coordinate_space": "points"},
                    "steps": steps, "evidence": evidence}
        (root / "manifest.json").write_text(json.dumps(manifest))
        return root

    def test_creates_verifiable_visual_and_behavior_record(self):
        output = self.root / "comparison"
        report = compare_playbooks(self.original, self.rebuilt, output)
        self.assertIn("平均 RGB 绝对差", report.read_text())
        self.assertTrue((output / "comparison/step-01-side_by_side.png").is_file())
        self.assertTrue(verify_case(output))

    def test_rejects_different_device(self):
        path = self.rebuilt / "manifest.json"
        data = json.loads(path.read_text())
        data["device_id_sha256_prefix"] = "other"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "same scenario, device and backend"):
            compare_playbooks(self.original, self.rebuilt, self.root / "comparison")

    def test_rejects_tampered_screenshot(self):
        (self.rebuilt / "step-03-screenshot.jpg").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            compare_playbooks(self.original, self.rebuilt, self.root / "comparison")

    def test_rejects_completed_run_without_screenshot_readiness(self):
        path = self.rebuilt / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["steps"][2]["ready_found"] = False
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "readiness was not verified"):
            compare_playbooks(self.original, self.rebuilt, self.root / "comparison")

    def test_screenshot_ocr_readiness_is_bound_to_saved_image(self):
        root = self.original
        image = root / "step-01-screenshot.jpg"
        ocr_path = root / "step-01-ready-ocr.json"
        source_hash = sha256_file(image)
        ocr = {"schema_version": 1, "kind": "saved_screenshot_ocr",
               "source_sha256": source_hash, "source_width": 40, "source_height": 60,
               "roi": None, "ocr_input_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
               "result": {"engine": "macos-vision", "texts": [{"text": "heading"}]}}
        ocr_path.write_text(json.dumps(ocr))
        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["steps"][0].update({"ready_source": "screenshot_ocr",
                                      "ready_ocr_path": ocr_path.name,
                                      "ready_ocr_sha256": sha256_file(ocr_path)})
        manifest["evidence"].append({"path": ocr_path.name,
                                     "sha256": sha256_file(ocr_path)})
        manifest_path.write_text(json.dumps(manifest))
        _load_run(root)
        ocr["source_sha256"] = "0" * 64
        ocr_path.write_text(json.dumps(ocr))
        manifest = json.loads(manifest_path.read_text())
        manifest["steps"][0]["ready_ocr_sha256"] = sha256_file(ocr_path)
        manifest["evidence"][-1]["sha256"] = sha256_file(ocr_path)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "OCR source mismatch"):
            _load_run(root)

    def test_rejects_different_tap_coordinate(self):
        path = self.rebuilt / "playbook.json"
        plan = json.loads(path.read_text())
        plan["steps"][1]["x"] = 21
        path.write_text(json.dumps(plan))
        manifest_path = self.rebuilt / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["evidence"][0]["sha256"] = sha256_file(path)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "tap coordinates differ"):
            compare_playbooks(self.original, self.rebuilt, self.root / "comparison")

    def test_rejects_different_label_regions(self):
        for root, region in ((self.original, [0, 30, 20, 50]),
                             (self.rebuilt, [20, 30, 40, 50])):
            plan_path = root / "playbook.json"
            manifest_path = root / "manifest.json"
            plan = json.loads(plan_path.read_text())
            manifest = json.loads(manifest_path.read_text())
            plan["steps"][1] = {"action": "tap_label", "label": "0",
                                "region_points": region}
            manifest["steps"][1]["action"] = "tap_label"
            manifest["steps"][1]["result"] = {
                "match": {"x": (region[0] + region[2]) / 2,
                          "y": (region[1] + region[3]) / 2}}
            plan_path.write_text(json.dumps(plan))
            manifest["evidence"][0]["sha256"] = sha256_file(plan_path)
            manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "tap labels or regions differ"):
            compare_playbooks(self.original, self.rebuilt, self.root / "comparison")

    def test_color_pulse_requires_visible_rise_and_return(self):
        images = {}
        for step, color in ((1, (0, 0, 0)), (3, (200, 0, 0)),
                            (5, (0, 0, 0))):
            path = self.root / f"pulse-{step}.png"
            Image.new("RGB", (40, 60), color).save(path)
            images[step] = path
        check = {"id": "red-marker", "kind": "color_pulse", "channel": "red",
                 "roi": [0, 0, 20, 20], "steps": [1, 3, 5],
                 "minimum_channel": 25, "dominance_ratio": 1.5,
                 "min_rise": 15, "max_return_delta": 10}
        self.assertTrue(_pulse_check(check, images)["passed"])
        Image.new("RGB", (40, 60), (0, 0, 0)).save(images[3])
        self.assertFalse(_pulse_check(check, images)["passed"])

    def test_color_match_accepts_absent_marker_and_rejects_one_sided_marker(self):
        original = self.root / "marker-original.png"
        rebuilt = self.root / "marker-rebuilt.png"
        Image.new("RGB", (40, 60), (0, 0, 0)).save(original)
        Image.new("RGB", (40, 60), (0, 0, 0)).save(rebuilt)
        check = {"id": "red-marker", "kind": "color_match", "channel": "red",
                 "roi": [0, 0, 20, 30], "steps": [1], "minimum_channel": 25,
                 "dominance_ratio": 1.5, "max_count_delta": 10}
        self.assertTrue(_color_match_check(check, {1: original}, {1: rebuilt})["original"]["passed"])
        Image.new("RGB", (40, 60), (255, 0, 0)).save(rebuilt)
        self.assertFalse(_color_match_check(check, {1: original}, {1: rebuilt})["original"]["passed"])

    def test_accepts_verified_same_app_handoff(self):
        for root in (self.original, self.rebuilt):
            plan_path = root / "playbook.json"
            manifest_path = root / "manifest.json"
            plan = json.loads(plan_path.read_text())
            manifest = json.loads(manifest_path.read_text())
            plan["steps"].append({"action": "expect_foreground",
                                  "bundle_id": "com.apple.Maps"})
            manifest["steps"].append({"index": 4, "action": "expect_foreground",
                                      "frontmost": "com.apple.Maps",
                                      "expected_frontmost": "com.apple.Maps"})
            plan_path.write_text(json.dumps(plan))
            manifest["evidence"][0]["sha256"] = sha256_file(plan_path)
            manifest_path.write_text(json.dumps(manifest))
        report = compare_playbooks(self.original, self.rebuilt,
                                   self.root / "comparison")
        self.assertIn("com.apple.Maps", report.read_text())


if __name__ == "__main__":
    unittest.main()
