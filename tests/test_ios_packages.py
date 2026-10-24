import hashlib
import io
import plistlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from tests.test_decrypt_package import binary
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.ios_offline import FAIRPLAY_REVISION, decrypt_offline
from copyapp.ios_packages import download_package, import_package
from copyapp.verify import sha256_file, verify_case


BUNDLE = "com.example.test"
MAIN = "Payload/Example.app/Example"
EXTENSION = "Payload/Example.app/PlugIns/Share.appex/Share"
SECRET = b"0123456789abcdef"


def ipa(path, encrypted=True, fat=False):
    executable = binary(encrypted)
    if fat:
        header = struct.pack(">IIiiIII", 0xCAFEBABE, 1, 0x0100000C, 0, 32, len(executable), 0)
        executable = header.ljust(32, b"\0") + executable
    with ZipFile(path, "w") as archive:
        archive.writestr("Payload/Example.app/Info.plist", plistlib.dumps({
            "CFBundleIdentifier": BUNDLE, "CFBundleExecutable": "Example",
            "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0",
            "CFBundleSupportedPlatforms": ["iPhoneOS"]}))
        archive.writestr(MAIN, executable)
        archive.writestr(EXTENSION, binary(encrypted))
        archive.writestr("Payload/Example.app/resource.txt", b"resource")


class IosPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.ipa"
        ipa(self.source)
        self.package = self.root / "package"
        import_package(self.source, self.package, BUNDLE)
        self.credentials = self.root / "credentials"
        self.credentials.mkdir()
        (self.credentials / "main.bin").write_bytes(SECRET)
        self.tool = self.root / "ipatool"
        self.tool.write_bytes(b"fake ipatool executable")
        self.console = redirect_stdout(io.StringIO())
        self.console.__enter__()
        self.addCleanup(self.console.__exit__, None, None, None)

    def test_import_retains_exact_source_and_survives_copying(self):
        self.assertTrue(verify_case(self.package))
        self.assertEqual(sha256_file(self.source), sha256_file(self.package / "input.ipa"))
        copied = self.root / "copied"
        shutil.copytree(self.package, copied)
        self.assertTrue(verify_case(copied))
        with self.assertRaisesRegex(ValueError, "Bundle ID"):
            import_package(self.source, self.root / "wrong", "com.another.app")

    def test_unencrypted_input_is_unchanged_and_never_claims_a_decrypt(self):
        plain = self.root / "plain.ipa"
        ipa(plain, encrypted=False)
        imported = self.root / "plain-package"
        import_package(plain, imported)
        with patch("copyapp.ios_offline._prepare_tool") as prepare:
            _, complete = decrypt_offline(imported, self.root / "offline")
        self.assertTrue(complete)
        self.assertTrue(verify_case(self.root / "offline"))
        prepare.assert_not_called()
        record = read_json(self.root / "offline/offline.json")
        self.assertEqual(record["strategy"], "source_already_unencrypted")
        self.assertEqual(record["recovered_binaries"], [])
        self.assertIsNone(record["credential_ref"])

    def test_missing_and_invalid_credentials_are_verified_failed_attempts(self):
        for reference in [None, "../../escape", "absent"]:
            out = self.root / ("missing-" + str(len(list(self.root.iterdir()))))
            with patch("copyapp.ios_offline._prepare_tool") as prepare:
                _, complete = decrypt_offline(self.package, out, credential_ref=reference,
                                               credential_store=self.credentials)
            self.assertFalse(complete)
            self.assertTrue(verify_case(out))
            self.assertEqual(read_json(out / "offline.json")["error"], "credential_unavailable")
            prepare.assert_not_called()

    def _offline_fixture(self, mutation=None, checkout_defaults=False):
        # Adapter fixture: this tests byte audits, not FairPlay cryptography.
        sources = {"decrypt.py": b"fixture", "core.py": b"fixture core", "transform.c": b"fixture c",
                   "transform_const_data.bin": b"fixture constants"}
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()}

        def prepare(_source, out):
            self.last_prepared_source = _source
            out.mkdir()
            for name, data in sources.items():
                (out / name).write_bytes(data)
            (out / "transform").write_bytes(b"fixture executable")
            return {"name": "EthanArbuckle/fairplay-decrypt", "revision": FAIRPLAY_REVISION,
                    "sources": hashes, "transform_sha256": sha256_file(out / "transform"),
                    "python_version": "fixture"}

        def run(command, **_kwargs):
            with ZipFile(command[4]) as before, ZipFile(command[5], "w") as after:
                for info in before.infolist():
                    value = before.read(info.filename)
                    if info.filename in (MAIN, EXTENSION):
                        value = binary(False)
                    if mutation:
                        value = mutation(info.filename, value)
                    after.writestr(info, value)
            return subprocess.CompletedProcess(command, 0, SECRET + b" session=token", SECRET)

        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch("copyapp.ios_offline.FAIRPLAY_FILES", hashes))
        stack.enter_context(patch("copyapp.ios_offline._prepare_tool", side_effect=prepare))
        stack.enter_context(patch("copyapp.ios_offline.subprocess.run", side_effect=run))
        self.addCleanup(stack.close)
        out = self.root / "offline"
        _, complete = decrypt_offline(self.package, out, None if checkout_defaults else Path("fixture"),
                                       "main", None if checkout_defaults else self.credentials)
        return out, complete

    def test_offline_defaults_use_explicit_checkout_without_copying_credential_contents(self):
        store = self.root / "cases/credentials/fairplay"
        store.mkdir(parents=True)
        shutil.copyfile(self.credentials / "main.bin", store / "main.bin")
        with patch("copyapp.ios_offline.source_root", return_value=self.root):
            output, complete = self._offline_fixture(checkout_defaults=True)
        self.assertTrue(complete)
        self.assertEqual(self.last_prepared_source, self.root / "toolchains/fairplay-decrypt-src")
        self.assertNotIn(str(store), (output / "offline.json").read_text())

    def test_all_binaries_and_resources_audited_without_claiming_plaintext_correctness(self):
        out, complete = self._offline_fixture()
        self.assertTrue(complete)
        self.assertTrue(verify_case(out))
        record = read_json(out / "offline.json")
        self.assertEqual(len(record["recovered_binaries"]), 2)
        self.assertEqual(record["plaintext_validation"], "structural_only")
        for path in out.rglob("*"):
            if path.is_file() and path.suffix in (".json", ".md", ".txt", ".log"):
                self.assertNotIn(SECRET, path.read_bytes())
                self.assertNotIn(b"session=token", path.read_bytes())

    def test_partial_decoder_success_cannot_hide_an_encrypted_extension(self):
        out, complete = self._offline_fixture(lambda name, value: binary(True) if name == EXTENSION else value)
        self.assertFalse(complete)
        self.assertTrue(verify_case(out))
        self.assertEqual(read_json(out / "offline.json")["error"], "package_audit_failed")

    def test_thin_x86_64_magic_is_not_accepted_as_arm64(self):
        source = self.root / "x86.ipa"
        with ZipFile(self.source) as before, ZipFile(source, "w") as after:
            for info in before.infolist():
                value = before.read(info.filename)
                if info.filename == MAIN:
                    value = bytearray(value)
                    struct.pack_into("<I", value, 4, 0x01000007)
                after.writestr(info, value)
        package = self.root / "x86-package"
        import_package(source, package)
        with patch("copyapp.ios_offline._prepare_tool") as tool:
            _, complete = decrypt_offline(package, self.root / "x86-offline")
            tool.assert_not_called()
        self.assertFalse(complete)
        self.assertEqual(read_json(self.root / "x86-offline/offline.json")["error"], "unsupported_binary_inventory")

    def test_unsupported_embedded_macho_is_indexed_and_blocks_false_package_success(self):
        source = self.root / "embedded32.ipa"
        ipa(source, encrypted=False)
        hidden = "Payload/Example.app/PlugIns/Other.appex/Other"
        with ZipFile(source, "a") as archive:
            archive.writestr(hidden, b"\xce\xfa\xed\xfe" + bytes(60))
        package = self.root / "embedded32-package"
        import_package(source, package)
        self.assertEqual(read_json(package / "package-index.json")["unsupported_binaries"][0]["path"], hidden)
        self.assertTrue(verify_case(package))
        with patch("copyapp.ios_offline._prepare_tool") as decoder:
            _, complete = decrypt_offline(package, self.root / "embedded32-offline")
            decoder.assert_not_called()
        self.assertFalse(complete)
        self.assertTrue(verify_case(self.root / "embedded32-offline"))

    def test_unencrypted_selected_fat_slice_does_not_prove_other_slices_are_clear(self):
        source = self.root / "fat-clear-selected.ipa"
        ipa(source, encrypted=False, fat=True)
        package = self.root / "fat-clear-package"
        import_package(source, package)
        _, complete = decrypt_offline(package, self.root / "fat-clear-offline")
        self.assertFalse(complete)
        self.assertEqual(read_json(self.root / "fat-clear-offline/offline.json")["error"], "unsupported_binary_inventory")

    def test_macho_outside_primary_app_is_not_silently_omitted(self):
        source = self.root / "extra-program.ipa"
        ipa(source, encrypted=False)
        with ZipFile(source, "a") as archive:
            archive.writestr("Payload/UnindexedProgram", binary(True))
        package = self.root / "extra-package"
        import_package(source, package)
        row = read_json(package / "package-index.json")["unsupported_binaries"][0]
        self.assertEqual(row["path"], "Payload/UnindexedProgram")
        self.assertEqual(row["status"], "unsupported_macho_location")
        self.assertFalse(decrypt_offline(package, self.root / "extra-offline")[1])

    def test_resource_or_out_of_range_changes_fail_independent_audit(self):
        def mutation(name, value):
            if name == MAIN:
                changed = bytearray(value)
                changed[60] = 7
                return bytes(changed)
            return value
        out, complete = self._offline_fixture(mutation)
        self.assertFalse(complete)
        self.assertTrue(verify_case(out))

    def test_cryptid_zero_without_changed_code_is_not_recovery(self):
        def mutation(name, value):
            if name == MAIN:
                original = bytearray(binary(True))
                struct.pack_into("<I", original, 48, 0)
                return bytes(original)
            return value
        out, complete = self._offline_fixture(mutation)
        self.assertFalse(complete)
        self.assertTrue(verify_case(out))

    def test_rehashed_recovered_resource_mutation_is_rejected(self):
        out, complete = self._offline_fixture()
        self.assertTrue(complete)
        recovered = out / "analysis.ipa"
        with ZipFile(recovered) as archive:
            members = [(item, archive.read(item.filename)) for item in archive.infolist()]
        with ZipFile(recovered, "w") as archive:
            for info, value in members:
                archive.writestr(info, b"changed" if info.filename.endswith("resource.txt") else value)
        record = read_json(out / "offline.json")
        record["analysis_ipa_sha256"] = sha256_file(recovered)
        write_json(out / "offline.json", record)
        seal_case(out, "ios_offline_package", status="complete", bundle_id=BUNDLE)
        self.assertFalse(verify_case(out))

    def test_fat_input_is_explicitly_rejected_until_all_slice_audits_exist(self):
        source = self.root / "fat.ipa"
        ipa(source, fat=True)
        package = self.root / "fat-package"
        import_package(source, package)
        out = self.root / "fat-offline"
        _, complete = decrypt_offline(package, out)
        self.assertFalse(complete)
        self.assertEqual(read_json(out / "offline.json")["error"], "unsupported_binary_inventory")
        self.assertTrue(verify_case(out))

    def test_download_pins_tool_and_version_without_retaining_account_output(self):
        calls = []
        def run(command, **_kwargs):
            calls.append(command)
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, b"ipatool version 2.7.0", b"")
            shutil.copyfile(self.source, Path(command[command.index("--output") + 1]))
            return subprocess.CompletedProcess(command, 0, b'email=private@example.test token=SECRET', SECRET)
        out = self.root / "download"
        with patch("copyapp.ios_packages.subprocess.run", side_effect=run):
            _, complete = download_package(BUNDLE, out, self.tool, "12345")
        self.assertTrue(complete)
        self.assertTrue(verify_case(out))
        self.assertIn("--non-interactive", calls[-1])
        self.assertNotIn("--purchase", calls[-1])
        for path in out.glob("*.json"):
            self.assertNotIn(b"private@example.test", path.read_bytes())
            self.assertNotIn(SECRET, path.read_bytes())

    def test_unreviewed_tool_version_is_rejected_before_account_download(self):
        with patch("copyapp.ios_packages.subprocess.run", return_value=subprocess.CompletedProcess(
                [], 0, b"ipatool version 9.9.9", b"")) as runner:
            with self.assertRaisesRegex(ValueError, "reviewed 2.7.0"):
                download_package(BUNDLE, self.root / "unsupported-tool", self.tool)
            self.assertEqual(runner.call_count, 1)

    def test_default_ipatool_comes_from_configured_source_checkout(self):
        tool = self.root / "toolchains/bin/ipatool"
        tool.parent.mkdir(parents=True)
        shutil.copyfile(self.tool, tool)

        def run(command, **_kwargs):
            self.assertEqual(command[0], str(tool.resolve()))
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, b"2.7.0", b"")
            shutil.copyfile(self.source, Path(command[command.index("--output") + 1]))
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with patch("copyapp.ios_packages.source_root", return_value=self.root), \
                patch("copyapp.ios_packages.subprocess.run", side_effect=run):
            _, complete = download_package(BUNDLE, self.root / "default-download")
        self.assertTrue(complete)

    def test_wrong_app_download_and_account_failure_never_become_success(self):
        def run(command, **_kwargs):
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, b"2.7.0", b"")
            shutil.copyfile(self.source, Path(command[command.index("--output") + 1]))
            return subprocess.CompletedProcess(command, 0, b"", b"")
        out = self.root / "wrong-download"
        with patch("copyapp.ios_packages.subprocess.run", side_effect=run):
            _, complete = download_package("com.other.app", out, self.tool)
        self.assertFalse(complete)
        self.assertTrue(verify_case(out))
        self.assertEqual(read_json(out / "package.json")["error"], "package_identity_or_structure_mismatch")


if __name__ == "__main__":
    unittest.main()
