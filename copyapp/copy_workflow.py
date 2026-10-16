"""One resumable, evidence-gated Analyze → Rebuild handoff."""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable, Optional

from copyapp.agent_run import run_agent_task
from copyapp.discover_check import accepted_playbooks
from copyapp.discovery_agent import run_discovery_agent
from copyapp.prepare_app import prepare_app
from copyapp.prepare_rebuild import prepare_rebuild
from copyapp.verify import sha256_file, verify_case


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _child(root: Path, name: str) -> Path:
    path = root / name
    if path.is_symlink() or path.resolve() != path:
        raise ValueError(f"workflow child is not a real local directory: {name}")
    return path


def _preparation_ready(root: Path, source: dict) -> bool:
    preparation = _child(root, "preparation")
    try:
        prep = _read(preparation / "manifest.json")
        return (prep.get("status") == "needs_semantic_review" and
                prep.get("bundle_id") == source["bundle_id"] and
                prep.get("device_id_sha256_prefix") == source["device_id_sha256_prefix"] and
                prep.get("scripts") == source["scripts"] and
                prep.get("rebuilt_bundle_id") == source["rebuilt_bundle_id"] and
                prep.get("provider") == source["analysis_provider"] and
                prep.get("ui_backend") == source["ui_backend"] and
                prep.get("investigation_backend") == source["backend"] and
                prep.get("decrypt") == source["decrypt"] and
                prep.get("decrypt_helper") == source["decrypt_helper"] and
                prep.get("ssh_port") == source["ssh_port"] and
                prep.get("ssh_user") == source["ssh_user"] and
                prep.get("ssh_identity") == source["ssh_identity"] and
                prep.get("ssh_known_hosts") == source["ssh_known_hosts"] and
                prep.get("ghidra_dir") == source["ghidra_dir"] and
                prep.get("java_home") == source["java_home"] and
                prep.get("disabled_analyzer") == source["disabled_analyzer"] and
                prep.get("timeout") == source["analysis_timeout"] and
                bool(prep.get("network_requested")) == source["network"] and
                verify_case(preparation))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def _handoff_ready(root: Path, source: dict, report: Path) -> bool:
    rebuilt = _child(root, "rebuild-preparation")
    try:
        handoff = _read(rebuilt / "manifest.json")
        selected = source["flow_ids"]
        if selected is None:
            selected = [flow["id"] for flow in _read(report / "feature-spec.json")["flows"]]
        return (handoff.get("status") in ("ready_for_agent", "selected_flows_ready") and
                handoff.get("report") == str(report) and
                handoff.get("device_udid") == source["device_udid"] and
                handoff.get("project_dir") == source["project_dir"] and
                handoff.get("ui_backend") == source["backend"] and
                handoff.get("selected_flow_ids") == selected and
                verify_case(rebuilt))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def _analysis_ready(root: Path, task: Path, provider: str) -> bool:
    run = _child(root, "analysis-agent")
    try:
        if provider == "current":
            report = _child(run, "reviewed-report")
            delivery = _child(run, "analysis-delivery")
            delivered = _read(delivery / "delivery.json")
            return (delivered.get("status") == "source_linked_report_ready_for_review" and
                    delivered.get("task_case") == str(task) and
                    delivered.get("report_case") == str(report) and
                    delivered.get("agent_run") is None and
                    verify_case(report) and verify_case(delivery))
        verification = _read(run / "analysis-verification.json")
        record = _read(run / "run.json")
        delivery = _child(run, "analysis-delivery")
        report = _child(run, "reviewed-report")
        return (verification.get("status") == "source_linked_report_ready_for_review" and
                record.get("task_case") == str(task) and
                record.get("provider") == provider and
                record.get("status") == "agent_exited_unverified" and
                verification.get("report_case") == str(report) and
                verification.get("analysis_delivery_case") == str(delivery) and
                verification.get("analysis_delivery_manifest_sha256") ==
                sha256_file(delivery / "manifest.json") and
                verify_case(run) and verify_case(report) and verify_case(delivery))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def _rebuild_ready(root: Path, task: Path, provider: str) -> bool:
    run = _child(root, "rebuild-agent")
    try:
        if provider == "current":
            delivery = _child(run, "agent-delivery")
            delivered = _read(delivery / "delivery.json")
            selected = _read(task / "task.json")["flows"]
            results = delivered.get("flow_results")
            return (delivered.get("task_case") == str(task) and
                    delivered.get("agent_run_case") is None and
                    delivered.get("visual_review_case") is not None and
                    delivered.get("asserted_flow_count") == len(selected) and
                    delivered.get("visual_unreviewed_flow_count") == 0 and
                    delivered.get("visual_major_difference_flow_count") == 0 and
                    isinstance(results, list) and len(results) == len(selected) and
                    all(isinstance(item, dict) and
                        (item.get("script_assertions_status") == "passed" or
                         item.get("final_view_status") == "passed")
                        for item in results) and verify_case(delivery))
        verification = _read(run / "rebuild-verification.json")
        record = _read(run / "run.json")
        delivery = _child(run, "agent-delivery")
        delivered = _read(delivery / "delivery.json")
        selected = _read(task / "task.json")["flows"]
        results = delivered.get("flow_results")
        behavior_passed = (isinstance(results, list) and
                           len(results) == len(selected) and
                           all(isinstance(item, dict) and
                               (item.get("script_assertions_status") == "passed" or
                                item.get("final_view_status") == "passed")
                               for item in results))
        return (verification.get("status") == "selected_flows_verified" and
                record.get("task_case") == str(task) and
                record.get("provider") == provider and
                record.get("status") == "agent_exited_unverified" and
                verification.get("agent_delivery_case") == str(delivery) and
                verification.get("agent_delivery_manifest_sha256") ==
                sha256_file(delivery / "manifest.json") and
                verification.get("selected_flow_count") == len(selected) and
                verification.get("asserted_flow_count") == len(selected) and
                delivered.get("asserted_flow_count") == len(selected) and
                behavior_passed and
                delivered.get("visual_unreviewed_flow_count") == 0 and
                delivered.get("visual_major_difference_flow_count") == 0 and
                verify_case(run) and verify_case(delivery))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


def _save(root: Path, record: dict) -> Path:
    paths = ("discovery-agent/manifest.json", "discovery-agent/discovery/manifest.json",
             "preparation/manifest.json", "analysis-agent/manifest.json",
             "analysis-agent/TASK.md", "rebuild-agent/TASK.md",
             "analysis-agent/analysis-verification.json",
             "analysis-agent/reviewed-report/report-index.json",
             "analysis-agent/analysis-delivery/manifest.json",
             "rebuild-preparation/manifest.json", "rebuild-agent/manifest.json",
             "rebuild-agent/rebuild-verification.json",
             "rebuild-agent/agent-delivery/manifest.json")
    record["evidence"] = [{"path": name, "sha256": sha256_file(root / name)}
                          for name in paths if (root / name).is_file()]
    record["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = root / "manifest.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def validate_copy_workflow(root: Path, record: dict) -> bool:
    """Recheck every source link before accepting a completed workflow."""
    try:
        if (record.get("schema_version") != 1 or
                record.get("kind") != "copy_workflow" or
                record.get("status") != "complete" or
                not isinstance(record.get("scripts"), list) or
                not 1 <= len(record["scripts"]) <= 12):
            return False
        if record.get("auto_discover"):
            agent = _child(root, "discovery-agent")
            agent_record = _read(agent / "manifest.json")
            if (record.get("discovery_agent_manifest_sha256") !=
                    sha256_file(agent / "manifest.json") or
                    agent_record.get("status") != "complete" or
                    agent_record.get("device_udid") != record["device_udid"] or
                    agent_record.get("bundle_id") != record["bundle_id"] or
                    agent_record.get("backend") != record["backend"] or
                    agent_record.get("provider") != record["agent_provider"] or
                    agent_record.get("scripts") != record["scripts"] or
                    record.get("discovery_case") != str(agent / "discovery") or
                    not verify_case(agent)):
                return False
        if record.get("discovery_case") is not None:
            discovery = Path(record["discovery_case"]).resolve(strict=True)
            if (sha256_file(discovery / "manifest.json") !=
                    record.get("discovery_manifest_sha256") or
                    [str(path) for path in accepted_playbooks(
                        discovery, record["device_udid"], record["bundle_id"],
                        record["backend"])] !=
                    [item["path"] for item in record["scripts"]]):
                return False
        preparation = _child(root, "preparation")
        scripts = record["scripts"]
        if (not _preparation_ready(root, record) or
                any(sha256_file(Path(item["path"])) != item["sha256"]
                    for item in scripts)):
            return False
        analysis_task = preparation / "preparation" / "draft"
        if not _analysis_ready(root, analysis_task, record["agent_provider"]):
            return False
        report = _child(root / "analysis-agent", "reviewed-report")
        spec = _read(report / "feature-spec.json")
        if (spec.get("target_bundle_id") != record["bundle_id"] or
                spec.get("rebuilt_bundle_id") != record["rebuilt_bundle_id"]):
            return False
        rebuilt = _child(root, "rebuild-preparation")
        if not _handoff_ready(root, record, report):
            return False
        return _rebuild_ready(root, rebuilt / "task", record["agent_provider"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False


async def copy_app(udid: str, bundle: str, scripts: list[Path], project: Path,
                   rebuilt_bundle: str, output: Path,
                   survey: Callable[..., Awaitable[int]], *,
                   workspace: Optional[Path] = None, backend: str = "ios-mcp",
                   ui_backend: str = "ios-mcp", analysis_provider: str = "none",
                   agent_provider: str = "codex", decrypt: bool = True,
                   network: bool = True, flow_ids: Optional[list[str]] = None,
                   decrypt_helper: Path = Path("../toolchains/ipadecrypt-helper-arm64"),
                   ssh_port: int = 22222, ssh_user: str = "mobile",
                   ssh_identity: Path = Path("cases/ssh/id_ed25519"),
                   ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
                   ghidra_dir: Optional[Path] = None, java_home: Optional[Path] = None,
                   disabled_analyzer: Optional[str] = None,
                   analysis_timeout: int = 240, agent_timeout: int = 7200,
                   agent_executable: Optional[Path] = None,
                   discovery_case: Optional[Path] = None,
                   auto_discover: bool = False,
                   resume: bool = False) -> tuple[Path, bool]:
    """Run both stages without accepting a CLI exit as proof of a deliverable.

    Failed Agent runs are not automatically repeated: they may have changed App or
    device state. Start a new workflow case after inspecting their saved output.
    """
    workspace = (workspace or Path(__file__).resolve().parents[1]).resolve(strict=True)
    output = output.resolve()
    project = project.resolve()
    if (not workspace.is_dir() or not output.is_relative_to(workspace) or
            not project.is_relative_to(workspace) or
            project == output or project in output.parents or output in project.parents):
        raise ValueError("workflow output and independent project must be separate workspace paths")
    if (not udid or not bundle or not rebuilt_bundle or bundle == rebuilt_bundle or
            agent_provider not in ("codex", "claude", "current") or
            backend not in ("ios-mcp", "ictrl") or
            ui_backend not in ("usb", "ios-mcp") or
            (not 1 <= len(scripts) <= 12 and not (auto_discover and not scripts)) or
            (auto_discover and (scripts or discovery_case is not None or
                                agent_provider == "current"))):
        raise ValueError("invalid workflow target, provider or playbook selection")
    if agent_executable is not None:
        agent_executable = agent_executable.resolve(strict=True)
    elif agent_provider != "current" and not shutil.which(agent_provider):
        raise FileNotFoundError(f"{agent_provider} CLI is not installed")
    if agent_provider == "current" and agent_executable is not None:
        raise ValueError("current-agent mode does not launch an executable")
    if auto_discover:
        agent_root = _child(output, "discovery-agent")
        if not resume and output.exists() and any(output.iterdir()):
            raise FileExistsError(f"workflow output is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        agent_manifest, ready = run_discovery_agent(
            udid, bundle, backend, agent_root, workspace=workspace,
            provider=agent_provider, timeout_seconds=agent_timeout,
            executable=agent_executable, resume=(agent_root / "manifest.json").is_file())
        if not ready:
            return agent_manifest, False
        discovery_case = agent_root / "discovery"
        scripts = accepted_playbooks(discovery_case, udid, bundle, backend)
    if discovery_case is not None:
        discovery_case = discovery_case.resolve(strict=True)
        nested_discovery = (auto_discover and
                            discovery_case == output / "discovery-agent/discovery")
        if (not discovery_case.is_relative_to(workspace) or
                (not nested_discovery and
                 (output == discovery_case or output in discovery_case.parents or
                  discovery_case in output.parents)) or
                [path.resolve(strict=True) for path in scripts] !=
                accepted_playbooks(discovery_case, udid, bundle, backend)):
            raise ValueError("workflow scripts differ from the verified discovery case")
    script_records = [{"path": str(path.resolve(strict=True)),
                       "sha256": sha256_file(path.resolve(strict=True))}
                      for path in scripts]
    if len({item["sha256"] for item in script_records}) != len(script_records):
        raise ValueError("duplicate playbooks")
    source = {
        "schema_version": 1, "kind": "copy_workflow", "bundle_id": bundle,
        "rebuilt_bundle_id": rebuilt_bundle, "device_udid": udid,
        "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
        "scripts": script_records, "project_dir": str(project),
        "workspace": str(workspace), "backend": backend, "ui_backend": ui_backend,
        "analysis_provider": analysis_provider, "agent_provider": agent_provider,
        "decrypt": decrypt, "network": network, "flow_ids": flow_ids,
        "decrypt_helper": str(decrypt_helper.resolve()),
        "ssh_port": ssh_port, "ssh_user": ssh_user,
        "ssh_identity": str(ssh_identity.resolve()),
        "ssh_known_hosts": str(ssh_known_hosts.resolve()),
        "ghidra_dir": str(ghidra_dir.resolve()) if ghidra_dir else None,
        "java_home": str(java_home.resolve()) if java_home else None,
        "disabled_analyzer": disabled_analyzer,
        "analysis_timeout": analysis_timeout, "agent_timeout": agent_timeout,
        "agent_executable": str(agent_executable.resolve()) if agent_executable else None,
        "auto_discover": auto_discover,
        "discovery_agent_manifest_sha256": (
            sha256_file(output / "discovery-agent/manifest.json") if auto_discover else None),
        "discovery_case": str(discovery_case) if discovery_case else None,
        "discovery_manifest_sha256":
        sha256_file(discovery_case / "manifest.json") if discovery_case else None,
    }
    manifest = output / "manifest.json"
    if resume and manifest.is_file():
        record = _read(manifest)
        if any(record.get(key) != value for key, value in source.items()):
            raise ValueError("resume target, playbooks or settings differ")
        if record.get("status") == "complete":
            return manifest, validate_copy_workflow(output, record) and verify_case(output)
    else:
        if resume and not auto_discover:
            raise ValueError("resume requires an existing Copy APP workflow")
        if output.exists() and any(output.iterdir()) and not (
                auto_discover and {item.name for item in output.iterdir()} == {"discovery-agent"}):
            raise FileExistsError(f"workflow output is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        record = dict(source, status="preparing")
        _save(output, record)
    preparation = _child(output, "preparation")
    analysis_run = _child(output, "analysis-agent")
    rebuild = _child(output, "rebuild-preparation")
    rebuild_run = _child(output, "rebuild-agent")
    try:
        if not _preparation_ready(output, record):
            path, ready = await prepare_app(
                udid, bundle, scripts, preparation, survey,
                ui_backend=ui_backend, backend=backend, decrypt=decrypt,
                decrypt_helper=decrypt_helper, ssh_port=ssh_port, ssh_user=ssh_user,
                ssh_identity=ssh_identity, ssh_known_hosts=ssh_known_hosts,
                provider=analysis_provider, ghidra_dir=ghidra_dir, java_home=java_home,
                disabled_analyzer=disabled_analyzer, network=network,
                timeout=analysis_timeout, rebuilt_bundle_id=rebuilt_bundle,
                resume=(preparation / "manifest.json").is_file())
            if not ready or not _preparation_ready(output, record):
                record["status"] = "preparation_incomplete"
                return _save(output, record), False
        task = preparation / "preparation" / "draft"
        if not _analysis_ready(output, task, agent_provider):
            if agent_provider == "current":
                analysis_run.mkdir(parents=True, exist_ok=True)
                brief = analysis_run / "TASK.md"
                if not brief.exists():
                    brief.write_text(
                        "# Current-agent analysis handoff\n\n"
                        f"Review [{task / 'TASK.md'}]({task / 'TASK.md'}) and its evidence. "
                        f"Save a formal report at `{analysis_run / 'reviewed-report'}`, "
                        "then run `copyapp analysis-delivery` with this draft task and "
                        f"that report into `{analysis_run / 'analysis-delivery'}`. "
                        "Resume the same `copyapp copy` case after both verify.\n",
                        encoding="utf-8")
                record["status"] = "analysis_agent_needs_review"
                return _save(output, record), False
            if analysis_run.exists() and any(analysis_run.iterdir()):
                record["status"] = "analysis_agent_needs_review"
                return _save(output, record), False
            _, ready = run_agent_task(task, analysis_run, agent_provider,
                                      workspace, agent_timeout, agent_executable,
                                      verify_analysis=True)
            if not ready or not _analysis_ready(output, task, agent_provider):
                record["status"] = "analysis_agent_needs_review"
                return _save(output, record), False
        report = analysis_run / "reviewed-report"
        spec = _read(report / "feature-spec.json")
        if (spec.get("target_bundle_id") != bundle or
                spec.get("rebuilt_bundle_id") != rebuilt_bundle):
            raise ValueError("reviewed report target or rebuilt bundle differs")
        if not _handoff_ready(output, record, report):
            _, ready = prepare_rebuild(report, rebuild, backend, flow_ids, udid,
                                       project, resume=(rebuild / "manifest.json").is_file())
            if not ready or not _handoff_ready(output, record, report):
                record["status"] = "rebuild_task_needs_evidence"
                return _save(output, record), False
        implementation_task = rebuild / "task"
        if not _rebuild_ready(output, implementation_task, agent_provider):
            if agent_provider == "current":
                rebuild_run.mkdir(parents=True, exist_ok=True)
                brief = rebuild_run / "TASK.md"
                if not brief.exists():
                    brief.write_text(
                        "# Current-agent rebuild handoff\n\n"
                        f"Implement [{implementation_task / 'TASK.md'}]"
                        f"({implementation_task / 'TASK.md'}) in `{project}`. "
                        "Install and compare the selected flows on the pinned device. "
                        f"Save installation at `{rebuild_run / 'install'}`, "
                        f"comparison at `{rebuild_run / 'rebuild-check'}`, "
                        f"visual review at `{rebuild_run / 'visual-review'}`, and "
                        f"`copyapp agent-delivery` at `{rebuild_run / 'agent-delivery'}` "
                        "without `--run`. Resume the same `copyapp copy` case after "
                        "all evidence verifies.\n", encoding="utf-8")
                record["status"] = "rebuild_agent_needs_review"
                return _save(output, record), False
            if rebuild_run.exists() and any(rebuild_run.iterdir()):
                record["status"] = "rebuild_agent_needs_review"
                return _save(output, record), False
            _, ready = run_agent_task(implementation_task, rebuild_run,
                                      agent_provider, workspace, agent_timeout,
                                      agent_executable, verify_rebuild=True)
            if not ready or not _rebuild_ready(output, implementation_task,
                                               agent_provider):
                record["status"] = "rebuild_agent_needs_review"
                return _save(output, record), False
        record["status"] = "complete"
        path = _save(output, record)
        if not validate_copy_workflow(output, record) or not verify_case(output):
            raise ValueError("completed workflow failed source verification")
        return path, True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        record["status"] = "failed"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
        return _save(output, record), False
