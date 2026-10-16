import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.prepare_app import prepare_app
from copyapp.verify import sha256_file, verify_case


class PrepareAppTest(unittest.IsolatedAsyncioTestCase):
    async def test_network_setting_reaches_preparation_and_resume_rejects_change(self):
        seen = []

        def prepare(*args, **kwargs):
            seen.append(kwargs.get("network"))
            return self._prepare(*args)

        with patch("copyapp.prepare_app.analyze_case", side_effect=self._analyze), \
             patch("copyapp.prepare_app.prepare_analysis", side_effect=prepare), \
             patch("copyapp.prepare_app.verify_case", return_value=True):
            manifest, ready = await prepare_app(self.udid, self.bundle, [self.script],
                                                self.output, self._survey, network=True)
            self.assertTrue(ready, manifest.read_text())
            self.assertEqual(seen, [True])
            with self.assertRaisesRegex(ValueError, "settings differ"):
                await prepare_app(self.udid, self.bundle, [self.script],
                                  self.output, self._survey, resume=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.udid = "exact-device"
        self.bundle = "com.example.app"
        self.prefix = hashlib.sha256(self.udid.encode()).hexdigest()[:16]
        self.script = self.root / "flow.json"
        self.script.write_text(json.dumps({"bundle_id": self.bundle,
                                           "steps": [{"action": "observe"}]}))
        self.output = self.root / "prepared"
        self.analyze_calls = 0
        self.prepare_calls = []

    async def _survey(self, *args):
        return 0

    def _doctor(self, output, *args):
        (output / "toolchain-doctor.json").write_text('{"healthy":true}')

    async def _analyze(self, udid, bundle, output, *args):
        self.analyze_calls += 1
        output.mkdir(parents=True, exist_ok=True)
        (output / "analysis-index.json").write_text(json.dumps({
            "steps": {name: {"ok": True} for name in ("survey", "bundle", "sandbox")}}))
        (output / "run-state.json").write_text(json.dumps({
            "bundle_id": bundle, "device_id_sha256_prefix": self.prefix,
            "decrypt_requested": False}))
        return True

    def _prepare(self, udid, analysis, scripts, output, *args):
        self.prepare_calls.append(args[-1])
        output.mkdir(exist_ok=True)
        (output / "manifest.json").write_text(json.dumps({
            "status": "needs_semantic_review", "analysis_case": str(analysis),
            "analysis_index_sha256": sha256_file(analysis / "analysis-index.json"),
            "scripts": [{"path": str(self.script.resolve()),
                         "sha256": sha256_file(self.script)}],
            "bundle_id": self.bundle, "device_id_sha256_prefix": self.prefix,
            "ui_backend": "ios-mcp", "provider": args[1],
            "rebuilt_bundle_id": ""}))
        return output / "manifest.json", True

    async def test_collect_prepare_verify_and_resume_without_device_touch(self):
        with patch("copyapp.prepare_app._ghidra_ready", side_effect=self._doctor), \
             patch("copyapp.prepare_app.analyze_case", side_effect=self._analyze), \
             patch("copyapp.prepare_app.prepare_analysis", side_effect=self._prepare), \
             patch("copyapp.prepare_app.verify_case", return_value=True):
            manifest, ready = await prepare_app(self.udid, self.bundle, [self.script],
                                                self.output, self._survey, provider="ghidra-direct")
            self.assertTrue(ready)
            self.assertEqual(self.analyze_calls, 1)
            with patch("copyapp.verify._verify_silent", return_value=True):
                self.assertTrue(verify_case(self.output))
            manifest, ready = await prepare_app(self.udid, self.bundle, [self.script],
                                                self.output, self._survey, provider="ghidra-direct", resume=True)
            self.assertTrue(ready)
            self.assertEqual(self.analyze_calls, 1)
        self.assertEqual(self.prepare_calls, [False])
        self.assertEqual(json.loads(manifest.read_text())["status"], "needs_semantic_review")

    async def test_changed_playbook_rejected_before_device_work(self):
        with patch("copyapp.prepare_app._ghidra_ready", side_effect=self._doctor), \
             patch("copyapp.prepare_app.analyze_case", side_effect=self._analyze), \
             patch("copyapp.prepare_app.prepare_analysis", side_effect=self._prepare), \
             patch("copyapp.prepare_app.verify_case", return_value=True):
            await prepare_app(self.udid, self.bundle, [self.script], self.output, self._survey,
                              provider="ghidra-direct")
            self.script.write_text(json.dumps({"bundle_id": self.bundle,
                                               "steps": [{"action": "tap", "x": 7}]}))
            with self.assertRaisesRegex(ValueError, "resume target, playbooks or settings differ"):
                await prepare_app(self.udid, self.bundle, [self.script], self.output,
                                  self._survey, provider="ghidra-direct", resume=True)
        self.assertEqual(self.analyze_calls, 1)

    async def test_missing_toolchain_fails_before_device_work(self):
        with patch("copyapp.prepare_app._ghidra_ready",
                   side_effect=FileNotFoundError("Ghidra not found")), \
             patch("copyapp.prepare_app.analyze_case", side_effect=self._analyze):
            manifest, ready = await prepare_app(self.udid, self.bundle, [self.script],
                                                self.output, self._survey, provider="ghidra-direct")
        self.assertFalse(ready)
        self.assertEqual(self.analyze_calls, 0)
        self.assertEqual(json.loads(manifest.read_text())["error"]["type"],
                         "FileNotFoundError")

    async def test_default_prepares_without_rea_toolchain(self):
        with patch("copyapp.prepare_app._ghidra_ready",
                   side_effect=AssertionError("Ghidra must not run")) as doctor, \
             patch("copyapp.prepare_app.analyze_case", side_effect=self._analyze), \
             patch("copyapp.prepare_app.prepare_analysis", side_effect=self._prepare), \
             patch("copyapp.prepare_app.verify_case", return_value=True):
            manifest, ready = await prepare_app(self.udid, self.bundle, [self.script],
                                                self.output, self._survey)
        self.assertTrue(ready, manifest.read_text())
        doctor.assert_not_called()
        self.assertEqual(json.loads(manifest.read_text())["provider"], "none")
        self.assertFalse((self.output / "toolchain-doctor.json").exists())
        with patch("copyapp.verify._verify_silent", return_value=True):
            self.assertTrue(verify_case(self.output))

    async def test_incomplete_encrypted_collection_resumes_before_preparation(self):
        attempts = []

        async def collect(udid, bundle, output, *args):
            attempts.append(args[-1])
            output.mkdir(parents=True, exist_ok=True)
            complete = len(attempts) == 2
            (output / "analysis-index.json").write_text(json.dumps({
                "steps": {name: {"ok": complete} for name in
                          ("survey", "bundle", "sandbox", "decryption")}}))
            (output / "run-state.json").write_text(json.dumps({
                "bundle_id": bundle, "device_id_sha256_prefix": self.prefix,
                "decrypt_requested": True}))
            return complete

        with patch("copyapp.prepare_app._ghidra_ready", side_effect=self._doctor), \
             patch("copyapp.prepare_app.analyze_case", side_effect=collect), \
             patch("copyapp.prepare_app.prepare_analysis", side_effect=self._prepare), \
             patch("copyapp.prepare_app.verify_case", return_value=True):
            manifest, ready = await prepare_app(self.udid, self.bundle, [self.script],
                                                self.output, self._survey, decrypt=True, provider="ghidra-direct")
            self.assertFalse(ready)
            self.assertEqual(json.loads(manifest.read_text())["status"],
                             "analysis_incomplete")
            self.assertFalse(self.prepare_calls)
            manifest, ready = await prepare_app(self.udid, self.bundle, [self.script],
                                                self.output, self._survey,
                                                decrypt=True, provider="ghidra-direct", resume=True)
            self.assertTrue(ready)
        self.assertEqual(attempts, [False, True])
        self.assertEqual(self.prepare_calls, [False])

    async def test_parent_verifier_rejects_changed_source_script(self):
        with patch("copyapp.prepare_app._ghidra_ready", side_effect=self._doctor), \
             patch("copyapp.prepare_app.analyze_case", side_effect=self._analyze), \
             patch("copyapp.prepare_app.prepare_analysis", side_effect=self._prepare), \
             patch("copyapp.prepare_app.verify_case", return_value=True):
            await prepare_app(self.udid, self.bundle, [self.script], self.output, self._survey,
                              provider="ghidra-direct")
        self.script.write_text(json.dumps({"bundle_id": self.bundle,
                                           "steps": [{"action": "tap", "x": 7}]}))
        with patch("copyapp.verify._verify_silent", return_value=True):
            self.assertFalse(verify_case(self.output))


if __name__ == "__main__":
    unittest.main()
