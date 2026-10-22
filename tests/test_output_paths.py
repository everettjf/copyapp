import asyncio
import tempfile
import unittest
from pathlib import Path

from copyapp.copy_workflow import copy_app
from copyapp.output_paths import copy_paths


class OutputPathsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_default_jobs_are_distinct_contained_and_do_not_create_files(self):
        first = copy_paths("../../com.example/app", workspace=self.root)
        second = copy_paths("../../com.example/app", workspace=self.root)
        workspace, evidence, project = first
        self.assertEqual(workspace, self.root)
        self.assertEqual(evidence.parent, project.parent)
        self.assertEqual(evidence.name, "evidence")
        self.assertEqual(project.name, "project")
        self.assertEqual(evidence.parent.parent, self.root / "output")
        self.assertNotEqual(first, second)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_custom_and_legacy_overrides_preserved(self):
        job = self.root / "My job"
        self.assertEqual(copy_paths("app", workspace=self.root, output_dir=job),
                         (self.root, job / "evidence", job / "project"))
        evidence, project = self.root / "cases/old", self.root / "rebuild/Old"
        self.assertEqual(copy_paths("app", workspace=self.root, output=evidence,
                                    project=project, resume=True),
                         (self.root, evidence, project))
        self.assertEqual(copy_paths("app", workspace=self.root, output_dir=job,
                                    project=project)[2], project)

    def test_resume_requires_explicit_previous_job_and_reuses_paths(self):
        with self.assertRaisesRegex(ValueError, "previous"):
            copy_paths("app", workspace=self.root, resume=True)
        job = self.root / "output/job"
        self.assertEqual(copy_paths("app", workspace=self.root, output_dir=job),
                         copy_paths("app", workspace=self.root, output_dir=job, resume=True))

    def test_invalid_overrides_rejected_without_mutation(self):
        for settings in (
            {"output": self.root / "case"},
            {"output": self.root / "case", "output_dir": self.root / "job"},
            {"output_dir": self.root.parent / "outside"},
            {"output_dir": self.root / "job", "project": self.root / "job/evidence/source"},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                copy_paths("app", workspace=self.root, **settings)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_current_agent_default_handoff_and_resume_preserve_existing_evidence(self):
        workspace, evidence, project = copy_paths("com.example.app", workspace=self.root)

        async def no_survey(*args):
            self.fail("discovery handoff must not touch the device")

        def run(resume=False):
            return asyncio.run(copy_app("device", "com.example.app", [], project,
                "com.example.clone", evidence, no_survey, workspace=workspace,
                agent_provider="current", auto_discover=True, resume=resume))

        task, complete = run()
        self.assertFalse(complete)
        self.assertEqual(task, evidence / "discovery-agent/TASK.md")
        before = task.read_bytes()
        self.assertEqual(run(True), (task, False))
        self.assertEqual(task.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            run()
        self.assertEqual(task.read_bytes(), before)
