import json
import tempfile
import unittest
from pathlib import Path

from copyapp.sandbox_diff import compare_sandbox
from copyapp.verify import sha256_file, verify_case


class SandboxDiffTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.before = self._snapshot("before.json", [{
            "relative": "Documents/notes.sqlite", "kind": "f", "size": 4096,
            "modified_epoch": 100.0}])
        self.after = self._snapshot("after.json", [{
            "relative": "Documents/notes.sqlite", "kind": "f", "size": 8192,
            "modified_epoch": 101.0}, {
            "relative": "Documents/notes.sqlite-wal", "kind": "f", "size": 128,
            "modified_epoch": 101.0}])

    def _snapshot(self, name, entries):
        path = self.root / name
        path.write_text(json.dumps({"schema_version": 1,
            "source": "read-only SSH find metadata through USB tunnel",
            "device_id_sha256_prefix": "device01", "bundle_id": "dev.example.notes",
            "container_path_sha256_prefix": "container01", "installed_version": "1.0",
            "installed_build": "1", "depth_limit": 8, "entries": entries}))
        return path

    def test_retains_verifiable_metadata_change_with_limits(self):
        output = self.root / "comparison"
        report = compare_sandbox(self.before, self.after, output)
        result = json.loads((output / "changes.json").read_text())
        self.assertEqual(result["counts"], {"added": 1, "removed": 0,
                                            "metadata_changed": 1})
        self.assertIn("不证明内容变化", report.read_text())
        self.assertTrue(verify_case(output))
        (output / "after.json").write_text("tampered")
        self.assertFalse(verify_case(output))

    def test_rejects_different_container_and_device(self):
        data = json.loads(self.after.read_text())
        data["container_path_sha256_prefix"] = "different"
        self.after.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "container changed"):
            compare_sandbox(self.before, self.after, self.root / "comparison")
        data["container_path_sha256_prefix"] = "container01"
        data["device_id_sha256_prefix"] = "different"
        self.after.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "device_id_sha256_prefix"):
            compare_sandbox(self.before, self.after, self.root / "comparison")

    def test_rejects_duplicate_path(self):
        data = json.loads(self.after.read_text())
        data["entries"].append(data["entries"][0])
        self.after.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "repeated sandbox path"):
            compare_sandbox(self.before, self.after, self.root / "comparison")

    def test_action_must_be_verified_and_between_captures(self):
        for path, at in ((self.before, "2026-01-01T00:00:00+00:00"),
                         (self.after, "2026-01-01T00:00:10+00:00")):
            data = json.loads(path.read_text())
            data["captured_at"] = at
            path.write_text(json.dumps(data))
        action = self.root / "action"
        action.mkdir()
        (action / "playbook.json").write_text('{"steps": []}')
        manifest = {"schema_version": 1, "status": "complete",
                    "bundle_id": "dev.example.notes", "device_id_sha256_prefix": "device01",
                    "started_at": "2026-01-01T00:00:02+00:00",
                    "finished_at": "2026-01-01T00:00:04+00:00",
                    "evidence": [{"path": "playbook.json",
                                  "sha256": sha256_file(action / "playbook.json")}]}
        (action / "manifest.json").write_text(json.dumps(manifest))
        output = self.root / "comparison"
        compare_sandbox(self.before, self.after, output, action)
        self.assertTrue(verify_case(output))
        manifest["started_at"] = "2025-12-31T23:59:59+00:00"
        (action / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "outside the before/after"):
            compare_sandbox(self.before, self.after, self.root / "invalid", action)


if __name__ == "__main__":
    unittest.main()
