import json
import shutil
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from copyapp.macos.case import canonical, digest
from copyapp.macos.share import share_request, share_result
from copyapp.verify import verify_case


def vm_fixture(root):
    vm = root / "Test.vm"
    (vm / "Shared/inbox").mkdir(parents=True)
    (vm / "Shared/outbox").mkdir()
    (vm / "spec.json").write_bytes(canonical({"id": str(uuid4()), "stage": "agentInstalled"}))
    (vm / "MachineIdentifier.bin").write_bytes(b"simulated public machine identifier")
    (vm / "HardwareModel.bin").write_bytes(b"simulated public hardware model")
    return vm


class MacShareProbeTests(unittest.TestCase):
    def test_request_and_simulated_reply_do_not_claim_runtime_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            vm = vm_fixture(root)
            request = share_request(vm, root / "request")
            self.assertTrue(verify_case(request))
            record = json.loads((request / "request.json").read_text())
            shutil.copyfile(vm / "Shared/inbox" / record["filename"], vm / "Shared/outbox" / record["filename"])
            result = share_result(request, root / "result", "contract-test", "Simulated host filesystem copy only; no live guest claim.")
            self.assertTrue(verify_case(result))
            data = json.loads((result / "result.json").read_text())
            self.assertFalse(data["guest_runtime_identity_verified"])
            self.assertFalse(data["complete_environment_acceptance"])
            data["guest_runtime_identity_verified"] = True
            (result / "result.json").write_bytes(canonical(data))
            manifest = json.loads((result / "manifest.json").read_text())
            for item in manifest["evidence"]:
                if item["path"] == "result.json": item["sha256"] = digest(result / "result.json")
            (result / "manifest.json").write_bytes(canonical(manifest))
            self.assertFalse(verify_case(result))

    def test_absent_wrong_linked_reply_or_changed_vm_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            vm = vm_fixture(root)
            request = share_request(vm, root / "request")
            record = json.loads((request / "request.json").read_text())
            reply = vm / "Shared/outbox" / record["filename"]
            with self.assertRaises(ValueError):
                share_result(request, root / "absent", "test", "No reply.")
            reply.write_bytes(b"another nonce")
            with self.assertRaises(ValueError):
                share_result(request, root / "wrong", "test", "Wrong reply.")
            reply.unlink()
            reply.symlink_to(request / "payload.txt")
            with self.assertRaises(ValueError):
                share_result(request, root / "linked", "test", "Linked reply.")
            reply.unlink()
            reply.write_bytes((request / "payload.txt").read_bytes())
            (vm / "MachineIdentifier.bin").write_bytes(b"changed identity")
            with self.assertRaises(ValueError):
                share_result(request, root / "changed", "test", "VM identity changed.")


if __name__ == "__main__":
    unittest.main()
