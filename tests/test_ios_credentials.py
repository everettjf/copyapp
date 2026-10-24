import contextlib
import hashlib
import io
from pathlib import Path
import plistlib
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from copyapp import ios_credentials as credentials
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.ios_packages import import_package
from copyapp.ssh_profile import save_ssh_profile
from copyapp.verify import sha256_file, verify_case
from tests.test_ios_packages import BUNDLE, ipa


UDID = "00008110-001650202E81401E"
SECRET = b"test-credential!"
LICENSE = b"fake-supported-license"
APP = {"CFBundleIdentifier": BUNDLE, "CFBundleVersion": "1",
       "CFBundleShortVersionString": "1.0", "CFBundleExecutable": "Example",
       "Path": "/var/containers/Bundle/Application/SAMPLE/Example.app"}


class FakeDevice:
    instances = []
    roothide = True
    native_id = b"verified-device"
    def __init__(self, command):
        self.command = command
        self.trigger_directory = "/private/var/tmp/fp-trigger-example"
        self.cleaned = False
        self.instances.append(self)
    def path(self, name):
        return "/private/var/tmp/fp-retrieve-example/" + name
    def write(self, name, data, executable=False):
        return self.path(name)
    def run(self, command):
        return b""
    def read(self, path):
        if path.endswith("device-udid.bin"):
            return self.native_id
        if path.endswith("Info.plist"):
            return plistlib.dumps(APP)
        if path.endswith(".sinf"):
            return LICENSE
        if path.endswith("credential.bin"):
            return SECRET
        raise AssertionError("unexpected remote read")
    def cleanup(self):
        self.cleaned = True


class CredentialRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "case"
        self.store = self.root / "private-store"
        self.key = self.root / "identity"
        self.hosts = self.root / "known-hosts"
        self.key.write_text("fake SSH identity")
        self.hosts.write_text("fake pinned host")
        self.sources = {"core.py": hashlib.sha256(b"public source").hexdigest()}
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(credentials, "CREDENTIAL_SOURCES", self.sources))
        self.target = self.stack.enter_context(patch.object(credentials, "_target", new=AsyncMock(
            return_value=({"ProductType": "iPhone14,7", "ProductVersion": "17.3.1", "BuildVersion": "21D61"}, dict(APP)))))
        self.tunnel = self.stack.enter_context(patch.object(credentials, "exact_ssh_tunnel"))
        self.tunnel.return_value.__enter__.return_value = 22317
        self.prepare = self.stack.enter_context(patch.object(credentials, "_prepare_tool", side_effect=self.prepare_tool))
        self.device = self.stack.enter_context(patch.object(credentials, "CredentialDevice", FakeDevice))
        FakeDevice.native_id = b"verified-device"
        FakeDevice.instances = []
        self.retriever = SimpleNamespace(
            BUNDLE=self.root, MAX_SINF_BYTES=1048576,
            fairplay_device_id=Mock(return_value=b"verified-device"),
            supported_sinf=Mock(return_value=True), sinf_field=Mock(return_value=b"account"),
            license_sinf=Mock(return_value=LICENSE), restart_fairplayd=Mock(return_value=123),
            observe_uid_layer=Mock())
        self.core = SimpleNamespace(derive_work16=Mock(return_value=b"work"))
        modules = self.stack.enter_context(patch.object(credentials, "_modules"))
        modules.return_value.__enter__.return_value = (self.retriever, self.core)

    def prepare_tool(self, source, output):
        output.mkdir()
        (output / "core.py").write_bytes(b"public source")
        bundle = output / "credential-retrieval/build/bundle"
        bundle.mkdir(parents=True)
        for name in credentials.DEVICE_FILES:
            (bundle / name).write_bytes(b"public helper " + name.encode())
        return {"revision": credentials.FAIRPLAY_REVISION, "sources": self.sources,
                "helpers": {name: sha256_file(bundle / name) for name in credentials.DEVICE_FILES}}

    def run_retrieval(self, **kwargs):
        options = dict(store=self.store, ssh_identity=self.key, ssh_known_hosts=self.hosts)
        options.update(kwargs)
        return credentials.retrieve_credential(UDID, BUNDLE, "account-a", self.out, **options)

    def record(self):
        return read_json(self.out / "retrieval.json")

    def reseal(self):
        record = self.record()
        seal_case(self.out, "ios_fairplay_credential", status=record["status"], bundle_id=BUNDLE)

    def test_success_uses_exact_route_and_keeps_secret_outside_verifiable_case(self):
        _, success = self.run_retrieval()
        self.assertTrue(success)
        self.assertTrue(verify_case(self.out))
        self.assertTrue(FakeDevice.instances[0].cleaned)
        saved = self.store / "account-a.bin"
        self.assertEqual(saved.read_bytes(), SECRET)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.stat().st_mode & 0o777, 0o700)
        self.tunnel.assert_called_once_with(UDID, 22222, self.key, self.hosts, "mobile")
        for path in self.out.rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET, path.read_bytes())
                self.assertNotIn(hashlib.sha256(SECRET).hexdigest().encode(), path.read_bytes())
                self.assertNotIn(str(saved).encode(), path.read_bytes())
        saved.unlink()
        self.assertTrue(verify_case(self.out))  # verification never needs the credential

    def test_collision_and_evidence_store_overlap_fail_before_device_work(self):
        for index, overlap in enumerate((False, True)):
            self.out = self.root / ("case" + str(index))
            if overlap:
                selected = self.out / "credentials"
            else:
                selected = self.store
                selected.mkdir()
                (selected / "account-a.bin").write_bytes(SECRET)
            _, complete = self.run_retrieval(store=selected)
            self.assertFalse(complete)
            self.assertEqual(self.record()["error"], "credential_store_unavailable")
            self.assertTrue(verify_case(self.out))
        self.target.assert_not_called()
        self.prepare.assert_not_called()
        self.assertEqual((self.store / "account-a.bin").read_bytes(), SECRET)

    def test_native_identity_mismatch_cleans_and_never_restarts_daemon(self):
        FakeDevice.native_id = b"another-device"
        _, complete = self.run_retrieval()
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "device_identity_mismatch")
        self.retriever.restart_fairplayd.assert_not_called()
        self.assertTrue(FakeDevice.instances[0].cleaned)
        self.assertFalse(self.store.exists())
        self.assertTrue(verify_case(self.out))

    def test_unsupported_license_does_not_restart_daemon(self):
        self.retriever.supported_sinf.return_value = False
        _, complete = self.run_retrieval()
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "unsupported_license")
        self.retriever.restart_fairplayd.assert_not_called()
        self.assertTrue(verify_case(self.out))

    def test_observer_failure_omits_raw_error_and_preserves_failed_case(self):
        self.retriever.observe_uid_layer.side_effect = RuntimeError("private account/session output")
        _, complete = self.run_retrieval()
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "observation_failed")
        self.assertTrue(FakeDevice.instances[0].cleaned)
        self.assertFalse(self.store.exists())
        self.assertTrue(verify_case(self.out))
        self.assertNotIn("private account/session", (self.out / "retrieval.json").read_text())

    def test_interrupted_observation_is_cleaned_and_retained(self):
        self.retriever.observe_uid_layer.side_effect = KeyboardInterrupt()
        _, complete = self.run_retrieval()
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "interrupted")
        self.assertTrue(FakeDevice.instances[0].cleaned)
        self.assertTrue(verify_case(self.out))

    def test_invalid_credential_is_never_saved(self):
        self.core.derive_work16.side_effect = ValueError("credential does not decode this SINF")
        _, complete = self.run_retrieval()
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "credential_validation_failed")
        self.assertFalse(self.store.exists())
        self.assertTrue(verify_case(self.out))

    def test_cleanup_failure_does_not_publish_credential(self):
        with patch.object(FakeDevice, "cleanup", side_effect=RuntimeError("SSH cleanup unavailable")):
            _, complete = self.run_retrieval()
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "cleanup_failed")
        self.assertFalse(self.store.exists())
        self.assertTrue(verify_case(self.out))

    def package(self):
        source = self.root / "source.ipa"
        ipa(source)
        package = self.root / "source-package"
        import_package(source, package, BUNDLE)
        return package

    def test_package_account_mismatch_refuses_before_observation(self):
        self.retriever.sinf_field.side_effect = [b"one-account", b"another-account"]
        _, complete = self.run_retrieval(package=self.package())
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "package_account_mismatch")
        self.retriever.restart_fairplayd.assert_not_called()
        self.assertTrue(verify_case(self.out))

    def test_selected_package_requires_two_license_checks_and_detects_rehashed_tampering(self):
        _, complete = self.run_retrieval(package=self.package(), sinf_member="selected.sinf")
        self.assertTrue(complete)
        self.assertEqual(self.core.derive_work16.call_count, 2)
        self.assertTrue(verify_case(self.out))
        record = self.record()
        record["stages"]["credential_matches_package_license"] = False
        write_json(self.out / "retrieval.json", record)
        self.reseal()
        self.assertFalse(verify_case(self.out))

    def test_source_hashes_are_checked_again_even_after_manifest_reseal(self):
        self.run_retrieval()
        (self.out / "tool/core.py").write_bytes(b"modified public source")
        self.reseal()
        self.assertFalse(verify_case(self.out))

    def test_new_reference_and_trusted_host_are_required(self):
        with self.assertRaises(ValueError):
            credentials.retrieve_credential(UDID, BUNDLE, "../escape", self.out)
        self.assertFalse(self.out.exists())
        with patch.object(credentials, "exact_ssh_tunnel", side_effect=RuntimeError("host key mismatch")):
            _, complete = self.run_retrieval()
        self.assertFalse(complete)
        self.assertEqual(self.record()["error"], "ssh_unavailable")
        self.assertFalse(FakeDevice.instances)
        self.assertTrue(verify_case(self.out))

    def test_alias_create_race_never_overwrites_existing_secret(self):
        self.store.mkdir()
        target = self.store / "account-a.bin"
        target.write_bytes(SECRET)
        with self.assertRaises(FileExistsError):
            credentials._save_credential(self.store, "account-a", bytes(16))
        self.assertEqual(target.read_bytes(), SECRET)


class PinnedCredentialToolTests(unittest.TestCase):
    def test_installed_wheel_route_defaults_follow_checkout_and_explicit_flags_win(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key, hosts = root / "key", root / "hosts"
            key.touch(); hosts.touch()
            save_ssh_profile(UDID, 22317, key, hosts, root / "cases/ssh/profiles.json")
            args = SimpleNamespace(udid=UDID, ssh_port=22222,
                ssh_identity=Path("cases/ssh/id_ed25519"), ssh_known_hosts=Path("cases/ssh-known-hosts"))
            with patch.object(credentials, "source_root", return_value=root):
                credentials.apply_credential_ssh_profile(args, [])
                self.assertEqual(args.ssh_port, 22317)
                self.assertEqual(args.ssh_identity, key.resolve())
                self.assertEqual(args.ssh_known_hosts, hosts.resolve())
                args.ssh_identity = Path("explicit-key")
                credentials.apply_credential_ssh_profile(args, ["--ssh-identity", "explicit-key"])
                self.assertEqual(args.ssh_identity, Path("explicit-key"))

    def test_modified_source_is_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "core.py").write_bytes(b"unreviewed code")
            pins = {"core.py": hashlib.sha256(b"reviewed code").hexdigest()}
            with patch.object(credentials, "CREDENTIAL_SOURCES", pins), \
                    patch.object(credentials.subprocess, "run") as build:
                with self.assertRaisesRegex(credentials.RetrievalError, "tool_unavailable_or_modified"):
                    credentials._prepare_tool(source, root / "output")
                build.assert_not_called()

    def test_remote_commands_enforce_strict_pinned_ssh_without_auto_auth_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity, hosts = root / "identity", root / "known-hosts"
            identity.touch(); hosts.touch()
            command = credentials._ssh_argv(22317, identity, hosts, "mobile")
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertIn("BatchMode=yes", command)
            self.assertIn("IdentitiesOnly=yes", command)
            self.assertIn("mobile@127.0.0.1", command)


if __name__ == "__main__":
    unittest.main()
