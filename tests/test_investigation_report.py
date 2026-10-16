import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.report import _validate_investigation
from copyapp.verify import sha256_file


class InvestigationReportTest(unittest.TestCase):
    def test_parent_import_checks_methods_script_candidate_and_rea_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("flow/playbook", "candidates/sources/flow-01", "rea"):
                (root / name).mkdir(parents=True)
            digest = "a" * 64
            methods = ["View::buttonPressed:"]
            script = root / "flow/playbook/playbook.json"
            script.write_text('{"bundle_id":"com.example.app"}')
            flow_manifest = root / "flow/manifest.json"
            flow_manifest.write_text('{"status":"complete"}')
            (root / "candidates/sources/flow-01/manifest.json").write_bytes(
                flow_manifest.read_bytes())
            candidate = root / "candidates/candidates.json"
            candidate.write_text(json.dumps({"bundle_id": "com.example.app",
                "device_id_sha256_prefix": "device", "binary_sha256": digest,
                "candidates": [{"class": "View", "selector": "buttonPressed:"}]}))
            (root / "candidates/manifest.json").write_text("{}")
            (root / "rea/manifest.json").write_text("{}")
            (root / "rea/queue.json").write_text("{}")
            (root / "review-brief.md").write_text("# Review\n")
            scout = root / "method-scout.json"
            scout.write_text(json.dumps({"binary_sha256": digest,
                                         "used_methods": methods}))
            required = ["method-scout.json", "review-brief.md", "flow/manifest.json",
                        "candidates/manifest.json", "candidates/candidates.json",
                        "rea/manifest.json", "rea/queue.json"]
            record = {"schema_version": 1, "kind": "investigated_ui_flow",
                      "status": "complete", "bundle_id": "com.example.app",
                      "device_id_sha256_prefix": "device", "binary_sha256": digest,
                      "ui_backend": "ios-mcp", "provider": "ghidra",
                      "flow_status": "complete", "candidate_status": "complete",
                      "rea_status": "complete", "selected_methods": methods,
                      "source_script_sha256": sha256_file(script),
                      "evidence": [{"path": name} for name in required]}
            (root / "manifest.json").write_text(json.dumps(record))
            flow = {"manifest": {"ui_backend": "ios-mcp"},
                    "trace": {"requested_methods": methods}}
            queue = {"record": {"binary_sha256": digest, "provider": "ghidra",
                                "candidate_case_sha256": sha256_file(candidate),
                                "results": [{}]}}
            with patch("copyapp.report.verify_case", return_value=True), \
                 patch("copyapp.report._validate_flow_capture", return_value=flow), \
                 patch("copyapp.report._validate_rea_queue", return_value=queue):
                result = _validate_investigation(root, "com.example.app", "device", {digest})
                self.assertEqual(result["manifest"]["status"], "complete")
                scout.write_text(json.dumps({"binary_sha256": digest,
                                             "used_methods": ["Other::pressed:"]}))
                with self.assertRaisesRegex(ValueError, "source chain differs"):
                    _validate_investigation(root, "com.example.app", "device", {digest})


if __name__ == "__main__":
    unittest.main()
