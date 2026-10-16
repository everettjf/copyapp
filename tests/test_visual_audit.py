import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.verify import sha256_file, verify_case
from copyapp.visual_audit import create_visual_audit


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class VisualAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.check = self.root / "check"
        comparison = self.check / "flows/example/comparison"
        self.original = comparison / "original/step-03-screenshot.jpg"
        self.rebuilt = comparison / "rebuilt/step-03-screenshot.jpg"
        for path in (self.original, self.rebuilt):
            path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (10, 10), "black").save(self.original)
        image = Image.new("RGB", (10, 10), "black")
        image.putpixel((5, 5), (255, 255, 255))
        image.save(self.rebuilt)
        write(comparison / "report-index.json", {
            "screenshots": [{"step": 3, "visual": {"width": 10, "height": 10}}],
            "artifacts": {
                "original/step-03-screenshot.jpg": {"sha256": sha256_file(self.original)},
                "rebuilt/step-03-screenshot.jpg": {"sha256": sha256_file(self.rebuilt)}}})
        write(self.check / "manifest.json", {
            "kind": "rebuild_check", "status": "complete",
            "device_id_sha256_prefix": "0123456789abcdef",
            "flows": [{"flow_id": "example", "screenshot_pairs": 1,
                       "comparison_index": "flows/example/comparison/report-index.json"}]})

    def test_metrics_recomputed_and_source_tamper_rejected(self):
        audit = self.root / "audit"
        with patch("copyapp.visual_audit.verify_case", return_value=True):
            create_visual_audit(self.check, audit, [0, 0, 10, 10], 0.05, 0.05)
            self.assertTrue(verify_case(audit))
            result = json.loads((audit / "audit.json").read_text())
            self.assertEqual(result["status"], "metric_within_threshold")
            self.assertEqual(len(result["pairs"]), 1)
            Image.new("RGB", (10, 10), "white").save(self.rebuilt)
            self.assertFalse(verify_case(audit))

    def test_rejects_tiny_region(self):
        with patch("copyapp.visual_audit.verify_case", return_value=True), \
                self.assertRaisesRegex(ValueError, "at least half"):
            create_visual_audit(self.check, self.root / "audit", [0, 0, 3, 3],
                                0.05, 0.05)


if __name__ == "__main__":
    unittest.main()
