import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from copyapp.compare_playbooks import _load_run
from copyapp.discover_check import inspect_playbook
from copyapp.experiment import ExperimentUI
from copyapp.playbook import run_playbook
from copyapp.text_actions import type_params


@contextmanager
def fake_tunnel(_udid):
    yield 22223


class FakeUI:
    typed = []

    def __init__(self, *_args, **_kwargs):
        pass

    def bounds(self):
        return 414, 896

    def frontmost(self):
        return "com.example.translate"

    def type_text(self, value):
        self.typed.append(value)
        return {"ok": True}


class PlaybookTextTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "flow.json"
        FakeUI.typed = []

    def replay(self, step, name, fresh=False):
        self.script.write_text(json.dumps({
            "schema_version": 1, "bundle_id": "com.example.translate",
            "scenario_id": "synthetic-phrase", "fresh_launch": fresh,
            "steps": [step],
        }))
        with patch("copyapp.playbook.ExperimentUI", FakeUI), \
             patch("copyapp.playbook.ios_mcp_tunnel", fake_tunnel), \
             patch("copyapp.playbook._fresh_launch", new_callable=AsyncMock) as launch:
            manifest, complete = run_playbook("device", "ios-mcp", self.script,
                                              self.root / name)
        return json.loads(manifest.read_text()), complete, launch

    def test_replay_binds_text_hash_without_copying_it_to_step_metadata(self):
        step = {"action": "type_text", "text": "hello"}
        record, complete, _ = self.replay(step, "valid")
        self.assertTrue(complete, record.get("error"))
        self.assertEqual(FakeUI.typed, ["hello"])
        self.assertEqual(record["steps"][0]["typed_text"], type_params(step))
        self.assertNotIn("hello", json.dumps(record["steps"][0]["typed_text"]))
        _load_run(self.root / "valid", require_comparable=False)

    def test_rejects_unbounded_or_control_text_before_launch(self):
        step = {"action": "type_text", "text": "hi\nthere"}
        record, complete, launch = self.replay(step, "invalid", fresh=True)
        self.assertFalse(complete)
        self.assertIn("printable", record["error"]["message"])
        launch.assert_not_called()
        self.assertEqual(FakeUI.typed, [])
        with self.assertRaisesRegex(ValueError, "128 printable"):
            type_params({"action": "type_text", "text": "x" * 129})

    def test_discovery_counts_synthetic_text_as_action(self):
        plan = {"schema_version": 1, "bundle_id": "com.example.translate",
                "scenario_id": "synthetic-phrase", "fresh_launch": True,
                "steps": [
                    {"action": "observe", "contains": ["Enter text"]},
                    {"action": "type_text", "text": "hello"},
                    {"action": "screenshot", "stable": True,
                     "ready_contains": "hello"},
                ]}
        self.script.write_text(json.dumps(plan))
        inspected = inspect_playbook(self.script, "com.example.translate")
        self.assertEqual(inspected["tap_count"], 1)
        self.assertEqual(inspected["tap_signature"][0][0], "type_text")

    def test_backend_mapping_preserves_short_text(self):
        ui = object.__new__(ExperimentUI)
        ui.backend = "ictrl"
        ui.client = Mock()
        ui.client.call_ui.return_value = {"ok": True}
        ui.type_text("hello")
        ui.client.call_ui.assert_called_once_with("type", {"text": "hello"})
        ui.backend = "ios-mcp"
        with patch("copyapp.experiment.IOSMCPClient.text_json", return_value={"ok": True}):
            ui.type_text("hello")
        ui.client.call_ui.assert_called_with("type_text", {"text": "hello"})


if __name__ == "__main__":
    unittest.main()
