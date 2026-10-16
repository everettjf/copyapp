import unittest
import json
import tempfile
from pathlib import Path

from copyapp.branch_map import summarize_mappings
from copyapp.verify import sha256_file, verify_case


class BranchMapTest(unittest.TestCase):
    def test_probe_coverage_does_not_create_false_conflicts(self):
        rows = [
            {"status": "correlated", "raw_argument": 8, "label": "add",
             "instrumented_offsets": ["0x1136c", "0xeb5c"],
             "branch_hits": {"0x1136c": 1}},
            {"status": "correlated", "raw_argument": 8, "label": "add",
             "instrumented_offsets": ["0x14840", "0x12cac"], "branch_hits": {}},
            {"status": "correlated", "raw_argument": 1, "label": "clear",
             "instrumented_offsets": ["0x14840", "0x12cac"],
             "branch_hits": {"0x14840": 1, "0x12cac": 1}},
            {"status": "hook_disagreement", "raw_argument": None, "label": "bad",
             "instrumented_offsets": ["0x1136c"], "branch_hits": {"0x1136c": 1}},
        ]
        result = summarize_mappings(rows)
        self.assertEqual([(item["raw_argument"], item["status"],
                           item["candidate_branch_offset"]) for item in result],
                         [(1, "multiple_branches", None),
                          (8, "single_observed_branch", "0x1136c")])

    def test_missing_hit_in_a_probe_is_not_a_single_branch(self):
        rows = [{"status": "correlated", "raw_argument": 8, "label": "add",
                 "instrumented_offsets": ["0x1136c"], "branch_hits": {"0x1136c": 1}},
                {"status": "correlated", "raw_argument": 8, "label": "add",
                 "instrumented_offsets": ["0x1136c"], "branch_hits": {}}]
        self.assertEqual(summarize_mappings(rows)[0]["status"],
                         "inconsistent_or_partial")

    def test_map_verification_detects_changed_source_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "manifest.json").write_text(json.dumps({
                "kind": "ui_flow_capture", "status": "complete", "evidence": []}))
            binary = root / "App"
            binary.write_bytes(b"app")
            output = root / "map"
            output.mkdir()
            mapped = {"binary_path": str(binary), "binary_sha256": sha256_file(binary),
                      "sources": [{"path": str(source),
                                   "manifest_sha256": sha256_file(source / "manifest.json")}]}
            (output / "branch-map.json").write_text(json.dumps(mapped))
            (output / "manifest.json").write_text(json.dumps({
                "kind": "branch_observation_map", "evidence": [
                    {"path": "branch-map.json",
                     "sha256": sha256_file(output / "branch-map.json")}] }))
            self.assertTrue(verify_case(output))
            (source / "manifest.json").write_text(json.dumps({
                "kind": "ui_flow_capture", "status": "failed", "evidence": []}))
            self.assertFalse(verify_case(output))


if __name__ == "__main__":
    unittest.main()
