import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from copyapp.playbook import _exact_labels, run_playbook


@contextmanager
def fake_tunnel(_udid):
    yield 22222


class FakeUI:
    elements = [{"text": "Stopwatch", "clickable": True}]

    def __init__(self, *_args):
        pass

    def bounds(self):
        return 414, 896

    def frontmost(self):
        return "com.apple.mobiletimer"

    def observe(self):
        return {"elements": list(self.elements), "element_count": len(self.elements)}


class PlaybookExactLabelsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "script.json"
        self.script.write_text(json.dumps({
            "schema_version": 1, "bundle_id": "com.apple.mobiletimer",
            "steps": [{"action": "observe", "contains": ["Stop"],
                       "exact_labels": ["Stop"]}],
        }))

    def run_fake(self, elements, name):
        with patch.object(FakeUI, "elements", elements), \
             patch("copyapp.playbook.ExperimentUI", FakeUI), \
             patch("copyapp.playbook.ios_mcp_tunnel", fake_tunnel), \
             patch("copyapp.playbook.time.sleep"):
            path, complete = run_playbook("device", "ios-mcp", self.script,
                                          self.root / name)
        return json.loads(path.read_text()), complete

    def test_stopwatch_does_not_satisfy_exact_stop(self):
        record, complete = self.run_fake([{"text": "Stopwatch"}], "missing")
        self.assertFalse(complete)
        self.assertEqual(record["steps"][0]["missing"], [])
        self.assertEqual(record["steps"][0]["missing_exact_labels"], ["Stop"])
        self.assertIn("missing exact accessibility labels", record["error"]["message"])

    def test_exact_stop_element_passes(self):
        record, complete = self.run_fake([{"text": "Stopwatch"}, {"text": "Stop"}], "matched")
        self.assertTrue(complete)
        self.assertEqual(record["steps"][0]["missing_exact_labels"], [])

    def test_ictrl_requires_ax_label_boundary(self):
        source = "Application, label: 'Clock'\n  Button, label: 'Stopwatch'\n"
        self.assertNotIn("Stop", _exact_labels({"source_channel": "ax", "source": source}, "ictrl"))
        source += "  Button, label: 'Stop'\n"
        self.assertIn("Stop", _exact_labels({"source_channel": "ax", "source": source}, "ictrl"))
        self.assertEqual(_exact_labels({"source_channel": "ocr", "source": source}, "ictrl"), set())


if __name__ == "__main__":
    unittest.main()
