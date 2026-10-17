import json
import hashlib
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from copyapp.analyze import analyze_case, _artifact_hashes, _stage_valid, _assert_stage_identity
from copyapp.ui_evidence import ui_attribution


class AnalyzeCaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tunnel = patch("copyapp.analyze.exact_ssh_tunnel",
                       side_effect=lambda _udid, port, *_args: nullcontext(port))
        tunnel.start()
        self.addCleanup(tunnel.stop)

    def test_resume_rejects_corrupted_derived_ui_and_static_indexes(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            udid, bundle = "device-123", "com.example.app"
            prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
            survey = output / "survey"
            survey.mkdir()
            (survey / "manifest.json").write_text(json.dumps({
                "bundle_id": bundle, "device_id_sha256_prefix": prefix,
                "evidence": []}))
            (survey / "app.json").write_text("{}")
            (survey / "ui.json").write_text('{"elements": []}')
            survey_record = {"ok": True,
                "key_sha256": hashlib.sha256((survey / "manifest.json").read_bytes()).hexdigest(),
                "artifact_hashes": _artifact_hashes(output, "survey")}
            self.assertTrue(_stage_valid(output, "survey", survey_record, udid, bundle))
            (survey / "ui.json").write_text('{"elements": ["corrupted"]}')
            self.assertFalse(_stage_valid(output, "survey", survey_record, udid, bundle))

            acquired = output / "acquired"
            (acquired / "static").mkdir(parents=True)
            (acquired / "acquisition.json").write_text(json.dumps({
                "bundle_id": bundle, "device_id_sha256_prefix": prefix}))
            (acquired / "static/ipa-index.json").write_text('{"binaries": []}')
            bundle_record = {"ok": True,
                "key_sha256": hashlib.sha256((acquired / "acquisition.json").read_bytes()).hexdigest(),
                "artifact_hashes": _artifact_hashes(output, "bundle")}
            with patch("copyapp.analyze.verify_case", return_value=True):
                self.assertTrue(_stage_valid(output, "bundle", bundle_record, udid, bundle))
                (acquired / "static/ipa-index.json").write_text("corrupted")
                self.assertFalse(_stage_valid(output, "bundle", bundle_record, udid, bundle))

    def test_stage_rejects_app_version_change_after_survey(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            (output / "survey").mkdir()
            (output / "survey/app.json").write_text(json.dumps({
                "CFBundleShortVersionString": "1.0", "CFBundleVersion": "10",
            }))
            with self.assertRaisesRegex(ValueError, "version differs"):
                _assert_stage_identity(output, "bundle", {
                    "bundle_id": "com.example.app",
                    "device_id_sha256_prefix": hashlib.sha256(b"device").hexdigest()[:16],
                    "installed_version": "2.0", "installed_build": "20",
                }, "device", "com.example.app")

    def test_saved_decryption_requires_matching_source_and_analysis_ipa(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            source = output / "acquired/bundle-snapshot.ipa"
            source.parent.mkdir()
            source.write_bytes(b"source")
            analysis = output / "decrypted/analysis.ipa"
            analysis.parent.mkdir()
            analysis.write_bytes(b"analysis")
            static = output / "decrypted/static/ipa-index.json"
            static.parent.mkdir()
            static.write_text("{}")
            udid, bundle = "device-123", "com.example.app"
            manifest = output / "decrypted/decryption.json"
            manifest.write_text(json.dumps({
                "bundle_id": bundle,
                "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                "all_macho_headers_decrypted": True,
                "source_snapshot_sha256": hashlib.sha256(b"source").hexdigest(),
                "analysis_ipa_sha256": hashlib.sha256(b"analysis").hexdigest(),
            }))
            record = {"ok": True, "key_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
            self.assertTrue(_stage_valid(output, "decryption", record, udid, bundle))
            analysis.write_bytes(b"tampered")
            self.assertFalse(_stage_valid(output, "decryption", record, udid, bundle))

    async def test_resume_reuses_verified_stages_and_archives_failed_partial_output(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "case"
            udid, bundle = "device-123", "com.example.app"
            prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
            calls = {"survey": 0, "bundle": 0, "sandbox": 0}

            async def survey(_udid, _bundle, directory, _launch):
                calls["survey"] += 1
                directory.mkdir()
                (directory / "manifest.json").write_text(json.dumps({
                    "bundle_id": bundle, "device_id_sha256_prefix": prefix,
                    "device": {"ProductType": "iPhone", "ProductVersion": "16.1"},
                    "evidence": [],
                }))
                (directory / "app.json").write_text("{}")
                (directory / "ui.json").write_text('{"elements": []}')
                (directory / "report.md").write_text("survey")

            async def acquire(_udid, _bundle, directory, *_ssh):
                calls["bundle"] += 1
                binary = directory / "bundle/Example.app/binary"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b"binary")
                snapshot = directory / "bundle-snapshot.ipa"
                snapshot.write_bytes(b"snapshot")
                (directory / "acquisition.json").write_text(json.dumps({
                    "bundle_id": bundle, "device_id_sha256_prefix": prefix,
                    "remote_bundle_path": "/Applications/Example.app",
                    "files": [{"relative": "binary",
                               "sha256": hashlib.sha256(b"binary").hexdigest()}],
                    "snapshot_sha256": hashlib.sha256(b"snapshot").hexdigest(),
                }))
                static = directory / "static"
                static.mkdir()
                (static / "ipa-index.json").write_text(json.dumps({
                    "executable": "binary", "binaries": [], "frameworks": [], "extensions": [],
                }))
                (static / "ipa-report.md").write_text("static")

            async def failing_sandbox(_udid, _bundle, path, *_ssh):
                calls["sandbox"] += 1
                path.write_text("partial sandbox evidence")
                raise PermissionError("temporary sandbox failure")

            async def working_sandbox(_udid, _bundle, path, *_ssh):
                calls["sandbox"] += 1
                path.write_text(json.dumps({"bundle_id": bundle,
                                            "device_id_sha256_prefix": prefix,
                                            "entries": []}))

            with patch("copyapp.analyze.acquire_bundle_ssh", acquire), patch(
                "copyapp.analyze.index_sandbox_ssh", failing_sandbox
            ):
                self.assertFalse(await analyze_case(
                    udid, bundle, output, False, 22222, "mobile", Path("key"),
                    Path("hosts"), survey))
            self.assertEqual(calls, {"survey": 1, "bundle": 1, "sandbox": 1})
            with patch("copyapp.analyze.acquire_bundle_ssh", acquire), patch(
                "copyapp.analyze.index_sandbox_ssh", working_sandbox
            ):
                self.assertTrue(await analyze_case(
                    udid, bundle, output, False, 22222, "mobile", Path("key"),
                    Path("hosts"), survey, resume=True))
            self.assertEqual(calls, {"survey": 1, "bundle": 1, "sandbox": 2})
            self.assertEqual((output / "attempts/sandbox-01/sandbox-index.json").read_text(),
                             "partial sandbox evidence")
            history = json.loads((output / "run-state.json").read_text())["history"]
            self.assertEqual(history[0]["stage"], "sandbox")
            self.assertIn("temporary sandbox failure", history[0]["error"])
            self.assertEqual(history[0]["archived_path"],
                             "attempts/sandbox-01/sandbox-index.json")
            self.assertTrue(json.loads((output / "analysis-index.json").read_text())
                            ["steps"]["survey"]["reused"])
            with self.assertRaisesRegex(ValueError, "resume target"):
                await analyze_case(udid, "com.example.other", output, False, 22222,
                                   "mobile", Path("key"), Path("hosts"), survey,
                                   resume=True)
            (output / "survey/manifest.json").write_text("corrupted")
            with patch("copyapp.analyze.acquire_bundle_ssh", acquire), patch(
                "copyapp.analyze.index_sandbox_ssh", working_sandbox
            ):
                self.assertTrue(await analyze_case(
                    udid, bundle, output, False, 22222, "mobile", Path("key"),
                    Path("hosts"), survey, resume=True))
            self.assertEqual(calls, {"survey": 2, "bundle": 1, "sandbox": 2})
            self.assertEqual((output / "attempts/survey-01/survey/manifest.json").read_text(),
                             "corrupted")

    def test_system_permission_for_another_app_is_not_target_ui(self):
        ui = {"elements": [{"caption": "Allow “Copy Compass” to use your location?"}]}
        self.assertEqual(ui_attribution(ui, "Compass")["status"],
                         "different_app_system_permission")

    async def test_partial_collection_keeps_evidence_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "case"

            async def survey(_udid, _bundle, directory, _launch):
                directory.mkdir()
                (directory / "manifest.json").write_text(json.dumps({
                    "bundle_id": "com.example.app",
                    "device_id_sha256_prefix": hashlib.sha256(b"device").hexdigest()[:16],
                    "evidence": [],
                }))
                (directory / "app.json").write_text("{}\n")
                (directory / "ui.json").write_text('{"elements": []}\n')
                (directory / "report.md").write_text("survey\n")
                return 0

            async def acquire(_udid, _bundle, directory, *_ssh):
                (directory / "static").mkdir(parents=True)
                (directory / "acquisition.json").write_text(
                    json.dumps({"remote_bundle_path": "/Applications/Example.app",
                                "bundle_id": "com.example.app",
                                "device_id_sha256_prefix": hashlib.sha256(b"device").hexdigest()[:16]}))
                (directory / "static" / "ipa-index.json").write_text(
                    '{"executable": "Example", "binaries": []}\n')
                (directory / "static" / "ipa-report.md").write_text("static\n")
                return directory / "static" / "ipa-report.md"

            async def sandbox(*_args):
                raise PermissionError("container unavailable")

            with patch("copyapp.analyze.acquire_bundle_ssh", acquire), patch(
                "copyapp.analyze.index_sandbox_ssh", sandbox
            ):
                complete = await analyze_case(
                    "device", "com.example.app", output, False, 22222, "mobile",
                    Path("key"), Path("hosts"), survey,
                )

            self.assertFalse(complete)
            index = json.loads((output / "analysis-index.json").read_text())
            self.assertTrue(index["steps"]["survey"]["ok"])
            self.assertTrue(index["steps"]["bundle"]["ok"])
            self.assertFalse(index["steps"]["sandbox"]["ok"])
            self.assertIn("static", index["artifacts"])
            self.assertNotIn("sandbox", index["artifacts"])
            self.assertIn("沙盒元数据：失败", (output / "analysis.md").read_text())

    async def test_requested_decryption_joins_case_and_report(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "case"

            async def survey(_udid, _bundle, directory, _launch):
                directory.mkdir()
                (directory / "manifest.json").write_text(json.dumps({
                    "bundle_id": "com.example.app",
                    "device_id_sha256_prefix": hashlib.sha256(b"device").hexdigest()[:16],
                    "evidence": [],
                }))
                (directory / "app.json").write_text("{}\n")
                (directory / "ui.json").write_text('{"elements": []}\n')

            async def acquire(_udid, _bundle, directory, *_ssh):
                directory.mkdir()
                (directory / "bundle-snapshot.ipa").write_bytes(b"snapshot")
                (directory / "acquisition.json").write_text(json.dumps({
                    "bundle_id": "com.example.app",
                    "device_id_sha256_prefix": hashlib.sha256(b"device").hexdigest()[:16],
                }))

            async def sandbox(_udid, _bundle, path, *_ssh):
                path.write_text(json.dumps({
                    "bundle_id": "com.example.app",
                    "device_id_sha256_prefix": hashlib.sha256(b"device").hexdigest()[:16],
                    "entries": [],
                }))

            def decrypt(_udid, _bundle, snapshot, _helper, directory, *_ssh):
                self.assertEqual(snapshot.read_bytes(), b"snapshot")
                (directory / "static").mkdir(parents=True)
                (directory / "static" / "ipa-index.json").write_text("{}\n")
                (directory / "static" / "objc-index.json").write_text("{}\n")
                (directory / "decryption.json").write_text(json.dumps({
                    "bundle_id": "com.example.app",
                    "device_id_sha256_prefix": hashlib.sha256(b"device").hexdigest()[:16],
                    "checked_macho_count": 3, "recovered_binaries": [{"path": "main"}],
                    "objc_class_count": 2, "objc_method_count": 5,
                    "analysis_ipa_sha256": "abc",
                }))

            with patch("copyapp.analyze.acquire_bundle_ssh", acquire), patch(
                "copyapp.analyze.index_sandbox_ssh", sandbox
            ), patch("copyapp.analyze.decrypt_package", decrypt):
                complete = await analyze_case(
                    "device", "com.example.app", output, False, 22222, "mobile",
                    Path("key"), Path("hosts"), survey, decrypt=True,
                )

            self.assertTrue(complete)
            index = json.loads((output / "analysis-index.json").read_text())
            self.assertTrue(index["steps"]["decryption"]["ok"])
            self.assertIn("decrypted_objc", index["artifacts"])
            self.assertIn("恢复原加密二进制：1 个", (output / "analysis.md").read_text())


if __name__ == "__main__":
    unittest.main()
