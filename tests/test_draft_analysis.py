import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from copyapp.draft_analysis import (_entry, _observed_conditions,
                                    _review_task, _upper_uikit_labels)


class DraftAnalysisTest(unittest.TestCase):
    def test_review_task_accepts_no_rea_and_no_trace(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, analysis, investigation = [root / name for name in
                                               ("draft", "analysis", "investigation")]
            copied = output / "report/evidence/app.all/flows/flow-01"
            for path in [analysis / "analysis-index.json",
                         investigation / "manifest.json",
                         output / "report/report-index.json",
                         copied / "flow/playbook/playbook.json",
                         copied / "flow/view-tree/view-tree.json",
                         copied / "flow/view-tree/screenshot.jpg"]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            specs = [{"id": "example", "entry": "点按按钮", "expected": ["显示结果"],
                      "source_script_sha256": "a" * 64}]
            _review_task(output, analysis, investigation, "dev.example", "a" * 16,
                         specs, {"flows": [{}]})
            task = json.loads((output / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(task["flows"][0]["pseudocode"], [])
            self.assertFalse(any("/rea/" in path or "/trace/" in path for path in
                                 task["flows"][0]["evidence_paths"]))

    def test_review_task_links_copied_pseudocode_and_requires_new_report(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, analysis, investigation = [root / name for name in
                                               ("draft", "analysis", "investigation")]
            copied = output / "report/evidence/app.all/flows/flow-01"
            for path in [analysis / "analysis-index.json",
                         investigation / "manifest.json",
                         investigation / "flows/flow-01/rea/queue.json",
                         output / "report/report-index.json",
                         output / "report/report.md",
                         output / "feature-spec.json",
                         copied / "flow/playbook/playbook.json",
                         copied / "flow/view-tree/view-tree.json",
                         copied / "flow/view-tree/screenshot.jpg",
                         copied / "flow/trace/trace.json",
                         copied / "rea/queue.json",
                         copied / "rea/targets/01/pseudocode.txt"]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            queue = {"results": [{"status": "complete", "address": "0x1000",
                                  "evidence_id": "ev_example",
                                  "summary": "targets/01/summary.json"}]}
            (investigation / "flows/flow-01/rea/queue.json").write_text(
                json.dumps(queue), encoding="utf-8")
            specs = [{"id": "example", "entry": "点按按钮", "expected": ["显示结果"],
                      "source_script_sha256": "a" * 64}]
            _review_task(output, analysis, investigation, "dev.example", "a" * 16,
                         specs, {"flows": [{}]})
            task = json.loads((output / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(task["status"], "needs_semantic_review")
            self.assertEqual(task["flows"][0]["pseudocode"][0]["address"], "0x1000")
            self.assertTrue((output / task["flows"][0]["pseudocode"][0]["path"]).is_file())
            brief = (output / "TASK.md").read_text(encoding="utf-8")
            self.assertIn("findings.json", brief)
            self.assertIn("copyapp report", brief)

    def test_uses_only_explicitly_checked_ui_conditions(self):
        plan = {"steps": [
            {"action": "tap_label", "label": "Notes"},
            {"action": "observe", "contains": "Add sample note",
             "capture_number": {"name": "count", "pattern": "Saved: ([0-9]+)"}},
            {"action": "tap_label", "label": "Add sample note"},
            {"action": "observe", "compare_number": {
                "to": "count", "pattern": "Saved: ([0-9]+)", "delta": 1}},
            {"action": "expect_foreground", "bundle_id": "com.apple.Maps"},
        ]}
        playbook = {"steps": [
            {"index": 1, "action": "tap_label"},
            {"index": 2, "action": "observe", "visible_text": "Add sample note\nPrivate note"},
            {"index": 3, "action": "tap_label"},
            {"index": 4, "action": "observe", "visible_text": "Private note",
             "number_comparison": {"before": 5, "after": 6, "delta": 1}},
            {"index": 5, "action": "expect_foreground"},
        ]}
        conditions = _observed_conditions(plan, playbook)
        self.assertEqual(conditions, [
            "步骤 2 可见预设文字：Add sample note",
            "步骤 4 的捕获数字相对前值变化 1（本次 5→6）",
            "步骤 5 到达 `com.apple.Maps` 前台",
        ])
        self.assertNotIn("Private note", "\n".join(conditions))
        self.assertEqual(_entry(plan), "点按 Notes；点按 Add sample note")

    def test_upper_label_candidates_do_not_promote_keypad_text(self):
        tree = {"nodes": [
            {"id": 0, "parent": None, "class_name": "UIWindow",
             "frame": {"x": 0, "y": 0, "width": 414, "height": 896},
             "hidden": False, "alpha": 1},
            {"id": 1, "parent": 0, "class_name": "UILabel", "text": "9",
             "frame": {"x": 320, "y": 200, "width": 50, "height": 110},
             "hidden": False, "alpha": 1},
            {"id": 2, "parent": 0, "class_name": "UILabel", "text": "9",
             "frame": {"x": 220, "y": 440, "width": 50, "height": 60},
             "hidden": False, "alpha": 1},
        ]}
        self.assertEqual([item["node_id"] for item in _upper_uikit_labels(tree, 896)], [1])


if __name__ == "__main__":
    unittest.main()
