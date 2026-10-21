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
                with self.assertRaises(UnknownCompletion):
                    client.call("health")
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
        from test_macos import make_server
        from copyapp.macos.setup import build_collector
        from copyapp.macos.deploy import prepare_collector
        from copyapp.macos.environment import register_environment
        from copyapp.macos.observation import observe_app
        from copyapp.macos.acquire import acquire_app
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = build_collector(root / "build")
            deployment = prepare_collector(root / "build", root / "deployment")
            self.assertTrue(verify_case(deployment))
            vm = root / "data/ChatComputer.vm"
            shared = vm / "Shared"
            shared.mkdir(parents=True)
            spec = {"id": str(uuid4()), "stage": "ready", "displayWidth": 32,
                    "displayHeight": 24, "cpuCount": 2, "memoryBytes": 2 << 30}
            (vm / "spec.json").write_bytes(canonical(spec))
            (vm / "MachineIdentifier.bin").write_bytes(b"simulated-machine-id")
            (vm / "HardwareModel.bin").write_bytes(b"simulated-hardware-model")
            fake = root / "fake"
            fake.mkdir()
            source, _ = make_server(fake)
            command = root / "ChatComputer.app/Contents/MacOS/ChatComputer"
            command.parent.mkdir(parents=True)
            shutil.copyfile(source, command)
            command.chmod(0o755)
            (command.parent.parent / "Info.plist").write_bytes(plistlib.dumps({
                "CFBundleIdentifier": "app.chatcomputer.ChatComputer",
                "CFBundleVersion": "1", "CFBundleShortVersionString": "0.9.11"}))
            process = subprocess.Popen([str(app / "Contents/MacOS/CopyAppMacCollector"),
                                        "--shared-root", str(shared)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                environment = register_environment(vm, root / "build", root / "environment",
                                                   str(command), timeout=5)
                self.assertTrue(verify_case(environment))
                case = observe_app(environment, str(app), "dev.copyapp.MacCollector", root / "observation")
                self.assertTrue(verify_case(case))
                acquisition = acquire_app(environment, str(app), "dev.copyapp.MacCollector",
                                          root / "acquisition", timeout=5)
                self.assertTrue(verify_case(acquisition))
                from macos_fakes import Desktop
                from copyapp.macos.playbook import run_playbook
                from copyapp.macos.chatcomputer import UnknownCompletion
                from unittest.mock import patch
                registered = json.loads((environment / "environment.json").read_text())
                source_index = json.loads((acquisition / "package/app-index.json").read_text())
                target = json.loads((acquisition / "acquisition.json").read_text())["guest_app_path"]
                script = {"schema_version": 2, "platform": "macos", "bundle_id": "dev.copyapp.MacCollector",
                          "app_path": target, "scenario_id": "edit-save-quit", "steps": [
                              {"action": "launch"}, {"action": "type", "text": "hello"},
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
                self.assertEqual(json.loads((replay / "manifest.json").read_text())["behavior_assertions"], 3)
                from copyapp.macos.report import report
                from copyapp.macos.rebuild import rebuild_plan
                flow_id = script["scenario_id"]
                review = {"schema_version": 2, "platform": "macos", "scope": "behavior_analysis",
                          "reviewer": "simulated-contract-test", "summary": "Simulated edit/save/quit evidence only.",
                          "findings": [{"id": "saved-text", "statement": "The asserted output contains hello.",
                                        "certainty": "observed", "evidence": [
                                            {"flow_id": flow_id, "path": "steps/05/output.bin"}]}],
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
                plan = rebuild_plan(reviewed, "dev.copyapp.Clone", "/Applications/Independent.app",
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
                input_path = replay / "steps/02/input.json"
                changed_input = json.loads(input_path.read_text())
                changed_input["arguments"]["text"] = "different input"
                input_path.write_bytes(canonical(changed_input))
                replay_manifest = json.loads((replay / "manifest.json").read_text())
                for item in replay_manifest["evidence"]:
                    if item["path"] == "steps/02/input.json":
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
