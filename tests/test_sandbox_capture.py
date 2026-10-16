import asyncio
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.sandbox_capture import (_relative, capture_sandbox_files,
                                     validate_sandbox_file_capture)
from copyapp.sqlite_schema import create_sqlite_schema
from copyapp.report import _validate_sqlite_schema
from copyapp.verify import sha256_file, verify_case


class _Device:
    async def close(self):
        return None


class _Proxy:
    def __init__(self, device, app):
        self.app = app

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get_apps(self, **_):
        return {"dev.copyapp.fixture": self.app}


class SandboxCaptureTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.udid = "known-device"
        self.prefix = hashlib.sha256(self.udid.encode()).hexdigest()[:16]
        self.container = "/var/mobile/Containers/Data/Application/12345678-1234-1234-1234-123456789abc"
        self.app = {"Container": self.container, "CFBundleShortVersionString": "1.0",
                    "CFBundleVersion": "1"}
        self.source_file = self.root / "live.sqlite"
        with sqlite3.connect(self.source_file) as db:
            db.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, secret TEXT)")
            db.execute("INSERT INTO notes(secret) VALUES ('private row content')")
        self.analysis = self.root / "analysis"
        (self.analysis / "survey").mkdir(parents=True)
        (self.analysis / "survey/manifest.json").write_text(json.dumps({
            "schema_version": 1, "bundle_id": "dev.copyapp.fixture",
            "device_id_sha256_prefix": self.prefix, "evidence": []}))
        sandbox = {"schema_version": 1,
                   "source": "read-only SSH find metadata through USB tunnel",
                   "bundle_id": "dev.copyapp.fixture",
                   "device_id_sha256_prefix": self.prefix,
                   "container_path_sha256_prefix": hashlib.sha256(
                       self.container.encode()).hexdigest()[:16],
                   "installed_version": "1.0", "installed_build": "1",
                   "entries": [{"relative": "Documents", "kind": "d", "size": 0},
                               {"relative": "Documents/notes.sqlite", "kind": "f",
                                "size": self.source_file.stat().st_size}]}
        (self.analysis / "sandbox-index.json").write_text(json.dumps(sandbox))
        (self.analysis / "analysis-index.json").write_text(json.dumps({
            "schema_version": 1, "artifacts": {"sandbox": {
                "path": "sandbox-index.json",
                "sha256": sha256_file(self.analysis / "sandbox-index.json")}}}))

    def _capture(self, app=None):
        async def device(*_, **__):
            return _Device()

        def stream(_argv, _container, _relative, destination, size):
            body = self.source_file.read_bytes()
            self.assertEqual(size, len(body))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
            return sha256_file(destination)

        selected_app = self.app if app is None else app
        with patch("copyapp.sandbox_capture.create_using_usbmux", device), \
             patch("copyapp.sandbox_capture.InstallationProxyService",
                   lambda device: _Proxy(device, selected_app)), \
             patch("copyapp.sandbox_capture._ssh_argv", return_value=["ssh"]), \
             patch("copyapp.sandbox_capture._stream_file", side_effect=stream):
            return asyncio.run(capture_sandbox_files(
                self.udid, self.analysis, ["Documents/notes.sqlite"],
                self.root / "capture", 22222, self.root / "identity",
                self.root / "known-hosts", "mobile"))

    def test_captured_database_drives_schema_without_exporting_rows(self):
        self._capture()
        captured = self.root / "capture"
        self.assertTrue(verify_case(captured))
        create_sqlite_schema(captured, "files/Documents/notes.sqlite",
                             self.root / "schema")
        self.assertTrue(verify_case(self.root / "schema"))
        checked = _validate_sqlite_schema(self.root / "schema", "dev.copyapp.fixture",
                                          sha256_file(self.analysis / "analysis-index.json"))
        self.assertEqual(checked["record"]["schema"]["tables"][0]["name"], "notes")
        with self.assertRaisesRegex(ValueError, "another app or analysis"):
            _validate_sqlite_schema(self.root / "schema", "dev.copyapp.fixture", "0" * 64)
        self.assertNotIn("private row content",
                         (self.root / "schema/report.md").read_text())
        self.assertTrue(validate_sandbox_file_capture(captured))
        (captured / "files/Documents/notes.sqlite").write_bytes(b"forged")
        self.assertFalse(verify_case(captured))
        self.assertFalse(verify_case(self.root / "schema"))

    def test_rejects_changed_container_before_copy(self):
        other = dict(self.app, Container=self.container.replace("12345678", "87654321"))
        with self.assertRaisesRegex(ValueError, "container or version differs"):
            self._capture(other)
        self.assertFalse((self.root / "capture").exists())

    def test_rejects_unindexed_or_unsafe_path(self):
        for path in ("../Library/private.sqlite", "/var/mobile/private.sqlite",
                     "Documents/missing.sqlite", "Documents//notes.sqlite"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                from copyapp.sandbox_capture import _source
                _source(self.analysis, [path])
        self.assertEqual(_relative("Documents/notes.sqlite"),
                         "Documents/notes.sqlite")


if __name__ == "__main__":
    unittest.main()
