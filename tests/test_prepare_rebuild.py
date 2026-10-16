import json
import tempfile
import unittest
from pathlib import Path

from copyapp.prepare_rebuild import prepare_rebuild
from copyapp.verify import sha256_file, verify_case


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


class PrepareRebuildTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.report = self.root / "report"
        self.output = self.root / "prepared"
        write(self.report / "feature-spec.json", {
            "schema_version": 1, "target_bundle_id": "com.example.original",
            "rebuilt_bundle_id": "com.example.clone", "minimum_ios": "16.0",
            "flows": [{"id": "one", "entry": "launch", "expected": ["ready"],
                       "verification": "screen", "evidence": []}],
        })
        (self.report / "report.md").write_text("# Reviewed\n", encoding="utf-8")
        artifacts = {}
        for path in self.report.rglob("*"):
            if path.is_file():
                name = str(path.relative_to(self.report))
                artifacts[name] = {"path": name, "sha256": sha256_file(path)}
        write(self.report / "report-index.json", {
            "schema_version": 1, "target_bundle_id": "com.example.original",
            "evidence": {}, "artifacts": artifacts,
        })

    def test_resume_reuses_verified_plan_and_task(self):
        _, ready = prepare_rebuild(self.report, self.output, flow_ids=["one"])
        self.assertFalse(ready)  # A reviewed report without a cited UI script needs evidence.
        self.assertTrue(verify_case(self.output))
        before = [sha256_file(self.output / name) for name in
                  ("plan/manifest.json", "task/manifest.json")]
        _, ready = prepare_rebuild(self.report, self.output, flow_ids=["one"], resume=True)
        self.assertFalse(ready)
        self.assertEqual(before, [sha256_file(self.output / name) for name in
                                  ("plan/manifest.json", "task/manifest.json")])
        self.assertFalse((self.output / "attempts").exists())

    def test_changed_selection_rejected_before_mutation(self):
        prepare_rebuild(self.report, self.output, flow_ids=["one"])
        before = (self.output / "manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "selection or settings differ"):
            prepare_rebuild(self.report, self.output, flow_ids=["one"],
                            backend="ictrl", resume=True)
        self.assertEqual(before, (self.output / "manifest.json").read_bytes())

    def test_tampered_task_is_archived_then_rebuilt(self):
        prepare_rebuild(self.report, self.output, flow_ids=["one"])
        task_file = self.output / "task/task.json"
        task_file.write_text("{}\n", encoding="utf-8")
        prepare_rebuild(self.report, self.output, flow_ids=["one"], resume=True)
        self.assertTrue(verify_case(self.output))
        self.assertEqual(json.loads(task_file.read_text())["status"], "needs_evidence")
        archived = list((self.output / "attempts").glob("task-*/task.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_text(), "{}\n")


if __name__ == "__main__":
    unittest.main()
