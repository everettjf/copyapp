import json
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from copyapp.playbook import _exact_labels, _fresh_launch, run_playbook


@contextmanager
def fake_tunnel(_udid, *_args):
    yield 22222


class FakeUI:
    elements = [{"text": "Stopwatch", "clickable": True}]

    def __init__(self, *_args, **_kwargs):
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

    def test_ictrl_fresh_launch_refreshes_frontmost_cache(self):
        class CachedUI:
            opened = []
            terminated = []

            def __init__(self, *_args, **_kwargs):
                self.app = ""
                self.client = Mock()
                self.client.call_ui.side_effect = lambda method, params: self.terminated.append((method, params))

            def bounds(self):
                return 414, 896

            def frontmost(self):
                return self.app

            def launch(self, bundle):
                self.opened.append(bundle)
                self.app = bundle

            def observe(self):
                return {"source_channel": "ax", "source": "Button, label: 'Start'"}

        self.script.write_text(json.dumps({
            "schema_version": 1, "bundle_id": "dev.copyapp.clockclone",
            "fresh_launch": True,
            "steps": [{"action": "observe", "exact_labels": ["Start"]}],
        }))
        with patch("copyapp.playbook.ExperimentUI", CachedUI), \
             patch("copyapp.playbook.ios_mcp_tunnel", fake_tunnel), \
             patch("copyapp.playbook._fresh_launch", new_callable=AsyncMock), \
             patch("copyapp.playbook.time.sleep"):
            record_path, complete = run_playbook("device", "ictrl", self.script,
                                                 self.root / "ictrl-cache", port=22224)
        record = json.loads(record_path.read_text())
        self.assertTrue(complete, record.get("error"))
        self.assertEqual(record["frontmost_backend"], "ios-mcp")
        self.assertEqual(CachedUI.opened, ["dev.copyapp.clockclone"])
        self.assertEqual(CachedUI.terminated, [
            ("terminate_app", {"bundle_id": "dev.copyapp.clockclone"})])

    def test_instruments_launch_is_bounded(self):
        with patch("copyapp.playbook.subprocess.run", side_effect=subprocess.TimeoutExpired(
                cmd="dvt", timeout=20)) as run:
            with self.assertRaisesRegex(TimeoutError, "exceeded 20 seconds"):
                import asyncio
                asyncio.run(_fresh_launch("00008020-000D650434B8003A", "dev.copyapp.fixture"))
        self.assertEqual(run.call_args.kwargs["timeout"], 20)

    def test_ios_mcp_fresh_launch_falls_back_to_ictrl_lifecycle(self):
        class FallbackClient:
            calls = []

            def __init__(self, **_kwargs):
                pass

            def call_ui(self, method, params):
                self.calls.append((method, params))

        self.script.write_text(json.dumps({
            "schema_version": 1, "bundle_id": "com.apple.mobiletimer",
            "fresh_launch": True,
            "steps": [{"action": "observe", "exact_labels": ["Stopwatch"]}],
        }))
        with patch("copyapp.playbook.ExperimentUI", FakeUI), \
             patch("copyapp.playbook.ios_mcp_tunnel", fake_tunnel), \
             patch("copyapp.playbook.ictrl_tunnel", fake_tunnel), \
             patch("copyapp.playbook.ICtrlClient", FallbackClient), \
             patch("copyapp.playbook._fresh_launch", new_callable=AsyncMock,
                   side_effect=TimeoutError("timed out")), \
             patch("copyapp.playbook.time.sleep"):
            path, complete = run_playbook("device", "ios-mcp", self.script,
                                          self.root / "fallback")
        record = json.loads(path.read_text())
        self.assertTrue(complete, record.get("error"))
        self.assertEqual(record["fresh_launch_backend"], "ictrl_lifecycle_fallback")
        self.assertIn("TimeoutError: timed out", record["fresh_launch_primary_error"])
        self.assertEqual(FallbackClient.calls, [
            ("terminate_app", {"bundle_id": "com.apple.mobiletimer"}),
            ("launch_app", {"bundle_id": "com.apple.mobiletimer"}),
        ])


if __name__ == "__main__":
    unittest.main()
