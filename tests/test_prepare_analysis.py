import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.prepare_analysis import prepare_analysis
from copyapp.verify import sha256_file


class PrepareAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.udid = "exact-device"
        self.bundle = "com.example.app"
        self.prefix = hashlib.sha256(self.udid.encode()).hexdigest()[:16]
        self.analysis = self.root / "analysis"
        (self.analysis / "survey").mkdir(parents=True)
        (self.analysis / "survey/manifest.json").write_text(json.dumps({
            "bundle_id": self.bundle, "device_id_sha256_prefix": self.prefix}))
        (self.analysis / "analysis-index.json").write_text("{}")
        self.script = self.root / "flow.json"
        self.script.write_text(json.dumps({"bundle_id": self.bundle,
                                           "steps": [{"action": "observe"}]}))
        self.output = self.root / "prepared"

    def test_interrupted_investigation_resumes_then_prepares_review_task(self):
        attempts = []

        def investigate(udid, analysis, scripts, output, *args):
            attempts.append(args[-1])
            output.mkdir(exist_ok=True)
            complete = len(attempts) == 2
            (output / "manifest.json").write_text(json.dumps({
                "status": "complete" if complete else "needs_review",
                "bundle_id": self.bundle,
                "device_id_sha256_prefix": self.prefix,
                "analysis_index_sha256": sha256_file(self.analysis / "analysis-index.json"),
                "scripts": [{"path": str(self.script.resolve()), "sha256": sha256_file(self.script)}],
                "ui_backend": "ios-mcp", "provider": "ghidra"}))
            return output / "manifest.json", complete

        def draft(analysis, investigation, output, rebuilt_bundle):
            output.mkdir()
            (output / "manifest.json").write_text(json.dumps({"status": "complete"}))
            (output / "task.json").write_text(json.dumps({
                "kind": "agent_semantic_review_task",
                "target_bundle_id": self.bundle,
                "device_id_sha256_prefix": self.prefix,
                "analysis_index_sha256": sha256_file(self.analysis / "analysis-index.json"),
                "app_investigation_sha256": sha256_file(investigation / "manifest.json")}))
            return output / "manifest.json", True

        with patch("copyapp.prepare_analysis.verify_case", return_value=True), \
             patch("copyapp.prepare_analysis._rea_ready"), \
             patch("copyapp.prepare_analysis.investigate_app", side_effect=investigate), \
             patch("copyapp.prepare_analysis.draft_analysis", side_effect=draft) as writer:
            _, ready = prepare_analysis(self.udid, self.analysis, [self.script], self.output,
                                        provider="ghidra")
            self.assertFalse(ready)
            self.assertEqual(json.loads((self.output / "manifest.json").read_text())["status"],
                             "investigation_incomplete")
            _, ready = prepare_analysis(self.udid, self.analysis, [self.script], self.output,
                                        provider="ghidra", resume=True)
            self.assertTrue(ready, (self.output / "manifest.json").read_text())
            writer.assert_called_once()
        self.assertEqual(attempts, [False, True])
        self.assertEqual(json.loads((self.output / "manifest.json").read_text())["status"],
                         "needs_semantic_review")

    def test_changed_script_rejected_before_device_work_on_resume(self):
        self.output.mkdir()
        (self.output / "manifest.json").write_text(json.dumps({
            "kind": "analysis_preparation", "analysis_case": str(self.analysis),
            "scripts": [{"path": str(self.script), "sha256": sha256_file(self.script)}]}))
        self.script.write_text(json.dumps({"bundle_id": self.bundle,
                                           "steps": [{"action": "tap", "x": 5}]}))
        with patch("copyapp.prepare_analysis.verify_case", return_value=True), \
             patch("copyapp.prepare_analysis.investigate_app") as worker:
            with self.assertRaisesRegex(ValueError, "resume target, scripts or settings differ"):
                prepare_analysis(self.udid, self.analysis, [self.script], self.output,
                                 resume=True)
        worker.assert_not_called()

    def test_missing_decompiler_stops_before_touching_phone(self):
        with patch("copyapp.prepare_analysis.verify_case", return_value=True), \
             patch("copyapp.prepare_analysis._rea_ready",
                   side_effect=FileNotFoundError("REA CLI not found")), \
             patch("copyapp.prepare_analysis.investigate_app") as worker:
            manifest, ready = prepare_analysis(
                self.udid, self.analysis, [self.script], self.output, provider="ghidra")
        self.assertFalse(ready)
        self.assertEqual(json.loads(manifest.read_text())["error"]["type"],
                         "FileNotFoundError")
        worker.assert_not_called()

    def test_default_skips_rea_doctor(self):
        with patch("copyapp.prepare_analysis.verify_case", return_value=True), \
             patch("copyapp.prepare_analysis._rea_ready",
                   side_effect=AssertionError("REA must not run")) as doctor, \
             patch("copyapp.prepare_analysis.investigate_app", return_value=(None, False)):
            manifest, ready = prepare_analysis(
                self.udid, self.analysis, [self.script], self.output)
        self.assertFalse(ready)
        doctor.assert_not_called()
        self.assertEqual(json.loads(manifest.read_text())["provider"], "none")


if __name__ == "__main__":
    unittest.main()
