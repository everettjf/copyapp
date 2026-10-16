import hashlib
import json
import plistlib
import struct
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from copyapp.decrypt_package import (PINNED_HELPER_SHA256, _canonicalize_analysis_ipa,
                                     _verify_changed_binaries, _write_case_manifest)
from copyapp.decrypt_verify import inspect_decrypted_ipa, write_decryption_check
from copyapp.ipa import analyze_ipa, write_ipa_report
from copyapp.verify import verify_case


def binary(encrypted=True):
    value = bytearray(80)
    struct.pack_into("<IiiIIIII", value, 0, 0xFEEDFACF, 0x0100000C, 0, 2,
                     1, 24, 0, 0)
    struct.pack_into("<IIIIII", value, 32, 0x2C, 24, 64, 8, int(encrypted), 0)
    value[64:72] = b"ENCRYPT!" if encrypted else b"CODECODE"
    return bytes(value)


class PackageByteAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.snapshot = self.root / "source.ipa"
        self.recovered = self.root / "recovered.ipa"
        self.main = "Payload/Example.app/Example"
        self.extension = "Payload/Example.app/PlugIns/Share.appex/Share"
        plist = plistlib.dumps({"CFBundleIdentifier": "com.example.test",
                                "CFBundleExecutable": "Example",
                                "CFBundleVersion": "1",
                                "CFBundleShortVersionString": "1.0"})
        with ZipFile(self.snapshot, "w") as archive:
            archive.writestr("Payload/Example.app/Info.plist", plist)
            archive.writestr(self.main, binary())
            archive.writestr(self.extension, binary())
        self.index = analyze_ipa(self.snapshot)

    def tearDown(self):
        self.temp.cleanup()

    def write_result(self, corrupt=False):
        extension = bytearray(binary(False))
        if corrupt:
            extension[60] = 7
        with ZipFile(self.recovered, "w") as archive:
            archive.writestr(self.main, binary(False))
            archive.writestr(self.extension, extension)

    def test_accepts_main_and_extension_with_only_encryption_changes(self):
        self.write_result()
        rows = _verify_changed_binaries(self.snapshot, self.recovered, self.index)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["only_cryptid_and_encrypted_region_changed"] for row in rows))

    def test_rejects_modified_code_outside_encrypted_range(self):
        self.write_result(corrupt=True)
        with self.assertRaisesRegex(ValueError, "outside encrypted region"):
            _verify_changed_binaries(self.snapshot, self.recovered, self.index)

    def _device_archive(self, destination, stamp, plist_override=None, omitted=()):
        with ZipFile(self.snapshot) as source, ZipFile(destination, "w") as archive:
            for info in source.infolist():
                if info.filename in omitted:
                    continue
                data = source.read(info.filename)
                if info.filename in (self.main, self.extension):
                    data = binary(False)
                if info.filename.endswith("Info.plist") and plist_override is not None:
                    data = plist_override
                device_info = ZipInfo(info.filename, stamp)
                device_info.compress_type = info.compress_type
                archive.writestr(device_info, data)

    def test_canonical_ipa_ignores_device_zip_timestamps(self):
        first = self.root / "device-1.ipa"
        second = self.root / "device-2.ipa"
        out1 = self.root / "canonical-1.ipa"
        out2 = self.root / "canonical-2.ipa"
        self._device_archive(first, (2026, 10, 15, 12, 0, 0))
        self._device_archive(second, (2026, 10, 15, 14, 0, 0))
        replaced = {self.main, self.extension}
        for recovered, output in ((first, out1), (second, out2)):
            rows = _verify_changed_binaries(self.snapshot, recovered, self.index)
            self.assertEqual({row["path"] for row in rows}, replaced)
            _canonicalize_analysis_ipa(self.snapshot, recovered, output, replaced)
        self.assertEqual(out1.read_bytes(), out2.read_bytes())
        with ZipFile(out1) as archive, ZipFile(self.snapshot) as source:
            self.assertEqual(archive.read(self.main), binary(False))
            self.assertEqual(archive.read(self.extension), binary(False))
            self.assertEqual(archive.read("Payload/Example.app/Info.plist"),
                             source.read("Payload/Example.app/Info.plist"))

    def test_canonical_ipa_rejects_nonbinary_mutation(self):
        self._device_archive(self.recovered, (2026, 10, 15, 14, 0, 0),
                             plist_override=b"changed")
        with self.assertRaisesRegex(ValueError, "changed unencrypted member"):
            _canonicalize_analysis_ipa(self.snapshot, self.recovered,
                                       self.root / "canonical.ipa",
                                       {self.main, self.extension})

    def test_canonical_ipa_accepts_only_sc_info_omission(self):
        receipt = "Payload/Example.app/SC_Info/Example.sinf"
        with ZipFile(self.snapshot, "a") as source:
            source.writestr(receipt, b"receipt")
        self._device_archive(self.recovered, (2026, 10, 15, 14, 0, 0),
                             omitted={receipt})
        output = self.root / "canonical.ipa"
        _canonicalize_analysis_ipa(self.snapshot, self.recovered, output,
                                   {self.main, self.extension})
        with ZipFile(output) as archive:
            self.assertNotIn(receipt, archive.namelist())

        other = self.root / "missing-plist.ipa"
        self._device_archive(other, (2026, 10, 15, 14, 0, 0),
                             omitted={"Payload/Example.app/Info.plist"})
        with self.assertRaisesRegex(ValueError, "member list differs"):
            _canonicalize_analysis_ipa(self.snapshot, other,
                                       self.root / "invalid.ipa",
                                       {self.main, self.extension})

    def test_standalone_package_case_rechecks_source_and_changed_bytes(self):
        self._device_archive(self.recovered, (2026, 10, 15, 14, 0, 0))
        case = self.root / "case"
        case.mkdir()
        ipa = case / "analysis.ipa"
        changed = _verify_changed_binaries(self.snapshot, self.recovered, self.index)
        _canonicalize_analysis_ipa(self.snapshot, self.recovered, ipa,
                                   {item["path"] for item in changed})
        check = inspect_decrypted_ipa(ipa, "com.example.test")
        self.assertTrue(check["header_check_passed"])
        write_decryption_check(check, case / "check")
        write_ipa_report(analyze_ipa(ipa), case / "static")
        (case / "static/objc-status.json").write_text(
            json.dumps({"status": "unsupported", "reason": "synthetic Mach-O"}))
        (case / "device-run").mkdir()
        device_id = "00000000-0000000000000000"
        (case / "device-run/result.json").write_text(json.dumps({
            "device_id": device_id, "exit_code": 0,
            "command": ["helper", "-v", "decrypt", "com.example.test", "/app", "/out"],
        }))
        (case / "device-run/output.txt").write_text("fixture")
        record = {
            "schema_version": 1, "bundle_id": "com.example.test",
            "device_id_sha256_prefix": hashlib.sha256(device_id.encode()).hexdigest()[:16],
            "installed_version": "1.0", "installed_build": "1",
            "source_snapshot_sha256": hashlib.sha256(self.snapshot.read_bytes()).hexdigest(),
            "analysis_ipa_sha256": hashlib.sha256(ipa.read_bytes()).hexdigest(),
            "helper_sha256": PINNED_HELPER_SHA256,
            "all_macho_headers_decrypted": True,
            "checked_macho_count": check["checked_binaries"],
            "recovered_binaries": changed,
            "objc_class_count": None, "objc_method_count": None,
        }
        (case / "decryption.json").write_text(json.dumps(record))
        _write_case_manifest(case, self.snapshot, record)
        self.assertTrue(verify_case(case))
        record["recovered_binaries"][0]["changed_encrypted_bytes"] += 1
        (case / "decryption.json").write_text(json.dumps(record))
        _write_case_manifest(case, self.snapshot, record)
        self.assertFalse(verify_case(case))


if __name__ == "__main__":
    unittest.main()
