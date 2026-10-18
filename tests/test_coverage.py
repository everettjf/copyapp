import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.coverage import create_coverage_delivery, create_coverage_plan
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report"
        write(self.report / "report-index.json", {"target_bundle_id": "com.example.original"})
        write(self.report / "feature-spec.json", {
            "schema_version": 1, "target_bundle_id": "com.example.original",
            "rebuilt_bundle_id": "com.example.clone",
            "flows": [{"id": "create"}, {"id": "search"}]})
        self.plans = []
        for name in ("create", "search"):
            plan = self.root / f"plan-{name}"
            write(plan / "manifest.json", {"kind": "rebuild_plan"})
            write(plan / "rebuild-plan.json", {
                "kind": "rebuild_plan", "status": "complete",
                "source_report_index_sha256": sha256_file(self.report / "report-index.json"),
                "feature_spec_sha256": sha256_file(self.report / "feature-spec.json"),
                "flows": [{"flow_id": name}]})
            self.plans.append(plan)
        self.inventory = self.root / "inventory.json"
        write(self.inventory, {
            "schema_version": 1, "target_bundle_id": "com.example.original",
            "rebuilt_bundle_id": "com.example.clone",
            "rationale": "Selected local tasks first", "unknowns": ["server behavior"],
            "capabilities": [
                {"id": "create", "name": "Create", "acceptance": "Create an item",
                 "basis": "observed original flow", "weight": 3,
                 "scope": "selected", "flow_ids": ["create"]},
                {"id": "search", "name": "Search", "acceptance": "Find an item",
                 "basis": "observed original flow", "weight": 2,
                 "scope": "selected", "flow_ids": ["search"]},
                {"id": "account", "name": "Account", "acceptance": "Sync an item",
                 "basis": "visible account entry; not entered", "weight": 5,
                 "scope": "blocked", "flow_ids": [], "reason": "No test account"}]})
        self.review = self.root / "review.json"
        write(self.review, {"schema_version": 1, "capabilities": [
            {"id": "create", "result": "verified", "notes": "Original and clone checks pass"},
            {"id": "search", "result": "partial", "notes": "Search result differs"},
            {"id": "account", "result": "untested", "notes": "Account unavailable"}]})
        self.deliveries = []
        for name, source in zip(("create", "search"), self.plans):
            task = self.root / f"task-{name}"
            write(task / "task.json", {
                "report_index_sha256": sha256_file(self.report / "report-index.json"),
                "rebuild_plan_sha256": sha256_file(source / "rebuild-plan.json")})
            delivery = self.root / f"delivery-{name}"
            write(delivery / "manifest.json", {"kind": "agent_delivery"})
            write(delivery / "delivery.json", {
                "kind": "agent_delivery", "task_case": str(task),
                "target_bundle_id": "com.example.original",
                "rebuilt_bundle_id": "com.example.clone",
                "flow_results": [{"id": name, "script_assertions_status": "passed",
                                  "final_view_status": "not_configured",
                                  "visual_review_status": "minor_difference"}]})
            self.deliveries.append(delivery)

    def test_target_revision_and_conservative_delivery_math(self):
        with patch("copyapp.coverage._verified"):
            first = self.root / "target-1"
            create_coverage_plan(self.report, self.plans, self.inventory, first)
            self.assertTrue(verify_case(first))
            target = json.loads((first / "coverage-plan.json").read_text())
            self.assertEqual(target["target_percent"], 50.0)
            self.assertEqual(target["revision"], 1)
            final = self.root / "final"
            create_coverage_delivery(first, self.deliveries, self.review, final)
            self.assertTrue(verify_case(final))
            result = json.loads((final / "coverage-delivery.json").read_text())
            self.assertEqual(result["milestone_completion_percent"], 60.0)
            self.assertEqual(result["verified_known_percent"], 30.0)
            self.assertEqual(result["status"], "target_not_met")
            source_plan = self.plans[0] / "manifest.json"
            write(source_plan, {"kind": "rebuild_plan", "changed": True})
            self.assertFalse(verify_case(first))
            write(source_plan, {"kind": "rebuild_plan"})
            self.assertTrue(verify_case(first))
            revision = json.loads(self.inventory.read_text())
            revision["revision_reason"] = "New priority after review"
            write(self.inventory, revision)
            second = self.root / "target-2"
            create_coverage_plan(self.report, self.plans, self.inventory, second, first)
            self.assertTrue(verify_case(second))
            self.assertEqual(json.loads((second / "coverage-plan.json").read_text())["revision"], 2)
            revised_final = self.root / "revised-final"
            create_coverage_delivery(second, self.deliveries, self.review, revised_final)
            self.assertTrue(verify_case(revised_final))
            revised = json.loads((revised_final / "coverage-delivery.json").read_text())
            self.assertEqual(revised["previous_target_percent"], 50.0)
            self.assertEqual(revised["revision_reason"], "New priority after review")

    def test_cannot_promote_unchecked_flow_or_drop_known_capability(self):
        with patch("copyapp.coverage._verified"):
            target = self.root / "target"
            create_coverage_plan(self.report, self.plans, self.inventory, target)
            inventory = json.loads(self.inventory.read_text())
            inventory["revision_reason"] = "Narrower target"
            inventory["capabilities"].pop()
            write(self.inventory, inventory)
            with self.assertRaisesRegex(ValueError, "remove or weaken"):
                create_coverage_plan(self.report, self.plans, self.inventory,
                                     self.root / "bad-revision", target)
            inventory["capabilities"].append({
                "id": "account", "name": "Account", "acceptance": "Sync an item",
                "basis": "visible account entry; not entered", "weight": 1,
                "scope": "blocked", "flow_ids": [], "reason": "No test account"})
            write(self.inventory, inventory)
            with self.assertRaisesRegex(ValueError, "remove or weaken"):
                create_coverage_plan(self.report, self.plans, self.inventory,
                                     self.root / "bad-weight", target)
            review = json.loads(self.review.read_text())
            review["capabilities"][1]["result"] = "verified"
            write(self.review, review)
            flow = self.deliveries[1] / "delivery.json"
            data = json.loads(flow.read_text())
            data["flow_results"][0]["visual_review_status"] = "major_difference"
            write(flow, data)
            with self.assertRaisesRegex(ValueError, "complete behavior and visual evidence"):
                create_coverage_delivery(target, self.deliveries, self.review,
                                         self.root / "false-success")

if __name__ == "__main__":
    unittest.main()
