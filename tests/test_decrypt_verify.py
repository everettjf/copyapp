import plistlib
import struct
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from copyapp.decrypt_verify import inspect_decrypted_ipa


def candidate_ipa(path: Path, cryptid: int, embedded_cryptid=None):
    binary = bytearray(56)
    struct.pack_into("<IiiIIIII", binary, 0, 0xFEEDFACF, 0x0100000C, 0, 2,
                     1, 24, 0, 0)
    struct.pack_into("<IIIIII", binary, 32, 0x2C, 24, 0, 0, cryptid, 0)
    info = {"CFBundleIdentifier": "com.example.test", "CFBundleExecutable": "Example",
            "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0"}
    with ZipFile(path, "w") as archive:
        archive.writestr("Payload/Example.app/Info.plist", plistlib.dumps(info))
        archive.writestr("Payload/Example.app/Example", binary)
        if embedded_cryptid is not None:
            nested = bytearray(binary)
            struct.pack_into("<I", nested, 48, embedded_cryptid)
            archive.writestr("Payload/Example.app/Frameworks/Utility.framework/RuntimeCore", nested)


class DecryptionCheckTest(unittest.TestCase):
    def test_rejects_nonzero_cryptid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.ipa"
            candidate_ipa(path, 1)
            result = inspect_decrypted_ipa(path, "com.example.test")
            self.assertFalse(result["header_check_passed"])
            self.assertIn("still_encrypted:Payload/Example.app/Example", result["failures"])

    def test_accepts_zero_cryptid_but_keeps_scope_narrow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.ipa"
            candidate_ipa(path, 0)
            result = inspect_decrypted_ipa(path, "com.example.test")
            self.assertTrue(result["header_check_passed"])
            self.assertEqual(result["checked_binaries"], 1)
            self.assertEqual(result["sc_info_file_count"], 0)

    def test_discovers_embedded_binary_with_nonmatching_framework_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.ipa"
            candidate_ipa(path, 0, embedded_cryptid=1)
            result = inspect_decrypted_ipa(path, "com.example.test")
            self.assertEqual(result["checked_binaries"], 2)
            self.assertIn("still_encrypted:Payload/Example.app/Frameworks/Utility.framework/RuntimeCore",
                          result["failures"])


if __name__ == "__main__":
    unittest.main()
