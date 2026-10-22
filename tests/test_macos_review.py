import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from copyapp.macos.case import canonical
from copyapp.macos.playbook import output_bytes, select_node, validate_script, wait_for_stopped
from copyapp.macos.report import validate_review
from copyapp.macos.ui import check_ui, validate_ui


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
    def test_graceful_shutdown_can_exceed_five_seconds_without_another_input(self):
        alive = {"response": {"result": {"processes": [{"active": False, "terminated": False}]}}}
        stopped = {"response": {"result": {"processes": []}}}
        collector, case = Mock(), Mock()
        collector.call.side_effect = [alive, alive, stopped]
        params = {"bundle_id": "example.original", "binary_sha256": "a" * 64}
        with patch("copyapp.macos.playbook.time.monotonic", side_effect=[0, 6, 12]), \
                patch("copyapp.macos.playbook.time.sleep"):
            self.assertEqual(wait_for_stopped(case, "steps/11", collector, params), stopped)
        self.assertEqual([call.args for call in collector.call.call_args_list], [("app_identity", params)] * 3)
        self.assertEqual(case.add.call_count, 2)

    def test_inactive_process_is_not_accepted_as_stopped_and_timeout_retains_poll(self):
        alive = {"response": {"result": {"processes": [{"active": False, "terminated": False}]}}}
        collector, case = Mock(), Mock()
        collector.call.return_value = alive
        with patch("copyapp.macos.playbook.time.monotonic", side_effect=[0, 31]), \
                self.assertRaisesRegex(ValueError, "did not stop"):
            wait_for_stopped(case, "steps/11", collector, {})
        collector.call.assert_called_once_with("app_identity", {})
        case.add.assert_called_once_with("steps/11/poll-1.json", alive)

    def test_actual_guest_language_list_is_retained_and_order_remains_pinned(self):
        from macos_fakes import UI
        languages = ["en", "fr", "de", "zh-Hans", "zh-Hant", "ja", "es", "it", "nl", "ko", "pt-BR", "pt-PT",
                     "da", "fi", "nb", "sv", "ru", "pl", "tr", "ar", "th", "cs", "hu", "ca", "hr", "el",
                     "he", "ro", "sk", "uk", "id", "ms", "vi", "es-419"]
        expected = dict(UI, preferred_languages=languages)
        check_ui(expected, {"response": {"result": {"ui_environment": expected}}})
        for changed in (languages[::-1], languages[:32]):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                check_ui(expected, {"response": {"result": {"ui_environment": dict(expected, preferred_languages=changed)}}})
        for invalid in (["en"] * 129, [True]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_ui(dict(expected, preferred_languages=invalid))

    def test_catalyst_description_selector_requires_a_unique_exact_match(self):
        selector = {"role": "AXButton", "description": "Continue"}
        validate_script({"schema_version": 2, "platform": "macos", "bundle_id": "example.catalyst",
                         "app_path": "/Applications/Example.app", "scenario_id": "welcome",
                         "steps": [{"action": "launch"}, {"action": "click_element", "selector": selector}]})
        node = {"id": 0, "parent": None, "role": "AXButton", "description": "Continue"}
        tree = {"source_channel": "ax", "truncated": False, "nodes": [node]}
        self.assertEqual(select_node(tree, selector), node)
        for nodes in ([], [dict(node, description="Continue Later")], [node, dict(node, id=1)]):
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                select_node(dict(tree, nodes=nodes), selector)

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
