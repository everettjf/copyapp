import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from copyapp.native_disasm import (direct_branches, direct_calls, disassemble_native_candidates,
                                   disassemble_native_function)
from copyapp.report import _validate_native_candidate_queue, _validate_native_disassembly
from copyapp.verify import sha256_file, verify_case


BASE = 0x100000000
ENTRY = BASE + 0x100


def sample_macho() -> bytes:
    blob = bytearray(0x200)
    blob[:4] = b"\xcf\xfa\xed\xfe"
    struct.pack_into("<II", blob, 16, 2, 168)
    struct.pack_into("<II", blob, 32, 0x19, 152)
    blob[40:46] = b"__TEXT"
    struct.pack_into("<QQQQ", blob, 56, BASE, len(blob), 0, len(blob))
    struct.pack_into("<I", blob, 96, 1)
    blob[104:110] = b"__text"
    blob[120:126] = b"__TEXT"
    struct.pack_into("<QQI", blob, 136, ENTRY, 0x40, 0x100)
    struct.pack_into("<II", blob, 184, 0x26, 16)
    struct.pack_into("<II", blob, 192, 0x180, 4)
    blob[0x180:0x184] = bytes((0x80, 0x02, 0x10, 0))
    return bytes(blob)


class NativeDisassemblyTest(unittest.TestCase):
    def test_direct_call_parser_does_not_infer_indirect_dispatch(self):
        assembly = ("1000: 94000001 bl 0x2000 <_objc_msgSend$pushViewController:animated:>\n"
                    "1004: d63f0000 blr x0\n")
        calls, truncated = direct_calls(assembly)
        self.assertFalse(truncated)
        self.assertEqual(calls[0]["objc_selector_stub"], "pushViewController:animated:")
        self.assertEqual(len(calls), 1)
        self.assertEqual(direct_branches("1008: 14000001 b 0x2000\n"
                                         "100c: d61f0000 br x0\n"),
                         [{"site": "0x1008", "mnemonic": "b", "target": "0x2000"}])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.binary = self.root / "app"
        self.binary.write_bytes(sample_macho())
        self.digest = sha256_file(self.binary)
        self.assembly = (f"{ENTRY:x}: d65f03c0 ret\n"
                         f"{ENTRY + 4:x}: d65f03c0 ret\n")

    def _run(self, command, **kwargs):
        if "--find" in command:
            return CompletedProcess(command, 0, stdout=sys.executable, stderr="")
        return CompletedProcess(command, 0, stdout=self.assembly, stderr="")

    def test_exact_hash_and_next_function_boundary(self):
        output = self.root / "function"
        with patch("copyapp.native_disasm.shutil.which", return_value=sys.executable), \
             patch("copyapp.native_disasm.subprocess.run", side_effect=self._run):
            summary = disassemble_native_function(self.binary, self.digest,
                                                  hex(ENTRY), output)
        record = json.loads(summary.read_text())
        self.assertEqual(record["stop_address"], hex(ENTRY + 0x10))
        self.assertEqual(record["boundary"], "next_function_start")
        self.assertFalse(record["truncated"])
        self.assertTrue(verify_case(output))
        self.assertEqual(_validate_native_disassembly(output, {self.digest})["summary"],
                         record)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            disassemble_native_function(self.binary, "0" * 64, hex(ENTRY),
                                        self.root / "invalid")

    def test_candidate_queue_retains_source_and_unavailable_tool(self):
        candidates = self.root / "candidates"
        candidates.mkdir()
        source = {"schema_version": 1, "kind": "runtime_static_candidates",
                  "binary_path": str(self.binary), "binary_sha256": self.digest,
                  "candidates": [{"class": "Screen", "selector": "tap:",
                                  "static_address": hex(ENTRY),
                                  "binary_sha256": self.digest,
                                  "observations": [{"calls": 1}]}]}
        source_path = candidates / "candidates.json"
        source_path.write_text(json.dumps(source))
        (candidates / "manifest.json").write_text(json.dumps({
            "evidence": [{"path": "candidates.json",
                          "sha256": sha256_file(source_path)}]}))
        output = self.root / "queue"
        with patch("copyapp.native_disasm.shutil.which", return_value=sys.executable), \
             patch("copyapp.native_disasm.subprocess.run", side_effect=self._run):
            index = disassemble_native_candidates(candidates, output)
        self.assertEqual(json.loads(index.read_text())["status"], "complete")
        self.assertEqual(_validate_native_candidate_queue(
            output, source, source_path, {self.digest})["complete_count"], 1)
        failed = self.root / "no-tool"
        with patch("copyapp.native_disasm.shutil.which", return_value=None):
            index = disassemble_native_candidates(candidates, failed)
        self.assertEqual(json.loads(index.read_text())["status"], "unavailable")
        self.assertEqual(_validate_native_candidate_queue(
            failed, source, source_path, {self.digest})["complete_count"], 0)

    def test_unique_local_call_is_followed_and_rechecked(self):
        candidates = self.root / "candidates-follow"
        candidates.mkdir()
        source = {"schema_version": 1, "kind": "runtime_static_candidates",
                  "binary_path": str(self.binary), "binary_sha256": self.digest,
                  "candidates": [{"class": "Screen", "selector": "tap:",
                                  "static_address": hex(ENTRY),
                                  "binary_sha256": self.digest,
                                  "observations": [{"calls": 1}]}]}
        source_path = candidates / "candidates.json"
        source_path.write_text(json.dumps(source))
        (candidates / "manifest.json").write_text(json.dumps({
            "evidence": [{"path": "candidates.json",
                          "sha256": sha256_file(source_path)}]}))

        def run(command, **kwargs):
            if "--find" in command:
                return CompletedProcess(command, 0, stdout=sys.executable, stderr="")
            address = next(arg for arg in command if arg.startswith("--start-address="))
            if address.endswith(hex(ENTRY)):
                output = f"{ENTRY:x}: 94000004 bl 0x{ENTRY + 0x10:x} <__text+0x10>\n"
            else:
                output = f"{ENTRY + 0x10:x}: d65f03c0 ret\n"
            return CompletedProcess(command, 0, stdout=output, stderr="")

        output = self.root / "follow"
        with patch("copyapp.native_disasm.shutil.which", return_value=sys.executable), \
             patch("copyapp.native_disasm.subprocess.run", side_effect=run):
            index = disassemble_native_candidates(candidates, output)
        record = json.loads(index.read_text())
        self.assertEqual(record["followed"][0]["address"], hex(ENTRY + 0x10))
        self.assertEqual(record["decisions"][0]["status"], "followed")
        self.assertEqual(_validate_native_candidate_queue(
            output, source, source_path, {self.digest})["complete_count"], 2)
        record["decisions"][0]["eligible_targets"] = []
        index.write_text(json.dumps(record))
        with patch("copyapp.report.verify_case", return_value=True):
            with self.assertRaisesRegex(ValueError, "decision differs"):
                _validate_native_candidate_queue(output, source, source_path,
                                                 {self.digest})


if __name__ == "__main__":
    unittest.main()
