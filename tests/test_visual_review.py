import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from copyapp.verify import sha256_file, verify_case
from copyapp.visual_review import create_visual_review


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class VisualReviewTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.check = self.root / "check"
        base = self.check / "flows/example/comparison"
        paths = {
            "original/step-03-screenshot.jpg": base / "original/step-03-screenshot.jpg",
            "rebuilt/step-03-screenshot.jpg": base / "rebuilt/step-03-screenshot.jpg",
            "comparison/step-03-side_by_side.png": base / "comparison/step-03-side_by_side.png",
        }
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (10, 10), "black").save(path)
        index = base / "report-index.json"
        write(index, {"screenshots": [{"step": 3}],
                      "artifacts": {name: {"sha256": sha256_file(path)}
                                    for name, path in paths.items()}})
        write(self.check / "manifest.json", {
            "kind": "rebuild_check", "status": "complete",
            "flows": [{"flow_id": "example", "screenshot_pairs": 1,
                       "comparison_index": str(index.relative_to(self.check))}],
            "evidence": [{"path": str(path.relative_to(self.check)),
                          "sha256": sha256_file(path)}
                         for path in [index, *paths.values()]],
        })
        self.judgments = self.root / "judgments.json"
        write(self.judgments, {"pairs": [{"flow_id": "example", "step": 3,
                                          "verdict": "minor_difference",
                                          "note": "The rebuilt glyph is slightly thinner."}]})

    def test_review_binds_every_image_and_source_hash(self):
        output = self.root / "review"
        create_visual_review(self.check, self.judgments, output, "test reviewer")
        self.assertTrue(verify_case(output))
        self.assertEqual(json.loads((output / "review.json").read_text())["status"],
                         "reviewed_with_minor_differences")
        image = self.check / "flows/example/comparison/rebuilt/step-03-screenshot.jpg"
        Image.new("RGB", (10, 10), "white").save(image)
        self.assertFalse(verify_case(output))

    def test_missing_pair_is_rejected_before_output(self):
        write(self.judgments, {"pairs": []})
        output = self.root / "review"
        with self.assertRaisesRegex(ValueError, "every saved screenshot pair"):
            create_visual_review(self.check, self.judgments, output, "test reviewer")
        self.assertFalse(output.exists())

    def test_short_or_empty_note_is_rejected(self):
        write(self.judgments, {"pairs": [{"flow_id": "example", "step": 3,
                                          "verdict": "match", "note": "fine"}]})
        with self.assertRaisesRegex(ValueError, "concrete note"):
            create_visual_review(self.check, self.judgments,
                                 self.root / "review", "test reviewer")


if __name__ == "__main__":
    unittest.main()
