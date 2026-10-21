"""Actual local collector file tests, explicitly not live guest acceptance."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from copyapp.macos.case import canonical
from copyapp.macos.data import data_file, source_path
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
