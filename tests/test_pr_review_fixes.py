"""Regressions for PR #4 review: default routing, case paths and numeric evidence."""

import copy
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from copyapp.cli import main
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.ios_credentials import retrieve_credential
from copyapp.ios_cross_check import cross_check_offline
from copyapp.ios_delivery import create_behavior_delivery
from copyapp.ios_offline import decrypt_offline
from copyapp.verify import sha256_file, verify_case
from tests import test_ios_analysis as analysis_fixtures
from tests.test_ios_analysis import BUNDLE, PREFIX, UDID, capabilities


class ReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.fixture = analysis_fixtures.IosAnalysisTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def test_actual_copy_cli_auto_defaults_reach_standard_behavior_review(self):
        workflow = self.root / "workflow"
        argv = ["copyapp", "copy", "--mode", "auto", "--agent-provider", "current",
                "--udid", UDID, "--bundle", BUNDLE, "--script", str(self.fixture.script),
                "--rebuilt-bundle", "dev.copyapp.counter", "--workspace", str(self.root),
                "--out", str(workflow), "--project", str(self.root / "project"),
                "--decrypt-helper", str(self.root / "helper")]
        with patch.object(sys, "argv", argv), \
                patch("copyapp.cli.apply_ssh_profile"), \
                patch("copyapp.ios_workflow.collect_capabilities", side_effect=capabilities), \
                patch("copyapp.cli.analyze_case") as enhanced:
            with self.assertRaises(SystemExit) as stopped:
                main()
        self.assertEqual(stopped.exception.code, 1)  # handoff, not completed rebuild
        enhanced.assert_not_called()
        self.assertEqual(read_json(workflow / "workflow.json")["status"], "needs_behavior_review")
        self.assertEqual(read_json(workflow / "analysis/analysis.json")["selected_mode"], "standard")
        self.assertTrue(verify_case(workflow))

    def test_explicit_auto_analyze_decrypt_still_requires_enhancement(self):
        output = self.root / "explicit-decryption"
        argv = ["copyapp", "analyze", "--mode", "auto", "--decrypt",
                "--udid", UDID, "--bundle", BUNDLE, "--script", str(self.fixture.script),
                "--out", str(output), "--decrypt-helper", str(self.root / "helper")]
        with patch.object(sys, "argv", argv), patch("copyapp.cli.apply_ssh_profile"), \
                patch("copyapp.cli.analyze_case", new=AsyncMock(return_value=False)) as enhanced, \
                patch("copyapp.ios_analysis.run_playbook") as replay:
            with self.assertRaises(SystemExit):
                main()
        enhanced.assert_awaited_once()
        replay.assert_not_called()
        state = read_json(output / "analysis.json")
        self.assertEqual(state["selected_mode"], "enhanced")
        self.assertEqual(state["status"], "failed")
        self.assertTrue(verify_case(output))

    def test_offline_rejects_nested_output_before_copying_or_touching_source(self):
        package = self.fixture.package()
        output = package / "offline"
        original = sha256_file(package / "manifest.json")
        with patch("copyapp.ios_offline.shutil.copytree",
                   side_effect=AssertionError("copied before checking overlap")) as copy:
            with self.assertRaisesRegex(ValueError, "separate|overlap"):
                decrypt_offline(package, output)
        copy.assert_not_called()
        self.assertFalse(output.exists())
        self.assertEqual(sha256_file(package / "manifest.json"), original)
        self.assertTrue(verify_case(package))

    def test_credential_retrieval_rejects_symlinked_nested_package_output(self):
        package = self.fixture.package()
        alias = self.root / "package-alias"
        alias.symlink_to(package, target_is_directory=True)
        output = alias / "credentials-case"
        with patch("copyapp.ios_credentials.shutil.copytree",
                   side_effect=AssertionError("copied before checking overlap")) as copy, \
                patch("copyapp.ios_credentials._target") as device:
            with self.assertRaisesRegex(ValueError, "separate|overlap"):
                retrieve_credential(UDID, BUNDLE, "test-account", output,
                                    store=self.root / "store", package=package)
        copy.assert_not_called()
        device.assert_not_called()
        self.assertFalse(output.exists())
        self.assertTrue(verify_case(package))

    def test_behavior_report_rejects_output_inside_original_collection(self):
        self.fixture.collect()
        analysis = self.root / "analysis"
        output = analysis / "report"
        with patch("copyapp.ios_report.shutil.copytree",
                   side_effect=AssertionError("copied before checking overlap")) as copy:
            with self.assertRaisesRegex(ValueError, "separate|overlap"):
                self.fixture.review(analysis, output)
        copy.assert_not_called()
        self.assertFalse(output.exists())
        self.assertTrue(verify_case(analysis))

    def test_behavior_delivery_cannot_invalidate_either_source_case(self):
        self.fixture.collect()
        analysis, report = self.root / "analysis", self.root / "report"
        self.fixture.review(analysis, report)
        for source in (analysis, report):
            with self.subTest(source=source.name):
                output = source / "delivery"
                with self.assertRaisesRegex(ValueError, "separate|overlap"):
                    create_behavior_delivery(analysis, report, output)
                self.assertFalse(output.exists())
                self.assertTrue(verify_case(analysis))
                self.assertTrue(verify_case(report))

    def test_offline_cross_check_rejects_output_in_either_source_before_validation(self):
        offline, device = self.root / "offline", self.root / "device"
        offline.mkdir()
        device.mkdir()
        alias = self.root / "device-alias"
        alias.symlink_to(device, target_is_directory=True)
        for source in (offline, alias):
            with self.subTest(source=source.name):
                output = source / "comparison"
                with patch("copyapp.ios_cross_check.recovery_links") as validate:
                    with self.assertRaisesRegex(ValueError, "separate|overlap"):
                        cross_check_offline(offline, device, output)
                    validate.assert_not_called()
                self.assertFalse(output.exists())

    def numeric_case(self, source="accessibility", before=1, after=2):
        script = read_json(self.fixture.script)
        script["steps"] = [
            {"action": "observe", "contains": ["Count"],
             "capture_number": {"name": "count", "pattern": r"Count (\d+)"}},
            {"action": "tap_label", "label": "Add"},
            {"action": "observe", "contains": ["Count"],
             "compare_number": {"to": "count", "pattern": r"Count (\d+)", "delta": after - before}},
            {"action": "screenshot", "stable": True, "ready_contains": "Count"}]
        write_json(self.fixture.script, script)

        def player(udid, backend, path, root, **kwargs):
            root.mkdir(parents=True)
            shutil.copyfile(path, root / "playbook.json")
            Image.new("RGB", (30, 30), "white").save(root / "screen.jpg")
            steps = []
            for index, value in ((1, before), (3, after)):
                write_json(root / f"observe-{index}.json", {"source": f"Count {value}"})
                item = {"index": index, "action": "observe", "frontmost": BUNDLE,
                        "observation_source": source, "missing": [],
                        "evidence_path": f"observe-{index}.json"}
                if source == "screenshot_ocr":
                    image = root / "screen.jpg"
                    write_json(root / f"ocr-{index}.json", {
                        "schema_version": 1, "kind": "saved_screenshot_ocr",
                        "source_sha256": sha256_file(image), "source_width": 30, "source_height": 30,
                        "roi": None, "ocr_input_sha256": sha256_file(image),
                        "result": {"engine": "macos-vision", "texts": [{"text": f"Count {value}"}]}})
                    item.update(observation_image_path=image.name, observation_image_sha256=sha256_file(image),
                                observation_ocr_path=f"ocr-{index}.json",
                                observation_ocr_sha256=sha256_file(root / f"ocr-{index}.json"))
                if index == 1:
                    item["captured_number"] = {"name": "count", "value": before}
                else:
                    item["number_comparison"] = {"before": before, "after": after, "delta": after - before}
                steps.append(item)
            steps.insert(1, {"index": 2, "action": "tap_label", "frontmost": BUNDLE, "result": {}})
            steps.append({"index": 4, "action": "screenshot", "frontmost": BUNDLE,
                          "evidence_path": "screen.jpg", "sha256": sha256_file(root / "screen.jpg"),
                          "stability": {"stable": True}, "ready_contains": "Count", "ready_found": True})
            write_json(root / "manifest.json", {
                "schema_version": 1, "bundle_id": BUNDLE, "ui_backend": backend,
                "scenario_id": script["scenario_id"], "device_id_sha256_prefix": PREFIX,
                "execution_mode": kwargs["mode"], "status": "complete", "steps": steps,
                "evidence": [{"path": p.name, "sha256": sha256_file(p)} for p in root.iterdir()]})
            return root / "manifest.json", True

        with patch("copyapp.ios_analysis.run_playbook", side_effect=player):
            self.fixture.collect()
        return self.root / "analysis"

    def reseal_numeric_case(self, root, flow):
        child = root / "flows/flow-01"
        for item in flow["evidence"]:
            item["sha256"] = sha256_file(child / item["path"])
        write_json(child / "manifest.json", flow)
        state = read_json(root / "analysis.json")
        state["flows"][0]["manifest_sha256"] = sha256_file(child / "manifest.json")
        write_json(root / "analysis.json", state)
        seal_case(root, "ios_analysis", status="complete", bundle_id=BUNDLE, device_id_sha256_prefix=PREFIX)

    def test_correct_ax_numeric_capture_and_delta_still_verify(self):
        self.assertTrue(verify_case(self.numeric_case(before=0, after=1)))

    def test_rehashed_ax_without_the_required_change_is_rejected(self):
        root = self.numeric_case()
        child = root / "flows/flow-01"
        flow = read_json(child / "manifest.json")
        write_json(child / "observe-3.json", {"source": "Count 1"})
        self.reseal_numeric_case(root, flow)
        self.assertFalse(verify_case(root))

    def test_claimed_numeric_metadata_must_match_raw_ax_values(self):
        root = self.numeric_case()
        child = root / "flows/flow-01"
        original = read_json(child / "manifest.json")
        for field, replacement in (("captured_number", {"name": "count", "value": 9}),
                                   ("captured_number", {"name": "count", "value": True}),
                                   ("captured_number", None),
                                   ("number_comparison", {"before": 1, "after": 9, "delta": 1}),
                                   ("number_comparison", None),
                                   ("number_comparison", {"before": True, "after": 2, "delta": 1})):
            with self.subTest(field=field, replacement=replacement):
                flow = copy.deepcopy(original)
                flow["steps"][0 if field == "captured_number" else 2][field] = replacement
                self.reseal_numeric_case(root, flow)
                self.assertFalse(verify_case(root))

    def test_numeric_decrease_to_zero_is_valid(self):
        self.assertTrue(verify_case(self.numeric_case(before=2, after=0)))

    def test_malformed_pattern_or_missing_capture_reference_fails_closed(self):
        root = self.numeric_case()
        child = root / "flows/flow-01"
        original = read_json(child / "playbook.json")
        for changed in ({"pattern": "["}, {"pattern": "Count [0-9]+"}, {"to": "absent"}):
            with self.subTest(changed=changed):
                script = copy.deepcopy(original)
                script["steps"][2]["compare_number"].update(changed)
                write_json(self.fixture.script, script)
                write_json(child / "playbook.json", script)
                write_json(root / "scripts/flow-01.json", script)
                inputs = read_json(root / "inputs.json")
                inputs["flows"][0]["source_script_sha256"] = sha256_file(child / "playbook.json")
                write_json(root / "inputs.json", inputs)
                state = read_json(root / "analysis.json")
                state["flows"][0]["source_script_sha256"] = inputs["flows"][0]["source_script_sha256"]
                write_json(root / "analysis.json", state)
                flow = read_json(child / "manifest.json")
                self.reseal_numeric_case(root, flow)
                self.assertFalse(verify_case(root))

    def test_correct_ocr_numeric_capture_and_delta_still_verify(self):
        self.assertTrue(verify_case(self.numeric_case(source="screenshot_ocr")))

    def test_rehashed_ocr_numeric_change_is_recomputed(self):
        root = self.numeric_case(source="screenshot_ocr")
        child = root / "flows/flow-01"
        record = read_json(child / "ocr-3.json")
        record["result"]["texts"] = [{"text": "Count 1"}]
        write_json(child / "ocr-3.json", record)
        flow = read_json(child / "manifest.json")
        flow["steps"][2]["observation_ocr_sha256"] = sha256_file(child / "ocr-3.json")
        self.reseal_numeric_case(root, flow)
        self.assertFalse(verify_case(root))


if __name__ == "__main__":
    unittest.main()
