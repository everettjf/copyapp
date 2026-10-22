"""Discovery contract exercised with the existing simulated-desktop fixture."""

import hashlib
import json
from unittest.mock import patch

from copyapp.macos.case import canonical, digest
from copyapp.macos.discovery import discover_check
from copyapp.macos.playbook import run_playbook
from copyapp.macos.report import report
from copyapp.verify import verify_case
from macos_fakes import Desktop


def exercise_discovery(test, root, acquisition, registered, source, target, replay, behavior_review):
    # These three flows are simulated contract evidence, not representative
    # acceptance for either of the two required live sample applications.
    script = json.loads((replay / "playbook.json").read_text())
    flows = {script["scenario_id"]: replay}
    variants = {
        "inspect-empty": [script["steps"][0], script["steps"][1], *script["steps"][-2:]],
        "edit-discard": [*script["steps"][:4], *script["steps"][-2:]],
        "renamed-duplicate": script["steps"],
    }
    for flow_id, steps in variants.items():
        variant = {**script, "scenario_id": flow_id, "steps": steps}
        path = root / (flow_id + ".json")
        path.write_bytes(canonical(variant))
        shared = root / (flow_id + "-share")
        shared.mkdir()
        desktop = Desktop(shared, registered, source, target)
        with patch("copyapp.macos.playbook.environment_session", desktop.session_context):
            value = run_playbook(acquisition, path, root / (flow_id + "-replay"))
        test.assertTrue(verify_case(value))
        if flow_id != "renamed-duplicate": flows[flow_id] = value
    flow_ids = sorted(flows)
    review = {"schema_version": 2, "platform": "macos", "scope": "representative_flow_discovery",
              "reviewer": "simulated-contract-test", "selection_note": "Contract-only selection of three distinct scripts.",
              "flows": [{"id": key, "source_script_sha256": digest(value / "playbook.json"),
                         "purpose": key, "selection_reason": "Bounded simulated assertion coverage."}
                        for key, value in sorted(flows.items())],
              "capabilities": [{"id": key, "title": key, "flow_ids": [key], "disposition": "available",
                                "reason": "Simulated replay has explicit assertions."} for key in flow_ids] +
                              [{"id": "printing", "title": "Printing", "flow_ids": [], "disposition": "deferred",
                                "reason": "Unobserved known surface retained in the inventory."}],
              "inventory_note": "Four known entries in a simulated test, not a whole-App census.",
              "unknowns": ["All live guest App behavior remains unverified."]}
    path = root / "discovery-review.json"
    path.write_bytes(canonical(review))
    accepted = discover_check(flows, path, root / "discovery")
    test.assertTrue(verify_case(accepted))
    test.assertEqual(json.loads((accepted / "discovery.json").read_text())["flow_count"], 3)
    test.assertFalse(json.loads((accepted / "discovery.json").read_text())["whole_app_coverage_verified"])
    with test.assertRaisesRegex(ValueError, "three to twelve"):
        discover_check({flow_ids[0]: flows[flow_ids[0]]}, path, root / "short-discovery")
    duplicate = {**flows, "renamed-duplicate": root / "renamed-duplicate-replay"}
    with test.assertRaisesRegex(ValueError, "duplicate effective"):
        discover_check(duplicate, path, root / "duplicate-discovery")
    wrong = json.loads(canonical(review))
    wrong["flows"][0]["source_script_sha256"] = "0" * 64
    path.write_bytes(canonical(wrong))
    with test.assertRaisesRegex(ValueError, "different saved script"):
        discover_check(flows, path, root / "wrong-script-discovery")
    wrong = json.loads(canonical(review))
    wrong["capabilities"][0]["flow_ids"] = []
    path.write_bytes(canonical(wrong))
    with test.assertRaises(ValueError):
        discover_check(flows, path, root / "uncovered-discovery")

    def rejects_rehashed(case, relative, change):
        artifact, manifest_path = case / relative, case / "manifest.json"
        original, original_manifest = artifact.read_bytes(), manifest_path.read_bytes()
        value = json.loads(original)
        change(value)
        artifact.write_bytes(canonical(value))
        manifest = json.loads(original_manifest)
        for item in manifest["evidence"]:
            if item["path"] == relative: item["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest_path.write_bytes(canonical(manifest))
        try:
            test.assertFalse(verify_case(case), relative)
        finally:
            artifact.write_bytes(original)
            manifest_path.write_bytes(original_manifest)

    rejects_rehashed(accepted, "discovery.json", lambda value: value.update(flow_count=12))
    rejects_rehashed(accepted, "discovery.json", lambda value: value.update(reconstruction_verified=True))
    rejects_rehashed(accepted, "sources.json", lambda value: value[0].update(effective_script_sha256="0" * 64))
    rejects_rehashed(accepted, "review.json", lambda value: value["flows"][0].update(source_script_sha256="0" * 64))

    formal = json.loads(canonical(behavior_review))
    original_id = script["scenario_id"]
    for key in flow_ids:
        if key == original_id: continue
        formal["findings"].append({"id": key, "statement": "The simulated initial empty text assertion passed.",
                                   "certainty": "observed", "evidence": [{"flow_id": key, "path": "steps/02/assertion.json"}]})
        formal["flows"].append({"id": key, "source_script_sha256": digest(flows[key] / "playbook.json"),
                                "expected_behavior": key, "findings": [key]})
    formal["capabilities"] = review["capabilities"]
    formal_path = root / "discovered-formal-review.json"
    formal_path.write_bytes(canonical(formal))
    reviewed = report({}, formal_path, root / "discovered-report", discovery=accepted)
    test.assertTrue(verify_case(reviewed))
    test.assertEqual(len(json.loads((reviewed / "feature-spec.json").read_text())["capabilities"]), 4)
    test.assertEqual(json.loads((reviewed / "discovery-link.json").read_text())["discovery_manifest_sha256"],
                     digest(accepted / "manifest.json"))
    rejects_rehashed(reviewed, "discovery-link.json", lambda value: value.update(discovery_manifest_sha256="0" * 64))
    rejects_rehashed(reviewed, "review.json", lambda value: value["capabilities"].pop())
    with test.assertRaisesRegex(ValueError, "choose explicit flows"):
        report(flows, formal_path, root / "mixed-report", discovery=accepted)
    formal["capabilities"] = formal["capabilities"][:-1]
    formal_path.write_bytes(canonical(formal))
    with test.assertRaisesRegex(ValueError, "silently drop"):
        report({}, formal_path, root / "dropped-inventory-report", discovery=accepted)
    # Source edits after report creation cannot change the report's saved chain.
    (accepted / "review.json").write_bytes(canonical(wrong))
    test.assertFalse(verify_case(accepted))
    test.assertTrue(verify_case(reviewed))
