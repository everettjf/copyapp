import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from copyapp.sqlite_schema import create_sqlite_schema
from copyapp.verify import sha256_file, verify_case


class SqliteSchemaTest(unittest.TestCase):
    def _source(self, root: Path) -> tuple[Path, Path]:
        source = root / "source"
        source.mkdir()
        db_file = source / "notes.sqlite"
        with sqlite3.connect(db_file) as db:
            db.executescript("CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT NOT NULL);"
                             "CREATE INDEX notes_title ON notes(title);")
            db.execute("INSERT INTO notes(title) VALUES (?)", ("private row value",))
        (source / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "captured_data",
            "evidence": [{"path": "notes.sqlite", "sha256": sha256_file(db_file)}],
        }))
        return source, db_file

    def test_schema_has_provenance_and_no_row_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, db_file = self._source(root)
            output = root / "schema"
            create_sqlite_schema(source, "notes.sqlite", output)
            record = json.loads((output / "schema.json").read_text())
            self.assertEqual(record["source_sha256"], sha256_file(db_file))
            self.assertEqual(record["schema"]["tables"][0]["name"], "notes")
            self.assertEqual([item["name"] for item in record["schema"]["tables"][0]["columns"]],
                             ["id", "title"])
            self.assertNotIn("private row value", (output / "schema.json").read_text())
            self.assertNotIn("private row value", (output / "report.md").read_text())
            self.assertTrue(verify_case(output))

    def test_source_change_and_rehashed_schema_forgery_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, db_file = self._source(root)
            output = root / "schema"
            create_sqlite_schema(source, "notes.sqlite", output)
            schema_path = output / "schema.json"
            changed = json.loads(schema_path.read_text())
            changed["schema"]["tables"][0]["columns"][0]["name"] = "forged"
            schema_path.write_text(json.dumps(changed))
            manifest = json.loads((output / "manifest.json").read_text())
            manifest["evidence"][0]["sha256"] = sha256_file(schema_path)
            (output / "manifest.json").write_text(json.dumps(manifest))
            self.assertFalse(verify_case(output))
            create_sqlite_schema(source, "notes.sqlite", root / "another")
            with sqlite3.connect(db_file) as db:
                db.execute("CREATE TABLE added (value TEXT)")
            self.assertFalse(verify_case(root / "another"))

    def test_unrecorded_db_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, _ = self._source(root)
            (source / "extra.sqlite").write_bytes(b"SQLite format 3\0")
            with self.assertRaisesRegex(ValueError, "recorded source artifact"):
                create_sqlite_schema(source, "extra.sqlite", root / "schema")

    def test_detached_wal_mode_database_is_read_without_sidecars(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, db_file = self._source(root)
            with sqlite3.connect(db_file) as db:
                self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            manifest = json.loads((source / "manifest.json").read_text())
            manifest["evidence"][0]["sha256"] = sha256_file(db_file)
            (source / "manifest.json").write_text(json.dumps(manifest))
            output = root / "schema"
            create_sqlite_schema(source, "notes.sqlite", output)
            self.assertTrue(verify_case(output))
            self.assertEqual(json.loads((output / "schema.json").read_text())["schema"]["tables"][0]["name"],
                             "notes")


if __name__ == "__main__":
    unittest.main()
