import hashlib
import json
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from uuid import uuid4

from copyapp.macos.bridge import Collector, atomic_json
from copyapp.macos.case import canonical
from copyapp.macos.chatcomputer import UnknownCompletion
from copyapp.verify import verify_case


def answer(client, *, change=None):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        files = list(client.requests.glob("*.json"))
        if files:
            request = json.loads(files[0].read_text())
            response = {"protocol_version": 2, "session_id": client.session,
                        "request_id": request["request_id"],
                        "request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
                        "collector_sha256": client.hash, "collector_instance": str(uuid4()),
                        "status": "complete", "result": {"ready": True}}
            if change:
                response.update(change)
            atomic_json(client.responses / files[0].name, response)
            return
        time.sleep(0.01)
    raise AssertionError("no collector request was written")


class BridgeTests(unittest.TestCase):
    def test_new_epoch_keeps_lock_and_rejects_old_reply(self):
        with tempfile.TemporaryDirectory() as folder:
            with Collector(Path(folder), "a" * 64, timeout=2) as client:
                worker = threading.Thread(target=answer, args=(client,))
                worker.start(); client.call("health"); worker.join()
                old_session, old_responses = client.session, client.responses
                old_files = list(old_responses.glob("*.json"))
                client.new_session()
                self.assertNotEqual(client.session, old_session)
                self.assertIsNone(client.instance)
                self.assertTrue(all(path.exists() for path in old_files))
                with self.assertRaises(BlockingIOError): Collector(Path(folder), "a" * 64)
                worker = threading.Thread(target=answer, args=(client,), kwargs={"change": {"session_id": old_session}})
                worker.start()
                with self.assertRaises(ValueError): client.call("health")
                worker.join()
                with self.assertRaises(RuntimeError): client.new_session()

    def test_bound_response_and_exclusive_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with Collector(root, "a" * 64, timeout=2) as client:
                with self.assertRaises(BlockingIOError):
                    Collector(root, "a" * 64)
                worker = threading.Thread(target=answer, args=(client,))
                worker.start()
                result = client.call("health")
                worker.join()
                self.assertTrue(result["response"]["result"]["ready"])
            with Collector(root, "a" * 64) as second:
                self.assertNotEqual(client.session, second.session)

    def test_rejects_stale_session_modified_request_and_wrong_build(self):
        for change in ({"session_id": str(uuid4())}, {"request_sha256": "b" * 64},
                       {"collector_sha256": "b" * 64}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                with Collector(Path(folder), "a" * 64, timeout=2) as client:
                    worker = threading.Thread(target=answer, args=(client,), kwargs={"change": change})
                    worker.start()
                    with self.assertRaises(ValueError):
                        client.call("health")
                    worker.join()
                    self.assertTrue(client.closed)

    def test_timeout_preserves_request_and_does_not_reissue(self):
        with tempfile.TemporaryDirectory() as folder:
            with Collector(Path(folder), "a" * 64, timeout=0.1) as client:
                with self.assertRaises(UnknownCompletion) as caught:
                    client.call("health")
                self.assertEqual(caught.exception.collector_evidence["request"]["method"], "health")
                self.assertIsNone(caught.exception.collector_evidence["response"])
                self.assertEqual(len(list(client.requests.glob("*.json"))), 1)
                with self.assertRaises(RuntimeError):
                    client.call("health")
                self.assertEqual(len(list(client.requests.glob("*.json"))), 1)

    def test_rejects_linked_outbox_reply(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outside = root / "other"
            outside.mkdir()
            (root / "outbox").symlink_to(outside, target_is_directory=True)
            with Collector(root, "a" * 64, timeout=2) as client:
                worker = threading.Thread(target=answer, args=(client,))
                worker.start()
                with self.assertRaises(ValueError):
                    client.call("health")
                worker.join()


@unittest.skipUnless(sys.platform == "darwin" and platform.machine() == "arm64",
                     "native collector build and local filesystem bridge require Apple Silicon macOS")
class NativeCollectorTests(unittest.TestCase):
    def test_simulated_environment_registration_and_bound_identity_observation(self):
        # A local helper plus a simulated MCP/VM configuration exercises the
        # provenance contracts. This does not count as live virtual-Mac evidence.
        from macos_snapshot_checks import make_snapshot_server, exercise_snapshot_protocol
        from copyapp.macos.setup import build_collector
        from copyapp.macos.deploy import prepare_collector
        from copyapp.macos.environment import register_environment
        from copyapp.macos.observation import observe_app
        from copyapp.macos.acquire import acquire_app
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            app = build_collector(root / "build")
            deployment = prepare_collector(root / "build", root / "deployment")
            self.assertTrue(verify_case(deployment))
            # A refreshed file hash cannot silently change a no-prompt launcher
            # into an Accessibility-prompting or arbitrary command launcher.
            launcher = deployment / "payload/Start Collector.command"
            old_launcher, old_deployment = launcher.read_bytes(), (deployment / "manifest.json").read_bytes()
            launcher.write_bytes(old_launcher.replace(b'--shared-root "/Volumes/My Shared Files"',
                                                      b'--shared-root "/Volumes/My Shared Files" --request-accessibility'))
            updated = json.loads(old_deployment)
            for row in updated["evidence"]:
                if row["path"] == "payload/Start Collector.command": row["sha256"] = hashlib.sha256(launcher.read_bytes()).hexdigest()
            (deployment / "manifest.json").write_bytes(canonical(updated))
            self.assertFalse(verify_case(deployment))
            launcher.write_bytes(old_launcher)
            (deployment / "manifest.json").write_bytes(old_deployment)
            vm = root / "data/ChatComputer.vm"
            shared = vm / "Shared"
            shared.mkdir(parents=True)
            (shared / "inbox").mkdir()
            (shared / "outbox").mkdir()
            spec = {"id": str(uuid4()), "stage": "ready", "displayWidth": 32,
                    "displayHeight": 24, "cpuCount": 2, "memoryBytes": 2 << 30}
            (vm / "spec.json").write_bytes(canonical(spec))
            (vm / "MachineIdentifier.bin").write_bytes(b"simulated-machine-id")
            (vm / "HardwareModel.bin").write_bytes(b"simulated-hardware-model")
            fake = root / "fake"
            fake.mkdir()
            source, _ = make_snapshot_server(fake, vm)
            command = root / "ChatComputer.app/Contents/MacOS/ChatComputer"
            command.parent.mkdir(parents=True)
            shutil.copyfile(source, command)
            command.chmod(0o755)
            (command.parent.parent / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "app.chatcomputer.ChatComputer",
                "CFBundleVersion": "1", "CFBundleShortVersionString": "0.9.11"}))
            process = subprocess.Popen([str(app / "Contents/MacOS/CopyAppMacCollector"),
                                        "--shared-root", str(shared), "--install-root", str(root / "guest-apps")],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                from copyapp.macos.probe import probe_collector
                probe = probe_collector(vm, root / "build", root / "collector-probe", timeout=5)
                self.assertTrue(verify_case(probe))
                probe_path = probe / "probe.json"
                original_probe, original_probe_manifest = probe_path.read_bytes(), (probe / "manifest.json").read_bytes()
                changed = json.loads(original_probe); changed["complete_environment_acceptance"] = True
                probe_path.write_bytes(canonical(changed))
                updated = json.loads(original_probe_manifest)
                for row in updated["evidence"]:
                    if row["path"] == "probe.json": row["sha256"] = hashlib.sha256(probe_path.read_bytes()).hexdigest()
                (probe / "manifest.json").write_bytes(canonical(updated))
                self.assertFalse(verify_case(probe))
                probe_path.write_bytes(original_probe)
                (probe / "manifest.json").write_bytes(original_probe_manifest)
                environment = register_environment(vm, root / "build", root / "environment",
                                                   str(command), timeout=5)
                self.assertTrue(verify_case(environment))
                exercise_snapshot_protocol(self, root, environment, vm)
                case = observe_app(environment, str(app), "dev.copyapp.MacCollector", root / "observation")
                self.assertTrue(verify_case(case))
                acquisition = acquire_app(environment, str(app), "dev.copyapp.MacCollector",
                                          root / "acquisition", timeout=5)
                self.assertTrue(verify_case(acquisition))
                from macos_data_checks import exercise_data_capture
                data_schemas = exercise_data_capture(self, root, acquisition)
                from macos_fakes import Desktop
                from copyapp.macos.playbook import run_playbook
                from copyapp.macos.chatcomputer import UnknownCompletion
                from unittest.mock import patch
                registered = json.loads((environment / "environment.json").read_text())
                source_index = json.loads((acquisition / "package/app-index.json").read_text())
                target = json.loads((acquisition / "acquisition.json").read_text())["guest_app_path"]
                script = {"schema_version": 2, "platform": "macos", "bundle_id": "dev.copyapp.MacCollector",
                          "app_path": target, "scenario_id": "edit-save-quit", "steps": [
                              {"action": "launch"},
                              {"action": "expect_text", "selector": {"identifier": "editor"}, "text": ""},
                              {"action": "type", "text": "hello"},
                              {"action": "expect_text", "selector": {"identifier": "editor"}, "text": "hello"},
                              {"action": "key", "combo": "cmd+s"},
                              {"action": "expect_file", "path": "output.json", "json_equals": {"text": "hello"}},
                              {"action": "quit"}, {"action": "expect_stopped"}]}
                script_path = root / "flow.json"
                script_path.write_bytes(canonical(script))
                simulated = root / "simulated-share"
                simulated.mkdir()
                desktop = Desktop(simulated, registered, source_index, target)
                with patch("copyapp.macos.playbook.environment_session", desktop.session_context):
                    replay = run_playbook(acquisition, script_path, root / "replay")
                self.assertTrue(verify_case(replay))
                self.assertEqual(json.loads((replay / "manifest.json").read_text())["behavior_assertions"], 4)
                from copyapp.macos.report import report
                from copyapp.macos.rebuild import rebuild_plan
                flow_id = script["scenario_id"]
                review = {"schema_version": 2, "platform": "macos", "scope": "behavior_analysis",
                          "reviewer": "simulated-contract-test", "summary": "Simulated edit/save/quit evidence only.",
                          "findings": [{"id": "saved-text", "statement": "The asserted output contains hello.",
                                        "certainty": "observed", "evidence": [
                                            {"flow_id": flow_id, "path": "steps/06/output.bin"}]}],
                          "flows": [{"id": flow_id, "source_script_sha256": hashlib.sha256((replay / "playbook.json").read_bytes()).hexdigest(),
                                     "expected_behavior": "Edit text, save JSON and quit.", "findings": ["saved-text"]}],
                          "capabilities": [
                              {"id": "editing", "title": "Edit and save", "flow_ids": [flow_id],
                               "disposition": "available", "reason": "Selected simulated behavior assertions exist."},
                              {"id": "printing", "title": "Printing", "flow_ids": [],
                               "disposition": "deferred", "reason": "No selected evidence."}],
                          "inventory_note": "Two reviewed known capabilities; the inventory is not whole-App coverage.",
                          "unknowns": ["All actual guest UI behavior remains unverified by this simulated test."]}
                review_path = root / "review.json"
                review_path.write_bytes(canonical(review))
                reviewed = report({flow_id: replay}, review_path, root / "report")
                self.assertTrue(verify_case(reviewed))
                from macos_data_checks import exercise_schema_report
                exercise_schema_report(self, root, {flow_id: replay}, review, data_schemas)
                from macos_discovery_checks import exercise_discovery
                exercise_discovery(self, root, acquisition, registered, source_index, target, replay, review)
                plan = rebuild_plan(reviewed, "dev.copyapp.Clone", str(root / "guest-apps/Independent.app"),
                                    root / "clone-project", ["editing"], root / "plan")
                self.assertTrue(verify_case(plan))
                frozen = json.loads((plan / "rebuild-plan.json").read_text())
                self.assertEqual(frozen["coverage"]["known_capabilities"], 2)
                self.assertEqual(frozen["coverage"]["target_percent"], 50)
                self.assertIsNone(frozen["coverage"]["verified_known_capabilities"])
                self.assertEqual(frozen["acceptance"], "not_run")
                clone_script = json.loads((plan / "scripts" / (flow_id + ".json")).read_text())
                self.assertEqual(clone_script["steps"], script["steps"])
                self.assertEqual(clone_script["bundle_id"], "dev.copyapp.Clone")
                with self.assertRaises(ValueError):
                    rebuild_plan(reviewed, script["bundle_id"], "/Applications/Independent.app",
                                 root / "clone-project", ["editing"], root / "same-bundle")
                with self.assertRaises(ValueError):
                    rebuild_plan(reviewed, "dev.copyapp.Clone", target,
                                 root / "clone-project", ["editing"], root / "same-path")
                with self.assertRaises(ValueError):
                    rebuild_plan(reviewed, "dev.copyapp.Clone", "/Applications/Independent.app",
                                 root / "clone-project", ["editing"], root / "outside-install-root")
                with self.assertRaises(ValueError):
                    rebuild_plan(reviewed, "dev.copyapp.Clone", str(root / "guest-apps/Independent.app"),
                                 root / "clone-project", ["printing"], root / "blocked-plan")
                # Semantic gates must reject a rehashed artifact too, including
                # fabricated coverage or modified generated replay instructions.
                def rejects_rehashed(case_root, relative, change):
                    artifact = case_root / relative
                    old_bytes = artifact.read_bytes()
                    old_manifest = (case_root / "manifest.json").read_bytes()
                    value = json.loads(old_bytes)
                    change(value)
                    artifact.write_bytes(canonical(value))
                    updated = json.loads(old_manifest)
                    for record in updated["evidence"]:
                        if record["path"] == relative:
                            record["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
                    (case_root / "manifest.json").write_bytes(canonical(updated))
                    try:
                        self.assertFalse(verify_case(case_root), relative)
                    finally:
                        artifact.write_bytes(old_bytes)
                        (case_root / "manifest.json").write_bytes(old_manifest)

                rejects_rehashed(plan, "rebuild-plan.json",
                                 lambda value: value["coverage"].update(verified_known_capabilities=2))
                rejects_rehashed(plan, "scripts/" + flow_id + ".json",
                                 lambda value: value["steps"][1].update(text="different behavior"))
                rejects_rehashed(reviewed, "feature-spec.json",
                                 lambda value: value.update(function_analysis="complete"))
                rejects_rehashed(reviewed, "citations.json",
                                 lambda value: value[0].update(sha256="0" * 64))
                from copyapp.macos.build import build_app, recipe_for
                project = root / "clone-project"
                project.mkdir()
                (project / "Main.swift").write_text('import AppKit\n@main struct Fixture { static func main() { print("independent build fixture") } }\n')
                (project / "Info.plist").write_bytes(plistlib.dumps({
                    "CFBundleIdentifier": "dev.copyapp.Clone", "CFBundlePackageType": "APPL",
                    "CFBundleExecutable": "Independent", "CFBundleName": "Independent",
                    "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1"}))
                (project / ".git").mkdir()
                (project / ".git/config").write_text("ignored repository metadata")
                native_build = build_app(plan, root / "native-build", recipe_for(
                    swift_sources=["Main.swift"], info_plist="Info.plist"))
                self.assertTrue(verify_case(native_build))
                self.assertFalse((native_build / "source/.git").exists())
                build_facts = json.loads((native_build / "build.json").read_text())
                self.assertIs(build_facts["installed"], False)
                self.assertIs(build_facts["behavior_checked"], False)
                self.assertEqual(build_facts["app"]["bundle_id"], "dev.copyapp.Clone")
                self.assertEqual((native_build / "source/Main.swift").read_bytes(), (project / "Main.swift").read_bytes())
                rejects_rehashed(native_build, "build.json", lambda value: value.update(installed=True))
                rejects_rehashed(native_build, "build-log.json", lambda value: value[-1].update(returncode=1))
                rejects_rehashed(native_build, "recipe.json", lambda value: value.update(swift_sources=["Other.swift"]))
                from copyapp.macos.install import install_app
                installed = install_app(native_build, root / "installed", timeout=10)
                self.assertTrue(verify_case(installed))
                receipt = json.loads((installed / "install.json").read_text())
                self.assertIs(receipt["launch_verified"], False)
                self.assertIs(receipt["behavior_checked"], False)
                installed_binary = root / "guest-apps/Independent.app/Contents/MacOS/Independent"
                installed_hash = hashlib.sha256(installed_binary.read_bytes()).hexdigest()
                self.assertEqual(installed_hash, build_facts["app"]["binary_sha256"])
                rejects_rehashed(installed, "install.json", lambda value: value.update(launch_verified=True))
                rejects_rehashed(installed, "install-request.json", lambda value: value.update(app_path="/Applications/Other.app"))
                # An explicit second request is refused without modifying the
                # existing App. Neither CLI nor helper treats it as a reinstall.
                with self.assertRaises(UnknownCompletion):
                    install_app(native_build, root / "duplicate-install", timeout=10)
                self.assertEqual(hashlib.sha256(installed_binary.read_bytes()).hexdigest(), installed_hash)
                self.assertFalse(verify_case(root / "duplicate-install"))
                rejected = json.loads((root / "duplicate-install/failed-collector-request.json").read_text())
                self.assertEqual(rejected["request"]["method"], "install_app")
                self.assertIn("Refusing to replace", rejected["response"]["error"])
                self.assertTrue(verify_case(installed))
                from macos_fakes import UI, WINDOW
                from copyapp.macos.checks import check_plan, rebuild_check
                from copyapp.macos.visual import visual_review
                from copyapp.macos.delivery import delivery
                conditions = {"schema_version": 2, "platform": "macos", "reviewer": "simulated-contract-test",
                              "expected_ui": UI, "network_expectation": "This simulated fixture uses no network.",
                              "flows": [{"id": flow_id, "starting_state": "A simulated blank editor is focused.",
                                         "window_frame": WINDOW, "input_data": "hello",
                                         "reset_policy": "The simulated fixture opens a fresh blank document after quit."}],
                              "masks": []}
                conditions_path = root / "conditions.json"
                conditions_path.write_bytes(canonical(conditions))
                paired_plan = check_plan(installed, conditions_path, root / "check-plan", rounds=3)
                self.assertTrue(verify_case(paired_plan))
                bad_conditions = json.loads(canonical(conditions))
                bad_conditions["masks"] = [{"flow_id": flow_id, "capture": "steps/01/after", "rect": [0, 0, 16, 12],
                                            "reason": "An invalid full-screen mask."}]
                conditions_path.write_bytes(canonical(bad_conditions))
                with self.assertRaises(ValueError):
                    check_plan(installed, conditions_path, root / "full-mask-plan", rounds=1)
                replay_share = root / "paired-simulated-share"
                replay_share.mkdir()
                all_desktops = []
                bad_ui = False

                def simulated_session(environment_path, *_):
                    parent = environment_path.parent
                    acquired_package = json.loads((parent / "package/app-index.json").read_text())
                    acquired_target = json.loads((parent / "acquisition.json").read_text())["guest_app_path"]
                    desktop = Desktop(replay_share, registered, acquired_package, acquired_target)
                    all_desktops.append(desktop)
                    if bad_ui:
                        original_rpc = desktop.rpc

                        def changed_health(method, params=None):
                            result = original_rpc(method, params)
                            if method == "health":
                                result["response"]["result"]["ui_environment"]["appearance"] = "dark"
                            return result

                        desktop.rpc = changed_health
                    return desktop.session_context()

                with patch("copyapp.macos.playbook.environment_session", simulated_session):
                    paired = rebuild_check(paired_plan, root / "paired-check", timeout=10)
                self.assertTrue(verify_case(paired))
                comparison = json.loads((paired / "comparison.json").read_text())
                self.assertEqual(comparison["selected_comparisons"], 3)
                self.assertEqual(comparison["behavior_passed"], 3)
                self.assertEqual(len(comparison["screenshot_pairs"]), 24)
                self.assertEqual(comparison["visual_review"], "not_reviewed")
                self.assertTrue((paired / "VISUAL_REVIEW.md").is_file())
                rejects_rehashed(paired, "comparison.json", lambda value: value.update(behavior_passed=0))
                rejects_rehashed(paired, "comparison.json", lambda value: value.update(selected_comparisons=True))
                rejects_rehashed(paired, "comparison.json",
                                 lambda value: value["screenshot_pairs"][0]["metrics"].update(mean_absolute_error=0.5))
                judgments_path = root / "visual-judgments.json"
                judgments = json.loads((paired / "visual-judgments-template.json").read_text())
                judgments["reviewer"] = "simulated-contract-test"
                judgments_path.write_bytes(canonical(judgments))
                with self.assertRaises(ValueError):
                    visual_review(paired, judgments_path, root / "unreviewed-visual")
                for judgment in judgments["judgments"]:
                    judgment.update(verdict="equivalent", notes="Both simulated blue frames are present; no live guest claim.", reviewed_full_screens=True)
                judgments["judgments"][0].update(verdict="minor_difference", notes="Simulated minor judgment retained despite zero pixel error.")
                for state in judgments["starting_states"]:
                    state.update(judgment="equivalent", notes="Both simulated initial text assertions and window frames match.")
                judgments_path.write_bytes(canonical(judgments))
                reviewed_visual = visual_review(paired, judgments_path, root / "visual-review")
                self.assertTrue(verify_case(reviewed_visual))
                self.assertEqual(json.loads((reviewed_visual / "visual-review.json").read_text())["minor_differences"], 1)
                rejects_rehashed(reviewed_visual, "visual-review.json", lambda value: value.update(minor_differences=0))
                coverage = {"schema_version": 2, "platform": "macos", "reviewer": "simulated-contract-test",
                            "capabilities": [
                                {"id": "editing", "decision": "verified", "evidence_flow_ids": [flow_id],
                                 "reason": "Selected simulated behavior and review contract gates passed."},
                                {"id": "printing", "decision": "deferred", "evidence_flow_ids": [],
                                 "reason": "No selected printing evidence."}]}
                coverage_path = root / "coverage-review.json"
                coverage_path.write_bytes(canonical(coverage))
                delivered = delivery(reviewed_visual, coverage_path, root / "delivery")
                self.assertTrue(verify_case(delivered))
                delivered_data = json.loads((delivered / "delivery.json").read_text())
                self.assertEqual(delivered_data["coverage"]["verified_known_percent"], 50)
                self.assertEqual(delivered_data["coverage"]["selected_flow_pass_rate"], 100)
                self.assertFalse(delivered_data["physical_mac_verified"])
                self.assertFalse(delivered_data["whole_app_parity"])
                self.assertEqual(delivered_data["visual_review"]["minor_differences"], 1)
                rejects_rehashed(delivered, "delivery.json", lambda value: value["coverage"].update(verified_known_capabilities=2))
                for variant in ("major", "unknown-start"):
                    adverse = json.loads(canonical(judgments))
                    if variant == "major":
                        adverse["judgments"][0].update(verdict="major_difference", notes="Simulated major difference for rejection coverage.")
                    else:
                        adverse["starting_states"][0].update(judgment="unknown", notes="Simulated starting-state uncertainty.")
                    judgments_path.write_bytes(canonical(adverse))
                    adverse_visual = visual_review(paired, judgments_path, root / (variant + "-visual"))
                    self.assertTrue(verify_case(adverse_visual))
                    with self.assertRaises(ValueError):
                        delivery(adverse_visual, coverage_path, root / (variant + "-delivery"))
                bad_coverage = json.loads(canonical(coverage))
                bad_coverage["capabilities"][0].update(decision="deferred", evidence_flow_ids=[])
                coverage_path.write_bytes(canonical(bad_coverage))
                with self.assertRaises(ValueError):
                    delivery(reviewed_visual, coverage_path, root / "missing-target-delivery")
                # A measured UI mismatch is rejected before acquiring the input
                # lease, and the failed first side is not replayed automatically.
                before_desktops = len(all_desktops)
                bad_ui = True
                with patch("copyapp.macos.playbook.environment_session", simulated_session):
                    with self.assertRaises(ValueError):
                        rebuild_check(paired_plan, root / "wrong-ui-check", timeout=10)
                self.assertEqual(len(all_desktops), before_desktops + 1)
                self.assertEqual(all_desktops[-1].calls, [])
                self.assertFalse(verify_case(root / "wrong-ui-check"))
                from macos_fakes import xcode_fixture
                xcode_fixture(project)
                xcode_built = build_app(plan, root / "xcode-build", recipe_for(
                    xcode_project="Independent.xcodeproj", scheme="Independent"), timeout=180)
                self.assertTrue(verify_case(xcode_built))
                (project / "Main.swift").write_text("invalid Swift source for the failed-build evidence test\n")
                # Later source edits cannot silently alter the saved build.
                self.assertTrue(verify_case(native_build))
                self.assertTrue(verify_case(delivered))
                coverage_path.write_bytes(canonical(coverage))
                with self.assertRaisesRegex(ValueError, "current project differs"):
                    delivery(reviewed_visual, coverage_path, root / "stale-source-delivery")
                with self.assertRaises(RuntimeError):
                    build_app(plan, root / "failed-native-build", recipe_for(
                        swift_sources=["Main.swift"], info_plist="Info.plist"))
                self.assertFalse(verify_case(root / "failed-native-build"))
                self.assertTrue((root / "failed-native-build/build-log.json").is_file())
                self.assertNotEqual(json.loads((root / "failed-native-build/build-log.json").read_text())[-1]["returncode"], 0)
                source_snapshot = native_build / "source/Main.swift"
                source_snapshot.write_text("changed captured source\n")
                self.assertFalse(verify_case(native_build))
                bad_review = json.loads(canonical(review))
                bad_review["flows"][0]["source_script_sha256"] = "0" * 64
                review_path.write_bytes(canonical(bad_review))
                with self.assertRaises(ValueError):
                    report({flow_id: replay}, review_path, root / "bad-report")
                bad_review = json.loads(canonical(review))
                bad_review["findings"][0]["evidence"][0]["path"] = "../playbook.json"
                review_path.write_bytes(canonical(bad_review))
                with self.assertRaises(ValueError):
                    report({flow_id: replay}, review_path, root / "escaping-report")
                self.assertTrue(verify_case(plan))
                # Changing the executed command and refreshing its file hash
                # cannot bypass the original saved playbook's input semantics.
                input_path = replay / "steps/03/input.json"
                changed_input = json.loads(input_path.read_text())
                changed_input["arguments"]["text"] = "different input"
                input_path.write_bytes(canonical(changed_input))
                replay_manifest = json.loads((replay / "manifest.json").read_text())
                for item in replay_manifest["evidence"]:
                    if item["path"] == "steps/03/input.json":
                        item["sha256"] = hashlib.sha256(input_path.read_bytes()).hexdigest()
                (replay / "manifest.json").write_bytes(canonical(replay_manifest))
                self.assertFalse(verify_case(replay))
                lost_share = root / "lost-share"
                lost_share.mkdir()
                lost = Desktop(lost_share, registered, source_index, target, lose_type_reply=True)
                with patch("copyapp.macos.playbook.environment_session", lost.session_context):
                    with self.assertRaises(UnknownCompletion):
                        run_playbook(acquisition, script_path, root / "interrupted")
                self.assertEqual([method for method, _ in lost.calls].count("type"), 1)
                failure = json.loads((root / "interrupted/failure.json").read_text())
                self.assertEqual(failure["error"], "UnknownCompletion")
                self.assertFalse(verify_case(root / "interrupted"))
                export = json.loads((acquisition / "export.json").read_text())
                self.assertEqual(export["response"]["result"]["source_app"]["binary_sha256"],
                                 json.loads((root / "build/collector-build.json").read_text())["executable_sha256"])
                acquired_binary = acquisition / "package/app/CopyAppMacCollector.app/Contents/MacOS/CopyAppMacCollector"
                acquired_binary.write_bytes(b"modified after acquisition")
                self.assertFalse(verify_case(acquisition))
                # Rehashing one changed artifact must not bypass the semantic
                # link to the environment's registered guest identity.
                path = case / "identity.json"
                changed = json.loads(path.read_text())
                changed["response"]["guest_machine_id"] = str(uuid4())
                path.write_bytes(canonical(changed))
                manifest = json.loads((case / "manifest.json").read_text())
                for item in manifest["evidence"]:
                    if item["path"] == "identity.json":
                        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                (case / "manifest.json").write_bytes(canonical(manifest))
                self.assertFalse(verify_case(case))
            finally:
                process.terminate()
                process.communicate(timeout=5)

    def test_build_artifact_real_swift_protocol_and_tamper_rejection(self):
        # This is explicitly a local filesystem probe, not guest/VM acceptance.
        from copyapp.macos.setup import build_collector
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = build_collector(root / "build")
            self.assertTrue(verify_case(root / "build"))
            binary = app / "Contents/MacOS/CopyAppMacCollector"
            metadata = json.loads((root / "build/collector-build.json").read_text())
            shared = root / "shared"
            shared.mkdir()
            process = subprocess.Popen([str(binary), "--shared-root", str(shared)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                with Collector(shared, metadata["executable_sha256"], timeout=10) as client:
                    health = client.call("health")["response"]["result"]
                    self.assertIn("app_identity", health["capabilities"])
                    identity = client.call("app_identity", {
                        "app_path": str(app), "bundle_id": "dev.copyapp.MacCollector",
                        "binary_sha256": metadata["executable_sha256"]})["response"]["result"]
                    self.assertEqual(identity["binary_sha256"], metadata["executable_sha256"])
            finally:
                process.terminate()
                process.communicate(timeout=5)
            (app / "Contents/Info.plist").write_bytes(b"tampered metadata")
            self.assertFalse(verify_case(root / "build"))


if __name__ == "__main__":
    unittest.main()
