"""Cross-check policy fixtures are not real FairPlay decryption evidence."""

import copy
import unittest

from copyapp.ios_cross_check import compare_recoveries


class OfflineCrossCheckTest(unittest.TestCase):
    def setUp(self):
        self.rows = [{"path": name, "uuid": uuid, "cryptoff": 64, "cryptsize": 8,
                      "encrypted_sha256": "1" * 64, "decrypted_sha256": "2" * 64,
                      "only_cryptid_and_encrypted_region_changed": True}
                     for name, uuid in (("Payload/App.app/Main", "3" * 32),
                                        ("Payload/App.app/PlugIns/Share.appex/Share", "4" * 32))]
        self.offline = {"status": "complete", "strategy": "fairplay_offline", "bundle_id": "com.example.app",
                        "plaintext_validation": "structural_only", "recovered_binaries": self.rows}
        self.device = {"bundle_id": "com.example.app", "installed_version": "1.0", "installed_build": "1",
                       "recovered_binaries": copy.deepcopy(self.rows)}
        self.package = {"bundle_id": "com.example.app", "version": "1.0", "build": "1"}

    def test_all_programs_must_match_in_source_and_recovered_bytes(self):
        result = compare_recoveries(self.offline, self.device, self.package)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["uuid"], "4" * 32)

    def test_an_unencrypted_passthrough_cannot_supply_positive_decryption_evidence(self):
        self.offline["strategy"] = "source_already_unencrypted"
        with self.assertRaisesRegex(ValueError, "genuine recovery"):
            compare_recoveries(self.offline, self.device, self.package)

    def test_different_build_or_partial_extension_inventory_is_rejected(self):
        changed = dict(self.package, build="2")
        with self.assertRaises(ValueError):
            compare_recoveries(self.offline, self.device, changed)
        self.device["recovered_binaries"].pop()
        with self.assertRaisesRegex(ValueError, "extension coverage"):
            compare_recoveries(self.offline, self.device, self.package)

    def test_matching_decrypted_hash_does_not_hide_wrong_encrypted_source_or_uuid(self):
        for key, value in (("encrypted_sha256", "5" * 64), ("uuid", "6" * 32),
                           ("decrypted_sha256", "7" * 64), ("cryptoff", 80)):
            with self.subTest(key=key):
                device = copy.deepcopy(self.device)
                device["recovered_binaries"][0][key] = value
                with self.assertRaisesRegex(ValueError, "binary identity"):
                    compare_recoveries(self.offline, device, self.package)
