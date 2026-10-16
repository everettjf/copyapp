import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.rea_queue import analyze_candidate_queue
from copyapp.report import _validate_rea_queue
from copyapp.verify import sha256_file, verify_case


class ReaQueueTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "App.app" / "App"
        self.binary.parent.mkdir()
        self.binary.write_bytes(b"exact candidate binary")
        self.digest = sha256_file(self.binary)
        self.case = self.root / "candidates"
        self.case.mkdir()
        self.data = {"schema_version": 1, "bundle_id": "com.example.app",
                     "device_id_sha256_prefix": "device-prefix",
                     "binary_path": str(self.binary),
                     "binary_sha256": self.digest,
                     "candidates": [{"class": "Demo", "selector": "tap:",
                                     "static_address": "0x100001000",
                                     "binary_sha256": self.digest,
                                     "observations": [{"calls": 1,
                                                       "static_entry": {"calls": 1}}]}]}
        self.save_case()

    def save_case(self):
        target = self.case / "candidates.json"
        target.write_text(json.dumps(self.data))
        (self.case / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "runtime_static_candidates",
            "evidence": [{"path": "candidates.json", "sha256": sha256_file(target)}]}))

    def test_runs_exact_address_and_retains_source(self):
        def fake_rea(binary, digest, procedure, provider, target, *_args):
            self.assertEqual((binary, digest, procedure, provider),
                             (self.binary, self.digest, "0x100001000", "ghidra"))
            target.mkdir(parents=True)
            summary = target / "summary.json"
            provider_identity = {"id": provider, "version": "fixture"}
            resolved = {"name": "Demo::tap:", "address": procedure}
            summary.write_text(json.dumps({"binary_sha256": digest,
                "provider": provider_identity, "analysis_profile_digest": "profile-fixture",
                "requested_procedure": procedure, "resolved_procedure": resolved,
                "evidence_id": "ev-fixture", "pseudocode_is_original_source": False}))
            (target / "pseudocode.txt").write_text("void tap() {}")
            (target / "evidence.json").write_text(json.dumps({
                "subject": {"digest": {"sha256": digest}},
                "provider": provider_identity, "analysis_profile": {"digest": "profile-fixture"},
                "parameters": {"procedure": procedure}, "evidence_id": "ev-fixture",
                "normalized_result": {"procedure": resolved, "pseudocode": "void tap() {}"}}))
            return summary

        output = self.root / "queue"
        with patch("copyapp.rea_queue.analyze_rea_function", side_effect=fake_rea):
            path, complete = analyze_candidate_queue(self.case, "ghidra", output)
        self.assertTrue(complete)
        self.assertTrue(verify_case(output))
        result = json.loads((output / "queue.json").read_text())
        self.assertEqual(result["results"][0]["evidence_id"], "ev-fixture")
        self.assertEqual(sha256_file(output / "sources/candidates/candidates.json"),
                         sha256_file(self.case / "candidates.json"))
        manifest = json.loads(path.read_text())
        self.assertIn("sources/candidates/manifest.json",
                      {item["path"] for item in manifest["evidence"]})
        self.assertEqual(_validate_rea_queue(output, "com.example.app", "device-prefix",
                                             {self.digest})["record"]["status"], "complete")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            _validate_rea_queue(output, "com.example.app", "another-device", {self.digest})
        self.assertEqual(path, output / "manifest.json")

    def test_stops_on_failure_and_keeps_verified_partial_case(self):
        output = self.root / "failed"
        with patch("copyapp.rea_queue.analyze_rea_function",
                   side_effect=RuntimeError("provider unavailable")):
            _, complete = analyze_candidate_queue(self.case, "ghidra", output)
        self.assertFalse(complete)
        self.assertTrue(verify_case(output))
        result = json.loads((output / "queue.json").read_text())
        self.assertEqual(result["results"][0]["status"], "failed")

    def test_rejects_modified_candidate_or_binary_before_provider(self):
        self.data["candidates"][0]["static_address"] = "0x100002000"
        (self.case / "candidates.json").write_text(json.dumps(self.data))
        with patch("copyapp.rea_queue.analyze_rea_function") as call:
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                analyze_candidate_queue(self.case, "ghidra", self.root / "tampered")
            call.assert_not_called()
        self.save_case()
        self.binary.write_bytes(b"changed")
        with patch("copyapp.rea_queue.analyze_rea_function") as call:
            with self.assertRaisesRegex(ValueError, "binary identity"):
                analyze_candidate_queue(self.case, "ghidra", self.root / "wrong-binary")
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
