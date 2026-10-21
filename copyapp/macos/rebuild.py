"""Freeze reviewed Mac scope and prepare a current-agent implementation brief."""

import json
import shutil
from pathlib import Path, PurePosixPath

from copyapp.macos.case import Case, digest
from copyapp.macos.playbook import validate_script
from copyapp.macos.report import identifier, read, text


def plan_record(report: Path, target: dict, capability_ids: list) -> dict:
    from copyapp.verify import verify_case
    if not verify_case(report) or read(report, "manifest.json").get("kind") != "mac_behavior_report":
        raise ValueError("a verified Mac behavior report is required")
    spec = read(report, "feature-spec.json")
    if set(target) != {"bundle_id", "app_path", "project"}:
        raise ValueError("invalid rebuild target")
    bundle, app_path, project = target["bundle_id"], target["app_path"], target["project"]
    text(bundle)
    if (len(bundle) > 255 or any(char.isspace() for char in bundle) or
            bundle == spec["app"]["bundle_id"]):
        raise ValueError("the independent rebuild needs a separate Bundle ID")
    if (not isinstance(app_path, str) or not app_path.startswith("/") or not app_path.endswith(".app") or
            ".." in PurePosixPath(app_path).parts or str(PurePosixPath(app_path)) != app_path or
            "\0" in app_path or not isinstance(project, str) or not Path(project).is_absolute()):
        raise ValueError("use an absolute guest .app path and host project directory")
    original_paths = {read(report / "evidence" / flow["id"], "playbook.json")["app_path"] for flow in spec["flows"]}
    if app_path in original_paths:
        raise ValueError("refusing to overwrite the original App path")
    if (not isinstance(capability_ids, list) or not capability_ids or
            any(not isinstance(value, str) for value in capability_ids) or
            len(set(capability_ids)) != len(capability_ids)):
        raise ValueError("select each target capability explicitly once")
    capabilities = {row["id"]: row for row in spec["capabilities"]}
    if not set(capability_ids).issubset(capabilities):
        raise ValueError("unknown target capability")
    if any(capabilities[key]["disposition"] != "available" for key in capability_ids):
        raise ValueError("blocked or deferred capabilities need a new reviewed report before targeting")
    flows = sorted({flow for key in capability_ids for flow in capabilities[key]["flow_ids"]})
    return {"schema_version": 2, "platform": "macos", "scope": "selected_behavior_rebuild",
            "status": "ready_for_current_agent", "report_manifest_sha256": digest(report / "manifest.json"),
            "target": target, "target_capability_ids": sorted(capability_ids), "selected_flow_ids": flows,
            "omitted_flow_ids": sorted({row["id"] for row in spec["flows"]} - set(flows)),
            "coverage": {"basis": "reviewed_known_inventory_only", "known_capabilities": len(capabilities),
                         "target_known_capabilities": len(capability_ids),
                         "target_percent": round(100 * len(capability_ids) / len(capabilities), 2),
                         "verified_known_capabilities": None, "selected_flow_pass_rate": None},
            "unknowns": spec["unknowns"], "acceptance": "not_run"}


def clone_script(report: Path, flow_id: str, target: dict) -> dict:
    script = read(report / "evidence" / flow_id, "playbook.json")
    script.update(bundle_id=target["bundle_id"], app_path=target["app_path"])
    validate_script(script)
    return script


def task_markdown(report: Path, plan: dict) -> str:
    spec = read(report, "feature-spec.json")
    lines = ["# Implement selected Mac behavior", "",
             "Status: ready for the current coding agent. Implementation and acceptance have not run.", "",
             "Read [the reviewed report](report/report.md) and [feature-spec.json](report/feature-spec.json),",
             "then inspect their linked raw evidence before interpreting the selected behavior.", "",
             "Host source directory: `" + plan["target"]["project"] + "`", "",
             "Rebuilt guest App: `" + plan["target"]["app_path"] + "`", "",
             "Independent Bundle ID: `" + plan["target"]["bundle_id"] + "`", "",
             "Use ChatComputer for guest keyboard/mouse input and screenshots. Preserve the exact",
             "registered environment and original App. Do not use an iOS UDID, IPA or iOS case.", "",
             "Implement independent source, build a native arm64 macOS .app, verify its package",
             "and signature, install under the separate target identity, then compare the same",
             "selected flows on the same environment. Review every required screenshot pair",
             "and output assertion. A task or successful build does not prove installation,",
             "launch, behavioral equivalence, physical-Mac compatibility or deep function analysis.", "",
             "Do the work in this agent session; do not launch another coding-agent CLI.", "",
             "## Frozen selected scope", ""]
    for flow in spec["flows"]:
        if flow["id"] in plan["selected_flow_ids"]:
            flow_id = flow["id"]
            lines.extend(["- " + flow_id + ": " + flow["expected_behavior"],
                          "  [Original evidence](report/evidence/" + flow_id + "/manifest.json) · " +
                          "[Rebuilt playbook](scripts/" + flow_id + ".json)"])
    coverage = plan["coverage"]
    lines.extend(["", "Target: " + str(coverage["target_known_capabilities"]) + "/" +
                  str(coverage["known_capabilities"]) + " reviewed known capabilities (" +
                  str(coverage["target_percent"]) + "%). Verified coverage and flow pass rate are not yet available.",
                  "This denominator covers the reviewed known inventory only.", "",
                  "Omitted report flows: " + (", ".join(plan["omitted_flow_ids"]) or "none") + ".", "",
                  "## Unknown behavior", ""] + ["- " + value for value in plan["unknowns"]] + [""])
    return "\n".join(lines)


def rebuild_plan(report: Path, bundle_id: str, app_path: str, project: Path,
                 capabilities: list, output: Path) -> Path:
    report = report.resolve(strict=True)
    if output.resolve() == report or report in output.resolve().parents:
        raise ValueError("rebuild plan must be outside its source report")
    target = {"bundle_id": bundle_id, "app_path": app_path, "project": str(project.resolve())}
    plan = plan_record(report, target, capabilities)
    case = Case(output, "mac_rebuild_plan")
    try:
        shutil.copytree(report, case.root / "report", symlinks=True)
        case.record("report/manifest.json")
        case.add("rebuild-plan.json", plan)
        for flow_id in plan["selected_flow_ids"]:
            case.add("scripts/" + flow_id + ".json", clone_script(report, flow_id, target))
        case.add("TASK.md", task_markdown(report, plan).encode("utf-8"), binary=True)
        case.finish("complete", scope="selected_behavior_rebuild", readiness="ready_for_current_agent")
        if not validate_plan(case.root, case.manifest, {row["path"] for row in case.manifest["evidence"]}):
            raise ValueError("copied rebuild inputs changed during preparation")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="selected_behavior_rebuild")
        raise


def validate_plan(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "selected_behavior_rebuild" or
            manifest.get("readiness") != "ready_for_current_agent" or
            not {"report/manifest.json", "rebuild-plan.json", "TASK.md"}.issubset(names)):
        return False
    plan = read(root, "rebuild-plan.json")
    expected = plan_record(root / "report", plan["target"], plan["target_capability_ids"])
    if plan != expected or (root / "TASK.md").read_text() != task_markdown(root / "report", plan):
        return False
    for flow_id in plan["selected_flow_ids"]:
        name = "scripts/" + identifier(flow_id) + ".json"
        if name not in names or read(root, name) != clone_script(root / "report", flow_id, plan["target"]):
            return False
    return True
