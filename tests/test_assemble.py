import hashlib
import json
import plistlib
import struct
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from copyapp.assemble import assemble_analysis_ipa, assemble_main_ipa


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(root):
    original = bytearray(80)
    struct.pack_into("<IiiIIIII", original, 0, 0xFEEDFACF, 0x0100000C, 0, 2,
                     1, 24, 0, 0)
    struct.pack_into("<IIIIII", original, 32, 0x2C, 24, 64, 8, 1, 0)
    original[64:72] = b"ENCRYPT!"
    recovered = bytearray(original)
    struct.pack_into("<I", recovered, 48, 0)
    recovered[64:72] = b"CODECODE"
    case = root / "case"
    case.mkdir()
    (case / "encrypted-main.bin").write_bytes(original)
    (case / "decrypted-main.bin").write_bytes(recovered)
    (case / "decryption.json").write_text(json.dumps({
        "bundle_id": "com.example.test", "executable": "Example",
        "installed_version": "1.0", "cryptoff": 64, "cryptsize": 8,
        "encrypted_file_sha256": digest(original),
        "decrypted_file_sha256": digest(recovered),
    }))
    plist = {"CFBundleIdentifier": "com.example.test", "CFBundleExecutable": "Example",
             "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0"}
    snapshot = root / "snapshot.ipa"
    with ZipFile(snapshot, "w") as archive:
        archive.writestr("Payload/Example.app/Info.plist", plistlib.dumps(plist))
        archive.writestr("Payload/Example.app/Example", original)
        archive.writestr("Payload/Example.app/PlugIns/Extension.appex/Extension", original)
    return snapshot, case, bytes(recovered)


class AssembleTest(unittest.TestCase):
    def test_replaces_main_and_extension_only_from_matching_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, main_case, recovered = fixture(root)
            extension_case = root / "extension"
            extension_case.mkdir()
            (extension_case / "encrypted-extension.bin").write_bytes(
                (main_case / "encrypted-main.bin").read_bytes())
            (extension_case / "decrypted-extension.bin").write_bytes(recovered)
            record = json.loads((main_case / "decryption.json").read_text())
            record["executable"] = "Extension"
            record["relative_path"] = "PlugIns/Extension.appex/Extension"
            (extension_case / "decryption.json").write_text(json.dumps(record))
            manifest = assemble_analysis_ipa(snapshot, [main_case, extension_case], root / "out")
            result = json.loads(manifest.read_text())
            self.assertTrue(result["all_macho_headers_decrypted"])
            self.assertEqual(len(result["recovered_binaries"]), 2)
            with ZipFile(root / "out" / "analysis-snapshot.ipa") as archive:
                self.assertEqual(archive.read("Payload/Example.app/Example"), recovered)
                self.assertEqual(archive.read("Payload/Example.app/PlugIns/Extension.appex/Extension"), recovered)

    def test_replaces_only_main_and_reports_remaining_encrypted_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, case, recovered = fixture(root)
            manifest = assemble_main_ipa(snapshot, case, root / "out")
            result = json.loads(manifest.read_text())
            self.assertFalse(result["all_macho_headers_decrypted"])
            self.assertIn("still_encrypted:Payload/Example.app/PlugIns/Extension.appex/Extension",
                          result["remaining_failures"])
            with ZipFile(root / "out" / "analysis-snapshot.ipa") as archive:
                self.assertEqual(archive.read("Payload/Example.app/Example"), recovered)

    def test_rejects_unexpected_patch_outside_encrypted_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, case, _ = fixture(root)
            path = case / "decrypted-main.bin"
            bad = bytearray(path.read_bytes())
            bad[60] = 7
            path.write_bytes(bad)
            record_path = case / "decryption.json"
            record = json.loads(record_path.read_text())
            record["decrypted_file_sha256"] = digest(bad)
            record_path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "outside cryptid and encrypted range"):
                assemble_main_ipa(snapshot, case, root / "out")


if __name__ == "__main__":
    unittest.main()
