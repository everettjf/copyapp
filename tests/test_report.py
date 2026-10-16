import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.ocr_file import ocr_file
from copyapp.report import compose_report, _validate_view_tree
from copyapp.sandbox_diff import compare_sandbox
from copyapp.verify import sha256_file, verify_case


class ReportCompositionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / "case"
        (self.case / "survey").mkdir(parents=True)
        (self.case / "acquired/static").mkdir(parents=True)
        (self.case / "analysis-index.json").write_text('{"artifacts": {}}')
        (self.case / "survey/manifest.json").write_text(json.dumps({
            "bundle_id": "com.example.target", "device": {"ProductType": "iPhone11,8",
                                                         "ProductVersion": "16.1.1"},
            "device_id_sha256_prefix": "abc123",
            "ui_attribution": {"status": "verified_frontmost"},
        }))
        (self.case / "survey/app.json").write_text('{"CFBundleShortVersionString": "1.0"}')
        (self.case / "survey/ui.json").write_text('{"elements": []}')
        (self.case / "acquired/static/ipa-index.json").write_text(json.dumps({
            "bundle_id": "com.example.target",
            "binaries": [{"path": "Payload/Target.app/Target", "sha256": "a" * 64}],
        }))
        self.findings = self.root / "findings.json"
        self.findings.write_text(json.dumps({
            "schema_version": 1, "target_bundle_id": "com.example.target",
            "sections": [{"title": "Function", "findings": [{
                "claim": "Tapped function ran", "confidence": "observed",
                "evidence": ["exp.tap"],
            }]}],
        }))
        self.exp = self.root / "exp"
        self.exp.mkdir()
        before, after = b"before", b"after"
        (self.exp / "before.jpg").write_bytes(before)
        (self.exp / "after.jpg").write_bytes(after)
        (self.exp / "experiment.json").write_text(json.dumps({
            "status": "complete", "bundle_id": "com.example.target",
            "device_id_sha256_prefix": "abc123",
            "frontmost_before": "com.example.target", "frontmost_after": "com.example.target",
            "methods": [{"class": "Example", "selector": "tap", "status": "hooked"}],
            "requested_methods": ["Example::tap"], "call_counts": [1],
            "screenshot_before_sha256": hashlib.sha256(before).hexdigest(),
            "screenshot_after_sha256": hashlib.sha256(after).hexdigest(),
        }))

    def test_composes_and_verifies_cited_experiment(self):
        with patch("copyapp.report.verify_case", return_value=True):
            report = compose_report(self.case, self.findings,
                                    ["exp.tap=" + str(self.exp)], self.root / "report")
        text = report.read_text()
        self.assertIn("Tapped function ran", text)
        self.assertIn("`Example::tap` 1 次", text)
        self.assertTrue(verify_case(self.root / "report"))

    def test_report_exposes_metadata_only_sandbox_and_asset_summary(self):
        static_path = self.case / "acquired/static/ipa-index.json"
        static = json.loads(static_path.read_text())
        static["asset_catalogs"] = [{"path": "Payload/Target.app/Assets.car", "assets": [
            {"name": "Button<Primary>"}, {"name": "AppIcon"}]}]
        static_path.write_text(json.dumps(static))
        (self.case / "sandbox-index.json").write_text(json.dumps({
            "bundle_id": "com.example.target", "depth_limit": 8,
            "entries": [
                {"relative": "Documents", "kind": "d"},
                {"relative": "Documents/state.sqlite", "kind": "f", "size": 512},
                {"relative": "Library", "kind": "d"},
                {"relative": "Library/Preferences/user.plist", "kind": "f", "size": 24},
            ],
        }))
        with patch("copyapp.report.verify_case", return_value=True):
            report = compose_report(self.case, self.findings,
                                    ["exp.tap=" + str(self.exp)], self.root / "rich-report")
        content = report.read_text()
        self.assertIn("Documents/state.sqlite", content)
        self.assertIn("2 个目录、2 个文件", content)
        self.assertIn("Button&lt;Primary&gt;", content)
        self.assertIn("未读取文件内容", content)
        self.assertTrue(verify_case(self.root / "rich-report"))

    def test_imports_native_assembly_without_rea(self):
        native = self.root / "native"
        native.mkdir()
        assembly = native / "assembly.txt"
        assembly.write_text("1000: d65f03c0 ret\n")
        summary = native / "summary.json"
        summary.write_text(json.dumps({
            "schema_version": 1, "kind": "native_disassembly",
            "status": "complete", "binary_sha256": "a" * 64,
            "address": "0x1000", "stop_address": "0x1004",
            "max_bytes": 16, "boundary": "bounded_window", "truncated": True,
            "tool_name": "llvm-objdump", "instruction_count": 1,
            "direct_calls": [], "direct_calls_truncated": False,
            "direct_branches": [],
            "assembly_sha256": sha256_file(assembly)}))
        (native / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "native_disassembly", "status": "complete",
            "evidence": [{"path": path.name, "sha256": sha256_file(path)}
                         for path in (assembly, summary)]}))
        findings = json.loads(self.findings.read_text())
        findings["sections"][0]["findings"][0]["evidence"] = ["asm.one"]
        self.findings.write_text(json.dumps(findings))
        with patch("copyapp.report.verify_case", return_value=True):
            compose_report(self.case, self.findings,
                           ["asm.one=" + str(native)], self.root / "native-report")
        output = self.root / "native-report"
        self.assertTrue(verify_case(output))
        index = json.loads((output / "report-index.json").read_text())
        self.assertEqual(index["evidence"]["asm.one"]["kind"], "native_disassembly")
        self.assertEqual(index["evidence"]["asm.one"]["instruction_count"], 1)

    def test_branch_map_import_keeps_replay_sources(self):
        source = self.root / "flow-source"
        source.mkdir()
        (source / "manifest.json").write_text('{"kind":"ui_flow_capture","evidence":[]}')
        (source / "unlisted.txt").write_text("must not be copied")
        binary = self.root / "Target"
        binary.write_bytes(b"mach-o")
        branch = self.root / "branch"
        branch.mkdir()
        for name in ("manifest.json", "branch-map.json", "report.md"):
            (branch / name).write_text(name)
        findings = json.loads(self.findings.read_text())
        findings["sections"][0]["findings"][0]["evidence"] = ["branch.buttons"]
        self.findings.write_text(json.dumps(findings))
        imported = {"manifest": {}, "record": {
            "binary_sha256": sha256_file(binary), "method": "Example::buttonPressed:",
            "observations": [{"step": 1}]},
            "files": ["manifest.json", "branch-map.json", "report.md"],
            "source_paths": [source], "binary_path": binary}
        with patch("copyapp.report.verify_case", return_value=True), \
                patch("copyapp.report.validate_branch_map", return_value=imported):
            compose_report(self.case, self.findings,
                           ["branch.buttons=" + str(branch)], self.root / "branch-report")
        report = self.root / "branch-report"
        replay = json.loads((report / "evidence/branch.buttons/replay-sources.json").read_text())
        self.assertEqual(replay["flows"][0]["path"], "sources/flow-01")
        self.assertEqual((report / "evidence/branch.buttons/sources/binary").read_bytes(), b"mach-o")
        self.assertTrue((report / "evidence/branch.buttons/sources/flow-01/manifest.json").is_file())
        self.assertFalse((report / "evidence/branch.buttons/sources/flow-01/unlisted.txt").exists())
        self.assertTrue(verify_case(report))

    def test_feature_spec_requires_imported_flow_evidence(self):
        specification = self.root / "feature-spec.json"
        specification.write_text(json.dumps({
            "target_bundle_id": "com.example.target",
            "flows": [{"id": "tap", "entry": "Tap", "expected": "State changes",
                       "verification": "Observe state", "evidence": ["exp.missing"]}],
        }))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "imported evidence"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp)], self.root / "rejected",
                           feature_spec=specification)
        spec = json.loads(specification.read_text())
        spec["flows"][0]["evidence"] = ["exp.tap"]
        specification.write_text(json.dumps(spec))
        with patch("copyapp.report.verify_case", return_value=True):
            report = compose_report(self.case, self.findings,
                                    ["exp.tap=" + str(self.exp)], self.root / "accepted",
                                    feature_spec=specification)
        self.assertTrue(report.is_file())

    def test_provisional_report_labels_spec_as_pending_review(self):
        findings = json.loads(self.findings.read_text())
        findings["review_status"] = "needs_semantic_review"
        self.findings.write_text(json.dumps(findings))
        specification = self.root / "draft-spec.json"
        specification.write_text(json.dumps({
            "target_bundle_id": "com.example.target",
            "review_status": "needs_semantic_review",
            "flows": [{"id": "tap", "entry": "Tap", "expected": ["Observed result"],
                       "verification": "Review screen", "evidence": ["exp.tap"]}],
        }))
        with patch("copyapp.report.verify_case", return_value=True):
            report = compose_report(self.case, self.findings,
                                    ["exp.tap=" + str(self.exp)], self.root / "draft-report",
                                    feature_spec=specification)
        text = report.read_text()
        self.assertIn("事实草稿：尚需审阅", text)
        self.assertIn("待审复刻规格", text)
        self.assertNotIn("可执行复刻规格", text)

    def test_rejects_experiment_from_other_app(self):
        record = json.loads((self.exp / "experiment.json").read_text())
        record["bundle_id"] = "com.example.other"
        (self.exp / "experiment.json").write_text(json.dumps(record))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "target app"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp)], self.root / "report")

    def test_rejects_experiment_from_other_device(self):
        record = json.loads((self.exp / "experiment.json").read_text())
        record["device_id_sha256_prefix"] = "different"
        (self.exp / "experiment.json").write_text(json.dumps(record))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "target app"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp)], self.root / "report")

    def test_rejects_static_experiment_from_other_binary(self):
        record = json.loads((self.exp / "experiment.json").read_text())
        record["static_binary_sha256"] = "f" * 64
        (self.exp / "experiment.json").write_text(json.dumps(record))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "another binary"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp)], self.root / "report")

    def test_imports_complete_playbook_and_rejects_tampered_frame(self):
        play = self.root / "play"
        play.mkdir()
        plan = {"schema_version": 1, "scenario_id": "tap-result",
                "bundle_id": "com.example.target", "steps": [
                    {"action": "screenshot", "stable": True, "ready_contains": "result"}]}
        (play / "playbook.json").write_text(json.dumps(plan))
        image = play / "step-01-screenshot.jpg"
        Image.new("RGB", (20, 30), "black").save(image)
        manifest = {"schema_version": 1, "scenario_id": "tap-result",
                    "bundle_id": "com.example.target", "status": "complete",
                    "ui_backend": "ios-mcp", "device_id_sha256_prefix": "abc123",
                    "screen": {"width": 20, "height": 30, "coordinate_space": "points"},
                    "steps": [{"index": 1, "action": "screenshot",
                               "frontmost": "com.example.target", "stability": {"stable": True},
                               "ready_contains": "result", "ready_found": True,
                               "evidence_path": image.name, "sha256": sha256_file(image)}],
                    "evidence": [{"path": "playbook.json", "sha256": sha256_file(play / "playbook.json")},
                                 {"path": image.name, "sha256": sha256_file(image)}]}
        (play / "manifest.json").write_text(json.dumps(manifest))
        ocr = self.root / "result-ocr.json"
        with patch("copyapp.ocr_file.recognize_screenshot",
                   return_value={"engine": "macos-vision", "texts": [{"text": "15"}]}):
            ocr_file(image, ocr, [0, 0, 20, 30])
        with patch("copyapp.report.verify_case", return_value=True):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp), "ui.flow=" + str(play),
                            "ui.ocr=" + str(ocr)],
                           self.root / "with-playbook")
        self.assertTrue((self.root / "with-playbook/evidence/ui.flow/step-01-screenshot.jpg").is_file())
        report_index = json.loads((self.root / "with-playbook/report-index.json").read_text())
        self.assertTrue(report_index["evidence"]["ui.ocr"]["identity_verified"])
        bad_ocr = json.loads(ocr.read_text())
        bad_ocr["source_sha256"] = "0" * 64
        ocr.write_text(json.dumps(bad_ocr))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "OCR source"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp), "ui.flow=" + str(play),
                            "ui.ocr=" + str(ocr)], self.root / "rejected-ocr")
        image.write_bytes(b"tampered")
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "SHA-256"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp), "ui.flow=" + str(play)],
                           self.root / "rejected-playbook")

    def test_view_tree_requires_matching_identity_and_valid_hierarchy(self):
        directory = self.root / "views"
        directory.mkdir()
        (directory / "screenshot.jpg").write_bytes(b"screenshot")
        (directory / "scan.js").write_text("// probe\n")
        tree = {"type": "view_tree", "roots": [{"root_node": 0}], "nodes": [
            {"id": 0, "parent": None, "class_name": "UIWindow",
             "frame": {"x": 0, "y": 0, "width": 40, "height": 60}},
            {"id": 1, "parent": 0, "class_name": "UILabel",
             "frame": {"x": 10, "y": 10, "width": 20, "height": 20}, "text": "9"}]}
        (directory / "view-tree.json").write_text(json.dumps(tree))
        manifest = {"schema_version": 1, "kind": "uikit_view_tree", "status": "complete",
                    "bundle_id": "com.example.target", "device_id_sha256_prefix": "abc123",
                    "frontmost_before": "com.example.target",
                    "frontmost_after": "com.example.target", "node_count": 2,
                    "window_count": 1, "truncated": False}

        def save_manifest():
            manifest["evidence"] = [{"path": name, "sha256": sha256_file(directory / name)}
                                    for name in ("screenshot.jpg", "scan.js", "view-tree.json")]
            (directory / "manifest.json").write_text(json.dumps(manifest))

        save_manifest()
        self.assertEqual(_validate_view_tree(directory, "com.example.target", "abc123")["tree"]["nodes"][1]["text"], "9")
        with self.assertRaisesRegex(ValueError, "another app or device"):
            _validate_view_tree(directory, "com.example.other", "abc123")
        tree["nodes"][1]["parent"] = 3
        (directory / "view-tree.json").write_text(json.dumps(tree))
        save_manifest()
        with self.assertRaisesRegex(ValueError, "invalid node structure"):
            _validate_view_tree(directory, "com.example.target", "abc123")

    def test_runtime_probe_import_checks_app_binary_and_screenshots(self):
        probe = self.root / "probe"
        probe.mkdir()
        (probe / "before.jpg").write_bytes(b"before")
        (probe / "after.jpg").write_bytes(b"after")
        (probe / "hook.js").write_text("// test hook\n")
        record = {"status": "complete", "bundle_id": "com.example.target",
                  "device_id_sha256_prefix": "abc123", "binary_sha256": "a" * 64,
                  "frontmost_before": "com.example.target",
                  "frontmost_after": "com.example.target",
                  "screenshot_before_sha256": hashlib.sha256(b"before").hexdigest(),
                  "screenshot_after_sha256": hashlib.sha256(b"after").hexdigest()}
        (probe / "probe.json").write_text(json.dumps(record))
        (probe / "manifest.json").write_text(json.dumps({
            "evidence": [{"path": name} for name in
                         ("probe.json", "before.jpg", "after.jpg", "hook.js")],
        }))
        with patch("copyapp.report.verify_case", return_value=True):
            report = compose_report(self.case, self.findings,
                                    ["exp.tap=" + str(self.exp), "probe.tap=" + str(probe)],
                                    self.root / "report")
        self.assertTrue(report.is_file())
        self.assertTrue((self.root / "report/evidence/probe.tap/hook.js").is_file())
        record["binary_sha256"] = "b" * 64
        (probe / "probe.json").write_text(json.dumps(record))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "another device, app or binary"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp), "probe.tap=" + str(probe)],
                           self.root / "rejected")

    def test_sandbox_diff_import_preserves_snapshots_and_checks_identity(self):
        snapshots = []
        for index, size in enumerate((10, 20)):
            path = self.root / f"sandbox-{index}.json"
            path.write_text(json.dumps({"schema_version": 1,
                "device_id_sha256_prefix": "abc123", "bundle_id": "com.example.target",
                "installed_version": "1.0", "installed_build": "1", "depth_limit": 8,
                "entries": [{"relative": "Documents/data.sqlite", "kind": "f",
                             "size": size, "modified_epoch": float(index)}]}))
            snapshots.append(path)
        diff = self.root / "sandbox-diff"
        compare_sandbox(*snapshots, diff)
        with patch("copyapp.report.verify_case", return_value=True):
            report = compose_report(self.case, self.findings,
                                    ["exp.tap=" + str(self.exp), "data.diff=" + str(diff)],
                                    self.root / "report")
        self.assertTrue(report.is_file())
        self.assertTrue((self.root / "report/evidence/data.diff/before.json").is_file())
        self.assertTrue(verify_case(self.root / "report"))
        changed = json.loads((diff / "changes.json").read_text())
        changed["device_id_sha256_prefix"] = "other"
        (diff / "changes.json").write_text(json.dumps(changed))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "another device or app"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp), "data.diff=" + str(diff)],
                           self.root / "rejected")
        changed["device_id_sha256_prefix"] = "abc123"
        changed["changes"] = []
        (diff / "changes.json").write_text(json.dumps(changed))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "does not match source metadata"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp), "data.diff=" + str(diff)],
                           self.root / "rejected-semantic")

    def test_rejects_unrelated_rea_binary(self):
        rea = self.root / "rea"
        rea.mkdir()
        (rea / "summary.json").write_text(json.dumps({
            "binary_sha256": "b" * 64, "evidence_id": "ev_1",
            "provider": {"id": "ghidra"}, "pseudocode_is_original_source": False,
        }))
        (rea / "evidence.json").write_text(json.dumps({
            "subject": {"digest": {"sha256": "b" * 64}},
            "evidence_id": "ev_1", "provider": {"id": "ghidra"},
        }))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "binary does not match"):
            compose_report(self.case, self.findings,
                           ["rea.other=" + str(rea), "exp.tap=" + str(self.exp)],
                           self.root / "report")

    def test_rejects_rea_pseudocode_not_in_evidence(self):
        rea = self.root / "rea"
        rea.mkdir()
        provider = {"id": "hopper", "version": "test"}
        procedure = {"name": "Example::tap", "address": "0x1000"}
        (rea / "summary.json").write_text(json.dumps({
            "binary_sha256": "a" * 64, "evidence_id": "ev_1",
            "provider": provider, "analysis_profile_digest": "profile",
            "requested_procedure": "0x1000", "resolved_procedure": procedure,
            "pseudocode_is_original_source": False,
        }))
        (rea / "evidence.json").write_text(json.dumps({
            "subject": {"digest": {"sha256": "a" * 64}},
            "evidence_id": "ev_1", "provider": provider,
            "analysis_profile": {"digest": "profile"},
            "parameters": {"procedure": "0x1000"},
            "normalized_result": {"procedure": procedure, "pseudocode": "return 1;"},
        }))
        (rea / "pseudocode.txt").write_text("return 0;")
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "identity mismatch"):
            compose_report(self.case, self.findings,
                           ["rea.tap=" + str(rea), "exp.tap=" + str(self.exp)],
                           self.root / "report")

    def test_rejects_uncited_assertion(self):
        findings = json.loads(self.findings.read_text())
        findings["sections"][0]["findings"][0]["evidence"] = []
        self.findings.write_text(json.dumps(findings))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "requires evidence"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp)], self.root / "report")

    def test_rejects_bundle_mismatch_in_static_index(self):
        static = self.case / "acquired/static/ipa-index.json"
        record = json.loads(static.read_text())
        record["bundle_id"] = "com.example.other"
        static.write_text(json.dumps(record))
        with patch("copyapp.report.verify_case", return_value=True), self.assertRaisesRegex(
                ValueError, "another bundle"):
            compose_report(self.case, self.findings,
                           ["exp.tap=" + str(self.exp)], self.root / "report")

    def test_uses_decrypted_index_and_png_screenshot(self):
        (self.case / "decrypted/static").mkdir(parents=True)
        (self.case / "decrypted/static/ipa-index.json").write_text(json.dumps({
            "bundle_id": "com.example.target", "executable": "Target",
            "file_count": 2, "binaries": [{"path": "Payload/Target.app/Target",
                                           "sha256": "b" * 64, "encryption_status": "not_encrypted"}],
        }))
        (self.case / "survey/screenshot.png").write_bytes(b"png")
        findings = json.loads(self.findings.read_text())
        findings["sections"][0]["findings"][0]["evidence"].append("case.decrypted_static")
        findings["sections"][0]["findings"][0]["evidence"].append("case.screenshot")
        self.findings.write_text(json.dumps(findings))
        with patch("copyapp.report.verify_case", return_value=True):
            report = compose_report(self.case, self.findings,
                                    ["exp.tap=" + str(self.exp)], self.root / "report")
        self.assertIn("解密后分析 IPA", report.read_text())
        self.assertTrue((self.root / "report/evidence/case.screenshot/screenshot.png").is_file())


if __name__ == "__main__":
    unittest.main()
