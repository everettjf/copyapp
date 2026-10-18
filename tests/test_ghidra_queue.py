import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.ghidra_queue import (decompile_candidate_queue, select_ghidra_targets,
                                  verified_indirect_targets)
from copyapp.prepare_analysis import _ghidra_ready
from copyapp.report import _validate_ghidra_direct_queue
from copyapp.verify import sha256_file, verify_case
from tests.test_native_disasm import BASE, ENTRY, sample_macho


class GhidraQueueTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binary = self.root / "App"
        self.binary.write_bytes(b"fixed test binary")
        self.digest = sha256_file(self.binary)
        self.candidates = self.root / "candidates"
        self.candidates.mkdir()
        source = {"schema_version": 1, "kind": "runtime_static_candidates",
                  "bundle_id": "dev.copyapp.fixture", "device_id_sha256_prefix": "device1234567890",
                  "binary_path": str(self.binary), "binary_sha256": self.digest,
                  "candidates": [{"static_address": "0x100001000",
                                  "binary_sha256": self.digest,
                                  "class": "Fixture", "selector": "tapped:",
                                  "observations": [{"calls": 1,
                                                    "static_entry": {"calls": 1}}]}]}
        (self.candidates / "candidates.json").write_text(json.dumps(source))
        (self.candidates / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "runtime_static_candidates", "status": "complete",
            "evidence": [{"path": "candidates.json", "sha256":
                          sha256_file(self.candidates / "candidates.json")}]}) + "\n")
        launcher = self.root / "ghidra/support/analyzeHeadless"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv
post = args.index('-postScript')
end = args.index('-max-cpu')
pairs = list(zip(args[post + 2:end:2], args[post + 3:end:2]))
output = pathlib.Path(pairs[0][1])
count = pathlib.Path(args[0]).parent / 'launcher-count.txt'
count.write_text(count.read_text() + 'x' if count.exists() else 'x')
if '-preScript' in args:
    pre = args.index('-preScript')
    (output / 'analysis-options.txt').write_text(args[pre + 2] + '=false\\n')
for address, path in pairs:
    destination = pathlib.Path(path)
    (destination / 'address.txt').write_text(address[2:] + '\\n')
    (destination / 'name.txt').write_text('tapped:\\n')
    (destination / 'language.txt').write_text('AARCH64:LE:64:AppleSilicon\\n')
    (destination / 'pseudocode.txt').write_text('void tapped(void) {}\\n')
    (destination / 'function-facts.json').write_text(json.dumps({'schema_version': 2,
        'address': address, 'name': 'tapped:', 'signature': 'void tapped(void)',
        'is_thunk': False, 'is_external': False, 'callers': [],
        'callers_truncated': False, 'callees': [], 'callees_truncated': False,
        'basic_blocks': [], 'basic_blocks_truncated': False,
        'instruction_references': [], 'instruction_references_truncated': False,
        'instructions_scanned': 0,
        'limitation': 'Ghidra static FunctionManager observations.'}))
    print('COPYAPP_DECOMPILE_COMPLETE ' + address[2:])
print('COPYAPP_BATCH_COMPLETE ' + str(len(pairs)))
pathlib.Path(args[args.index('-log') + 1]).write_text('fake provider\\n')
""")
        launcher.chmod(0o755)

    def test_queue_keeps_ranked_source_and_rejects_semantic_tamper(self):
        output = self.root / "queue"
        manifest, complete = decompile_candidate_queue(
            self.candidates, output, self.root / "ghidra", limit=1)
        self.assertTrue(complete)
        self.assertEqual(manifest, output / "manifest.json")
        self.assertTrue(verify_case(output))
        checked = _validate_ghidra_direct_queue(
            output, "dev.copyapp.fixture", "device1234567890", {self.digest})
        self.assertEqual(checked["record"]["results"][0]["address"], "0x100001000")
        record = json.loads((output / "queue.json").read_text())
        record["selected"][0]["selector"] = "other:"
        (output / "queue.json").write_text(json.dumps(record))
        outer = json.loads(manifest.read_text())
        for item in outer["evidence"]:
            if item["path"] == "queue.json":
                item["sha256"] = sha256_file(output / "queue.json")
        manifest.write_text(json.dumps(outer))
        self.assertTrue(verify_case(output))
        with self.assertRaisesRegex(ValueError, "ranked candidate"):
            _validate_ghidra_direct_queue(
                output, "dev.copyapp.fixture", "device1234567890", {self.digest})

    def test_direct_preflight_requires_ghidra_and_jdk_without_rea(self):
        doctor_dir = self.root / "doctor"
        doctor_dir.mkdir()
        java_home = self.root / "jdk"
        (java_home / "bin").mkdir(parents=True)
        java = java_home / "bin/java"
        java.write_text("#!/bin/sh\necho 'openjdk version 21-test' >&2\n")
        java.chmod(0o755)
        with patch.dict(os.environ, {"JAVA_HOME": ""}):
            with self.assertRaisesRegex(FileNotFoundError, "JDK"):
                _ghidra_ready(doctor_dir, self.root / "ghidra", None)
        _ghidra_ready(doctor_dir,
                   self.root / "ghidra", java_home)
        doctor = json.loads((doctor_dir / "toolchain-doctor.json").read_text())
        self.assertEqual(doctor["provider"], "ghidra-direct")
        self.assertTrue(doctor["healthy"])

    def test_queue_profile_is_bound_to_every_function(self):
        output = self.root / "profiled-queue"
        _, complete = decompile_candidate_queue(
            self.candidates, output, self.root / "ghidra", limit=1,
            disabled_analyzer="Objective-C Message Analyzer")
        self.assertTrue(complete)
        checked = _validate_ghidra_direct_queue(
            output, "dev.copyapp.fixture", "device1234567890", {self.digest})
        self.assertEqual(checked["record"]["disabled_analyzer"],
                         "Objective-C Message Analyzer")

    def test_two_candidates_use_one_import_and_keep_function_identity(self):
        source_path = self.candidates / "candidates.json"
        source = json.loads(source_path.read_text())
        source["candidates"].append({"static_address": "0x100001100",
                                     "binary_sha256": self.digest,
                                     "class": "Fixture", "selector": "next:",
                                     "observations": [{"calls": 1,
                                                       "static_entry": {"calls": 1}}]})
        source_path.write_text(json.dumps(source))
        manifest_path = self.candidates / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["evidence"][0]["sha256"] = sha256_file(source_path)
        manifest_path.write_text(json.dumps(manifest))
        output = self.root / "two-functions"
        _, complete = decompile_candidate_queue(
            self.candidates, output, self.root / "ghidra", limit=2,
            disabled_analyzer="Objective-C Message Analyzer")
        self.assertTrue(complete)
        self.assertEqual((self.root / "ghidra/support/launcher-count.txt").read_text(), "x")
        checked = _validate_ghidra_direct_queue(
            output, "dev.copyapp.fixture", "device1234567890", {self.digest})
        self.assertEqual(checked["record"]["execution"], "single_import")
        self.assertEqual([item["address"] for item in checked["record"]["results"]],
                         ["0x100001000", "0x100001100"])
        target = output / "targets/function-02/summary.json"
        altered = json.loads(target.read_text())
        altered["batch_index"] = 1
        target.write_text(json.dumps(altered))
        target_manifest = output / "targets/function-02/manifest.json"
        child = json.loads(target_manifest.read_text())
        for item in child["evidence"]:
            if item["path"] == "summary.json":
                item["sha256"] = sha256_file(target)
        target_manifest.write_text(json.dumps(child))
        outer_path = output / "manifest.json"
        outer = json.loads(outer_path.read_text())
        for item in outer["evidence"]:
            if item["path"] == "targets/function-02/summary.json":
                item["sha256"] = sha256_file(target)
            if item["path"] == "targets/function-02/manifest.json":
                item["sha256"] = sha256_file(target_manifest)
        outer_path.write_text(json.dumps(outer))
        self.assertTrue(verify_case(output))
        with self.assertRaisesRegex(ValueError, "target differs"):
            _validate_ghidra_direct_queue(
                output, "dev.copyapp.fixture", "device1234567890", {self.digest})

    def test_follow_selection_only_uses_completed_edges_from_selected_root(self):
        source = json.loads((self.candidates / "candidates.json").read_text())
        native = {"followed": [
            {"status": "complete", "root_address": "0x100001000",
             "source_address": "0x100001000", "address": "0x100001100",
             "depth": 1, "summary": "followed-01/summary.json"},
            {"status": "unavailable", "root_address": "0x100001000",
             "source_address": "0x100001100", "address": "0x100001200",
             "depth": 2},
            {"status": "complete", "root_address": "0x100002000",
             "source_address": "0x100002000", "address": "0x100002100",
             "depth": 1, "summary": "followed-03/summary.json"}]}
        chosen = select_ghidra_targets(source["candidates"], self.digest, 1, native)
        self.assertEqual([item["address"] for item in chosen],
                         ["0x100001000", "0x100001100"])
        self.assertEqual(chosen[1]["origin"], "native_direct_follow")
        self.assertEqual(chosen[1]["native_summary"], "followed-01/summary.json")

    def test_indirect_target_requires_exact_blr_site_and_function_start(self):
        binary = self.root / "indirect-app"
        blob = bytearray(sample_macho())
        struct.pack_into("<I", blob, 0x104, 0xd63f0260)
        binary.write_bytes(blob)
        native = self.root / "indirect-native"
        target = native / "function-01"
        target.mkdir(parents=True)
        (target / "summary.json").write_text(json.dumps({
            "address": hex(ENTRY), "stop_address": hex(ENTRY + 0x10)}))
        (target / "assembly.txt").write_text(f"{ENTRY + 4:x}: d63f0260 blr x19\n")
        record = {"results": [{"status": "complete", "address": hex(ENTRY),
                                "summary": "function-01/summary.json"}], "followed": []}
        observed = [{"static_address": hex(ENTRY), "class": "Screen", "selector": "tap:"}]
        trace = {"static_entries": [{"index": 0, "status": "hooked",
                                     "module_offset": hex(ENTRY - BASE),
                                     "class": "Screen", "selector": "tap:"}],
                 "branch_requested_offsets": [hex(ENTRY + 4 - BASE)],
                 "branch_registers": [{"offset": hex(ENTRY + 4 - BASE), "register": "x19"}],
                 "steps": [{"index": 3, "static_call_counts": [1],
                            "branch_call_counts": [1], "branch_register_hits": [
                                {"index": 0, "register": "x19", "status": "app_image",
                                 "target_offset": hex(ENTRY + 0x10 - BASE)}]}]}
        chosen = verified_indirect_targets({"binary_path": str(binary)}, native,
                                           record, trace, observed)
        self.assertEqual(chosen[0]["address"], hex(ENTRY + 0x10))
        self.assertEqual(chosen[0]["origin"], "runtime_indirect_target")
        trace["steps"][0]["branch_register_hits"][0]["target_offset"] = hex(ENTRY + 8 - BASE)
        with self.assertRaisesRegex(ValueError, "exact Mach-O function start"):
            verified_indirect_targets({"binary_path": str(binary)}, native,
                                      record, trace, observed)
        trace["steps"][0]["branch_register_hits"][0]["target_offset"] = hex(ENTRY + 0x10 - BASE)
        (target / "assembly.txt").write_text(f"{ENTRY + 4:x}: d61f0260 br x19\n")
        with self.assertRaisesRegex(ValueError, "BLR instruction"):
            verified_indirect_targets({"binary_path": str(binary)}, native,
                                      record, trace, observed)


if __name__ == "__main__":
    unittest.main()
