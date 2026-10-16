import ast
import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.hopper_direct import decompile_hopper_function
from copyapp.hopper_queue import decompile_hopper_queue
from copyapp.report import _validate_hopper_direct, _validate_hopper_direct_queue
from copyapp.verify import sha256_file, verify_case
from tests.test_native_disasm import ENTRY, sample_macho


class HopperDirectTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binary = self.root / "App"
        self.binary.write_bytes(sample_macho())
        self.digest = sha256_file(self.binary)
        self.app = self.root / "Hopper.app"
        launcher = self.app / "Contents/MacOS/hopper"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\n")
        launcher.chmod(0o755)
        (self.app / "Contents/Info.plist").write_bytes(
            plistlib.dumps({"CFBundleShortVersionString": "test"}))

    @staticmethod
    def _launcher(command, **_kwargs):
        config = ast.literal_eval(Path(command[command.index("-Y") + 1])
                                  .read_text().splitlines()[0].removeprefix("CONFIG = "))
        Path(config["pseudocode"]).write_text("void tapped(void) {}\n")
        Path(config["result"]).write_text(json.dumps({
            "status": "complete", "address": config["address"],
            "binary_path": config["target"], "slice_sha256": config["slice_sha256"],
            "name": "tapped", "signature": "void tapped(void)"}))

        class Finished:
            @staticmethod
            def poll():
                return 0

        return Finished()

    def test_single_function_is_source_bound_and_rejects_semantic_tamper(self):
        output = self.root / "function"
        with patch("copyapp.hopper_direct.subprocess.Popen", side_effect=self._launcher):
            decompile_hopper_function(self.binary, self.digest, hex(ENTRY), output,
                                      self.app, timeout=60)
        self.assertTrue(verify_case(output))
        self.assertEqual(_validate_hopper_direct(output, {self.digest})["summary"]["address"],
                         hex(ENTRY))
        summary = output / "summary.json"
        changed = json.loads(summary.read_text())
        changed["address"] = "0x100001200"
        summary.write_text(json.dumps(changed))
        manifest = output / "manifest.json"
        record = json.loads(manifest.read_text())
        record["address"] = changed["address"]
        for item in record["evidence"]:
            if item["path"] == "summary.json":
                item["sha256"] = sha256_file(summary)
        manifest.write_text(json.dumps(record))
        self.assertTrue(verify_case(output))
        with self.assertRaisesRegex(ValueError, "identity"):
            _validate_hopper_direct(output, {self.digest})

    def test_queue_selects_verified_candidate_and_retains_function(self):
        candidates = self.root / "candidates"
        candidates.mkdir()
        source = {"schema_version": 1, "kind": "runtime_static_candidates",
                  "bundle_id": "dev.copyapp.fixture",
                  "device_id_sha256_prefix": "device1234567890",
                  "binary_path": str(self.binary), "binary_sha256": self.digest,
                  "candidates": [{"static_address": hex(ENTRY),
                                  "binary_sha256": self.digest,
                                  "class": "Fixture", "selector": "tapped:",
                                  "observations": [{"calls": 1,
                                                    "static_entry": {"calls": 1}}]}]}
        (candidates / "candidates.json").write_text(json.dumps(source))
        (candidates / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "runtime_static_candidates",
            "status": "complete", "evidence": [{"path": "candidates.json",
                                                  "sha256": sha256_file(candidates / "candidates.json")}]}))
        output = self.root / "queue"
        with patch("copyapp.hopper_direct.subprocess.Popen", side_effect=self._launcher):
            _, ready = decompile_hopper_queue(candidates, output, self.app, limit=1,
                                              timeout=60)
        self.assertTrue(ready)
        self.assertEqual(_validate_hopper_direct_queue(
            output, "dev.copyapp.fixture", "device1234567890", {self.digest})
            ["record"]["selected"][0]["address"], hex(ENTRY))


if __name__ == "__main__":
    unittest.main()
