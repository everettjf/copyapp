import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from copyapp.macos.case import canonical, digest
from copyapp.macos.chatcomputer import ChatComputer, ChatComputerError, UnknownCompletion
from copyapp.macos.snapshots import catalog, quiet_catalog, snapshot_inventory
from copyapp.verify import verify_case
from macos_snapshot_checks import make_snapshot_server


class SnapshotMetadataTests(unittest.TestCase):
    def vm(self, root):
        vm = root / "ChatComputer.vm"
        vm.mkdir()
        (vm / "spec.json").write_bytes(canonical({"id": str(uuid4()), "stage": "agentInstalled"}))
        (vm / "MachineIdentifier.bin").write_bytes(b"simulated-machine")
        (vm / "HardwareModel.bin").write_bytes(b"simulated-hardware")
        return vm

    def test_readonly_inventory_preserves_incomplete_state_without_claiming_readiness(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); vm = self.vm(root)
            empty = snapshot_inventory(vm, root / "empty")
            self.assertTrue(verify_case(empty))
            self.assertFalse(json.loads((empty / "inventory.json").read_text())["guest_runtime_identity_verified"])
            (vm / "Snapshots/.restore").mkdir(parents=True)
            (vm / "Snapshots/state.json").write_bytes(canonical({"currentID": str(uuid4())}))
            incomplete = snapshot_inventory(vm, root / "incomplete")
            self.assertTrue(verify_case(incomplete))
            value = json.loads((incomplete / "catalog.json").read_text())
            self.assertTrue(value["restore_in_progress"])
            with self.assertRaisesRegex(ValueError, "needs inspection"): quiet_catalog(value)
            path = incomplete / "inventory.json"
            changed = json.loads(path.read_text()); changed["snapshot_count"] = 10
            path.write_bytes(canonical(changed))
            manifest = json.loads((incomplete / "manifest.json").read_text())
            for row in manifest["evidence"]:
                if row["path"] == "inventory.json": row["sha256"] = digest(path)
            (incomplete / "manifest.json").write_bytes(canonical(manifest))
            self.assertFalse(verify_case(incomplete))

    def test_inventory_rejects_linked_roots_and_mismatched_snapshot_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); vm = self.vm(root)
            outside = root / "elsewhere"; outside.mkdir()
            (vm / "Snapshots").symlink_to(outside)
            with self.assertRaises(ValueError): catalog(vm)
            (vm / "Snapshots").unlink()
            selected = vm / "Snapshots" / str(uuid4()); selected.mkdir(parents=True)
            (selected / "snapshot.json").write_bytes(canonical({"id": str(uuid4()), "name": "wrong ID", "kind": "manual",
                "createdAt": "2026-10-21T00:00:00.000Z", "overlayCount": 1, "hasThumbnail": False, "isProtected": False}))
            with self.assertRaisesRegex(ValueError, "IDs differ"): snapshot_inventory(vm, root / "failed")
            self.assertTrue((root / "failed/failure.json").exists())
            self.assertFalse(verify_case(root / "failed"))


class SnapshotClientTests(unittest.TestCase):
    def test_lost_readonly_catalog_reply_is_not_an_uncertain_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            executable, log = make_snapshot_server(root, root / "simulated.vm")
            with patch.dict("os.environ", {"COPYAPP_TEST_SNAPSHOT_MODE": "lost-list"}):
                with ChatComputer(executable, timeout=2) as computer:
                    with self.assertRaises(ChatComputerError) as caught: computer.call("snapshot_list")
                    self.assertNotIsInstance(caught.exception, UnknownCompletion)
                    self.assertIsNone(computer.process)
                    self.assertEqual(caught.exception.chatcomputer_evidence["request"]["params"]["name"], "snapshot_list")
            self.assertEqual(len(log.read_text().splitlines()), 1)


if __name__ == "__main__": unittest.main()
