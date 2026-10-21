"""Actual local collector file tests, explicitly not live guest acceptance."""

import hashlib
import json
import os
import plistlib
import sqlite3
import tempfile
from pathlib import Path

from copyapp.macos.case import canonical
from copyapp.macos.data import data_file, source_path
from copyapp.macos.data_schema import data_schema
from copyapp.verify import verify_case


def exercise_data_capture(test, root, acquisition):
    # Only a uniquely owned temporary support folder is created. No existing
    # App preferences or containers are changed, and no TCC grant is requested.
    support = Path.home() / "Library/Application Support"
    with tempfile.TemporaryDirectory(prefix="CopyAppFixture-", dir=support) as directory:
        folder = Path(directory)
        data = b"copyapp-owned-fixture\n\x00\xff"
        (folder / "payload.bin").write_bytes(data)
        relative = folder.name + "/payload.bin"
        captured = data_file(acquisition, "support", relative, root / "selected-data")
        test.assertTrue(verify_case(captured))
        test.assertEqual((captured / "data.bin").read_bytes(), data)
        record = json.loads((captured / "data-file.json").read_text())
        test.assertFalse(record["atomic_database_snapshot"])
        test.assertFalse(record["complete_app_data"])
        test.assertEqual(record["association"], "explicit_path_not_proof_of_app_ownership")
        test.assertEqual(record["size"], len(data))
        test.assertTrue((captured / "export.json").is_file())
        schemas = {}
        private = "PRIVATE-SCALAR-AND-ROW-CONTENT"
        preference = {"editor": {"wrap": True, "fontSize": 14, "lastDocument": private},
                      "recent": [{"title": private}], "blob": private.encode()}
        for name, fmt in (("binary", plistlib.FMT_BINARY), ("xml", plistlib.FMT_XML)):
            (folder / (name + ".plist")).write_bytes(plistlib.dumps(preference, fmt=fmt))
            saved = data_file(acquisition, "support", folder.name + "/" + name + ".plist", root / (name + "-plist-data"))
            schema = data_schema(saved, "plist", root / (name + "-plist-structure"))
            test.assertTrue(verify_case(schema))
            test.assertNotIn(private, (schema / "structure.json").read_text())
            test.assertNotIn(private, (schema / "schema.md").read_text())
            fields = json.loads((schema / "structure.json").read_text())["fields"]
            test.assertIn({"path": "/editor/wrap", "type": "boolean"}, fields)
            test.assertIn({"path": "/recent/*/title", "type": "string"}, fields)
            if name == "binary": schemas["preferences"] = schema
        database = folder / "store.sqlite"
        with sqlite3.connect(database) as db:
            db.executescript('''CREATE TABLE parent (id INTEGER PRIMARY KEY);
                CREATE TABLE document (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id),
                    title TEXT DEFAULT 'PRIVATE-SCALAR-AND-ROW-CONTENT', payload BLOB);
                CREATE INDEX title_index ON document(title);
                CREATE VIEW visible_documents AS SELECT title FROM document;
                CREATE TRIGGER changed AFTER UPDATE ON document BEGIN
                    SELECT 'PRIVATE-SCALAR-AND-ROW-CONTENT'; END;
                CREATE TABLE "weird""name" ("quoted""column" TEXT);
                PRAGMA user_version=3;''')
            db.execute("INSERT INTO document(title) VALUES (?)", (private,))
        saved_db = data_file(acquisition, "support", folder.name + "/store.sqlite", root / "sqlite-data")
        schemas["store"] = data_schema(saved_db, "sqlite", root / "sqlite-structure")
        test.assertTrue(verify_case(schemas["store"]))
        for path in ("structure.json", "schema.md"):
            test.assertNotIn(private, (schemas["store"] / path).read_text())
        structured = json.loads((schemas["store"] / "structure.json").read_text())
        test.assertEqual(structured["user_version"], 3)
        document = next(row for row in structured["tables"] if row["name"] == "document")
        test.assertEqual(document["foreign_keys"], [{"from": "parent_id", "to": "id", "referenced_table": "parent"}])
        test.assertIn('weird"name', [row["name"] for row in structured["tables"]])
        for kind in ("plist", "sqlite"):
            with test.assertRaises(ValueError):
                data_schema(captured, kind, root / ("invalid-" + kind))
            test.assertFalse(verify_case(root / ("invalid-" + kind)))
            test.assertTrue((root / ("invalid-" + kind) / "failure.json").is_file())
        # A second valid registration/acquisition has a different environment
        # manifest even though the machine and App bytes are the same.
        from copyapp.macos.environment import register_environment
        from copyapp.macos.acquire import acquire_app
        registered = json.loads((acquisition / "environment/environment.json").read_text())
        target = json.loads((acquisition / "acquisition.json").read_text())
        alternate_environment = register_environment(Path(registered["vm_directory"]),
            acquisition / "environment/collector-build", root / "alternate-environment",
            registered["chatcomputer"]["path"], timeout=5)
        alternate_acquisition = acquire_app(alternate_environment, target["guest_app_path"], target["bundle_id"],
                                           root / "alternate-acquisition", timeout=5)
        alternate_data = data_file(alternate_acquisition, "support", folder.name + "/binary.plist", root / "alternate-data")
        alternate_schema = data_schema(alternate_data, "plist", root / "alternate-schema")
        test.assertTrue(verify_case(alternate_schema))
        (folder / "empty").write_bytes(b"")
        empty = data_file(acquisition, "support", folder.name + "/empty", root / "empty-data")
        test.assertTrue(verify_case(empty))
        (folder / "linked.bin").symlink_to("payload.bin")
        os.mkfifo(folder / "fifo")
        with (folder / "oversized").open("wb") as stream: stream.truncate((64 << 20) + 1)
        for name in ("linked.bin", "fifo", "oversized", "absent"):
            failed = root / ("failed-data-" + name.replace(".", "-"))
            with test.assertRaises(RuntimeError):
                data_file(acquisition, "support", folder.name + "/" + name, failed, timeout=5)
            test.assertFalse(verify_case(failed))
            test.assertTrue((failed / "failed-collector-request.json").is_file())
        for location, relative in (("sandbox", "../outside"), ("sandbox", "."), ("sandbox", "/absolute"),
                                   ("preferences", "another.app.plist"), ("support", "folder"), ("home", "file")):
            with test.assertRaises(ValueError):
                source_path(location, relative, "dev.copyapp.MacCollector", "/guest/Library")

        def rejects_rehashed(relative, change):
            path, manifest_path = captured / relative, captured / "manifest.json"
            original, original_manifest = path.read_bytes(), manifest_path.read_bytes()
            value = json.loads(original)
            change(value)
            path.write_bytes(canonical(value))
            manifest = json.loads(original_manifest)
            for item in manifest["evidence"]:
                if item["path"] == relative: item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_bytes(canonical(manifest))
            try: test.assertFalse(verify_case(captured), relative)
            finally:
                path.write_bytes(original)
                manifest_path.write_bytes(original_manifest)

        rejects_rehashed("data-file.json", lambda value: value.update(atomic_database_snapshot=True))
        rejects_rehashed("data-file.json", lambda value: value.update(association="app_ownership_verified"))
        rejects_rehashed("session-health.json", lambda value: value["response"]["result"].update(capabilities=[]))
        rejects_rehashed("export.json", lambda value: value["response"]["result"].update(guest_source_path="/unrelated/private"))
        path = captured / "data.bin"
        original = path.read_bytes()
        path.write_bytes(b"changed file")
        test.assertFalse(verify_case(captured))
        path.write_bytes(original)
        (folder / "payload.bin").write_bytes(b"later data")
        test.assertTrue(verify_case(captured))  # Saved evidence has no mutable-home dependency.
    return schemas


def exercise_schema_report(test, root, flows, review, schemas):
    from copyapp.macos.report import report
    from copyapp.macos.rebuild import rebuild_plan
    from copyapp.macos.case import digest
    reviewed = json.loads(canonical(review))
    for source_id in schemas:
        reviewed["findings"].append({"id": "data-" + source_id, "certainty": "observed",
                                     "statement": "The saved fixture has the cited structure; ownership is not proven.",
                                     "evidence": [{"data_id": source_id, "path": "structure.json"}]})
    path = root / "review-with-data.json"
    path.write_bytes(canonical(reviewed))
    combined = report(flows, path, root / "report-with-data", data=schemas)
    test.assertTrue(verify_case(combined))
    test.assertIn("data-evidence/preferences/structure.json", (combined / "report.md").read_text())
    test.assertIn("simultaneous UI/file", (combined / "report.md").read_text())
    test.assertEqual(len(json.loads((combined / "data-sources.json").read_text())), 2)
    environment = json.loads((root / "environment/environment.json").read_text())
    plan = rebuild_plan(combined, "dev.copyapp.DataClone", environment["install_root"] + "/DataIndependent.app",
                        root / "data-clone-project", ["editing"], root / "data-plan")
    test.assertTrue(verify_case(plan))
    invalid = json.loads(canonical(reviewed))
    invalid["findings"][-1]["evidence"][0]["path"] = "source/data.bin"
    path.write_bytes(canonical(invalid))
    with test.assertRaisesRegex(ValueError, "structure.json"):
        report(flows, path, root / "raw-data-report", data=schemas)
    invalid = json.loads(canonical(reviewed))
    invalid["flows"][0]["findings"] = ["data-preferences"]
    path.write_bytes(canonical(invalid))
    with test.assertRaisesRegex(ValueError, "no matching reviewed source"):
        report(flows, path, root / "data-only-flow-report", data=schemas)
    path.write_bytes(canonical(reviewed))
    with test.assertRaisesRegex(ValueError, "unknown flow|supplied verified"):
        report(flows, path, root / "missing-data-report")
    with test.assertRaisesRegex(ValueError, "same exact App"):
        report(flows, path, root / "different-data-environment-report",
               data={**schemas, "preferences": root / "alternate-schema"})
    # Refreshing artifact hashes must not make source/structure claims true.
    cases = [(combined, "data-sources.json", lambda value: value[0].update(package_sha256="0" * 64)),
             (schemas["preferences"], "data-schema.json", lambda value: value.update(atomic_database_snapshot=True)),
             (schemas["store"], "structure.json", lambda value: value.update(user_version=99)),
             (combined, "citations.json", lambda value: value[-1].update(sha256="0" * 64))]
    for case, relative, change in cases:
        artifact, manifest_path = case / relative, case / "manifest.json"
        original, original_manifest = artifact.read_bytes(), manifest_path.read_bytes()
        value = json.loads(original)
        change(value)
        artifact.write_bytes(canonical(value))
        manifest = json.loads(original_manifest)
        for item in manifest["evidence"]:
            if item["path"] == relative: item["sha256"] = digest(artifact)
        manifest_path.write_bytes(canonical(manifest))
        try: test.assertFalse(verify_case(case), relative)
        finally:
            artifact.write_bytes(original)
            manifest_path.write_bytes(original_manifest)
    test.assertTrue(verify_case(combined))
