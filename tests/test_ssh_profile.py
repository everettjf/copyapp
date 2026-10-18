import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from copyapp.ssh_profile import (apply_ssh_profile, load_ssh_profile,
                                 remember_verified_doctor_case, save_ssh_profile)


UDID_16 = "00008020-000D650434B8003A"
UDID_26 = "00008030-000E45AE0C42402E"


class SSHProfileTests(unittest.TestCase):
    def test_separate_verified_routes_and_explicit_cli_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profiles.json"
            for label, udid, port in (("xr", UDID_16, 22316),
                                      ("ios26", UDID_26, 22326)):
                identity = root / f"{label}-identity"
                hosts = root / f"{label}-known-hosts"
                identity.write_text("key")
                hosts.write_text("pinned host")
                save_ssh_profile(udid, port, identity, hosts, profile)

            self.assertEqual(load_ssh_profile(UDID_16, profile)["ssh_port"], 22316)
            self.assertEqual(load_ssh_profile(UDID_26, profile)["ssh_port"], 22326)
            self.assertNotIn(UDID_16, profile.read_text())
            self.assertNotIn(UDID_26, profile.read_text())
            args = SimpleNamespace(udid=UDID_26, ssh_port=22222,
                                   ssh_identity=Path("cases/ssh/id_ed25519"),
                                   ssh_known_hosts=Path("cases/ssh-known-hosts"))
            apply_ssh_profile(args, [], profile)
            self.assertEqual(args.ssh_port, 22326)
            self.assertEqual(args.ssh_identity, (root / "ios26-identity").resolve())
            self.assertEqual(args.ssh_known_hosts, (root / "ios26-known-hosts").resolve())

            explicit = SimpleNamespace(udid=UDID_16, ssh_port=22999,
                                       ssh_identity=Path("manual-key"),
                                       ssh_known_hosts=Path("manual-hosts"))
            apply_ssh_profile(explicit, ["--ssh-port=22999", "--ssh-identity",
                                         "manual-key", "--ssh-known-hosts=manual-hosts"],
                              profile)
            self.assertEqual(explicit.ssh_port, 22999)
            self.assertEqual(explicit.ssh_identity, Path("manual-key"))
            self.assertEqual(explicit.ssh_known_hosts, Path("manual-hosts"))

    def test_doctor_case_is_remembered_only_after_exact_ssh_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            case.mkdir()
            identity = root / "key"
            hosts = root / "hosts"
            identity.write_text("key")
            hosts.write_text("pinned host")
            profile = root / "profiles.json"
            record = {"device": {"UniqueDeviceID": UDID_16},
                      "probes": {"ssh_mobile": {"status": "host_key_mismatch"}}}
            (case / "device.json").write_text(json.dumps(record))
            self.assertFalse(remember_verified_doctor_case(case, 22316, identity,
                                                             hosts, profile))
            self.assertFalse(profile.exists())
            record["probes"]["ssh_mobile"]["status"] = "available"
            (case / "device.json").write_text(json.dumps(record))
            self.assertTrue(remember_verified_doctor_case(case, 22316, identity,
                                                            hosts, profile))
            self.assertEqual(load_ssh_profile(UDID_16, profile)["ssh_port"], 22316)


if __name__ == "__main__":
    unittest.main()
