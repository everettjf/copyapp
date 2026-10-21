import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from copyapp.macos.case import canonical
from copyapp.macos.playbook import output_bytes, select_node, validate_script
from copyapp.macos.report import validate_review


class MacReviewContractTests(unittest.TestCase):
    def test_review_requires_exact_script_and_recorded_citations(self):
        # This tests review input validation only, not environment/flow acceptance.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            artifact = root / "steps/02/output.bin"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"expected output")
            (root / "manifest.json").write_bytes(canonical({"evidence": [{"path": "steps/02/output.bin"}]}))
            sources = {"save": {"source_script_sha256": "a" * 64}}
            review = {"schema_version": 2, "platform": "macos", "scope": "behavior_analysis",
                      "reviewer": "contract-test", "summary": "Observed output only.",
                      "inventory_note": "Known selected inventory, with unknown behavior retained.",
                      "unknowns": ["Other behavior is unobserved."],
                      "findings": [{"id": "output", "certainty": "observed", "statement": "The file has the expected bytes.",
                                    "evidence": [{"flow_id": "save", "path": "steps/02/output.bin"}]}],
                      "flows": [{"id": "save", "source_script_sha256": "a" * 64,
                                 "expected_behavior": "Save the selected output.", "findings": ["output"]}],
                      "capabilities": [{"id": "saving", "title": "Save", "flow_ids": ["save"],
                                        "disposition": "available", "reason": "Selected asserted output."}]}
            citations = validate_review(review, sources, {"save": root})
            self.assertEqual(citations[0]["sha256"], hashlib.sha256(b"expected output").hexdigest())
            mutations = [
                lambda value: value.update(scope="deep_function_analysis"),
                lambda value: value.update(schema_version=2.0),
                lambda value: value.update(unknowns=[]),
                lambda value: value["flows"][0].update(source_script_sha256="b" * 64),
                lambda value: value["findings"][0]["evidence"][0].update(path="steps/99/missing.json"),
                lambda value: value["findings"][0]["evidence"][0].update(path="../output.bin"),
                lambda value: value["capabilities"][0].update(flow_ids=[]),
                lambda value: value["capabilities"].append(value["capabilities"][0]),
            ]
            for mutate in mutations:
                changed = json.loads(canonical(review))
                mutate(changed)
                with self.assertRaises(ValueError):
                    validate_review(changed, sources, {"save": root})


class MacReplayInputTests(unittest.TestCase):
    def test_script_rejects_unsafe_inputs_before_replay(self):
        base = {"schema_version": 2, "platform": "macos", "bundle_id": "example.original",
                "app_path": "/Applications/Original.app", "scenario_id": "bounded", "steps": [{"action": "launch"}]}
        bad_steps = [
            {"action": "click", "x": 1, "y": 2, "modifiers": [{}]},
            {"action": "click", "x": 1, "y": 2, "modifiers": ["cmd", "cmd"]},
            {"action": "click", "x": True, "y": 2},
            {"action": "expect_file", "path": "../elsewhere", "text_equals": "hello"},
            {"action": "expect_file", "path": "output", "text_equals": 12},
            {"action": "expect_file", "path": "output", "sha256": "x" * 64},
            {"action": "wait", "seconds": 30},
            {"action": "shell", "command": "anything"},
        ]
        for step in bad_steps:
            with self.subTest(step=step), self.assertRaises(ValueError):
                validate_script(dict(base, steps=base["steps"] + [step]))

    def test_ambiguous_or_truncated_ax_does_not_select_first_match(self):
        tree = {"source_channel": "ax", "truncated": False, "nodes": [
            {"id": 0, "parent": None, "role": "AXApplication"},
            {"id": 1, "parent": 0, "role": "AXWindow", "title": "A"},
            {"id": 2, "parent": 1, "role": "AXButton", "title": "Save"},
            {"id": 3, "parent": 0, "role": "AXWindow", "title": "B"},
            {"id": 4, "parent": 3, "role": "AXButton", "title": "Save"}]}
        with self.assertRaises(ValueError):
            select_node(tree, {"title": "Save", "role": "AXButton"})
        self.assertEqual(select_node(tree, {"title": "Save", "window": "B"})["id"], 4)
        with self.assertRaises(ValueError):
            select_node(dict(tree, truncated=True), {"title": "Save", "window": "B"})

    def test_output_capture_rejects_links_and_special_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            run = root / "run"
            run.mkdir()
            output = run / "output"
            output.write_bytes(b"saved bytes")
            self.assertEqual(output_bytes(output, run), b"saved bytes")
            outside = root / "outside"
            outside.write_bytes(b"unrelated")
            (run / "link").symlink_to(outside)
            with self.assertRaises(ValueError):
                output_bytes(run / "link", run)
            os.mkfifo(run / "fifo")
            with self.assertRaises(ValueError):
                output_bytes(run / "fifo", run)
            with self.assertRaises(ValueError):
                output_bytes(outside, run)
            (run / "large").write_bytes(b"x" * ((8 << 20) + 1))
            with self.assertRaises(ValueError):
                output_bytes(run / "large", run)


if __name__ == "__main__":
    unittest.main()
