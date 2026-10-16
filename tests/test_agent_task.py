import json
import tempfile
import unittest
from pathlib import Path

from copyapp.agent_task import _evidence_files, create_agent_task
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


class AgentTaskTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report"
        self.plan = self.root / "plan"
        self.script = {"schema_version": 1, "scenario_id": "one",
                       "bundle_id": "com.example.original", "fresh_launch": True,
                       "steps": [{"action": "observe", "contains": "ready"},
                                 {"action": "screenshot", "stable": True,
                                  "ready_contains": "ready"}]}
        evidence = self.report / "evidence/ui.original"
        write(evidence / "playbook.json", self.script)
        write(evidence / "manifest.json", {"status": "complete"})
        self.spec = {"schema_version": 1, "target_bundle_id": "com.example.original",
                     "rebuilt_bundle_id": "dev.example.clone", "minimum_ios": "16.0",
                     "reference_device": "iPhone XR", "flows": [
                         {"id": "one", "entry": "launch", "expected": ["ready"],
                          "verification": "screen visible", "evidence": ["ui.original"]}],
                     "unknowns": ["other screens"]}
        write(self.report / "feature-spec.json", self.spec)
        (self.report / "report.md").write_text("# Example\n")
        artifacts = {}
        for path in self.report.rglob("*"):
            if path.is_file():
                name = str(path.relative_to(self.report))
                artifacts[name] = {"path": name, "sha256": sha256_file(path)}
        write(self.report / "report-index.json", {
            "schema_version": 1, "target_bundle_id": "com.example.original",
            "evidence": {"ui.original": {"kind": "playbook",
                                         "path": "evidence/ui.original/manifest.json"}},
            "artifacts": artifacts})
        write(self.plan / "feature-spec.json", self.spec)
        write(self.plan / "flows/one/original.json", self.script)
        rebuilt_script = dict(self.script)
        rebuilt_script["bundle_id"] = "dev.example.clone"
        write(self.plan / "flows/one/rebuilt.json", rebuilt_script)
        (self.plan / "runbook.md").write_text("# Plan\n")
        write(self.plan / "rebuild-plan.json", {
            "schema_version": 1, "kind": "rebuild_plan", "status": "complete",
            "target_bundle_id": "com.example.original",
            "rebuilt_bundle_id": "dev.example.clone", "ui_backend": "ios-mcp",
            "source_report_index_sha256": sha256_file(self.report / "report-index.json"),
            "feature_spec_sha256": sha256_file(self.plan / "feature-spec.json"),
            "ready_count": 1, "needs_attention_count": 0,
            "flows": [{"flow_id": "one", "status": "ready_for_implementation",
                       "source_evidence_id": "ui.original",
                       "source_script_sha256": sha256_file(evidence / "playbook.json"),
                       "scenario_id": "one", "original_script": "flows/one/original.json",
                       "rebuilt_script": "flows/one/rebuilt.json"}],
            "rebuild_check_argv": ["copyapp", "rebuild-check", "--udid", "<UDID>",
                                   "--out", "<NEW_CASE>"]})
        self._refresh_plan_manifest()

    def _refresh_plan_manifest(self):
        files = [{"path": str(path.relative_to(self.plan)), "sha256": sha256_file(path)}
                 for path in self.plan.rglob("*") if path.is_file() and path.name != "manifest.json"]
        write(self.plan / "manifest.json", {"schema_version": 1, "evidence": files})

    def test_creates_verified_source_linked_task(self):
        output = self.root / "task"
        create_agent_task(self.report, self.plan, output,
                          "00008020-1111111111111111", self.root / "Clone")
        task = json.loads((output / "task.json").read_text())
        self.assertEqual(task["status"], "ready_for_agent")
        self.assertEqual(task["flows"][0]["source_evidence_id"], "ui.original")
        self.assertIn("evidence/ui.original/playbook.json",
                      task["flows"][0]["evidence"][0]["files"])
        self.assertIn("00008020-1111111111111111", (output / "TASK.md").read_text())
        self.assertTrue(verify_case(output))

    def test_direct_queue_links_each_function_for_rebuild_agent(self):
        queue = self.report / "evidence/code.chain"
        write(queue / "manifest.json", {"status": "complete"})
        write(queue / "queue.json", {"results": [
            {"status": "complete", "summary": "targets/function-01/summary.json"},
            {"status": "complete", "summary": "targets/function-02/summary.json"}]})
        for index in (1, 2):
            target = queue / f"targets/function-{index:02d}"
            write(target / "summary.json", {"address": f"0x{index:x}"})
            (target / "pseudocode.txt").write_text(f"function {index}\n")
            (target / "function-facts.json").write_text("{}\n")
        native = queue / "sources/native"
        write(native / "index.json", {"results": [], "followed": [
            {"status": "complete", "summary": "followed-01/summary.json"}]})
        write(native / "followed-01/summary.json", {"address": "0x2"})
        (native / "followed-01/assembly.txt").write_text("bl 0x2\n")
        write(queue / "sources/branch-flow/trace/trace.json", {"branch_call_counts": [1]})
        entry = {"kind": "ghidra_direct_queue",
                 "path": "evidence/code.chain/manifest.json"}
        files = _evidence_files(self.report.resolve(), entry)
        self.assertIn("evidence/code.chain/queue.json", files)
        self.assertIn("evidence/code.chain/targets/function-01/pseudocode.txt", files)
        self.assertIn("evidence/code.chain/targets/function-02/pseudocode.txt", files)
        self.assertIn("evidence/code.chain/targets/function-01/function-facts.json", files)
        self.assertIn("evidence/code.chain/sources/native/followed-01/assembly.txt", files)
        self.assertIn("evidence/code.chain/sources/branch-flow/trace/trace.json", files)

    def test_rejects_stale_report_index(self):
        path = self.report / "report-index.json"
        index = json.loads(path.read_text())
        index["changed"] = True
        write(path, index)
        with self.assertRaisesRegex(ValueError, "stale"):
            create_agent_task(self.report, self.plan, self.root / "task")

    def test_verified_task_detects_source_report_change_after_creation(self):
        output = self.root / "task"
        create_agent_task(self.report, self.plan, output)
        self.assertTrue(verify_case(output))
        path = self.report / "report-index.json"
        index = json.loads(path.read_text())
        index["changed"] = True
        write(path, index)
        self.assertFalse(verify_case(output))

    def test_rejects_clone_script_that_changes_behavior(self):
        path = self.plan / "flows/one/rebuilt.json"
        script = json.loads(path.read_text())
        script["steps"][0]["contains"] = "different"
        write(path, script)
        self._refresh_plan_manifest()
        with self.assertRaisesRegex(ValueError, "no longer match cited"):
            create_agent_task(self.report, self.plan, self.root / "task")

    def test_missing_original_playbook_is_not_marked_ready(self):
        path = self.plan / "rebuild-plan.json"
        plan = json.loads(path.read_text())
        plan["ready_count"] = 0
        plan["needs_attention_count"] = 1
        plan["flows"] = [{"flow_id": "one", "status": "needs_original_playbook",
                          "reason": "no cited original playbook"}]
        write(path, plan)
        self._refresh_plan_manifest()
        output = self.root / "task"
        create_agent_task(self.report, self.plan, output)
        task = json.loads((output / "task.json").read_text())
        self.assertEqual(task["status"], "needs_evidence")
        self.assertEqual(task["ready_count"], 0)

    def test_selected_subset_does_not_claim_whole_report_ready(self):
        self.spec["flows"].append({"id": "two", "entry": "another page",
                                   "expected": ["other"], "evidence": ["ui.original"]})
        write(self.report / "feature-spec.json", self.spec)
        write(self.plan / "feature-spec.json", self.spec)
        report_index_path = self.report / "report-index.json"
        report_index = json.loads(report_index_path.read_text())
        report_index["artifacts"]["feature-spec.json"]["sha256"] = sha256_file(
            self.report / "feature-spec.json")
        write(report_index_path, report_index)
        plan_path = self.plan / "rebuild-plan.json"
        plan = json.loads(plan_path.read_text())
        plan["source_report_index_sha256"] = sha256_file(report_index_path)
        plan["feature_spec_sha256"] = sha256_file(self.plan / "feature-spec.json")
        write(plan_path, plan)
        self._refresh_plan_manifest()
        output = self.root / "task"
        create_agent_task(self.report, self.plan, output)
        task = json.loads((output / "task.json").read_text())
        self.assertEqual(task["status"], "selected_flows_ready")
        self.assertEqual(task["omitted_flow_ids"], ["two"])


if __name__ == "__main__":
    unittest.main()
