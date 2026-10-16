import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.rebuild_task_check import rebuild_task_check
from copyapp.verify import sha256_file


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class RebuildTaskCheckTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.report = self.root / "report"
        self.plan = self.root / "plan"
        self.task = self.root / "task"
        self.udid = "00008020-1111111111111111"
        original = self.plan / "flows/add/original.json"
        rebuilt = self.plan / "flows/add/rebuilt.json"
        write(original, {"bundle_id": "com.example.original"})
        write(rebuilt, {"bundle_id": "dev.example.clone"})
        source = self.report / "evidence/ui/playbook.json"
        write(source, {"bundle_id": "com.example.original"})
        write(self.report / "evidence/ui/manifest.json", {"status": "complete"})
        write(self.report / "feature-spec.json", {
            "rebuilt_bundle_id": "dev.example.clone"})
        write(self.report / "report-index.json", {
            "evidence": {"ui": {"kind": "playbook",
                                "path": "evidence/ui/manifest.json"}}})
        write(self.plan / "feature-spec.json", {"flows": [{"id": "add"}]})
        write(self.plan / "rebuild-plan.json", {
            "kind": "rebuild_plan", "status": "complete", "ui_backend": "ios-mcp",
            "source_report_index_sha256": sha256_file(self.report / "report-index.json"),
            "rebuilt_bundle_id": "dev.example.clone",
            "feature_spec_sha256": sha256_file(self.plan / "feature-spec.json"),
            "ready_count": 1, "needs_attention_count": 0,
            "flows": [{"flow_id": "add", "status": "ready_for_implementation",
                       "source_evidence_id": "ui",
                       "original_script": "flows/add/original.json",
                       "rebuilt_script": "flows/add/rebuilt.json",
                       "source_script_sha256": sha256_file(source)}],
        })
        write(self.task / "task.json", {
            "kind": "agent_implementation_task", "status": "ready_for_agent",
            "device_udid": self.udid, "rebuild_plan": str(self.plan),
            "rebuild_plan_sha256": sha256_file(self.plan / "rebuild-plan.json"),
            "report": str(self.report),
            "report_index_sha256": sha256_file(self.report / "report-index.json"),
            "rebuilt_bundle_id": "dev.example.clone",
            "flows": [{"id": "add", "status": "ready_for_implementation",
                       "source_evidence_id": "ui",
                       "original_script": str(original), "rebuilt_script": str(rebuilt),
                       "source_script_sha256": sha256_file(source)}],
        })

    def test_runs_exact_selected_pairs_from_verified_task(self):
        with patch("copyapp.rebuild_task_check.verify_case", return_value=True), \
             patch("copyapp.rebuild_task_check.rebuild_check",
                   return_value=(self.root / "check/manifest.json", True)) as worker:
            path, complete = rebuild_task_check(self.task, self.root / "check")
        self.assertTrue(complete)
        self.assertEqual(path, self.root / "check/manifest.json")
        args = worker.call_args.args
        self.assertEqual(args[0], self.udid)
        self.assertEqual(args[2][0][0], "add")
        self.assertEqual(args[4], "ios-mcp")

    def test_replays_source_inside_app_investigation(self):
        source = self.report / "evidence/ui/playbook.json"
        nested = self.report / "evidence/app.all/flows/flow-01"
        write(nested / "flow/playbook/playbook.json", json.loads(source.read_text()))
        write(nested / "manifest.json", {
            "source_script_sha256": sha256_file(nested / "flow/playbook/playbook.json")})
        write(self.report / "evidence/app.all/manifest.json", {
            "flows": [{"index": 1,
                       "manifest": "flows/flow-01/manifest.json",
                       "manifest_sha256": sha256_file(nested / "manifest.json"),
                       "script_sha256": sha256_file(nested / "flow/playbook/playbook.json")}]
        })
        index = json.loads((self.report / "report-index.json").read_text())
        index["evidence"] = {"app.all": {
            "kind": "app_investigation", "path": "evidence/app.all/manifest.json"}}
        write(self.report / "report-index.json", index)
        plan = json.loads((self.plan / "rebuild-plan.json").read_text())
        plan["source_report_index_sha256"] = sha256_file(self.report / "report-index.json")
        plan["flows"][0].update(source_evidence_id="app.all", source_flow_index=1)
        write(self.plan / "rebuild-plan.json", plan)
        task = json.loads((self.task / "task.json").read_text())
        task["report_index_sha256"] = sha256_file(self.report / "report-index.json")
        task["rebuild_plan_sha256"] = sha256_file(self.plan / "rebuild-plan.json")
        task["flows"][0].update(source_evidence_id="app.all", source_flow_index=1)
        write(self.task / "task.json", task)
        with patch("copyapp.rebuild_task_check.verify_case", return_value=True), \
             patch("copyapp.rebuild_task_check.rebuild_check",
                   return_value=(self.root / "check/manifest.json", True)) as worker:
            _, complete = rebuild_task_check(self.task, self.root / "check")
        self.assertTrue(complete)
        worker.assert_called_once()

    def test_rejects_device_mismatch_before_replay(self):
        with patch("copyapp.rebuild_task_check.verify_case", return_value=True), \
             patch("copyapp.rebuild_task_check.rebuild_check") as worker:
            with self.assertRaisesRegex(ValueError, "device differs"):
                rebuild_task_check(self.task, self.root / "check",
                                   "00008020-000D650434B8003B")
        worker.assert_not_called()

    def test_rejects_stale_pair_before_replay(self):
        path = self.plan / "flows/add/original.json"
        write(path, {"bundle_id": "com.example.changed"})
        with patch("copyapp.rebuild_task_check.verify_case", return_value=True), \
             patch("copyapp.rebuild_task_check.rebuild_check") as worker:
            with self.assertRaisesRegex(ValueError, "stale"):
                rebuild_task_check(self.task, self.root / "check")
        worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
