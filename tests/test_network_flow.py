import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.network_flow import NetworkObserver, _event, network_hook_source
from copyapp.verify import sha256_file, verify_case


class NetworkFlowTest(unittest.TestCase):
    def test_observer_attributes_only_valid_metadata_to_active_tap(self):
        with tempfile.TemporaryDirectory() as directory, patch("copyapp.network_flow.time.sleep"):
            observer = NetworkObserver(Path(directory))
            event = {"type": "network_task_resume", "scheme": "https",
                     "host": "example.com", "method": "POST",
                     "path_fingerprint": "12345678", "path_depth": 2,
                     "query": "secret-value"}
            observer.begin_step(3, "tap_label")
            observer._on_message({"type": "send", "payload": event}, None)
            observer.end_step()
            observer._on_message({"type": "send", "payload": {**event, "host": "bad/host"}}, None)
            self.assertEqual(observer.events[0]["step_index"], 3)
            self.assertNotIn("secret-value", json.dumps(observer.events))
            self.assertEqual(observer.record["steps"][0]["event_count"], 1)
            self.assertEqual(len(observer.errors), 1)
            with self.assertRaises(ValueError):
                _event({**event, "path_fingerprint": "/private/path"})

    def test_verified_parent_rejects_rehashed_cross_app_and_step_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            play = root / "playbook"
            network = root / "network"
            play.mkdir()
            network.mkdir()
            bundle = "com.example.app"
            prefix = hashlib.sha256(b"device").hexdigest()[:16]

            def write(path, data):
                path.write_text(json.dumps(data) + "\n", encoding="utf-8")

            def evidence(parent, files):
                return [{"path": name, "sha256": sha256_file(parent / name)}
                        for name in files]

            write(play / "playbook.json", {"bundle_id": bundle, "steps": []})
            write(play / "manifest.json", {
                "status": "complete", "bundle_id": bundle,
                "device_id_sha256_prefix": prefix, "ui_backend": "ios-mcp",
                "steps": [{"index": 1, "action": "tap_label"}],
                "evidence": evidence(play, ["playbook.json"]),
            })
            (network / "hook.js").write_text(network_hook_source(), encoding="utf-8")
            event = {"scheme": "https", "host": "example.com", "method": "GET",
                     "path_fingerprint": "12345678", "path_depth": 1,
                     "observed_at": "2026-01-01T00:00:00+00:00", "step_index": 1}
            trace = {"kind": "ui_network_flow_trace", "status": "complete",
                     "bundle_id": bundle, "device_id_sha256_prefix": prefix,
                     "hook_count": 1, "dropped_events": 0,
                     "steps": [{"index": 1, "action": "tap_label", "event_count": 1}],
                     "events": [event]}
            write(network / "network.json", trace)

            def seal():
                write(network / "manifest.json", {
                    "kind": "ui_network_flow_trace", "status": "complete",
                    "bundle_id": bundle, "device_id_sha256_prefix": prefix,
                    "evidence": evidence(network, ["hook.js", "network.json"]),
                })
                child_files = sorted(str(path.relative_to(root)) for child in (play, network)
                                     for path in child.iterdir() if path.is_file())
                write(root / "manifest.json", {
                    "schema_version": 1, "kind": "ui_network_flow", "status": "complete",
                    "bundle_id": bundle, "device_id_sha256_prefix": prefix,
                    "ui_backend": "ios-mcp",
                    "event_count": len(trace["events"]),
                    "source_script_sha256": sha256_file(play / "playbook.json"),
                    "evidence": evidence(root, child_files),
                })

            seal()
            self.assertTrue(verify_case(root))
            trace["events"][0]["step_index"] = 9
            write(network / "network.json", trace)
            seal()
            self.assertFalse(verify_case(root))
            trace["events"][0]["step_index"] = 1
            trace["bundle_id"] = "com.other.app"
            write(network / "network.json", trace)
            seal()
            self.assertFalse(verify_case(root))


if __name__ == "__main__":
    unittest.main()
