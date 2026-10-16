import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.agent_delivery import create_agent_delivery
from copyapp.verify import sha256_file, verify_case


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


class AgentDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = self.root / "task"
        self.project = self.root / "rebuild/Clone"
        self.project.mkdir(parents=True)
        (self.project / "App.swift").write_text("struct Clone {}\n")
        self.original_script = self.root / "original.json"
        self.rebuilt_script = self.root / "rebuilt.json"
        write(self.original_script, {"bundle_id": "com.example.original"})
        write(self.rebuilt_script, {"bundle_id": "dev.example.clone"})
        self.udid = "00008020-1111111111111111"
        self.prefix = hashlib.sha256(self.udid.encode()).hexdigest()[:16]
        write(self.task / "task.json", {
            "status": "ready_for_agent", "device_udid": self.udid,
            "project_dir": str(self.project),
            "target_bundle_id": "com.example.original",
            "rebuilt_bundle_id": "dev.example.clone",
            "flows": [{"id": "one", "scenario_id": "one",
                       "original_script": str(self.original_script),
                       "rebuilt_script": str(self.rebuilt_script)}]})
        write(self.task / "manifest.json", {"kind": "agent_implementation_task"})
        self.ipa = self.root / "Clone.ipa"
        self.ipa.write_bytes(b"independent-test-package")
        self.install = self.root / "install.json"
        self.install_data = {
            "schema_version": 1, "status": "installed", "helper_exit_code": 0,
            "ipa": str(self.ipa), "ipa_sha256": sha256_file(self.ipa),
            "staged_sha256": sha256_file(self.ipa), "device_id": self.udid,
            "bundle_id": "dev.example.clone", "version": "0.1", "build": "2"}
        write(self.install, self.install_data)
        self.check = self.root / "check"
        comparison = self.check / "flows/one/comparison/report-index.json"
        write(comparison, {
            "scenario_id": "one", "original_bundle_id": "com.example.original",
            "rebuilt_bundle_id": "dev.example.clone",
            "device_id_sha256_prefix": self.prefix, "checks_status": "unreviewed"})
        self.check_data = {
            "kind": "rebuild_check", "status": "complete",
            "device_id_sha256_prefix": self.prefix,
            "installed_apps": [
                {"bundle_id": "com.example.original", "version": "1", "build": "1"},
                {"bundle_id": "dev.example.clone", "version": "0.1", "build": "2"}],
            "pairs": [{"flow_id": "one", "scenario_id": "one",
                       "original_script_sha256": sha256_file(self.original_script),
                       "rebuilt_script_sha256": sha256_file(self.rebuilt_script)}],
            "flows": [{"flow_id": "one", "scenario_id": "one",
                       "comparison_index": "flows/one/comparison/report-index.json",
                       "comparison_sha256": sha256_file(comparison),
                       "final_view_status": "passed", "checks_status": "unreviewed",
                       "screenshot_pairs": 1}]}
        write(self.check / "manifest.json", self.check_data)

    def _create(self):
        with patch("copyapp.agent_delivery.verify_case", return_value=True):
            return create_agent_delivery(self.task, self.install, self.check,
                                         self.root / "delivery")

    def test_records_scoped_behavior_and_unreviewed_visuals(self):
        report = self._create()
        data = json.loads((report.parent / "delivery.json").read_text())
        self.assertEqual(data["status"], "selected_behavior_verified_visual_unreviewed")
        self.assertEqual(data["asserted_flow_count"], 1)
        self.assertEqual(data["visual_unreviewed_flow_count"], 1)
        self.assertIsNone(data["agent_run_status"])
        self.assertTrue((report.parent / "source-project.tar").is_file())
        self.assertTrue((report.parent / "installed.ipa").is_file())
        with patch("copyapp.verify._verify_silent", return_value=True):
            self.assertTrue(verify_case(report.parent))
            (self.project / "App.swift").write_text("struct NewVersion {}\n")
            self.ipa.write_bytes(b"later-build")
            self.assertTrue(verify_case(report.parent))

    def test_explicit_review_records_differences_separately_from_script_checks(self):
        review_case = self.root / "review"
        write(review_case / "review.json", {
            "rebuild_check_case": str(self.check.resolve()),
            "rebuild_check_manifest_sha256": sha256_file(self.check / "manifest.json"),
            "pairs": [{"flow_id": "one", "step": 3,
                       "verdict": "minor_difference", "note": "Glyph shape differs."}],
        })
        write(review_case / "manifest.json", {"kind": "visual_review"})
        with patch("copyapp.agent_delivery.verify_case", return_value=True):
            report = create_agent_delivery(self.task, self.install, self.check,
                                           self.root / "reviewed-delivery",
                                           visual_review_case=review_case)
        data = json.loads((report.parent / "delivery.json").read_text())
        self.assertEqual(data["status"],
                         "selected_behavior_verified_visual_reviewed_with_differences")
        self.assertEqual(data["visual_unreviewed_flow_count"], 0)
        self.assertEqual(data["visual_minor_difference_flow_count"], 1)
        self.assertEqual(data["flow_results"][0]["visual_checks_status"], "unreviewed")
        self.assertEqual(data["flow_results"][0]["visual_review_status"], "minor_difference")
        with patch("copyapp.verify._verify_silent", return_value=True):
            self.assertTrue(verify_case(report.parent))
            data["flow_results"][0]["visual_review_status"] = "match"
            write(report.parent / "delivery.json", data)
            manifest = json.loads((report.parent / "manifest.json").read_text())
            for item in manifest["evidence"]:
                if item["path"] == "delivery.json":
                    item["sha256"] = sha256_file(report.parent / "delivery.json")
            write(report.parent / "manifest.json", manifest)
            self.assertFalse(verify_case(report.parent))

    def test_rejects_installed_package_hash_change(self):
        self.ipa.write_bytes(b"different-package")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            self._create()

    def test_rejects_clone_version_mismatch(self):
        self.check_data["installed_apps"][1]["build"] = "3"
        write(self.check / "manifest.json", self.check_data)
        with self.assertRaisesRegex(ValueError, "different clone version"):
            self._create()

    def test_rejects_missing_task_flow(self):
        self.check_data["flows"] = []
        write(self.check / "manifest.json", self.check_data)
        with self.assertRaisesRegex(ValueError, "does not cover every task flow"):
            self._create()

    def test_post_tap_numeric_assertion_counts_without_uikit_label(self):
        original = {"bundle_id": "com.example.original", "steps": [
            {"action": "observe", "contains": "Increment counter"},
            {"action": "tap_label", "label": "Increment counter"},
            {"action": "observe", "compare_number": {
                "to": "before", "pattern": "Counter: ([0-9]+)", "delta": 1}},
        ]}
        write(self.original_script, original)
        write(self.rebuilt_script, dict(original, bundle_id="dev.example.clone"))
        pair = self.check_data["pairs"][0]
        pair["original_script_sha256"] = sha256_file(self.original_script)
        pair["rebuilt_script_sha256"] = sha256_file(self.rebuilt_script)
        self.check_data["flows"][0]["final_view_status"] = "not_configured"
        write(self.check / "manifest.json", self.check_data)
        report = self._create()
        delivery = json.loads((report.parent / "delivery.json").read_text())
        self.assertEqual(delivery["status"], "selected_behavior_verified_visual_unreviewed")
        self.assertEqual(delivery["asserted_flow_count"], 1)
        self.assertEqual(delivery["flow_results"][0]["script_assertions"],
                         ["step-03:numeric_change"])
        with patch("copyapp.verify._verify_silent", return_value=True):
            self.assertTrue(verify_case(report.parent))
            delivery["flow_results"][0]["script_assertions"] = []
            write(report.parent / "delivery.json", delivery)
            manifest = json.loads((report.parent / "manifest.json").read_text())
            for item in manifest["evidence"]:
                if item["path"] == "delivery.json":
                    item["sha256"] = sha256_file(report.parent / "delivery.json")
            write(report.parent / "manifest.json", manifest)
            self.assertFalse(verify_case(report.parent))

    def test_selected_subset_delivery_lists_omitted_report_flow(self):
        task = json.loads((self.task / "task.json").read_text())
        task.update({"status": "selected_flows_ready", "ready_count": 1,
                     "needs_attention_count": 0,
                     "omitted_flow_ids": ["two"]})
        task["flows"][0]["status"] = "ready_for_implementation"
        write(self.task / "task.json", task)
        report = self._create()
        delivery = json.loads((report.parent / "delivery.json").read_text())
        self.assertEqual(delivery["omitted_flow_ids"], ["two"])
        self.assertIn("`two`", report.read_text())

    def test_selected_subset_may_reuse_check_covering_extra_flows(self):
        task = json.loads((self.task / "task.json").read_text())
        task.update({"status": "selected_flows_ready", "ready_count": 1,
                     "needs_attention_count": 0, "omitted_flow_ids": ["two"]})
        task["flows"][0]["status"] = "ready_for_implementation"
        write(self.task / "task.json", task)
        self.check_data["pairs"].append({"flow_id": "two", "scenario_id": "two"})
        self.check_data["flows"].append({"flow_id": "two", "scenario_id": "two"})
        write(self.check / "manifest.json", self.check_data)
        report = self._create()
        delivery = json.loads((report.parent / "delivery.json").read_text())
        self.assertEqual(delivery["additional_check_flow_ids"], ["two"])
        self.assertEqual([item["id"] for item in delivery["flow_results"]], ["one"])
        self.assertIn("不计入本任务交付", report.read_text())


if __name__ == "__main__":
    unittest.main()
