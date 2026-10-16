import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from copyapp.ghidra_direct import (decompile_ghidra_batch,
                                  decompile_ghidra_function,
                                  validate_function_facts)
from copyapp.report import _validate_ghidra_direct
from copyapp.verify import sha256_file, verify_case


class GhidraDirectTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.binary = self.root / "App"
        self.binary.write_bytes(b"fixed test binary")
        self.digest = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.ghidra = self.root / "ghidra/support"
        self.ghidra.mkdir(parents=True)
        launcher = self.ghidra / "analyzeHeadless"
        launcher.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv
address = args[9]
output = pathlib.Path(args[10])
(output / 'address.txt').write_text(address[2:] + '\\n')
(output / 'name.txt').write_text('buttonPressed:\\n')
(output / 'language.txt').write_text('AARCH64:LE:64:AppleSilicon\\n')
(output / 'pseudocode.txt').write_text('void buttonPressed(void) {}\\n')
(output / 'function-facts.json').write_text(json.dumps({'schema_version': 2,
    'address': address, 'name': 'buttonPressed:', 'signature': 'void buttonPressed(void)',
    'is_thunk': False, 'is_external': False, 'callers': [], 'callers_truncated': False,
    'callees': [], 'callees_truncated': False,
    'basic_blocks': [], 'basic_blocks_truncated': False,
    'instruction_references': [], 'instruction_references_truncated': False,
    'instructions_scanned': 0,
    'limitation': 'Ghidra static FunctionManager observations.'}))
(output / 'ghidra.log').write_text('fake provider\\n')
""")
        launcher.chmod(0o755)

    def test_direct_case_is_importable_without_rea(self):
        output = self.root / "decompilation"
        result = decompile_ghidra_function(self.binary, self.digest,
                                           "0x100001000", output,
                                           self.ghidra.parent)
        self.assertEqual(result.name, "summary.json")
        self.assertTrue(verify_case(output))
        checked = _validate_ghidra_direct(output, {self.digest})
        self.assertEqual(checked["summary"]["function_name"], "buttonPressed:")
        self.assertIn("CopyAppDecompile.java", checked["files"])
        self.assertIn("function-facts.json", checked["files"])
        (output / "function-facts.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            _validate_ghidra_direct(output, {self.digest})
        output.joinpath("function-facts.json").write_text(json.dumps({
            "schema_version": 1, "address": "0x100001000", "name": "buttonPressed:",
            "signature": "void buttonPressed(void)", "is_thunk": False,
            "is_external": False, "callers": [], "callers_truncated": False,
            "callees": [], "callees_truncated": False,
            "limitation": "Ghidra static FunctionManager observations."}))
        (output / "pseudocode.txt").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            _validate_ghidra_direct(output, {self.digest})

    def test_rejects_wrong_binary_before_launch(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            decompile_ghidra_function(self.binary, "0" * 64, "0x100001000",
                                      self.root / "rejected", self.ghidra.parent)
        self.assertFalse((self.root / "rejected").exists())

    def test_rejects_old_fact_schema_from_new_script(self):
        launcher = self.ghidra / "analyzeHeadless"
        launcher.write_text(launcher.read_text().replace("'schema_version': 2",
                                                       "'schema_version': 1"))
        output = self.root / "old-facts-from-new-script"
        with self.assertRaisesRegex(RuntimeError, "direct Ghidra decompilation failed"):
            decompile_ghidra_function(self.binary, self.digest, "0x100001000",
                                      output, self.ghidra.parent)
        failure = json.loads((output / "failure.json").read_text())
        self.assertIn("schema differs", failure["message"])

    def test_rejects_rehashed_oversized_string_reference(self):
        output = self.root / "reference-facts"
        decompile_ghidra_function(self.binary, self.digest, "0x100001000",
                                  output, self.ghidra.parent)
        facts_path = output / "function-facts.json"
        facts = json.loads(facts_path.read_text())
        facts["instruction_references"] = [{
            "from": "0x100001010", "to": "0x100002000", "type": "DATA",
            "string_preview": "x" * 257}]
        facts_path.write_text(json.dumps(facts))
        summary_path = output / "summary.json"
        summary = json.loads(summary_path.read_text())
        summary["facts_sha256"] = sha256_file(facts_path)
        summary_path.write_text(json.dumps(summary))
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for item in manifest["evidence"]:
            if item["path"] in ("function-facts.json", "summary.json"):
                item["sha256"] = sha256_file(output / item["path"])
        manifest_path.write_text(json.dumps(manifest))
        self.assertTrue(verify_case(output))
        with self.assertRaisesRegex(ValueError, "instruction reference"):
            _validate_ghidra_direct(output, {self.digest})

    def test_accepts_saved_v1_facts(self):
        path = self.root / "legacy-facts.json"
        path.write_text(json.dumps({
            "schema_version": 1, "address": "0x100001000", "name": "older",
            "signature": "void older(void)", "is_thunk": False,
            "is_external": False, "callers": [], "callers_truncated": False,
            "callees": [], "callees_truncated": False,
            "limitation": "Ghidra static FunctionManager observations."}))
        self.assertEqual(validate_function_facts(path, "0x100001000", "older")
                         ["schema_version"], 1)

    def test_rejects_rehashed_function_facts_for_another_address(self):
        output = self.root / "wrong-facts"
        decompile_ghidra_function(self.binary, self.digest, "0x100001000",
                                  output, self.ghidra.parent)
        facts_path = output / "function-facts.json"
        facts = json.loads(facts_path.read_text())
        facts["address"] = "0x100002000"
        facts_path.write_text(json.dumps(facts))
        summary_path = output / "summary.json"
        summary = json.loads(summary_path.read_text())
        summary["facts_sha256"] = sha256_file(facts_path)
        summary_path.write_text(json.dumps(summary))
        manifest_path = output / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for item in manifest["evidence"]:
            if item["path"] in ("function-facts.json", "summary.json"):
                item["sha256"] = sha256_file(output / item["path"])
        manifest_path.write_text(json.dumps(manifest))
        self.assertTrue(verify_case(output))
        with self.assertRaisesRegex(ValueError, "function facts identity"):
            _validate_ghidra_direct(output, {self.digest})

    def test_recorded_analyzer_profile_is_source_bound(self):
        launcher = self.ghidra / "analyzeHeadless"
        launcher.write_text("""#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv
pre = args.index('-preScript')
post = args.index('-postScript')
name = args[pre + 2]
output = pathlib.Path(args[pre + 3])
address = args[post + 2]
(output / 'analysis-options.txt').write_text(name + '=false\\n')
(output / 'address.txt').write_text(address[2:] + '\\n')
(output / 'name.txt').write_text('buttonPressed:\\n')
(output / 'language.txt').write_text('AARCH64:LE:64:AppleSilicon\\n')
(output / 'pseudocode.txt').write_text('void buttonPressed(void) {}\\n')
(output / 'function-facts.json').write_text(json.dumps({'schema_version': 2,
    'address': address, 'name': 'buttonPressed:', 'signature': 'void buttonPressed(void)',
    'is_thunk': False, 'is_external': False, 'callers': [], 'callers_truncated': False,
    'callees': [], 'callees_truncated': False,
    'basic_blocks': [], 'basic_blocks_truncated': False,
    'instruction_references': [], 'instruction_references_truncated': False,
    'instructions_scanned': 0,
    'limitation': 'Ghidra static FunctionManager observations.'}))
(output / 'ghidra.log').write_text('fake provider\\n')
""")
        output = self.root / "profiled"
        decompile_ghidra_function(self.binary, self.digest, "0x100001000",
                                  output, self.ghidra.parent, disabled_analyzer=
                                  "Objective-C Message Analyzer")
        checked = _validate_ghidra_direct(output, {self.digest})
        self.assertEqual(checked["summary"]["disabled_analyzer"],
                         "Objective-C Message Analyzer")
        (output / "analysis-options.txt").write_text("other=false\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            _validate_ghidra_direct(output, {self.digest})

    def test_rejects_partial_auto_analysis_even_with_pseudocode(self):
        launcher = self.ghidra / "analyzeHeadless"
        original = launcher.read_text()
        launcher.write_text(original + "\nprint('ERROR REPORT: Analysis timed out at 60 seconds. Processing not completed for file: test')\n")
        output = self.root / "partial"
        with self.assertRaisesRegex(RuntimeError, "direct Ghidra decompilation failed"):
            decompile_ghidra_function(self.binary, self.digest,
                                      "0x100001000", output, self.ghidra.parent)
        failure = json.loads((output / "failure.json").read_text())
        self.assertEqual(failure["type"], "TimeoutError")

    def test_batch_rejects_missing_completion_marker_for_all_targets(self):
        launcher = self.ghidra / "analyzeHeadless"
        launcher.write_text("""#!/usr/bin/env python3
import pathlib, sys
args = sys.argv
post, end = args.index('-postScript'), args.index('-max-cpu')
for address, path in zip(args[post + 2:end:2], args[post + 3:end:2]):
    target = pathlib.Path(path)
    (target / 'address.txt').write_text(address[2:] + '\\n')
    (target / 'name.txt').write_text('tapped:\\n')
    (target / 'language.txt').write_text('AARCH64:LE:64:AppleSilicon\\n')
    (target / 'pseudocode.txt').write_text('void tapped(void) {}\\n')
""")
        output = self.root / "batch-incomplete"
        with self.assertRaisesRegex(RuntimeError, "batch failed"):
            decompile_ghidra_batch(self.binary, self.digest,
                                   ["0x100001000", "0x100001100"], output,
                                   self.ghidra.parent)
        for target in sorted((output / "targets").iterdir()):
            record = json.loads((target / "manifest.json").read_text())
            failure = json.loads((target / "failure.json").read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(failure["type"], "ValueError")
            self.assertFalse((target / "summary.json").exists())
