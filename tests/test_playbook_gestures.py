import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from copyapp.compare_playbooks import _load_run
from copyapp.discover_check import inspect_playbook
from copyapp.gestures import gesture_params
from copyapp.playbook import run_playbook


@contextmanager
def fake_tunnel(_udid, *_args):
    yield 22223


class GestureUI:
    calls = []

    def __init__(self, *_args, **_kwargs):
        pass

    def bounds(self):
        return 414, 896

    def frontmost(self):
        return "com.example.target"

    def swipe(self, *args):
        self.calls.append(("swipe", args))
        return {"ok": True}

    def long_press(self, *args):
        self.calls.append(("long_press", args))
        return {"ok": True}

    def double_tap(self, *args):
        self.calls.append(("double_tap", args))
        return {"ok": True}


class PlaybookGestureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "flow.json"
        GestureUI.calls = []

    def replay(self, step, output="run", fresh_launch=False):
        self.script.write_text(json.dumps({
            "schema_version": 1, "bundle_id": "com.example.target",
            "scenario_id": "gesture", "fresh_launch": fresh_launch,
            "steps": [step],
        }))
        with patch("copyapp.playbook.ExperimentUI", GestureUI), \
             patch("copyapp.playbook.ios_mcp_tunnel", fake_tunnel), \
             patch("copyapp.playbook._fresh_launch", new_callable=AsyncMock) as launch, \
             patch("copyapp.playbook.time.sleep"):
            manifest, complete = run_playbook("device", "ios-mcp", self.script,
                                              self.root / output)
        return json.loads(manifest.read_text()), complete, launch

    def test_replays_and_binds_swipe_long_press_and_double_tap(self):
        steps = [
            {"action": "swipe", "from_x": 300, "from_y": 280,
             "to_x": 100, "to_y": 280, "duration_ms": 400},
            {"action": "long_press", "x": 205, "y": 280, "duration_ms": 900},
            {"action": "double_tap", "x": 205, "y": 280, "interval_ms": 120},
        ]
        for index, step in enumerate(steps):
            root = f"run-{index}"
            record, complete, _ = self.replay(step, root)
            self.assertTrue(complete, record.get("error"))
            self.assertEqual(record["steps"][0]["gesture"], gesture_params(step))
            _load_run(self.root / root, require_comparable=False)
        self.assertEqual([name for name, _ in GestureUI.calls],
                         ["swipe", "long_press", "double_tap"])

    def test_invalid_gesture_rejected_before_launch_or_touch(self):
        record, complete, launch = self.replay(
            {"action": "swipe", "from_x": 300, "from_y": 280,
             "to_x": 300, "to_y": 280}, "invalid", fresh_launch=True)
        self.assertFalse(complete)
        self.assertIn("too short", record["error"]["message"])
        launch.assert_not_called()
        self.assertEqual(GestureUI.calls, [])
        with self.assertRaisesRegex(ValueError, "horizontal or vertical"):
            gesture_params({"action": "swipe", "from_x": 300, "from_y": 280,
                            "to_x": 100, "to_y": 260})

    def test_discovery_accepts_gesture_and_rejects_out_of_bounds(self):
        plan = {"schema_version": 1, "bundle_id": "com.example.target",
                "scenario_id": "gesture-discovery", "fresh_launch": True,
                "steps": [
                    {"action": "observe", "contains": ["Calculator"]},
                    {"action": "swipe", "from_x": 300, "from_y": 280,
                     "to_x": 100, "to_y": 280},
                    {"action": "screenshot", "stable": True,
                     "ready_contains": "Result"},
                ]}
        self.script.write_text(json.dumps(plan))
        inspected = inspect_playbook(self.script, "com.example.target")
        self.assertEqual(inspected["tap_count"], 1)
        self.assertEqual(inspected["tap_signature"][0][0], "swipe")
        plan["steps"][1]["from_x"] = 10001
        self.script.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError, "invalid swipe coordinate"):
            inspect_playbook(self.script, "com.example.target")


if __name__ == "__main__":
    unittest.main()
