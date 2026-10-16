import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.agent_run import run_agent_task


class AgentRunTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / "task"
        self.task.mkdir()
        (self.task / "TASK.md").write_text("# Verified implementation task\n")
        (self.task / "task.json").write_text(json.dumps({
            "kind": "agent_implementation_task", "status": "ready_for_agent",
            "project_dir": str(self.root / "rebuild/Clone")}))
        (self.task / "manifest.json").write_text('{}')
        self.executable = self.root / "fake-codex"
        self.executable.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, sys\n"
            "prompt = sys.stdin.read()\n"
            "source = pathlib.Path('rebuild/Clone/Generated.swift')\n"
            "source.parent.mkdir(parents=True, exist_ok=True)\n"
            "source.write_text('struct Generated {}\\n')\n"
            "print(json.dumps({'type': 'thread.started', 'thread_id': 'fake-thread'}))\n"
            "print(json.dumps({'type': 'turn.completed', 'prompt_read': bool(prompt)}))\n")
        self.executable.chmod(0o755)

    def test_codex_exit_is_recorded_without_claiming_app_completion(self):
        with patch("copyapp.agent_run.verify_case", return_value=True):
            path, success = run_agent_task(self.task, self.root / "run", workspace=self.root,
                                           executable=self.executable)
        self.assertTrue(success)
        record = json.loads(path.read_text())
        self.assertEqual(record["status"], "agent_exited_unverified")
        self.assertEqual(record["agent_session_id"], "fake-thread")
        self.assertEqual(record["exit_code"], 0)
        self.assertTrue(record["project_source_changed"])
        self.assertIsNone(record["project_source_before_sha256"])
        self.assertIsInstance(record["project_source_after_sha256"], str)
        self.assertTrue(json.loads((path.parent / "stdout.jsonl").read_text().splitlines()[1])
                        ["prompt_read"])

    def test_dry_run_does_not_launch_provider(self):
        with patch("copyapp.agent_run.verify_case", return_value=True):
            path, success = run_agent_task(self.task, self.root / "run", provider="claude",
                                           workspace=self.root, executable=self.executable,
                                           dry_run=True)
        self.assertTrue(success)
        record = json.loads(path.read_text())
        self.assertEqual(record["status"], "prepared")
        self.assertIn("--permission-mode", record["argv"])
        self.assertNotIn("bypassPermissions", record["argv"])
        self.assertEqual((path.parent / "stdout.jsonl").read_text(), "")

    def test_rejects_partial_task_before_launch(self):
        path = self.task / "task.json"
        task = json.loads(path.read_text())
        task["status"] = "selected_flows_ready"
        path.write_text(json.dumps(task))
        with patch("copyapp.agent_run.verify_case", return_value=True), \
                self.assertRaisesRegex(ValueError, "selected implementation scope"):
            run_agent_task(self.task, self.root / "run", workspace=self.root,
                           executable=self.executable)
        self.assertFalse((self.root / "run").exists())

    def test_selected_report_subset_can_run_with_scope_retained(self):
        path = self.task / "task.json"
        task = json.loads(path.read_text())
        task.update({"status": "selected_flows_ready", "ready_count": 1,
                     "needs_attention_count": 0,
                     "flows": [{"id": "one", "status": "ready_for_implementation"}],
                     "omitted_flow_ids": ["two"]})
        path.write_text(json.dumps(task))
        with patch("copyapp.agent_run.verify_case", return_value=True):
            record_path, success = run_agent_task(
                self.task, self.root / "subset-run", workspace=self.root,
                executable=self.executable)
        self.assertTrue(success)
        record = json.loads(record_path.read_text())
        self.assertEqual(record["selected_flow_ids"], ["one"])
        self.assertEqual(record["omitted_flow_ids"], ["two"])
        self.assertEqual(record["status"], "agent_exited_unverified")

    def test_semantic_review_task_uses_installed_agent_without_claiming_report(self):
        task = {"kind": "agent_semantic_review_task",
                "status": "needs_semantic_review",
                "analysis_case": str(self.root / "analysis"),
                "app_investigation_case": str(self.root / "investigation"),
                "flows": [{"id": "example"}]}
        (self.task / "task.json").write_text(json.dumps(task))
        with patch("copyapp.agent_run.verify_case", return_value=True):
            path, success = run_agent_task(self.task, self.root / "review-run",
                                           workspace=self.root,
                                           executable=self.executable)
        self.assertTrue(success)
        record = json.loads(path.read_text())
        self.assertEqual(record["task_kind"], "agent_semantic_review_task")
        self.assertEqual(record["status"], "agent_exited_unverified")
        self.assertIsNone(record["project_dir"])
        self.assertIsNone(record["project_source_changed"])
        self.assertTrue(json.loads((path.parent / "stdout.jsonl").read_text().splitlines()[1])
                        ["prompt_read"])

    def test_verified_analysis_requires_a_report_and_links_delivery(self):
        task = {"kind": "agent_semantic_review_task",
                "status": "needs_semantic_review",
                "analysis_case": str(self.root / "analysis"),
                "app_investigation_case": str(self.root / "investigation"),
                "flows": [{"id": "example"}]}
        (self.task / "task.json").write_text(json.dumps(task))
        self.executable.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, re, sys\n"
            "prompt = sys.stdin.read()\n"
            "target = re.search(r'Save the formal copyapp report at exactly (.*?). Include', prompt)\n"
            "assert target is not None\n"
            "pathlib.Path(target.group(1)).mkdir(parents=True)\n"
            "print(json.dumps({'type': 'thread.started', 'thread_id': 'review-session'}))\n")
        self.executable.chmod(0o755)

        def fake_delivery(task_case, report_case, output, run_case):
            self.assertEqual(task_case, self.task.resolve())
            self.assertEqual(report_case, (self.root / "review-run/reviewed-report").resolve())
            self.assertEqual(output, (self.root / "review-run/analysis-delivery").resolve())
            self.assertEqual(run_case.resolve(), (self.root / "review-run").resolve())
            output.mkdir()
            (output / "manifest.json").write_text('{}')
            (output / "report.md").write_text("verified fixture delivery")

        with patch("copyapp.agent_run.verify_case", return_value=True), \
                patch("copyapp.analysis_delivery.create_analysis_delivery",
                      side_effect=fake_delivery):
            path, success = run_agent_task(self.task, self.root / "review-run",
                                           workspace=self.root, executable=self.executable,
                                           verify_analysis=True)
        self.assertTrue(success)
        self.assertEqual(json.loads((path.parent / "analysis-verification.json").read_text())
                         ["status"], "source_linked_report_ready_for_review")
        self.assertEqual(json.loads(path.read_text())["expected_report_case"],
                         str((self.root / "review-run/reviewed-report").resolve()))

    def test_verified_analysis_does_not_accept_process_exit_without_report(self):
        task = {"kind": "agent_semantic_review_task",
                "status": "needs_semantic_review",
                "analysis_case": str(self.root / "analysis"),
                "app_investigation_case": str(self.root / "investigation"),
                "flows": [{"id": "example"}]}
        (self.task / "task.json").write_text(json.dumps(task))
        with patch("copyapp.agent_run.verify_case", return_value=True):
            path, success = run_agent_task(self.task, self.root / "review-run",
                                           workspace=self.root, executable=self.executable,
                                           verify_analysis=True)
        self.assertFalse(success)
        self.assertEqual(json.loads(path.read_text())["status"], "agent_exited_unverified")
        self.assertEqual(json.loads((path.parent / "analysis-verification.json").read_text())
                         ["status"], "report_missing_or_agent_failed")

    def test_verified_analysis_preserves_rejected_report_diagnostics(self):
        task = {"kind": "agent_semantic_review_task",
                "status": "needs_semantic_review",
                "analysis_case": str(self.root / "analysis"),
                "app_investigation_case": str(self.root / "investigation"),
                "flows": [{"id": "example"}]}
        (self.task / "task.json").write_text(json.dumps(task))
        self.executable.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib, re, sys\n"
            "prompt = sys.stdin.read()\n"
            "path = re.search(r'Save the formal copyapp report at exactly (.*?). Include', prompt)\n"
            "pathlib.Path(path.group(1)).mkdir(parents=True)\n")
        self.executable.chmod(0o755)
        with patch("copyapp.agent_run.verify_case", return_value=True), \
                patch("copyapp.analysis_delivery.create_analysis_delivery",
                      side_effect=ValueError("missing investigated flow")):
            path, success = run_agent_task(self.task, self.root / "review-run",
                                           workspace=self.root, executable=self.executable,
                                           verify_analysis=True)
        self.assertFalse(success)
        status = json.loads((path.parent / "analysis-verification.json").read_text())
        self.assertEqual(status["status"], "analysis_delivery_rejected")
        self.assertIn("missing investigated flow", status["error"]["message"])

    def test_verified_analysis_rejects_implementation_task(self):
        with patch("copyapp.agent_run.verify_case", return_value=True), \
                self.assertRaisesRegex(ValueError, "requires a semantic review"):
            run_agent_task(self.task, self.root / "run", workspace=self.root,
                           executable=self.executable, verify_analysis=True)
        self.assertFalse((self.root / "run").exists())

    def _write_fake_rebuild_agent(self):
        self.executable.write_text(
            "#!/usr/bin/env python3\n"
            "import json, pathlib, re, sys\n"
            "prompt = sys.stdin.read()\n"
            "match = re.search(r'Save the real-device installation case at exactly (.*?) using copyapp install', prompt)\n"
            "assert match is not None\n"
            "base = pathlib.Path(match.group(1)).parent\n"
            "for name in ('install', 'rebuild-check', 'visual-review'):\n"
            "    (base / name).mkdir(parents=True)\n"
            "(base / 'install/install.json').write_text('{}')\n"
            "source = pathlib.Path('rebuild/Clone/Generated.swift')\n"
            "source.parent.mkdir(parents=True, exist_ok=True)\n"
            "source.write_text('struct Generated {}\\n')\n"
            "print(json.dumps({'type': 'thread.started', 'thread_id': 'rebuild-session'}))\n")
        self.executable.chmod(0o755)

    def test_verified_rebuild_links_device_evidence_and_checks_behavior(self):
        task_path = self.task / "task.json"
        task = json.loads(task_path.read_text())
        task["flows"] = [{"id": "one"}]
        task_path.write_text(json.dumps(task))
        self._write_fake_rebuild_agent()

        def fake_delivery(task_case, install_record, check_case, output, run_case,
                          visual_review_case):
            base = (self.root / "rebuild-run").resolve()
            self.assertEqual(task_case, self.task.resolve())
            self.assertEqual(install_record, base / "install/install.json")
            self.assertEqual(check_case, base / "rebuild-check")
            self.assertEqual(output, base / "agent-delivery")
            self.assertEqual(run_case.resolve(), base)
            self.assertEqual(visual_review_case, base / "visual-review")
            output.mkdir()
            (output / "manifest.json").write_text('{}')
            (output / "report.md").write_text("verified fixture delivery")
            (output / "delivery.json").write_text(json.dumps({
                "asserted_flow_count": 1,
                "visual_unreviewed_flow_count": 0,
                "visual_major_difference_flow_count": 0,
                "flow_results": [{"id": "one", "script_assertions_status": "passed",
                                  "final_view_status": "not_configured"}],
            }))

        with patch("copyapp.agent_run.verify_case", return_value=True), \
                patch("copyapp.agent_delivery.create_agent_delivery",
                      side_effect=fake_delivery):
            path, success = run_agent_task(self.task, self.root / "rebuild-run",
                                           workspace=self.root, executable=self.executable,
                                           verify_rebuild=True)
        self.assertTrue(success)
        status = json.loads((path.parent / "rebuild-verification.json").read_text())
        self.assertEqual(status["status"], "selected_flows_verified")
        self.assertTrue(status["behavior_assertions_passed"])

    def test_verified_rebuild_keeps_major_visual_gap_open(self):
        task_path = self.task / "task.json"
        task = json.loads(task_path.read_text())
        task["flows"] = [{"id": "one"}]
        task_path.write_text(json.dumps(task))
        self._write_fake_rebuild_agent()

        def fake_delivery(*args):
            output = args[3]
            output.mkdir()
            (output / "manifest.json").write_text('{}')
            (output / "delivery.json").write_text(json.dumps({
                "asserted_flow_count": 1,
                "visual_unreviewed_flow_count": 0,
                "visual_major_difference_flow_count": 1,
                "flow_results": [{"id": "one", "script_assertions_status": "passed"}],
            }))

        with patch("copyapp.agent_run.verify_case", return_value=True), \
                patch("copyapp.agent_delivery.create_agent_delivery",
                      side_effect=fake_delivery):
            path, success = run_agent_task(self.task, self.root / "rebuild-run",
                                           workspace=self.root, executable=self.executable,
                                           verify_rebuild=True)
        self.assertFalse(success)
        self.assertEqual(json.loads((path.parent / "rebuild-verification.json").read_text())
                         ["status"], "selected_flow_gaps_remain")

    def test_verified_rebuild_requires_device_evidence(self):
        task_path = self.task / "task.json"
        task = json.loads(task_path.read_text())
        task["flows"] = [{"id": "one"}]
        task_path.write_text(json.dumps(task))
        with patch("copyapp.agent_run.verify_case", return_value=True):
            path, success = run_agent_task(self.task, self.root / "rebuild-run",
                                           workspace=self.root, executable=self.executable,
                                           verify_rebuild=True)
        self.assertFalse(success)
        self.assertEqual(json.loads((path.parent / "rebuild-verification.json").read_text())
                         ["status"], "rebuild_evidence_missing_or_agent_failed")

    def test_verified_rebuild_rejects_semantic_review_task(self):
        task = {"kind": "agent_semantic_review_task",
                "status": "needs_semantic_review",
                "analysis_case": str(self.root / "analysis"),
                "app_investigation_case": str(self.root / "investigation"),
                "flows": [{"id": "example"}]}
        (self.task / "task.json").write_text(json.dumps(task))
        with patch("copyapp.agent_run.verify_case", return_value=True), \
                self.assertRaisesRegex(ValueError, "requires an implementation task"):
            run_agent_task(self.task, self.root / "run", workspace=self.root,
                           executable=self.executable, verify_rebuild=True)

    def test_semantic_review_rejects_external_source_case(self):
        task = {"kind": "agent_semantic_review_task",
                "status": "needs_semantic_review",
                "analysis_case": "/private/tmp/outside-analysis",
                "app_investigation_case": str(self.root / "investigation"),
                "flows": [{"id": "example"}]}
        (self.task / "task.json").write_text(json.dumps(task))
        with patch("copyapp.agent_run.verify_case", return_value=True), \
                self.assertRaisesRegex(ValueError, "outside workspace"):
            run_agent_task(self.task, self.root / "review-run", workspace=self.root,
                           executable=self.executable)
        self.assertFalse((self.root / "review-run").exists())


if __name__ == "__main__":
    unittest.main()
