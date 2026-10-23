"""Reviewed behavior reports from UI-first cases, compatible with rebuild plans."""

import io
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from copyapp.compare_playbooks import _load_run
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.verify import checked_path, sha256_file, verify_case


def _verified(root):
    with redirect_stdout(io.StringIO()):
        if not verify_case(root):
            raise ValueError(f"case verification failed: {root}")


def _report_evidence(source: Path) -> dict:
    state = read_json(source / "analysis.json")
    entries = {item["id"]: {"kind": "playbook", "path": f"source/{item['case']}/manifest.json",
                          "sha256": item["manifest_sha256"]}
            for item in state["flows"]}
    for number, item in enumerate(state.get("packages", []), 1):
        key = f"package.{number}"
        if key in entries:
            raise ValueError("flow ID collides with a reserved package evidence ID")
        entries[key] = {"kind": "package_static" if item["kind"] == "ios_package" else "offline_package",
                        "path": f"source/{item['case']}/manifest.json",
                        "sha256": item["manifest_sha256"], "association": item["association"]}
    return entries


def _review_contract(source: Path, findings: dict, spec: dict, entries: dict) -> None:
    from copyapp.report import _validate_findings

    inputs = read_json(source / "inputs.json")
    state = read_json(source / "analysis.json")
    bundle = inputs["bundle_id"]
    if state.get("status") != "complete":
        raise ValueError("UI collection is incomplete")
    if spec.get("execution_mode") != state["selected_mode"]:
        raise ValueError("specification execution mode differs from observed flows")
    _validate_findings(findings, bundle, set(entries))
    if (findings.get("review_status") != "reviewed" or
            not isinstance(findings.get("reviewer"), str) or not findings["reviewer"].strip()):
        raise ValueError("findings require an explicit review status and reviewer")
    if (spec.get("schema_version") != 1 or spec.get("review_status") != "reviewed" or
            spec.get("target_bundle_id") != bundle or
            not isinstance(spec.get("rebuilt_bundle_id"), str) or
            not spec["rebuilt_bundle_id"] or spec["rebuilt_bundle_id"] == bundle or
            not isinstance(spec.get("scope"), str) or not spec["scope"].strip() or
            not isinstance(spec.get("unknowns"), list)):
        raise ValueError("provide a reviewed, bounded feature specification and independent Bundle ID")
    flows = spec.get("flows")
    known = {item["id"]: item for item in state["flows"]}
    if (not isinstance(flows, list) or not flows or
            len({item.get("id") for item in flows if isinstance(item, dict)}) != len(flows)):
        raise ValueError("feature specification needs distinct observed flows")
    for flow in flows:
        identifier = flow.get("id")
        refs = flow.get("evidence")
        expected = flow.get("expected")
        if (identifier not in known or not isinstance(refs, list) or identifier not in refs or
                any(ref not in entries for ref in refs) or
                flow.get("source_script_sha256") != known[identifier]["source_script_sha256"] or
                not isinstance(expected, list) or not expected or
                any(not isinstance(text, str) or not text.strip() for text in expected) or
                not isinstance(flow.get("verification"), str) or not flow["verification"].strip() or
                flow.get("review_status", "reviewed") != "reviewed"):
            raise ValueError(f"flow lacks source-linked reviewed assertions: {identifier}")
        # UI-only reports use AX/explicit playbook assertions, never a Frida UIKit gate.
        if flow.get("final_view") is not None:
            raise ValueError("UI behavior reports require playbook assertions; UIKit final_view needs enhanced evidence")
        child = source / known[identifier]["case"]
        with redirect_stdout(io.StringIO()):
            _load_run(child, require_comparable=True)
        script = read_json(child / "playbook.json")
        last_action = max((i for i, step in enumerate(script["steps"]) if step.get("action") in
                           ("tap", "tap_label", "type_text", "swipe", "long_press", "double_tap")), default=-1)
        if not any(step.get("action") == "observe" and
                   (step.get("contains") or step.get("exact_labels") or step.get("compare_number"))
                   for step in script["steps"][last_action + 1:]):
            raise ValueError("a reviewed flow needs a behavior assertion after its final action")
    for section in findings["sections"]:
        for finding in section.get("findings", []):
            basis = finding.get("basis", "ui")
            allowed = {"playbook"} if basis == "ui" else {"package_static", "offline_package"} if basis == "package" else set()
            if not allowed or any(entries[ref]["kind"] not in allowed for ref in finding["evidence"]):
                raise ValueError("finding basis must match UI or package evidence; function/sandbox claims need enhanced review")


def compose_behavior_report(case: Path, findings_path: Path, spec_path: Path,
                             output: Path) -> Path:
    if output.exists():
        raise FileExistsError(output)
    _verified(case)
    if read_json(case / "manifest.json").get("kind") != "ios_analysis":
        raise ValueError("behavior report requires a UI-first iOS analysis case")
    findings, spec = read_json(findings_path), read_json(spec_path)
    spec.setdefault("execution_mode", read_json(case / "analysis.json")["selected_mode"])
    entries = _report_evidence(case)
    _review_contract(case, findings, spec, entries)
    output.mkdir(parents=True)
    shutil.copytree(case, output / "source")
    write_json(output / "findings.json", findings)
    write_json(output / "feature-spec.json", spec)
    lines = ["# Reviewed iOS behavior report", "",
             f"Target: `{spec['target_bundle_id']}`. Reviewer: {findings['reviewer']}.", "",
             spec["scope"], "",
             "This report reviews observed UI behavior. It does not establish native function semantics, "
             "private sandbox structure, server implementation or whole-App parity.", ""]
    labels = {"observed": "Observed", "inferred": "Inferred", "unknown": "Unknown"}
    for section in findings["sections"]:
        lines += ["## " + section["title"], ""]
        for finding in section["findings"]:
            citations = ", ".join(f"[{ref}]({entries[ref]['path']})" for ref in finding["evidence"])
            lines += [f"- **{labels[finding['confidence']]}:** {finding['claim']} {citations}"]
        lines.append("")
    lines += ["## Unknowns", "", *["- " + text for text in spec["unknowns"]], "",
              "[Feature specification](feature-spec.json) · [Source collection](source/TASK.md)", ""]
    for key, entry in entries.items():
        if entry["kind"] in ("package_static", "offline_package"):
            stem = str(Path(entry["path"]).parent)
            lines += ["## Package evidence " + key, "",
                      f"[Static package index]({stem}/package-index.json). "
                      f"Association with phone observations: `{entry['association']['relation']}`. "
                      "Runtime binary identity remains unverified; a static package observation is not "
                      "evidence that its code ran during the cited UI flow.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    artifacts = {str(path.relative_to(output)): {"path": str(path.relative_to(output)),
                 "sha256": sha256_file(path)} for path in sorted(output.rglob("*")) if path.is_file()}
    index = {"schema_version": 2, "kind": "ios_behavior_report", "analysis_scope": "ui_behavior",
             "target_bundle_id": spec["target_bundle_id"], "source_case": str(case.resolve()),
             "source_case_index_sha256": sha256_file(case / "manifest.json"),
             "evidence": entries, "artifacts": artifacts}
    write_json(output / "report-index.json", index)
    seal_case(output, "ios_behavior_report", status="reviewed",
              bundle_id=spec["target_bundle_id"], analysis_scope="ui_behavior")
    return output / "report.md"


def validate_behavior_report(root: Path, manifest: dict) -> bool:
    source = root / "source"
    _verified(source)
    index = read_json(root / "report-index.json")
    spec, findings = read_json(root / "feature-spec.json"), read_json(root / "findings.json")
    entries = _report_evidence(source)
    _review_contract(source, findings, spec, entries)
    expected_artifacts = {str(path.relative_to(root)): {"path": str(path.relative_to(root)),
                          "sha256": sha256_file(path)} for path in sorted(root.rglob("*"))
                          if path.is_file() and path not in (root / "report-index.json", root / "manifest.json")}
    return (manifest.get("status") == "reviewed" and manifest.get("analysis_scope") == "ui_behavior" and
            manifest.get("bundle_id") == spec["target_bundle_id"] == index.get("target_bundle_id") and
            index.get("kind") == "ios_behavior_report" and index.get("schema_version") == 2 and
            index.get("analysis_scope") == "ui_behavior" and index.get("evidence") == entries and
            index.get("source_case_index_sha256") == sha256_file(source / "manifest.json") and
            index.get("artifacts") == expected_artifacts)
