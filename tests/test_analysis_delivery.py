import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.analysis_delivery import _covered_flows, create_analysis_delivery
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class AnalysisDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / "task"
        self.report = self.root / "report"
        self.analysis = self.root / "analysis"
        self.investigation = self.root / "investigation"
        write(self.analysis / "analysis-index.json", {"case": "analysis"})
        write(self.investigation / "manifest.json", {"case": "investigation"})
        write(self.task / "manifest.json", {"kind": "draft_analysis"})
        digest = "a" * 64
        write(self.task / "task.json", {
            "kind": "agent_semantic_review_task", "status": "needs_semantic_review",
            "target_bundle_id": "dev.example", "analysis_case": str(self.analysis),
            "app_investigation_case": str(self.investigation),
            "analysis_index_sha256": sha256_file(self.analysis / "analysis-index.json"),
            "app_investigation_sha256": sha256_file(self.investigation / "manifest.json"),
            "flows": [{"id": "flow-01", "source_script_sha256": digest}]})
        write(self.task / "feature-spec.json", {"flows": [{
            "id": "flow-01", "source_script_sha256": digest,
            "expected": ["具体行为待审阅"]}]})
        write(self.report / "report-index.json", {
            "target_bundle_id": "dev.example",
            "source_case": str(self.analysis),
            "source_case_index_sha256": sha256_file(self.analysis / "analysis-index.json"),
            "evidence": {"app.all": {"kind": "app_investigation",
                                      "sha256": sha256_file(self.investigation / "manifest.json")}}})
        write(self.report / "feature-spec.json", {
            "target_bundle_id": "dev.example", "flows": [{
                "id": "reviewed-flow", "source_script_sha256": digest,
                "entry": "tap Add", "expected": ["result label shows 15"],
                "verification": "replay original and inspect result label",
                "evidence": ["app.all"]}]})
        write(self.report / "findings.json", {
            "target_bundle_id": "dev.example", "sections": [{"title": "flow", "findings": [
                {"claim": "result label shows 15", "confidence": "observed",
                 "evidence": ["app.all"]}]}]})

    def test_binds_report_and_detects_later_spec_change(self):
        output = self.root / "delivery"
        with patch("copyapp.analysis_delivery.verify_case", return_value=True):
            create_analysis_delivery(self.task, self.report, output)
            self.assertTrue(verify_case(output))
            result = json.loads((output / "delivery.json").read_text())
            self.assertEqual(result["flow_coverage"][0]["report_flow_id"],
                             "reviewed-flow")
            self.assertIsNone(result["agent_run"])
            spec = json.loads((self.report / "feature-spec.json").read_text())
            spec["flows"][0]["expected"] = ["changed later"]
            write(self.report / "feature-spec.json", spec)
            self.assertFalse(verify_case(output))

    def test_rejects_unchanged_provisional_scenario(self):
        task = json.loads((self.task / "task.json").read_text())
        draft = json.loads((self.task / "feature-spec.json").read_text())
        reviewed = json.loads((self.report / "feature-spec.json").read_text())
        reviewed["flows"][0]["expected"] = draft["flows"][0]["expected"]
        with self.assertRaisesRegex(ValueError, "concrete reviewed assertions"):
            _covered_flows(task, draft, reviewed)

    def test_rejects_missing_investigated_flow(self):
        task = json.loads((self.task / "task.json").read_text())
        draft = json.loads((self.task / "feature-spec.json").read_text())
        reviewed = json.loads((self.report / "feature-spec.json").read_text())
        reviewed["flows"][0]["source_script_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "omits investigated flow"):
            _covered_flows(task, draft, reviewed)

    def test_rejects_another_investigation_even_with_same_app(self):
        index = json.loads((self.report / "report-index.json").read_text())
        index["evidence"]["app.all"]["sha256"] = "b" * 64
        write(self.report / "report-index.json", index)
        with patch("copyapp.analysis_delivery.verify_case", return_value=True), \
                self.assertRaisesRegex(ValueError, "different source identity"):
            create_analysis_delivery(self.task, self.report, self.root / "delivery")
        self.assertFalse((self.root / "delivery").exists())


if __name__ == "__main__":
    unittest.main()
