"""Resume the verified report-to-plan-to-agent-task handoff."""

import io
import json
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.agent_task import UDID, create_agent_task
from copyapp.rebuild_plan import FLOW_ID, create_rebuild_plan
from copyapp.verify import sha256_file, verify_case


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verified(path: Path) -> bool:
    with redirect_stdout(io.StringIO()):
        return verify_case(path)


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _archive(output: Path, name: str) -> None:
    source = output / name
    if not source.exists():
        return
    attempts = output / "attempts"
    attempts.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    shutil.move(str(source), str(attempts / f"{name}-{stamp}"))


def prepare_rebuild(report: Path, output: Path, backend: str = "ios-mcp",
                    flow_ids: Optional[list[str]] = None, udid: Optional[str] = None,
                    project: Optional[Path] = None,
                    resume: bool = False) -> tuple[Path, bool]:
    """Produce a source-bound plan and task, reusing verified stages on resume."""
    report = report.resolve(strict=True)
    output = output.resolve()
    if output == report or output in report.parents or report in output.parents:
        raise ValueError("report and preparation output must be separate directories")
    if not _verified(report):
        raise ValueError("analysis report evidence hash mismatch")
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    if udid is not None and not UDID.fullmatch(udid):
        raise ValueError("invalid device UDID")
    spec = _read(report / "feature-spec.json")
    index = _read(report / "report-index.json")
    flows = spec.get("flows")
    if (spec.get("schema_version") != 1 or
            spec.get("review_status") == "needs_semantic_review" or
            not isinstance(flows, list) or not flows or
            spec.get("target_bundle_id") != index.get("target_bundle_id")):
        raise ValueError("report has no reviewed rebuild specification")
    known = [item.get("id") for item in flows if isinstance(item, dict)]
    if (len(known) != len(flows) or len(set(known)) != len(known) or
            any(not isinstance(item, str) or not FLOW_ID.fullmatch(item) for item in known)):
        raise ValueError("feature specification has invalid or duplicate flow IDs")
    selected = list(flow_ids) if flow_ids is not None else known
    if (not 1 <= len(selected) <= 12 or len(set(selected)) != len(selected) or
            any(item not in known for item in selected)):
        raise ValueError("provide 1–12 unique flow IDs from the report")
    identity = {"schema_version": 1, "kind": "rebuild_preparation",
                "report": str(report),
                "report_index_sha256": sha256_file(report / "report-index.json"),
                "feature_spec_sha256": sha256_file(report / "feature-spec.json"),
                "selected_flow_ids": selected, "ui_backend": backend,
                "device_udid": udid,
                "project_dir": str(project.resolve()) if project else None,
                "evidence": []}
    manifest_path = output / "manifest.json"
    if output.exists() and any(output.iterdir()):
        if not resume or not manifest_path.is_file():
            raise FileExistsError(f"output directory is not an existing preparation: {output}")
        previous = _read(manifest_path)
        if any(previous.get(key) != value for key, value in identity.items()):
            raise ValueError("resume report, flow selection or settings differ")
    else:
        output.mkdir(parents=True, exist_ok=True)
        _write(manifest_path, dict(identity, status="preparing"))

    plan = output / "plan"
    task = output / "task"
    previous = _read(manifest_path)
    plan_manifest = plan / "manifest.json"
    try:
        plan_data = _read(plan / "rebuild-plan.json") if plan_manifest.is_file() else {}
        plan_ok = (plan_manifest.is_file() and
                   previous.get("plan_manifest_sha256") == sha256_file(plan_manifest) and
                   _verified(plan) and
                   plan_data.get("source_report_index_sha256") ==
                   identity["report_index_sha256"] and
                   plan_data.get("ui_backend") == backend and
                   [item.get("flow_id") for item in plan_data["flows"]] == selected)
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        plan_ok = False
    if not plan_ok:
        if task.exists():
            _archive(output, "task")
        if plan.exists():
            _archive(output, "plan")
        create_rebuild_plan(report, plan, backend, selected)
    previous["plan_manifest_sha256"] = sha256_file(plan_manifest)
    if not plan_ok:
        previous.pop("task_manifest_sha256", None)
    previous["status"] = "plan_ready"
    _write(manifest_path, previous)

    task_manifest = task / "manifest.json"
    try:
        task_data = _read(task / "task.json") if task_manifest.is_file() else {}
        task_ok = (task_manifest.is_file() and
                   _read(manifest_path).get("task_manifest_sha256") == sha256_file(task_manifest) and
                   _verified(task) and
                   task_data.get("report_index_sha256") == identity["report_index_sha256"] and
                   task_data.get("rebuild_plan_sha256") ==
                   sha256_file(plan / "rebuild-plan.json") and
                   task_data.get("device_udid") == udid and
                   (project is None or task_data.get("project_dir") == str(project.resolve())))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        task_ok = False
    if not task_ok:
        if task.exists():
            _archive(output, "task")
        create_agent_task(report, plan, task, udid, project)
    status = _read(task / "task.json")["status"]
    previous["task_manifest_sha256"] = sha256_file(task_manifest)
    previous["status"] = status
    _write(manifest_path, previous)
    return manifest_path, status in ("ready_for_agent", "selected_flows_ready")
