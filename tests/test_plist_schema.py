import json
import plistlib
import tempfile
import unittest
from pathlib import Path

from copyapp.plist_schema import create_plist_schema
from copyapp.report import _validate_plist_schema
from copyapp.verify import sha256_file, verify_case


class PlistSchemaTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.file = self.source / "preferences.plist"
        self.file.write_bytes(plistlib.dumps({
            "fixture.counter": 12,
            "privateToken": "never-export-this-value",
            "profiles": [{"name": "Alice", "enabled": True},
                         {"name": "Bob", "enabled": False}],
        }))
        (self.source / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "captured_data",
            "evidence": [{"path": self.file.name, "sha256": sha256_file(self.file)}]}))

    def test_only_key_paths_and_types_are_exported(self):
        output = self.root / "schema"
        create_plist_schema(self.source, self.file.name, output)
        profile = json.loads((output / "profile.json").read_text())
        fields = {(item["path"], item["type"])
                  for item in profile["structure"]["fields"]}
        self.assertIn(("/fixture.counter", "integer"), fields)
        self.assertIn(("/profiles/*/enabled", "boolean"), fields)
        self.assertEqual(profile["structure"]["root_type"], "dictionary")
        for path in (output / "profile.json", output / "report.md"):
            text = path.read_text()
            self.assertNotIn("never-export-this-value", text)
            self.assertNotIn("Alice", text)
            self.assertNotIn("Bob", text)
        self.assertTrue(verify_case(output))

    def test_rehashed_structure_forgery_and_changed_source_are_rejected(self):
        output = self.root / "schema"
        create_plist_schema(self.source, self.file.name, output)
        profile_path = output / "profile.json"
        profile = json.loads(profile_path.read_text())
        profile["structure"]["fields"][0]["type"] = "forged"
        profile_path.write_text(json.dumps(profile))
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["evidence"][0]["sha256"] = sha256_file(profile_path)
        manifest_path.write_text(json.dumps(manifest))
        self.assertFalse(verify_case(output))
        another = self.root / "another"
        create_plist_schema(self.source, self.file.name, another)
        self.file.write_bytes(plistlib.dumps({"fixture.counter": 13}))
        self.assertFalse(verify_case(another))

    def test_unrecorded_file_is_rejected(self):
        extra = self.source / "unrecorded.plist"
        extra.write_bytes(plistlib.dumps({"x": "y"}))
        with self.assertRaisesRegex(ValueError, "recorded source artifact"):
            create_plist_schema(self.source, extra.name, self.root / "schema")

    def test_report_import_requires_same_analysis_identity(self):
        report_source = self.root / "source-report"
        report_source.mkdir()
        captured = report_source / self.file.name
        captured.write_bytes(self.file.read_bytes())
        report_source.joinpath("report-index.json").write_text(json.dumps({
            "target_bundle_id": "dev.copyapp.fixture",
            "source_case_index_sha256": "a" * 64,
            "artifacts": {"plist": {"path": self.file.name,
                                     "sha256": sha256_file(captured)}}}))
        output = self.root / "from-report"
        create_plist_schema(report_source, self.file.name, output)
        self.assertEqual(_validate_plist_schema(output, "dev.copyapp.fixture", "a" * 64)
                         ["record"]["structure"]["root_type"], "dictionary")
        with self.assertRaisesRegex(ValueError, "another app or analysis"):
            _validate_plist_schema(output, "dev.copyapp.fixture", "b" * 64)


if __name__ == "__main__":
    unittest.main()
