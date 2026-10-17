import hashlib
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from copyapp.investigate_flow import _resolve_target, investigate_flow
from copyapp.report import _validate_investigation
from copyapp.experiment import _static_targets
from copyapp.trace import trace_script
from copyapp.method_scout import refine_scout_with_view_tree, scout_methods
from copyapp.verify import sha256_file, verify_case


def minimal_macho():
    data = bytearray(104)
    data[:4] = b"\xcf\xfa\xed\xfe"
    struct.pack_into("<II", data, 16, 1, 72)
    struct.pack_into("<II", data, 32, 0x19, 72)
    struct.pack_into("<QQQQ", data, 56, 0x100000000, 0x1000, 0, len(data))
    return bytes(data)


class InvestigateFlowTest(unittest.TestCase):
    def test_hopper_preflight_precedes_device_capture(self):
        with patch("copyapp.hopper_direct.check_direct_hopper",
                   side_effect=FileNotFoundError("Hopper unavailable")), \
             patch("copyapp.investigate_flow.capture_flow") as capture:
            with self.assertRaisesRegex(FileNotFoundError, "Hopper unavailable"):
                investigate_flow(self.udid, self.analysis, self.script,
                                 self.root / "hopper-preflight",
                                 provider="hopper-direct")
        capture.assert_not_called()

    def test_removed_rea_provider_is_rejected_before_device_work(self):
        with patch("copyapp.investigate_flow.capture_flow") as capture:
            with self.assertRaisesRegex(ValueError, "unsupported analysis provider"):
                investigate_flow(self.udid, self.analysis, self.script,
                                 self.root / "removed-rea", provider="ghidra")
        capture.assert_not_called()

    def test_network_option_reaches_flow_and_is_pinned_for_resume(self):
        output = self.root / "network-option"
        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_flow",
                   side_effect=RuntimeError("stop before device touch")) as flow:
            manifest, complete = investigate_flow(
                self.udid, self.analysis, self.script, output,
                methods=["View::buttonPressed:"], network=True)
        self.assertFalse(complete)
        self.assertTrue(flow.call_args.kwargs["network"])
        self.assertTrue(json.loads(manifest.read_text())["network_requested"])
        with patch("copyapp.investigate_flow.verify_case", return_value=True):
            with self.assertRaisesRegex(ValueError, "identity differs"):
                investigate_flow(self.udid, self.analysis, self.script, output,
                                 methods=["View::buttonPressed:"], resume=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.analysis = self.root / "analysis"
        for part in ("survey", "acquired/bundle/App.app", "acquired/static"):
            (self.analysis / part).mkdir(parents=True)
        self.udid = "exact-device"
        self.prefix = hashlib.sha256(self.udid.encode()).hexdigest()[:16]
        self.bundle = "com.example.app"
        self.binary = self.analysis / "acquired/bundle/App.app/App"
        self.binary.write_bytes(minimal_macho())
        self.digest = sha256_file(self.binary)
        self.index = self.analysis / "acquired/static/objc-index.json"
        self.save_index([("View", "buttonPressed:", "0x100001000")])
        (self.analysis / "acquired/static/ipa-index.json").write_text(json.dumps({
            "binaries": [{"path": "Payload/App.app/App", "sha256": self.digest,
                          "encrypted_on_disk": False}]}))
        (self.analysis / "survey/manifest.json").write_text(json.dumps({
            "bundle_id": self.bundle, "device_id_sha256_prefix": self.prefix}))
        (self.analysis / "survey/app.json").write_text(json.dumps({
            "CFBundleIdentifier": self.bundle, "CFBundleExecutable": "App"}))
        (self.analysis / "acquired/acquisition.json").write_text(json.dumps({
            "bundle_id": self.bundle, "device_id_sha256_prefix": self.prefix,
            "remote_bundle_path": "/Applications/App.app"}))
        (self.analysis / "analysis-index.json").write_text(json.dumps({
            "steps": {"survey": {"ok": True}, "bundle": {"ok": True}}}))
        self.script = self.root / "flow.json"
        self.script.write_text(json.dumps({"schema_version": 1,
                                           "bundle_id": self.bundle,
                                           "steps": [{"action": "tap", "x": 1, "y": 1}]}))

    def save_index(self, methods):
        classes = {}
        for cls, selector, imp in methods:
            classes.setdefault(cls, []).append({"selector": selector, "imp": imp})
        self.index.write_text(json.dumps({"schema_version": 1,
            "binary_sha256": self.digest, "image_base": "0x100000000",
            "classes": [{"name": name, "instance_methods": values}
                        for name, values in classes.items()]}))

    def test_scout_selects_unique_action_and_stops_on_ambiguity(self):
        selected = scout_methods(self.index)
        self.assertEqual(selected["selected_method"], "View::buttonPressed:")
        self.save_index([("View", "tappedOne:", "0x100001000"),
                         ("View", "tappedTwo:", "0x100001004")])
        ambiguous = scout_methods(self.index)
        self.assertEqual(ambiguous["status"], "needs_review")
        self.assertIsNone(ambiguous["selected_method"])
        self.save_index([("HomeViewController", "showCounter", "0x100001000"),
                         ("HomeViewController", "showNotes", "0x100001004")])
        fallback = scout_methods(self.index)
        self.assertEqual(fallback["status"], "needs_review")
        self.assertEqual({item["selector"] for item in fallback["ranked"]},
                         {"showCounter", "showNotes"})
        by_label = scout_methods(self.index, tap_labels=["Counter · UserDefaults",
                                                        "Increment counter"])
        self.assertEqual(by_label["selected_method"], "HomeViewController::showCounter")
        self.assertEqual(by_label["selection_basis"], "unique_exact_tap_labels")
        self.assertIsNone(scout_methods(self.index, tap_labels=["Increment counter"])
                          ["selected_method"])
        self.save_index([("HomeViewController", "showNotes", "0x100001000"),
                         ("NotesViewController", "addNote", "0x100001004")])
        two = scout_methods(self.index, tap_labels=["Notes · SQLite", "Add sample note"])
        self.assertEqual(two["selected_methods"],
                         ["HomeViewController::showNotes", "NotesViewController::addNote"])

    def test_playbook_label_selects_unique_navigation_entry(self):
        self.save_index([("HomeViewController", "showCounter", "0x100001000"),
                         ("HomeViewController", "showNotes", "0x100001004")])
        self.script.write_text(json.dumps({"schema_version": 1, "bundle_id": self.bundle,
            "steps": [{"action": "tap_label", "label": "Counter · UserDefaults"}]}))
        output = self.root / "label-selected"
        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_flow", side_effect=RuntimeError("stop")) as flow:
            path, complete = investigate_flow(self.udid, self.analysis, self.script, output,
                                              provider="none")
        self.assertFalse(complete)
        self.assertEqual(flow.call_args.kwargs["methods"],
                         ["HomeViewController::showCounter"])
        self.assertEqual(json.loads(path.read_text())["error"]["stage"], "flow_capture")

    def test_runtime_button_class_refines_ambiguous_method_scout(self):
        self.save_index([("_TtC13DeepSeek_Chat8DSButton", "objcOnTap", "0x100001000"),
                         ("OtherView", "didTap:", "0x100001004")])
        tree = self.root / "entry-tree.json"
        tree.write_text(json.dumps({"type": "view_tree", "nodes": [
            {"id": 0, "parent": None, "class_name": "UIWindow"},
            {"id": 1, "parent": 0, "class_name": "DeepSeek_Chat.DSButton"},
            {"id": 2, "parent": 1, "class_name": "UILabel",
             "text": "Continue with Password"}]}))
        scout = scout_methods(self.index, tap_labels=["Continue with Password"])
        self.assertEqual(scout["selected_methods"], [])
        refined = refine_scout_with_view_tree(scout, self.index, tree,
                                              ["Continue with Password"])
        self.assertEqual(refined["selected_methods"],
                         ["_TtC13DeepSeek_Chat8DSButton::objcOnTap"])
        self.assertEqual(refined["runtime_view_sha256"], sha256_file(tree))
        self.assertEqual(refine_scout_with_view_tree(scout, self.index, tree,
                         ["Missing button"])["selected_methods"], [])

    def test_default_uses_entry_view_candidate_without_rea(self):
        self.save_index([("_TtC13DeepSeek_Chat8DSButton", "objcOnTap", "0x100001000"),
                         ("OtherView", "didTap:", "0x100001004")])
        self.script.write_text(json.dumps({"schema_version": 1,
            "bundle_id": self.bundle, "steps": [
                {"action": "tap_label", "label": "Continue with Password"}]}))
        output = self.root / "runtime-selected"

        def entry_stage(udid, bundle, target, **kwargs):
            target.mkdir()
            (target / "view-tree.json").write_text(json.dumps({
                "type": "view_tree", "nodes": [
                    {"id": 0, "parent": None, "class_name": "UIWindow"},
                    {"id": 1, "parent": 0, "class_name": "DeepSeek_Chat.DSButton",
                     "accessibility_label": "Continue with Password"}]}))
            (target / "manifest.json").write_text("{}")
            return target / "manifest.json", True

        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_view_tree",
                   side_effect=entry_stage) as entry, \
             patch("copyapp.investigate_flow.capture_flow",
                   side_effect=RuntimeError("stop before touching device")) as flow:
            manifest, complete = investigate_flow(self.udid, self.analysis,
                                                  self.script, output)
        self.assertFalse(complete)
        entry.assert_called_once()
        self.assertEqual(flow.call_args.kwargs["methods"],
                         ["_TtC13DeepSeek_Chat8DSButton::objcOnTap"])
        record = json.loads(manifest.read_text())
        self.assertEqual(record["provider"], "none")
        self.assertEqual(record["method_selection"], "runtime_view_heuristic")
        self.assertEqual(record["entry_view_status"], "complete")
        self.assertTrue(verify_case(output))

    def test_failed_entry_view_keeps_no_rea_ui_capture_available(self):
        self.save_index([("View", "tappedOne:", "0x100001000"),
                         ("View", "tappedTwo:", "0x100001004")])
        self.script.write_text(json.dumps({"schema_version": 1,
            "bundle_id": self.bundle, "steps": [
                {"action": "tap_label", "label": "Continue"}]}))
        output = self.root / "view-unavailable"

        def entry_stage(udid, bundle, target, **kwargs):
            target.mkdir()
            (target / "manifest.json").write_text(json.dumps({
                "kind": "uikit_view_tree", "status": "failed",
                "bundle_id": bundle,
                "device_id_sha256_prefix": self.prefix, "evidence": []}))
            return target / "manifest.json", False

        def flow_stage(udid, backend, script, target, **kwargs):
            (target / "playbook").mkdir(parents=True)
            (target / "playbook/playbook.json").write_bytes(script.read_bytes())
            (target / "manifest.json").write_text(json.dumps({
                "bundle_id": self.bundle, "ui_backend": backend}))
            return target / "manifest.json", True

        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_view_tree",
                   side_effect=entry_stage) as entry, \
             patch("copyapp.investigate_flow.capture_flow",
                   side_effect=flow_stage) as flow, \
             patch("copyapp.investigate_flow.build_candidates") as candidates:
            manifest, complete = investigate_flow(self.udid, self.analysis,
                                                  self.script, output)
        self.assertTrue(complete)
        entry.assert_called_once()
        self.assertIsNone(flow.call_args.kwargs["methods"])
        candidates.assert_not_called()
        record = json.loads(manifest.read_text())
        self.assertEqual(record["entry_view_status"], "unavailable")
        self.assertEqual(record["rea_status"], "not_requested")
        self.assertTrue(verify_case(output))
        with patch("copyapp.report.verify_case", return_value=True), \
             patch("copyapp.report._validate_flow_capture", return_value={
                 "trace": None, "manifest": {"ui_backend": "ios-mcp"}}):
            _validate_investigation(output, self.bundle, self.prefix, {self.digest})



    def test_failed_flow_retry_archives_original_before_new_device_touch(self):
        self.save_index([("View", "firstAction:", "0x100001000"),
                         ("View", "secondAction:", "0x100001004")])
        output = self.root / "flow-retry"
        calls = []

        def flow_stage(*args, **kwargs):
            target = args[3]
            target.mkdir(parents=True)
            calls.append(target)
            status = "failed" if len(calls) == 1 else "complete"
            manifest = target / "manifest.json"
            manifest.write_text(json.dumps({"status": status, "evidence": []}))
            return manifest, status == "complete"

        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_flow", side_effect=flow_stage), \
             patch("copyapp.investigate_flow.write_review_brief"):
            _, complete = investigate_flow(self.udid, self.analysis, self.script, output,
                                           provider="none")
            self.assertFalse(complete)
            self.assertEqual(json.loads((output / "manifest.json").read_text())
                             ["error"]["stage"], "flow_capture")
            _, complete = investigate_flow(self.udid, self.analysis, self.script, output,
                                           provider="none", resume=True)
        self.assertTrue(complete)
        self.assertEqual(len(calls), 2)
        archives = list((output / "attempts").glob("flow-*/manifest.json"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(json.loads(archives[0].read_text())["status"], "failed")
        self.assertEqual(json.loads((output / "flow/manifest.json").read_text())["status"],
                         "complete")
        self.assertTrue(verify_case(output))


    def test_default_needs_no_rea_or_objc_method_for_ui_evidence(self):
        self.save_index([("View", "tappedOne:", "0x100001000"),
                         ("View", "tappedTwo:", "0x100001004")])
        output = self.root / "ui-only"

        def flow_stage(udid, backend, script, target, **kwargs):
            (target / "playbook").mkdir(parents=True)
            (target / "playbook/playbook.json").write_bytes(script.read_bytes())
            (target / "manifest.json").write_text(json.dumps({
                "bundle_id": self.bundle, "ui_backend": backend}))
            return target / "manifest.json", True

        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_flow", side_effect=flow_stage) as capture, \
             patch("copyapp.investigate_flow.build_candidates") as candidates:
            manifest, complete = investigate_flow(self.udid, self.analysis,
                                                  self.script, output)
        self.assertTrue(complete, manifest.read_text())
        self.assertIsNone(capture.call_args.kwargs["methods"])
        candidates.assert_not_called()
        record = json.loads(manifest.read_text())
        self.assertEqual(record["provider"], "none")
        self.assertEqual(record["rea_status"], "not_requested")
        self.assertTrue(verify_case(output))
        with patch("copyapp.report.verify_case", return_value=True), \
             patch("copyapp.report._validate_flow_capture", return_value={
                 "trace": None, "manifest": {"ui_backend": "ios-mcp"}}):
            _validate_investigation(output, self.bundle, self.prefix, {self.digest})

    def test_default_keeps_trace_when_static_candidate_is_empty(self):
        output = self.root / "trace-no-candidate"

        def flow_stage(udid, backend, script, target, **kwargs):
            (target / "playbook").mkdir(parents=True)
            (target / "playbook/playbook.json").write_bytes(script.read_bytes())
            (target / "trace").mkdir()
            (target / "trace/trace.json").write_text(json.dumps({
                "requested_methods": ["View::buttonPressed:"], "steps": []}))
            (target / "manifest.json").write_text(json.dumps({
                "bundle_id": self.bundle, "ui_backend": backend}))
            return target / "manifest.json", True

        def candidate_stage(udid, bundle, binary, index, flows, target):
            (target / "sources/flow-01").mkdir(parents=True)
            (target / "sources/flow-01/manifest.json").write_bytes(
                (flows[0] / "manifest.json").read_bytes())
            (target / "candidates.json").write_text(json.dumps({
                "bundle_id": bundle, "device_id_sha256_prefix": self.prefix,
                "binary_sha256": self.digest, "candidates": []}))
            (target / "manifest.json").write_text("{}")
            return target / "candidates.json", False

        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_flow", side_effect=flow_stage), \
             patch("copyapp.investigate_flow.build_candidates", side_effect=candidate_stage):
            manifest, complete = investigate_flow(self.udid, self.analysis,
                                                  self.script, output)
        self.assertTrue(complete, manifest.read_text())
        self.assertEqual(json.loads(manifest.read_text())["candidate_status"],
                         "no_candidates")
        with patch("copyapp.report.verify_case", return_value=True), \
             patch("copyapp.report._validate_flow_capture", return_value={
                 "trace": {"requested_methods": ["View::buttonPressed:"]},
                 "manifest": {"ui_backend": "ios-mcp"}}):
            _validate_investigation(output, self.bundle, self.prefix, {self.digest})

    def test_default_completes_when_native_disassembly_is_unavailable(self):
        output = self.root / "native-unavailable"

        def flow_stage(udid, backend, script, target, **kwargs):
            (target / "playbook").mkdir(parents=True)
            (target / "playbook/playbook.json").write_bytes(script.read_bytes())
            (target / "trace").mkdir()
            (target / "trace/trace.json").write_text(json.dumps({
                "requested_methods": ["View::buttonPressed:"], "steps": []}))
            (target / "manifest.json").write_text(json.dumps({
                "bundle_id": self.bundle, "ui_backend": backend}))
            return target / "manifest.json", True

        def candidate_stage(udid, bundle, binary, index, flows, target):
            (target / "sources/flow-01").mkdir(parents=True)
            (target / "sources/flow-01/manifest.json").write_bytes(
                (flows[0] / "manifest.json").read_bytes())
            source = target / "candidates.json"
            source.write_text(json.dumps({
                "schema_version": 1, "kind": "runtime_static_candidates",
                "bundle_id": bundle, "device_id_sha256_prefix": self.prefix,
                "binary_path": str(binary.resolve()), "binary_sha256": self.digest,
                "candidates": [{"class": "View", "selector": "buttonPressed:",
                                "static_address": "0x100001000",
                                "binary_sha256": self.digest,
                                "observations": [{"calls": 1}]}]}))
            (target / "manifest.json").write_text(json.dumps({
                "evidence": [{"path": "candidates.json", "sha256": sha256_file(source)}]}))
            return source, True

        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_flow", side_effect=flow_stage), \
             patch("copyapp.investigate_flow.build_candidates", side_effect=candidate_stage):
            manifest, complete = investigate_flow(self.udid, self.analysis,
                                                  self.script, output)
        self.assertTrue(complete, manifest.read_text())
        self.assertEqual(json.loads(manifest.read_text())["native_status"],
                         "unavailable")
        self.assertTrue(verify_case(output))
        with patch("copyapp.report.verify_case", return_value=True), \
             patch("copyapp.report._validate_flow_capture", return_value={
                 "trace": {"requested_methods": ["View::buttonPressed:"]},
                 "manifest": {"ui_backend": "ios-mcp"}}):
            validated = _validate_investigation(output, self.bundle,
                                                self.prefix, {self.digest})
        self.assertEqual(validated["native"]["complete_count"], 0)


    def test_resolves_decrypted_main_from_verified_ipa_member(self):
        decrypted = self.analysis / "decrypted"
        (decrypted / "static").mkdir(parents=True)
        (decrypted / "static/objc-index.json").write_bytes(self.index.read_bytes())
        (decrypted / "static/ipa-index.json").write_text(json.dumps({
            "binaries": [{"path": "Payload/App.app/App", "sha256": self.digest}]}))
        (decrypted / "decryption.json").write_text(json.dumps({
            "all_macho_headers_decrypted": True}))
        with zipfile.ZipFile(decrypted / "analysis.ipa", "w") as archive:
            archive.writestr("Payload/App.app/App", self.binary.read_bytes())
        analysis_index = json.loads((self.analysis / "analysis-index.json").read_text())
        analysis_index["steps"]["decryption"] = {"ok": True}
        (self.analysis / "analysis-index.json").write_text(json.dumps(analysis_index))
        with patch("copyapp.investigate_flow.verify_case", return_value=True):
            target, index, kind = _resolve_target(self.analysis, self.udid, self.bundle,
                                                  self.root / "extracted")
        self.assertEqual(kind, "decrypted_ipa_member")
        self.assertEqual(sha256_file(target), self.digest)
        self.assertEqual(index, decrypted / "static/objc-index.json")

    def test_rejects_encrypted_acquired_main_before_device_actions(self):
        source = self.analysis / "acquired/static/ipa-index.json"
        data = json.loads(source.read_text())
        data["binaries"][0]["encryption_info"] = {"cryptid": 1}
        source.write_text(json.dumps(data))
        with patch("copyapp.investigate_flow.verify_case", return_value=True), \
             patch("copyapp.investigate_flow.capture_flow") as flow:
            _, complete = investigate_flow(self.udid, self.analysis, self.script,
                                           self.root / "encrypted")
        self.assertFalse(complete)
        flow.assert_not_called()

    def test_legacy_index_without_image_base_uses_pinned_macho_base(self):
        index = json.loads(self.index.read_text())
        index.pop("image_base")
        self.index.write_text(json.dumps(index))
        digest, targets = _static_targets(self.binary, self.index,
                                          [("View", "buttonPressed:")])
        self.assertEqual(digest, self.digest)
        self.assertEqual(targets[0]["offset"], 0x1000)

    def test_embedded_framework_method_binds_to_full_app_relative_path(self):
        framework = self.binary.parent / "Frameworks" / "StoreUI.framework" / "StoreUI"
        framework.parent.mkdir(parents=True)
        framework.write_bytes(minimal_macho())
        index = self.root / "storeui-objc-index.json"
        index.write_text(json.dumps({
            "schema_version": 1, "binary_sha256": sha256_file(framework),
            "image_base": "0x100000000", "classes": [{
                "name": "SearchCell", "instance_methods": [{
                    "selector": "initWithFrame:", "imp": "0x100001000"}]}],
        }))
        _, targets = _static_targets(framework, index,
                                     [("SearchCell", "initWithFrame:")])
        self.assertEqual(targets[0]["app_dir"], "App.app")
        self.assertEqual(targets[0]["relative_path"],
                         "Frameworks/StoreUI.framework/StoreUI")
        script = trace_script([("SearchCell", "initWithFrame:")],
                              static_targets=targets)
        self.assertIn("target.relative_path || target.binary_name", script)

    def test_unrelated_duplicate_index_method_does_not_block_selected_target(self):
        self.save_index([("View", "buttonPressed:", "0x100001000"),
                         ("SDK", "isEnabled", "0x100001010"),
                         ("SDK", "isEnabled", "0x100001020")])
        _, targets = _static_targets(self.binary, self.index,
                                     [("View", "buttonPressed:")])
        self.assertEqual(targets[0]["offset"], 0x1000)
        with self.assertRaisesRegex(ValueError, "ambiguous Objective-C index method"):
            _static_targets(self.binary, self.index, [("SDK", "isEnabled")])


if __name__ == "__main__":
    unittest.main()
