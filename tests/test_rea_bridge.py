import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.rea_bridge import bridge_callees, follow_rea_bridges
from copyapp.report import _validate_rea_bridge
from copyapp.verify import sha256_file, verify_case


def evidence(address, callees):
    return {"normalized_result": {"procedure": {"address": address},
                                   "callees": callees}}


def callee(address, name, thunk=False):
    return {"address": address, "name": name,
            "classification": {"external": False, "thunk": thunk},
            "body": {"available": True}}


class ReaBridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "App"
        self.binary.write_bytes(b"synthetic binary")
        self.digest = sha256_file(self.binary)
        self.queue = self.root / "queue"
        seed = self.queue / "targets/01-100001000"
        seed.mkdir(parents=True)
        (self.queue / "sources/candidates").mkdir(parents=True)
        (self.queue / "sources/candidates/candidates.json").write_text(json.dumps({
            "bundle_id": "com.example.app", "device_id_sha256_prefix": "abc123",
            "binary_sha256": self.digest}))
        (self.queue / "queue.json").write_text(json.dumps({
            "provider": "ghidra", "binary_path": str(self.binary),
            "binary_sha256": self.digest,
            "results": [{"address": "0x100001000",
                         "summary": "targets/01-100001000/summary.json"}]}))
        (self.queue / "manifest.json").write_text("{}")
        (seed / "summary.json").write_text("{}")
        (seed / "evidence.json").write_text(json.dumps(evidence("0x100001000", [
            callee("0x100001100", "FUN_100001100"),
            callee("0x10000f000", "_objc_release", thunk=True)])))

    def test_filters_runtime_thunks_and_unresolved_targets(self):
        links = bridge_callees(evidence("0x100001000", [
            callee("0x100001100", "FUN_100001100"),
            callee("0x100001100", "FUN_100001100"),
            callee("0x10000f000", "FUN_10000f000", thunk=True),
            callee("EXTERNAL:123", "FUN_123")]))
        self.assertEqual(links, [{"address": "0x100001100", "name": "FUN_100001100"}])

    def test_follows_one_bridge_and_stops_at_branch_fanout(self):
        output = self.root / "bridge"

        def analyze(binary, digest, address, provider, target, *args):
            target.mkdir(parents=True)
            (target / "summary.json").write_text(json.dumps({
                "binary_sha256": digest, "provider": {"id": provider},
                "resolved_procedure": {"address": address}, "evidence_id": "ev_synthetic"}))
            (target / "evidence.json").write_text(json.dumps(evidence(address, [
                callee("0x100001200", "FUN_100001200"),
                callee("0x100001300", "FUN_100001300")])))
            (target / "pseudocode.txt").write_text("switch (button) { ... }")
            return target / "summary.json"

        with patch("copyapp.report._validate_rea_queue"), \
             patch("copyapp.rea_bridge.analyze_rea_function", side_effect=analyze) as tool:
            path, complete = follow_rea_bridges(self.queue, output)
        self.assertTrue(complete)
        tool.assert_called_once()
        record = json.loads((output / "bridge-map.json").read_text())
        self.assertEqual([item["status"] for item in record["decisions"]],
                         ["followed", "ambiguous"])
        self.assertEqual(record["results"][0]["address"], "0x100001100")
        self.assertEqual(json.loads(path.read_text())["status"], "complete")
        self.assertTrue(verify_case(output))
        fake_queue = json.loads((self.queue / "queue.json").read_text())
        fake_summary = json.loads((output / record["results"][0]["summary"]).read_text())
        with patch("copyapp.report._validate_rea_queue", return_value={"record": fake_queue}), \
             patch("copyapp.report._validate_rea", return_value=fake_summary):
            validated = _validate_rea_bridge(output, "com.example.app", "abc123",
                                             {self.digest})
        self.assertEqual(validated["record"]["status"], "complete")

        record["decisions"][0]["eligible_callees"] = []
        (output / "bridge-map.json").write_text(json.dumps(record))
        manifest = json.loads(path.read_text())
        for item in manifest["evidence"]:
            if item["path"] == "bridge-map.json":
                item["sha256"] = sha256_file(output / "bridge-map.json")
        path.write_text(json.dumps(manifest))
        with patch("copyapp.report._validate_rea_queue", return_value={"record": fake_queue}), \
             patch("copyapp.report._validate_rea", return_value=fake_summary):
            with self.assertRaisesRegex(ValueError, "callee decision"):
                _validate_rea_bridge(output, "com.example.app", "abc123",
                                     {self.digest})


if __name__ == "__main__":
    unittest.main()
