import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.indirect_follow import _files, discover_blr_sites, follow_indirect
from copyapp.verify import sha256_file
from tests.test_native_disasm import BASE, ENTRY, sample_macho


class IndirectFollowTest(unittest.TestCase):
    def test_resume_reuses_verified_branch_flow_after_ghidra_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            investigation = root / "investigation"
            for name in ("flow/playbook", "candidates", "native"):
                (investigation / name).mkdir(parents=True)
            binary = root / "App"
            binary.write_bytes(sample_macho())
            digest = sha256_file(binary)
            udid = "selected-test-device"
            prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
            script = investigation / "flow/playbook/playbook.json"
            script.write_text('{"bundle_id":"com.example.app"}\n')
            source = {"kind": "runtime_static_candidates", "binary_path": str(binary),
                      "binary_sha256": digest, "bundle_id": "com.example.app",
                      "device_id_sha256_prefix": prefix, "candidates": []}
            (investigation / "candidates/candidates.json").write_text(json.dumps(source))
            (investigation / "manifest.json").write_text(json.dumps({
                "kind": "investigated_ui_flow", "status": "complete",
                "bundle_id": "com.example.app", "device_id_sha256_prefix": prefix,
                "binary_sha256": digest, "source_script_sha256": sha256_file(script),
                "selected_methods": ["Screen::tap:"], "ui_backend": "ios-mcp"}))
            objc_index = root / "objc-index.json"
            objc_index.write_text(json.dumps({"binary_sha256": digest}))
            output = root / "follow"
            for name in ("sources", "branch-flow", "queue"):
                (output / name).mkdir(parents=True)
            (output / "sources/objc-index.json").write_bytes(objc_index.read_bytes())
            (output / "sources/investigation-manifest.json").write_bytes(
                (investigation / "manifest.json").read_bytes())
            (output / "branch-flow/manifest.json").write_text("{}\n")
            (output / "queue/failed.json").write_text("{}\n")
            sites = [{"address": hex(ENTRY + 4), "offset": ENTRY + 4 - BASE,
                      "register": "x19", "source_address": hex(ENTRY)}]
            run = {"schema_version": 1, "kind": "ghidra_indirect_follow",
                   "status": "failed", "bundle_id": "com.example.app",
                   "device_id_sha256_prefix": prefix, "binary_sha256": digest,
                   "source_investigation_manifest_sha256":
                       sha256_file(investigation / "manifest.json"),
                   "objc_index_sha256": sha256_file(objc_index),
                   "source_script_sha256": sha256_file(script),
                   "function_limit": 1, "branch_limit": 8,
                   "selected_sites": sites, "disabled_analyzer": None,
                   "error": {"stage": "direct_ghidra_queue", "type": "TimeoutError",
                             "message": "provider timed out"}}
            (output / "run.json").write_text(json.dumps(run))
            (output / "manifest.json").write_text(json.dumps({
                "kind": "ghidra_indirect_follow", "status": "failed",
                "evidence": _files(output)}))
            trace = {"requested_methods": ["Screen::tap:"],
                     "static_binary_sha256": digest,
                     "branch_requested_offsets": [hex(ENTRY + 4 - BASE)],
                     "branch_registers": [{"offset": hex(ENTRY + 4 - BASE),
                                           "register": "x19"}]}

            def fake_decompile(_candidate, destination, *_args):
                destination.mkdir()
                (destination / "manifest.json").write_text("{}\n")
                return destination / "manifest.json", True

            with patch("copyapp.indirect_follow.check_direct_ghidra"), \
                 patch("copyapp.indirect_follow.verify_case", return_value=True), \
                 patch("copyapp.indirect_follow._validate_native_candidate_queue",
                       return_value={"record": {}}), \
                 patch("copyapp.indirect_follow.rank_native_candidates",
                       return_value=[{"static_address": hex(ENTRY)}]), \
                 patch("copyapp.indirect_follow.discover_blr_sites", return_value=sites), \
                 patch("copyapp.indirect_follow._validate_flow_capture",
                       return_value={"trace": trace}), \
                 patch("copyapp.indirect_follow._validate_ghidra_direct_queue",
                       return_value={"record": {"selected": [
                           {"origin": "runtime_indirect_target"}]}}), \
                 patch("copyapp.indirect_follow.capture_flow") as capture, \
                 patch("copyapp.indirect_follow.decompile_candidate_queue",
                       side_effect=fake_decompile) as decompile:
                _, complete = follow_indirect(
                    udid, investigation, objc_index, output, root, root,
                    function_limit=1, resume=True)
            self.assertTrue(complete)
            capture.assert_not_called()
            decompile.assert_called_once()
            self.assertEqual(len(list((output / "attempts").iterdir())), 1)
            self.assertEqual(json.loads((output / "run.json").read_text())["status"],
                             "complete")

    def test_discovers_only_blr_sites_belonging_to_selected_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "App"
            blob = bytearray(sample_macho())
            struct.pack_into("<I", blob, 0x104, 0xd63f0260)
            struct.pack_into("<I", blob, 0x114, 0xd63f0280)
            binary.write_bytes(blob)
            native = root / "native"
            for name, address, instruction in (
                    ("selected", ENTRY, f"{ENTRY + 4:x}: d63f0260 blr x19\n"),
                    ("other", ENTRY + 0x10,
                     f"{ENTRY + 0x14:x}: d63f0280 blr x20\n")):
                folder = native / name
                folder.mkdir(parents=True)
                (folder / "summary.json").write_text(json.dumps({
                    "address": hex(address), "stop_address": hex(address + 0x10)}))
                (folder / "assembly.txt").write_text(instruction)
            record = {"results": [
                {"status": "complete", "address": hex(ENTRY),
                 "summary": "selected/summary.json"},
                {"status": "complete", "address": hex(ENTRY + 0x10),
                 "summary": "other/summary.json"}], "followed": []}
            observed = [{"static_address": hex(ENTRY)}]
            sites = discover_blr_sites({"binary_path": str(binary)}, native, record,
                                       observed)
            self.assertEqual(sites, [{"address": hex(ENTRY + 4),
                                      "offset": ENTRY + 4 - BASE,
                                      "register": "x19",
                                      "source_address": hex(ENTRY)}])
            (native / "selected/assembly.txt").write_text(
                f"{ENTRY + 4:x}: d63f0280 blr x20\n")
            with self.assertRaisesRegex(ValueError, "differs from acquired Mach-O"):
                discover_blr_sites({"binary_path": str(binary)}, native, record,
                                   observed)
            (native / "selected/assembly.txt").write_text(
                f"{ENTRY + 0x10:x}: d63f0260 blr x19\n")
            with self.assertRaisesRegex(ValueError, "outside its verified function"):
                discover_blr_sites({"binary_path": str(binary)}, native, record,
                                   observed)


if __name__ == "__main__":
    unittest.main()
