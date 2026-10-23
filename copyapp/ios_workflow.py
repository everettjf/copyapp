"""Current-agent UI-first workflow; historical strict copy remains independent."""

import hashlib
import re
from pathlib import Path
from typing import Optional

from copyapp.copy_workflow import _rebuild_ready
from copyapp.discover_check import accepted_playbooks
from copyapp.ios_analysis import _package_inputs, _script_inputs, _verified, collect_ios_analysis
from copyapp.ios_capabilities import collect_capabilities
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.ios_delivery import behavior_delivery_links
from copyapp.prepare_rebuild import prepare_rebuild
from copyapp.verify import checked_path, compare, sha256_file


def _inputs(udid, bundle, rebuilt_bundle, project, mode, scripts, discovery, auto_discover,
            packages, flow_ids, backend):
    if (mode not in ("auto", "standard", "enhanced") or bundle == rebuilt_bundle or
            not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid) or
            any(not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in (bundle, rebuilt_bundle)) or
            backend not in (None, "ictrl", "ios-mcp") or
            sum((bool(scripts), discovery is not None, auto_discover)) != 1):
        raise ValueError("choose one flow source, an independent Bundle ID and an explicit mode")
    source = [{**item, "source": str(path.resolve(strict=True))}
              for item, path in zip(_script_inputs(scripts, bundle), scripts)] if scripts else []
    if flow_ids is not None and (not 1 <= len(flow_ids) <= 12 or len(set(flow_ids)) != len(flow_ids) or
                                any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", item) for item in flow_ids)):
        raise ValueError("provide 1–12 distinct selected flow IDs")
    package_records = _package_inputs(packages, bundle)
    return {"udid": udid, "bundle_id": bundle, "rebuilt_bundle_id": rebuilt_bundle,
            "project": str(project.resolve()), "requested_mode": mode, "scripts": source,
            "requested_backend": backend,
            "discovery": str(discovery.resolve(strict=True)) if discovery else None,
            "discovery_manifest_sha256": sha256_file(discovery / "manifest.json") if discovery else None,
            "auto_discover": auto_discover, "selected_flow_ids": flow_ids,
            "packages": [{**item, "source": str(path.resolve(strict=True))}
                         for item, path in zip(package_records, packages)]}


def _plan(root, inputs):
    _verified(root / "capabilities")
    plan = read_json(root / "capabilities/capabilities.json")
    if (plan["device"]["UniqueDeviceID"] != inputs["udid"] or
            plan["requested_mode"] != inputs["requested_mode"]):
        raise ValueError("workflow capabilities belong to another target or mode")
    if inputs["requested_backend"] is not None and inputs["requested_backend"] != plan["ui_backend"]:
        raise ValueError("requested backend is unavailable in the selected mode; choose an explicit compatible route")
    return plan


def _scripts(root, inputs, plan):
    if inputs["scripts"]:
        return [Path(item["source"]) for item in inputs["scripts"]]
    discovery = (root / "discovery-agent/discovery" if inputs["auto_discover"]
                 else Path(inputs["discovery"]))
    if not (discovery / "manifest.json").is_file():
        return []
    if (not inputs["auto_discover"] and sha256_file(discovery / "manifest.json") !=
            inputs["discovery_manifest_sha256"]):
        raise ValueError("accepted discovery source changed")
    record = read_json(discovery / "manifest.json")
    if record.get("execution_mode") != plan["selected_mode"]:
        raise ValueError("discovery must be replayed in the workflow execution mode")
    return accepted_playbooks(discovery, inputs["udid"], inputs["bundle_id"], plan["ui_backend"])


def _collection(root, inputs, scripts, plan):
    source = root / "analysis"
    _verified(source)
    identity = read_json(source / "inputs.json")
    expected = {"udid": inputs["udid"], "bundle_id": inputs["bundle_id"],
                "requested_mode": inputs["requested_mode"],
                "flows": _script_inputs(scripts, inputs["bundle_id"])}
    if inputs["packages"]:
        expected["packages"] = [{key: value for key, value in row.items() if key != "source"}
                                for row in inputs["packages"]]
    if identity != expected:
        raise ValueError("workflow analysis inputs changed")
    state = read_json(source / "analysis.json")
    if state["status"] == "complete" and (
            state["selected_mode"] != plan["selected_mode"] or state["ui_backend"] != plan["ui_backend"]):
        raise ValueError("analysis route differs from the frozen workflow route; start a new workflow")
    return state


def _report_ready(root, inputs):
    report = root / "analysis-agent/reviewed-report"
    delivered = root / "analysis-agent/analysis-delivery"
    if not (report / "manifest.json").exists() or not (delivered / "manifest.json").exists():
        return False
    if read_json(delivered / "manifest.json").get("kind") != "ios_behavior_delivery":
        raise ValueError("workflow requires a UI behavior delivery")
    _verified(delivered)
    if read_json(delivered / "delivery.json") != behavior_delivery_links(root / "analysis", report):
        raise ValueError("behavior delivery source differs from this workflow")
    spec = read_json(report / "feature-spec.json")
    analysis = read_json(root / "analysis/analysis.json")
    if (spec["rebuilt_bundle_id"] != inputs["rebuilt_bundle_id"] or
            spec.get("execution_mode") != analysis["selected_mode"]):
        raise ValueError("reviewed rebuild identity or execution mode differs")
    return True


def _handoff_ready(root, inputs, plan):
    prep = root / "rebuild-preparation"
    _verified(prep)
    record = read_json(prep / "manifest.json")
    report = root / "analysis-agent/reviewed-report"
    selected = inputs["selected_flow_ids"] or [item["id"] for item in read_json(report / "feature-spec.json")["flows"]]
    if (record.get("report") != str(report) or record.get("device_udid") != inputs["udid"] or
            record.get("project_dir") != inputs["project"] or
            record.get("ui_backend") != plan["ui_backend"] or record.get("selected_flow_ids") != selected):
        raise ValueError("rebuild preparation belongs to different workflow settings")
    return record.get("status") in ("ready_for_agent", "selected_flows_ready")


def _save(root, inputs, status, error=None):
    state = {"status": status, "scope": "selected_flows", "agent_provider": "current"}
    if error:
        state["error"] = {"type": type(error).__name__, "message": str(error)[:500]}
    write_json(root / "workflow.json", state)
    (root / "report.md").write_text(
        "# UI-first iOS copy workflow\n\n"
        f"App: `{inputs['bundle_id']}`. Status: `{status}`.\n\n"
        "Follow TASK.md and resume this exact case. Completion requires source-linked analysis, "
        "an independently installed rebuild, paired behavior assertions and full visual review with "
        "no major differences. A fidelity milestone alone does not complete this strict parent. "
        "Whole-App parity and function semantics are outside this UI behavior contract.\n", encoding="utf-8")
    return seal_case(root, "ios_copy_workflow", status=status, bundle_id=inputs["bundle_id"],
                     device_id_sha256_prefix=hashlib.sha256(inputs["udid"].encode()).hexdigest()[:16])


def copy_ios(udid: str, bundle: str, scripts: list[Path], project: Path,
             rebuilt_bundle: str, output: Path, mode: str = "standard", *,
             discovery: Optional[Path] = None, auto_discover: bool = False,
             packages: Optional[list[Path]] = None, flow_ids: Optional[list[str]] = None,
             backend: Optional[str] = None,
             resume: bool = False, retry_failed: bool = False, enhanced_collector=None,
             ssh_port=22222, ssh_identity=Path("cases/ssh/id_ed25519"),
             ssh_known_hosts=Path("cases/ssh-known-hosts")) -> tuple[Path, bool]:
    output = output.resolve()
    inputs = _inputs(udid, bundle, rebuilt_bundle, project, mode, scripts, discovery,
                     auto_discover, packages or [], flow_ids, backend)
    if output == project.resolve() or output in project.resolve().parents or project.resolve() in output.parents:
        raise ValueError("project and evidence must be separate directory trees")
    if output.exists() and any(output.iterdir()):
        if not resume or read_json(output / "inputs.json") != inputs:
            raise ValueError("resume requires this workflow's exact inputs")
        previous = read_json(output / "manifest.json")
        if previous.get("kind") != "ios_copy_workflow" or not compare(output, previous["evidence"]):
            raise ValueError("saved workflow evidence changed; preserve it and start a new case")
    else:
        if resume:
            raise ValueError("resume requires an existing workflow")
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "inputs.json", inputs)
    status = "failed"
    try:
        if not (output / "capabilities").exists():
            collect_capabilities(udid, output / "capabilities", mode, ssh_port, ssh_identity, ssh_known_hosts)
        plan = _plan(output, inputs)
        discovery_dir = output / "discovery-agent"
        if auto_discover and not (discovery_dir / "TASK.md").exists():
            discovery_dir.mkdir(exist_ok=True)
            (discovery_dir / "TASK.md").write_text(
                f"# Discover representative flows\n\nObserve `{bundle}` on exact USB device `{udid}`. "
                "Write 3–12 distinct bounded flows using visible entry assertions, at most eight actions, "
                "a post-action behavior assertion and a stable final screenshot. Review side effects before replay. "
                f"Run `copyapp discover-check --mode {plan['selected_mode']} --backend {plan['ui_backend']} "
                f"--udid {udid} --bundle {bundle} --script <PATH> ... --out {discovery_dir / 'discovery'}` "
                "then resume this workflow. Work in the current agent session; do not launch another coding agent.\n",
                encoding="utf-8")
        (output / "TASK.md").write_text(
            "# Continue the UI-first workflow\n\n"
            "1. Complete discovery-agent/TASK.md if present.\n"
            "2. Review analysis/TASK.md, every screenshot and raw accessibility observation. Write reviewed findings "
            "and feature-spec (with all source script hashes, bounded scope, unknowns and independent Bundle ID). "
            f"Use execution_mode `{plan['selected_mode']}` and rebuilt Bundle ID `{rebuilt_bundle}`. "
            "Run `copyapp report --case <THIS>/analysis --findings <JSON> --feature-spec <JSON> "
            "--out <THIS>/analysis-agent/reviewed-report`, then `copyapp analysis-delivery --task <THIS>/analysis "
            "--report <THIS>/analysis-agent/reviewed-report --out <THIS>/analysis-agent/analysis-delivery`. Resume.\n"
            "3. Follow rebuild-preparation/task/TASK.md. Freeze capability coverage and fidelity before implementation "
            "using docs/coverage-targets.md and docs/fidelity.md. Implement in the pinned sibling project, build, "
            "sign, install via USB in standard mode, run rebuild-task-check, inspect all screenshot pairs, create "
            "visual-review and agent-delivery at rebuild-agent/agent-delivery. Use the current session, without --run. "
            "Record every difference and omitted flow. Resume this exact workflow.\n"
            "A bounded fidelity result does not replace the strict delivery gates of this parent.\n",
            encoding="utf-8")
        selected = _scripts(output, inputs, plan)
        if not selected:
            status = "needs_discovery"
        else:
            analysis = output / "analysis"
            if not analysis.exists() or read_json(analysis / "analysis.json")["status"] != "complete":
                collect_ios_analysis(udid, bundle, selected, analysis, mode, analysis.exists(), retry_failed,
                                     ssh_port=ssh_port, ssh_identity=ssh_identity, ssh_known_hosts=ssh_known_hosts,
                                     enhanced_collector=enhanced_collector, package_cases=packages)
            collection = _collection(output, inputs, selected, plan)
            if collection["status"] != "complete":
                status = "collection_failed"
            elif not _report_ready(output, inputs):
                status = "needs_behavior_review"
            else:
                prep = output / "rebuild-preparation"
                prepare_rebuild(output / "analysis-agent/reviewed-report", prep, plan["ui_backend"],
                                flow_ids, udid, project, prep.exists())
                if not _handoff_ready(output, inputs, plan):
                    status = "needs_rebuild_evidence"
                elif _rebuild_ready(output, prep / "task", "current"):
                    status = "complete"
                else:
                    status = "needs_implementation"
        return _save(output, inputs, status), status == "complete"
    except Exception as exc:
        return _save(output, inputs, "failed", exc), False


def validate_ios_workflow(root: Path, manifest: dict) -> bool:
    inputs, state = read_json(root / "inputs.json"), read_json(root / "workflow.json")
    if (manifest.get("status") != state["status"] or manifest.get("bundle_id") != inputs["bundle_id"] or
            manifest.get("device_id_sha256_prefix") != hashlib.sha256(inputs["udid"].encode()).hexdigest()[:16] or
            state.get("scope") != "selected_flows" or state.get("agent_provider") != "current"):
        return False
    if state["status"] == "failed":
        return isinstance(state.get("error"), dict)
    plan = _plan(root, inputs)
    scripts = _scripts(root, inputs, plan)
    if state["status"] == "needs_discovery":
        return inputs["auto_discover"] and not scripts and (root / "discovery-agent/TASK.md").is_file()
    collection = _collection(root, inputs, scripts, plan)
    if state["status"] == "collection_failed":
        return collection["status"] == "failed"
    if collection["status"] != "complete":
        return False
    if state["status"] == "needs_behavior_review":
        return not _report_ready(root, inputs)
    if not _report_ready(root, inputs):
        return False
    ready = _handoff_ready(root, inputs, plan)
    if state["status"] == "needs_rebuild_evidence":
        return not ready
    if not ready:
        return False
    delivered = _rebuild_ready(root, root / "rebuild-preparation/task", "current")
    return (state["status"] == "complete" and delivered or
            state["status"] == "needs_implementation" and not delivered)
