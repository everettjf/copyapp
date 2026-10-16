import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.investigate_app import _files, _verified_resume_evidence, investigate_app
from copyapp.report import _validate_app_investigation
from copyapp.verify import sha256_file, verify_case


class InvestigateAppTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.udid = "exact-device"
        self.bundle = "com.example.app"
        self.prefix = hashlib.sha256(self.udid.encode()).hexdigest()[:16]
        self.analysis = self.root / "analysis"
        (self.analysis / "survey").mkdir(parents=True)
        (self.analysis / "survey/manifest.json").write_text(json.dumps({
            "bundle_id": self.bundle,
            "device_id_sha256_prefix": self.prefix}))
        (self.analysis / "analysis-index.json").write_text("{}")
        self.scripts = []
        for index in (1, 2):
            path = self.root / f"flow-{index}.json"
            path.write_text(json.dumps({"bundle_id": self.bundle,
                                        "steps": [{"action": "tap", "x": index}]}))
            self.scripts.append(path)

    def test_stops_then_resumes_without_repeating_completed_flow(self):
        output = self.root / "investigation"

        def first_pass(udid, analysis, script, child, **kwargs):
            child.mkdir(parents=True)
            status = "complete" if script == self.scripts[0] else "needs_review"
            path = child / "manifest.json"
            path.write_text(json.dumps({"status": status, "bundle_id": self.bundle,
                "device_id_sha256_prefix": self.prefix,
                "ui_backend": "ios-mcp", "provider": "none",
                "selected_methods": [],
                "source_script_sha256": sha256_file(script)}))
            return path, status == "complete"

        with patch("copyapp.investigate_app.verify_case", return_value=True), \
             patch("copyapp.investigate_app.investigate_flow", side_effect=first_pass) as worker:
            parent, complete = investigate_app(self.udid, self.analysis,
                                               self.scripts, output, provider="none")
        self.assertFalse(complete)
        self.assertEqual(worker.call_count, 2)
        self.assertEqual(json.loads(parent.read_text())["status"], "needs_review")
        self.assertTrue(verify_case(output))

        def second_pass(udid, analysis, script, child, **kwargs):
            self.assertEqual(script, self.scripts[1])
            self.assertTrue(kwargs["resume"])
            path = child / "manifest.json"
            data = json.loads(path.read_text())
            data["status"] = "complete"
            path.write_text(json.dumps(data))
            return path, True

        with patch("copyapp.investigate_app.verify_case", return_value=True), \
             patch("copyapp.report._validate_investigation"), \
             patch("copyapp.report._main_and_embedded_hashes", return_value=set()), \
             patch("copyapp.investigate_app.investigate_flow", side_effect=second_pass) as worker:
            parent, complete = investigate_app(self.udid, self.analysis,
                                               self.scripts, output, provider="none", resume=True)
        self.assertTrue(complete)
        worker.assert_called_once()
        record = json.loads(parent.read_text())
        self.assertEqual([item["status"] for item in record["flows"]],
                         ["complete", "complete"])
        self.assertEqual(record["history"][0]["previous_status"], "needs_review")
        self.assertTrue(verify_case(output))
        with patch("copyapp.report._validate_investigation", side_effect=lambda child, *_: {
                "manifest": json.loads((child / "manifest.json").read_text()),
                "files": ["manifest.json"]}):
            validated = _validate_app_investigation(
                output, self.bundle, self.prefix, set(),
                sha256_file(self.analysis / "analysis-index.json"))
        self.assertEqual(len(validated["manifest"]["flows"]), 2)

    def test_rejects_script_from_another_bundle_before_touch(self):
        self.scripts[1].write_text(json.dumps({"bundle_id": "com.other"}))
        with patch("copyapp.investigate_app.verify_case", return_value=True), \
             patch("copyapp.investigate_app.investigate_flow") as worker:
            with self.assertRaisesRegex(ValueError, "another app"):
                investigate_app(self.udid, self.analysis, self.scripts,
                                self.root / "invalid")
        worker.assert_not_called()

    def test_separately_completed_child_can_refresh_only_its_own_evidence(self):
        output = self.root / "promoted"
        child = output / "flows/flow-01"
        child.mkdir(parents=True)
        manifest = child / "manifest.json"
        manifest.write_text(json.dumps({"status": "needs_review",
                                        "source_script_sha256": sha256_file(self.scripts[0])}))
        (output / "other.txt").write_text("unchanged")
        previous = {"flows": [{"index": 1, "status": "needs_review",
                               "manifest": "flows/flow-01/manifest.json"}],
                    "evidence": _files(output)}
        (output / "manifest.json").write_text(json.dumps(previous))
        manifest.write_text(json.dumps({"status": "complete",
                                        "source_script_sha256": sha256_file(self.scripts[0])}))
        (child / "new-result.json").write_text("{}")
        records = [{"sha256": sha256_file(self.scripts[0])}]
        with patch("copyapp.report._main_and_embedded_hashes", return_value=set()), \
             patch("copyapp.report._validate_investigation") as validated:
            self.assertTrue(_verified_resume_evidence(output, previous, self.bundle,
                                                      self.prefix, self.analysis, records))
            validated.assert_called_once()
            (output / "other.txt").write_text("tampered")
            self.assertFalse(_verified_resume_evidence(output, previous, self.bundle,
                                                       self.prefix, self.analysis, records))


if __name__ == "__main__":
    unittest.main()
