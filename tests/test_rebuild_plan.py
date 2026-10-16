import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.rebuild_plan import create_rebuild_plan
from copyapp.agent_task import create_agent_task
from copyapp.verify import sha256_file, verify_case


class RebuildPlanTest(unittest.TestCase):
    def test_app_investigation_selects_one_cited_child_and_builds_agent_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report"
            app = report / "evidence/app.all"
            scripts = []
            flows = []
            for index in (1, 2):
                child = app / f"flows/flow-{index:02d}"
                play = child / "flow/playbook"
                play.mkdir(parents=True)
                script = {"schema_version": 1, "bundle_id": "com.example.original",
                          "scenario_id": f"addition-{index}", "fresh_launch": True,
                          "steps": [{"action": "observe", "contains": ["all clear"]},
                                    {"action": "tap_label", "label": "equals"},
                                    {"action": "screenshot", "stable": True,
                                     "ready_contains": "clear"}]}
                (play / "playbook.json").write_text(json.dumps(script))
                (child / "manifest.json").write_text(json.dumps({
                    "status": "complete", "bundle_id": "com.example.original",
                    "source_script_sha256": sha256_file(play / "playbook.json")}))
                scripts.append(script)
                flows.append({"index": index, "status": "complete",
                              "manifest": f"flows/flow-{index:02d}/manifest.json",
                              "manifest_sha256": sha256_file(child / "manifest.json"),
                              "script_sha256": sha256_file(play / "playbook.json")})
            app.mkdir(parents=True, exist_ok=True)
            (app / "manifest.json").write_text(json.dumps({
                "kind": "investigated_app", "status": "complete",
                "bundle_id": "com.example.original", "flows": flows}))
            (report / "report-index.json").write_text(json.dumps({
                "target_bundle_id": "com.example.original",
                "evidence": {"app.all": {"kind": "app_investigation",
                                         "path": "evidence/app.all/manifest.json"}}}))
            (report / "feature-spec.json").write_text(json.dumps({
                "schema_version": 1, "target_bundle_id": "com.example.original",
                "rebuilt_bundle_id": "com.example.clone", "flows": [{
                    "id": "addition-2", "entry": "clear then equals", "expected": ["15"],
                    "verification": "final label", "evidence": ["app.all"],
                    "source_script_sha256": flows[1]["script_sha256"],
                    "final_view": {"text": "15", "region_points": [0, 0, 400, 400]}}]}))

            def load_run(path):
                index = 1 if "flow-01" in str(path) else 2
                return {"bundle_id": "com.example.original"}, scripts[index - 1]

            with patch("copyapp.rebuild_plan.verify_case", return_value=True), \
                    patch("copyapp.rebuild_plan._load_run", side_effect=load_run), \
                    patch("copyapp.rebuild_plan.check_final_view",
                          side_effect=lambda path, _: {"passed": "flow-02" in str(path)}):
                create_rebuild_plan(report, root / "plan")
            plan = json.loads((root / "plan/rebuild-plan.json").read_text())
            self.assertEqual(plan["ready_count"], 1)
            self.assertEqual(plan["flows"][0]["source_flow_index"], 2)
            self.assertEqual(plan["flows"][0]["source_evidence_id"], "app.all")
            with patch("copyapp.agent_task.verify_case", return_value=True):
                create_agent_task(report, root / "plan", root / "task")
            task = json.loads((root / "task/task.json").read_text())
            self.assertEqual(task["status"], "ready_for_agent")
            self.assertEqual(task["flows"][0]["source_flow_index"], 2)
            self.assertTrue(any("flow-02/flow/playbook/playbook.json" in path
                                for path in task["flows"][0]["evidence"][0]["files"]))

    def test_selects_cited_flow_with_matching_final_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report"
            report.mkdir()
            flow_id = "clear-repeat"
            script = {"schema_version": 1, "bundle_id": "com.example.original",
                      "scenario_id": "clear-then-repeat", "fresh_launch": True,
                      "steps": [{"action": "observe", "contains": ["all clear"]},
                                {"action": "tap_label", "label": "equals"},
                                {"action": "screenshot", "stable": True,
                                 "ready_contains": "clear"}]}
            entries = {}
            for evidence_id in ("clear.states", "clear.repeat"):
                base = report / "evidence" / evidence_id
                (base / "playbook").mkdir(parents=True)
                (base / "manifest.json").write_text('{}')
                (base / "playbook/playbook.json").write_text(json.dumps(script))
                entries[evidence_id] = {"kind": "flow_capture",
                                        "path": f"evidence/{evidence_id}/manifest.json"}
            (report / "report-index.json").write_text(json.dumps({
                "target_bundle_id": "com.example.original", "evidence": entries}))
            (report / "feature-spec.json").write_text(json.dumps({
                "schema_version": 1, "target_bundle_id": "com.example.original",
                "rebuilt_bundle_id": "com.example.clone", "flows": [{
                    "id": flow_id, "entry": "clear then repeat", "expected": ["8"],
                    "verification": "final label", "evidence": list(entries),
                    "final_view": {"text": "8", "region_points": [0, 0, 400, 400]}}]}))
            def final_check(source, _assertion):
                return {"passed": source.name == "clear.repeat"}
            with patch("copyapp.rebuild_plan.verify_case", return_value=True), \
                    patch("copyapp.rebuild_plan._load_run",
                          return_value=({"bundle_id": "com.example.original"}, script)), \
                    patch("copyapp.rebuild_plan.check_final_view", side_effect=final_check):
                create_rebuild_plan(report, root / "plan")
            plan = json.loads((root / "plan/rebuild-plan.json").read_text())
            self.assertEqual(plan["ready_count"], 1)
            self.assertEqual(plan["flows"][0]["source_evidence_id"], "clear.repeat")
            clone = json.loads((root / "plan/flows/clear-repeat/rebuilt.json").read_text())
            self.assertEqual(clone["bundle_id"], "com.example.clone")
            self.assertEqual(clone["steps"], script["steps"])
            self.assertTrue(verify_case(root / "plan"))

    def test_refuses_unreviewed_spec_before_generating_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report"
            report.mkdir()
            (report / "report-index.json").write_text(json.dumps({
                "target_bundle_id": "com.example.original", "evidence": {}}))
            (report / "feature-spec.json").write_text(json.dumps({
                "schema_version": 1, "review_status": "needs_semantic_review",
                "target_bundle_id": "com.example.original",
                "rebuilt_bundle_id": "com.example.clone",
                "flows": [{"id": "one"}]}))
            with patch("copyapp.rebuild_plan.verify_case", return_value=True), \
                    self.assertRaisesRegex(ValueError, "reviewed rebuild specification"):
                create_rebuild_plan(report, root / "plan")
            self.assertFalse((root / "plan").exists())


if __name__ == "__main__":
    unittest.main()
