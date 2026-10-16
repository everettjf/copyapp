import hashlib
import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.compare_playbooks import _load_run
from copyapp.playbook import run_playbook
from copyapp.verify import sha256_file


@contextmanager
def fake_tunnel(_udid):
    yield 22222


class FakeUI:
    def __init__(self, *_args, **_kwargs):
        pass

    def bounds(self):
        return 414, 896

    def frontmost(self):
        return "com.apple.mobiletimer"

    def observe(self):
        return {"elements": [{"text": "Stop"}]}


class PlaybookVisualLabelsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        image = Image.new("RGB", (414, 896), "black")
        stream = io.BytesIO()
        image.save(stream, format="JPEG")
        self.image = stream.getvalue()
        self.script = self.root / "script.json"
        self.script.write_text(json.dumps({
            "schema_version": 1, "scenario_id": "stopwatch-state",
            "bundle_id": "com.apple.mobiletimer",
            "steps": [{"action": "screenshot", "stable": True,
                       "ready_contains": "Stop", "ready_ocr_labels": ["Stop"]}],
        }))

    def run_with_painted_labels(self, painted, name):
        def fake_ocr(source, output):
            data = source.read_bytes()
            output.write_text(json.dumps({
                "schema_version": 1, "kind": "saved_screenshot_ocr",
                "source_path": str(source.resolve()),
                "source_sha256": sha256_file(source),
                "source_width": 414, "source_height": 896,
                "roi": None, "ocr_input_sha256": hashlib.sha256(data).hexdigest(),
                "result": {"engine": "macos-vision",
                           "texts": [{"text": label} for label in painted]},
            }))
            return output

        with patch("copyapp.playbook.ExperimentUI", FakeUI), \
             patch("copyapp.playbook.ios_mcp_tunnel", fake_tunnel), \
             patch("copyapp.playbook.capture_stable", return_value=(
                 self.image, {"stable": True, "samples": 5})), \
             patch("copyapp.playbook.ocr_file", fake_ocr), \
             patch("copyapp.playbook.time.sleep"):
            path, complete = run_playbook("device", "ios-mcp", self.script,
                                          self.root / name)
        return path, complete

    def test_invalid_visual_labels_rejected_before_device_access(self):
        plan = json.loads(self.script.read_text())
        plan["steps"][0]["ready_ocr_labels"] = "Stop"
        self.script.write_text(json.dumps(plan))
        with patch("copyapp.playbook.ios_mcp_tunnel") as tunnel:
            with self.assertRaisesRegex(ValueError, "invalid ready_ocr_labels"):
                run_playbook("device", "ios-mcp", self.script, self.root / "invalid")
        tunnel.assert_not_called()
        self.assertFalse((self.root / "invalid").exists())

    def test_accessibility_stop_does_not_hide_missing_painted_stop(self):
        path, complete = self.run_with_painted_labels(["Stopwatch"], "missing")
        record = json.loads(path.read_text())
        self.assertFalse(complete)
        self.assertEqual(record["steps"][0]["ready_found"], True)
        self.assertEqual(record["steps"][0]["missing_ready_ocr_labels"], ["Stop"])
        self.assertIn("screenshot lacks visible labels", record["error"]["message"])

    def test_saved_visual_evidence_is_rechecked(self):
        path, complete = self.run_with_painted_labels(["Stop"], "matched")
        self.assertTrue(complete)
        run = path.parent
        _load_run(run)
        ocr_path = run / "step-01-visual-ocr.json"
        value = json.loads(ocr_path.read_text())
        value["result"]["texts"] = [{"text": "Stopwatch"}]
        ocr_path.write_text(json.dumps(value))
        manifest = json.loads(path.read_text())
        manifest["steps"][0]["ready_ocr_labels_sha256"] = sha256_file(ocr_path)
        manifest["evidence"][-1]["sha256"] = sha256_file(ocr_path)
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "visual labels do not match image OCR"):
            _load_run(run)


if __name__ == "__main__":
    unittest.main()
