import hashlib
import io
import json
import plistlib
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from PIL import Image

from copyapp.agent_task import create_agent_task
from copyapp.ios_analysis import collect_ios_analysis
from copyapp.ios_capabilities import capability_plan
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.ios_report import compose_behavior_report
from copyapp.analysis_delivery import create_analysis_delivery
from copyapp.ios_workflow import copy_ios
from copyapp.ios_packages import import_package
from tests.test_decrypt_package import binary
from copyapp.rebuild_plan import create_rebuild_plan
from copyapp.verify import sha256_file, verify_case


UDID = "00008030-000E45AE0C42402E"
BUNDLE = "com.example.counter"
PREFIX = hashlib.sha256(UDID.encode()).hexdigest()[:16]
IDENTITY = {"device": {"UniqueDeviceID": UDID, "ProductVersion": "26.0.1"},
            "app": {"bundle_id": BUNDLE, "name": "Counter", "version": "1", "build": "1"}}


def capabilities(_udid, root, mode, *_args):
    data = {"device": IDENTITY["device"],
            "probes": {name: {"status": "available"} for name in
                       ("usb_lockdown", "usb_screenshot", "ictrl")},
            "host": {"xcode": {"status": "available"},
                     "development_signing": {"status": "available"}}}
    for name in ("ssh_mobile", "frida_usb", "ios_mcp"):
        data["probes"][name] = {"status": "not_probed"}
    if mode == "enhanced":
        for name in ("ssh_mobile", "frida_usb"):
            data["probes"][name] = {"status": "available"}
    write_json(root / "baseline/device.json", data)
    write_json(root / "baseline/manifest.json", {"schema_version": 1, "kind": "device_doctor", "evidence": []})
    write_json(root / "capabilities.json", {**data, **capability_plan(data, mode)})
    seal_case(root, "ios_capabilities", status="complete", requested_mode=mode,
              selected_mode=capability_plan(data, mode)["selected_mode"], device_id_sha256_prefix=PREFIX)


def player(_udid, backend, script, root, **kwargs):
    root.mkdir(parents=True)
    shutil.copyfile(script, root / "playbook.json")
    plan = read_json(script)
    write_json(root / "observe.json", {"bundle_id": BUNDLE, "source": "StaticText, label: 'Count 1'"})
    Image.new("RGB", (30, 30), "white").save(root / "screen.jpg")
    record = {"schema_version": 1, "bundle_id": BUNDLE, "ui_backend": backend,
              "scenario_id": plan["scenario_id"], "device_id_sha256_prefix": PREFIX,
              "execution_mode": kwargs["mode"], "status": "complete", "steps": [
                  {"index": 1, "action": "tap_label", "frontmost": BUNDLE, "result": {}},
                  {"index": 2, "action": "observe", "frontmost": BUNDLE,
                   "observation_source": "accessibility", "evidence_path": "observe.json", "missing": []},
                  {"index": 3, "action": "screenshot", "frontmost": BUNDLE,
                   "evidence_path": "screen.jpg", "sha256": sha256_file(root / "screen.jpg"),
                   "stability": {"stable": True}, "ready_contains": "Count", "ready_found": True}],
              "evidence": [{"path": p.name, "sha256": sha256_file(p)} for p in sorted(root.iterdir())]}
    write_json(root / "manifest.json", record)
    return root / "manifest.json", True


class IosAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "flow.json"
        write_json(self.script, {"schema_version": 1, "bundle_id": BUNDLE,
                                "scenario_id": "counter", "fresh_launch": True, "steps": [
                                    {"action": "tap_label", "label": "Add"},
                                    {"action": "observe", "contains": ["Count 1"]},
                                    {"action": "screenshot", "stable": True, "ready_contains": "Count"}]})
        for target, replacement in (("collect_capabilities", capabilities), ("run_playbook", player),
                                    ("target_identity", AsyncMock(return_value=IDENTITY))):
            patcher = patch("copyapp.ios_analysis." + target, side_effect=replacement) if target != "target_identity" else patch(
                "copyapp.ios_analysis.target_identity", new=replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.display = redirect_stdout(io.StringIO())
        self.display.__enter__()
        self.addCleanup(self.display.__exit__, None, None, None)

    def collect(self, **kwargs):
        return collect_ios_analysis(UDID, BUNDLE, [self.script], self.root / "analysis", **kwargs)

    def review(self, analysis, output):
        write_json(self.root / "findings.json", {"schema_version": 1, "target_bundle_id": BUNDLE,
                   "review_status": "reviewed", "reviewer": "test reviewer", "sections": [{
                       "title": "Counter", "findings": [{"claim": "Add displays Count 1.",
                           "confidence": "observed", "evidence": ["counter"]}]}]})
        write_json(self.root / "spec.json", {"schema_version": 1, "target_bundle_id": BUNDLE,
                   "rebuilt_bundle_id": "dev.copyapp.counter", "review_status": "reviewed",
                   "scope": "One local counter flow", "unknowns": ["Other states"], "flows": [{
                       "id": "counter", "entry": "Counter", "expected": ["Count 1"],
                       "verification": "Replay and inspect screenshots", "evidence": ["counter"],
                       "source_script_sha256": sha256_file(self.script)}]})
        compose_behavior_report(analysis, self.root / "findings.json", self.root / "spec.json", output)

    def package(self, version="1", bundle=BUNDLE):
        source = self.root / f"{len(list(self.root.iterdir()))}.ipa"
        with ZipFile(source, "w") as archive:
            archive.writestr("Payload/Counter.app/Info.plist", plistlib.dumps({
                "CFBundleIdentifier": bundle, "CFBundleExecutable": "Counter",
                "CFBundleShortVersionString": version, "CFBundleVersion": "1",
                "CFBundleSupportedPlatforms": ["iPhoneOS"]}))
            archive.writestr("Payload/Counter.app/Counter", binary(False))
        output = source.with_suffix("")
        import_package(source, output)
        return output

    def test_external_package_association_is_metadata_only_and_is_recomputed(self):
        matching, older = self.package(), self.package(version="0.9")
        self.assertTrue(self.collect(package_cases=[matching, older])[1])
        analysis = self.root / "analysis"
        state = read_json(analysis / "analysis.json")
        self.assertEqual([row["association"]["relation"] for row in state["packages"]],
                         ["metadata_match", "bundle_only"])
        self.assertTrue(all(row["association"]["runtime_binary_identity"] == "not_verified"
                            for row in state["packages"]))
        self.review(analysis, self.root / "report")
        self.assertTrue(verify_case(self.root / "report"))
        self.assertEqual(read_json(self.root / "report/report-index.json")["evidence"]["package.2"]
                         ["association"]["relation"], "bundle_only")
        state["packages"][1]["association"]["relation"] = "metadata_match"
        write_json(analysis / "analysis.json", state)
        seal_case(analysis, "ios_analysis", status="complete", bundle_id=BUNDLE,
                  device_id_sha256_prefix=PREFIX)
        self.assertFalse(verify_case(analysis))

    def test_wrong_package_is_rejected_before_any_device_operation(self):
        other = self.package(bundle="com.example.other")
        with patch("copyapp.ios_analysis.target_identity") as device:
            with self.assertRaisesRegex(ValueError, "another App"):
                self.collect(package_cases=[other])
            device.assert_not_called()

    def test_static_package_claim_cannot_cite_an_unrelated_ui_flow(self):
        self.collect(package_cases=[self.package()])
        self.review(self.root / "analysis", self.root / "report")
        findings = read_json(self.root / "findings.json")
        row = findings["sections"][0]["findings"][0]
        row.update(basis="package", claim="Package metadata declares this Bundle ID.", evidence=["package.1"])
        write_json(self.root / "findings.json", findings)
        compose_behavior_report(self.root / "analysis", self.root / "findings.json",
                                self.root / "spec.json", self.root / "static-report")
        self.assertTrue(verify_case(self.root / "static-report"))
        row["evidence"] = ["counter"]
        write_json(self.root / "findings.json", findings)
        with self.assertRaisesRegex(ValueError, "basis"):
            compose_behavior_report(self.root / "analysis", self.root / "findings.json",
                                    self.root / "spec.json", self.root / "wrong-report")

    def test_ui_delivery_rechecks_full_source_identity_even_after_rehash(self):
        self.collect()
        report, delivery = self.root / "report", self.root / "delivery"
        self.review(self.root / "analysis", report)
        create_analysis_delivery(self.root / "analysis", report, delivery)
        self.assertTrue(verify_case(delivery))
        saved = read_json(delivery / "delivery.json")
        saved["flow_coverage"][0]["source_script_sha256"] = "0" * 64
        write_json(delivery / "delivery.json", saved)
        seal_case(delivery, "ios_behavior_delivery", status="source_linked_report_ready_for_review", bundle_id=BUNDLE)
        self.assertFalse(verify_case(delivery))
        self.collect(resume=True)
        other = self.root / "different-source"
        shutil.copytree(self.root / "analysis", other)
        # Even an exact copied source is a separate collection identity for delivery.
        with self.assertRaisesRegex(ValueError, "different UI analysis"):
            create_analysis_delivery(other, report, self.root / "wrong-delivery")

    def test_current_workflow_waits_for_review_then_implementation_and_never_launches_agent(self):
        workflow, project = self.root / "workflow", self.root / "project"

        def run(**kwargs):
            return copy_ios(UDID, BUNDLE, [self.script], project, "dev.copyapp.counter",
                            workflow, **kwargs)

        with patch("copyapp.ios_workflow.collect_capabilities", side_effect=capabilities), \
                patch("copyapp.agent_run.run_agent_task") as external:
            self.assertFalse(run()[1])
            self.assertEqual(read_json(workflow / "workflow.json")["status"], "needs_behavior_review")
            self.assertTrue(verify_case(workflow))
            with patch("copyapp.ios_analysis.run_playbook") as replay:
                self.assertFalse(run(resume=True)[1])
                replay.assert_not_called()
            report = workflow / "analysis-agent/reviewed-report"
            self.review(workflow / "analysis", report)
            create_analysis_delivery(workflow / "analysis", report,
                                     workflow / "analysis-agent/analysis-delivery")
            self.assertFalse(run(resume=True)[1])
            self.assertEqual(read_json(workflow / "workflow.json")["status"], "needs_implementation")
            self.assertTrue(verify_case(workflow))
            external.assert_not_called()
        # Rehashing a success flag cannot replace a real device delivery.
        state = read_json(workflow / "workflow.json")
        state["status"] = "complete"
        write_json(workflow / "workflow.json", state)
        seal_case(workflow, "ios_copy_workflow", status="complete", bundle_id=BUNDLE,
                  device_id_sha256_prefix=PREFIX)
        self.assertFalse(verify_case(workflow))

    def test_auto_discovery_writes_a_current_session_handoff_without_phone_actions(self):
        workflow = self.root / "workflow"
        with patch("copyapp.ios_workflow.collect_capabilities", side_effect=capabilities), \
                patch("copyapp.ios_analysis.run_playbook") as replay:
            self.assertFalse(copy_ios(UDID, BUNDLE, [], self.root / "project", "dev.copyapp.counter",
                                      workflow, auto_discover=True)[1])
            replay.assert_not_called()
        self.assertEqual(read_json(workflow / "workflow.json")["status"], "needs_discovery")
        self.assertIn("--mode standard --backend ictrl", (workflow / "discovery-agent/TASK.md").read_text())
        self.assertTrue(verify_case(workflow))

    def test_auto_falls_back_to_ui_and_explicit_enhancement_keeps_source_binding(self):
        collector = unittest.mock.Mock()
        self.assertTrue(self.collect(mode="auto", enhanced_collector=collector)[1])
        collector.assert_not_called()
        enhanced = self.root / "enhanced-analysis"

        def legacy_collection(output, bundle=BUNDLE):
            write_json(output / "survey/manifest.json", {"schema_version": 1,
                       "bundle_id": bundle, "device_id_sha256_prefix": PREFIX, "evidence": []})
            write_json(output / "analysis-index.json", {"steps": {name: {"ok": True}
                       for name in ("survey", "bundle", "sandbox")}, "artifacts": {}})
            return True

        self.assertTrue(collect_ios_analysis(UDID, BUNDLE, [self.script], enhanced, mode="enhanced",
                                             enhanced_collector=legacy_collection)[1])
        self.assertTrue(verify_case(enhanced))
        wrong = self.root / "wrong-enhancement"
        self.assertFalse(collect_ios_analysis(UDID, BUNDLE, [self.script], wrong, mode="enhanced",
                        enhanced_collector=lambda out: legacy_collection(out, "com.example.wrong"))[1])
        self.assertTrue(verify_case(wrong))

    def test_ui_only_analysis_report_and_implementation_task_need_no_package(self):
        _, complete = self.collect()
        self.assertTrue(complete)
        self.assertTrue(verify_case(self.root / "analysis"))
        digest = sha256_file(self.script)
        write_json(self.root / "findings.json", {"schema_version": 1, "target_bundle_id": BUNDLE,
                   "review_status": "reviewed", "reviewer": "test reviewer", "sections": [{
                       "title": "Counter", "findings": [{"claim": "Add displays Count 1.",
                           "confidence": "observed", "evidence": ["counter"]}]}]})
        write_json(self.root / "spec.json", {"schema_version": 1, "target_bundle_id": BUNDLE,
                   "rebuilt_bundle_id": "dev.copyapp.counter", "review_status": "reviewed",
                   "scope": "One local counter flow", "unknowns": ["Other states"], "flows": [{
                       "id": "counter", "entry": "Counter", "expected": ["Count 1"],
                       "verification": "Replay and inspect screenshots", "evidence": ["counter"],
                       "source_script_sha256": digest}]})
        report = self.root / "report"
        compose_behavior_report(self.root / "analysis", self.root / "findings.json",
                                self.root / "spec.json", report)
        self.assertTrue(verify_case(report))
        create_rebuild_plan(report, self.root / "plan", backend="ictrl")
        self.assertTrue(verify_case(self.root / "plan"))
        create_agent_task(report, self.root / "plan", self.root / "task", udid=UDID)
        self.assertTrue(verify_case(self.root / "task"))
        self.assertEqual(read_json(self.root / "task/task.json")["status"], "ready_for_agent")
        findings = read_json(report / "findings.json")
        findings["sections"][0]["findings"][0]["basis"] = "function"
        write_json(report / "findings.json", findings)
        seal_case(report, "ios_behavior_report", status="reviewed", bundle_id=BUNDLE, analysis_scope="ui_behavior")
        self.assertFalse(verify_case(report))

    def test_resume_reuses_verified_complete_flows_without_device_actions(self):
        self.collect()
        with patch("copyapp.ios_analysis.run_playbook") as replay, \
                patch("copyapp.ios_analysis.target_identity") as device:
            _, complete = self.collect(resume=True)
        self.assertTrue(complete)
        replay.assert_not_called()
        device.assert_not_called()

    def test_rehashed_observation_cannot_claim_a_missing_result(self):
        self.collect()
        root = self.root / "analysis"
        child = root / "flows/flow-01"
        write_json(child / "observe.json", {"bundle_id": BUNDLE, "source": "Count 0"})
        flow = read_json(child / "manifest.json")
        for item in flow["evidence"]:
            item["sha256"] = sha256_file(child / item["path"])
        write_json(child / "manifest.json", flow)
        state = read_json(root / "analysis.json")
        state["flows"][0]["manifest_sha256"] = sha256_file(child / "manifest.json")
        write_json(root / "analysis.json", state)
        seal_case(root, "ios_analysis", status="complete", bundle_id=BUNDLE, device_id_sha256_prefix=PREFIX)
        self.assertFalse(verify_case(root))

    def test_failed_flow_requires_reviewed_explicit_retry_and_is_archived(self):
        def failed(*args, **kwargs):
            manifest, _ = player(*args, **kwargs)
            data = read_json(manifest)
            data["status"] = "failed"
            data["error"] = {"message": "reply lost, completion unknown"}
            write_json(manifest, data)
            return manifest, False

        with patch("copyapp.ios_analysis.run_playbook", side_effect=failed):
            self.assertFalse(self.collect()[1])
        with patch("copyapp.ios_analysis.run_playbook") as replay:
            self.assertFalse(self.collect(resume=True)[1])
            replay.assert_not_called()
        self.assertTrue(self.collect(resume=True, retry_failed=True)[1])
        attempts = self.root / "analysis/attempts"
        self.assertEqual(len(list(attempts.iterdir())), 1)
        self.assertTrue(verify_case(self.root / "analysis"))


if __name__ == "__main__":
    unittest.main()
