import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.playbook_auto import run_playbook_auto
from copyapp.verify import sha256_file, verify_case


class PlaybookAutoTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "script.json"
        self.script.write_text('{"schema_version":1,"bundle_id":"dev.example","steps":[]}')

    @staticmethod
    def fake_run(udid, backend, script, output, ictrl_client=None):
        output.mkdir()
        (output / "playbook.json").write_bytes(script.read_bytes())
        first = backend == "ictrl"
        manifest = {"status": "failed" if first else "complete",
                    "bundle_id": "dev.example",
                    "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                    "ui_backend": backend,
                    "steps": [] if first else [{"action": "observe"}],
                    "evidence": [{"path": "playbook.json",
                                  "sha256": sha256_file(output / "playbook.json")}],
                    "error": {"type": "ConnectionError"} if first else None}
        path = output / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path, not first

    def test_falls_back_after_connection_failure_and_retains_both(self):
        output = self.root / "auto"
        with patch("copyapp.playbook_auto.run_playbook", side_effect=self.fake_run) as mocked:
            _, complete = run_playbook_auto("device-1", "ictrl", "ios-mcp",
                                            self.script, output)
        self.assertTrue(complete)
        self.assertEqual(mocked.call_count, 2)
        self.assertTrue(verify_case(output))
        record = json.loads((output / "manifest.json").read_text())
        self.assertEqual(record["selected_backend"], "ios-mcp")
        self.assertEqual([item["status"] for item in record["attempts"]],
                         ["failed", "complete"])

    def test_stops_after_touch_attempt_even_if_backend_errors(self):
        output = self.root / "auto"

        def touched(udid, backend, script, root, ictrl_client=None):
            path, _ = self.fake_run(udid, backend, script, root, ictrl_client)
            record = json.loads(path.read_text())
            record["steps"] = [{"action": "tap_label"}]
            path.write_text(json.dumps(record))
            return path, False

        with patch("copyapp.playbook_auto.run_playbook", side_effect=touched) as mocked:
            _, complete = run_playbook_auto("device-1", "ictrl", "ios-mcp",
                                            self.script, output)
        self.assertFalse(complete)
        self.assertEqual(mocked.call_count, 1)
        self.assertTrue(verify_case(output))
        self.assertTrue(json.loads((output / "manifest.json").read_text())[
            "fallback_skipped_after_touch"])


if __name__ == "__main__":
    unittest.main()
