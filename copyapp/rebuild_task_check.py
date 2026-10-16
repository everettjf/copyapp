"""Run an implementation task's verified paired UI plan on one exact device."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional

from copyapp.agent_task import UDID, _source_script
from copyapp.rebuild_check import rebuild_check
from copyapp.verify import checked_path, sha256_file, verify_case


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def rebuild_task_check(task_case: Path, output: Path,
                       udid: Optional[str] = None,
                       resume: bool = False) -> tuple[Path, bool]:
    """Bind task, source plan and selected scripts before any device interaction."""
    task_case = task_case.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(task_case):
            raise ValueError("implementation task failed source verification")
    task = _read(task_case / "task.json")
    if task.get("kind") != "agent_implementation_task" or task.get("status") not in (
            "ready_for_agent", "selected_flows_ready"):
        raise ValueError("implementation task is not ready")
    pinned = task.get("device_udid")
    if udid is not None and pinned is not None and udid != pinned:
        raise ValueError("requested device differs from implementation task")
    selected_udid = udid or pinned
    if not isinstance(selected_udid, str) or not UDID.fullmatch(selected_udid):
        raise ValueError("provide an exact device UDID")

    plan_case = Path(task["rebuild_plan"]).resolve(strict=True)
    report_case = Path(task["report"]).resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(plan_case):
            raise ValueError("rebuild plan failed verification")
    plan = _read(plan_case / "rebuild-plan.json")
    report = _read(report_case / "report-index.json")
    spec = _read(report_case / "feature-spec.json")
    records = plan.get("flows")
    flows = task.get("flows")
    if (plan.get("kind") != "rebuild_plan" or plan.get("status") != "complete" or
            plan.get("ui_backend") not in ("ios-mcp", "ictrl") or
            sha256_file(plan_case / "rebuild-plan.json") != task.get("rebuild_plan_sha256") or
            sha256_file(plan_case / "feature-spec.json") != plan.get("feature_spec_sha256") or
            sha256_file(report_case / "report-index.json") != task.get("report_index_sha256") or
            plan.get("source_report_index_sha256") != task.get("report_index_sha256") or
            plan.get("rebuilt_bundle_id") != task.get("rebuilt_bundle_id") or
            not isinstance(records, list) or not records or len(records) > 12 or
            not isinstance(flows, list) or len(flows) != len(records) or
            plan.get("ready_count") != len(records) or
            plan.get("needs_attention_count") != 0):
        raise ValueError("implementation task plan has gaps or stale identity")
    pairs = []
    for record, flow in zip(records, flows):
        if (not isinstance(record, dict) or not isinstance(flow, dict) or
                record.get("status") != "ready_for_implementation" or
                flow.get("status") != "ready_for_implementation" or
                record.get("flow_id") != flow.get("id")):
            raise ValueError("implementation task flow differs from source plan")
        original = checked_path(plan_case, record["original_script"])
        rebuilt = checked_path(plan_case, record["rebuilt_script"])
        source_id = record.get("source_evidence_id")
        entry = report.get("evidence", {}).get(source_id)
        if not isinstance(entry, dict) or source_id != flow.get("source_evidence_id"):
            raise ValueError("implementation task source evidence differs from report")
        if record.get("source_flow_index") != flow.get("source_flow_index"):
            raise ValueError("implementation task source flow differs from plan")
        source = _source_script(report_case, entry,
                                record.get("source_flow_index"))
        source_data = _read(source)
        expected_rebuilt = dict(source_data, bundle_id=spec.get("rebuilt_bundle_id"))
        if (original != Path(flow["original_script"]).resolve(strict=True) or
                rebuilt != Path(flow["rebuilt_script"]).resolve(strict=True) or
                record.get("source_script_sha256") != flow.get("source_script_sha256") or
                sha256_file(source) != record.get("source_script_sha256") or
                _read(original) != source_data or _read(rebuilt) != expected_rebuilt):
            raise ValueError("implementation task paired scripts are stale")
        pairs.append((record["flow_id"], original, rebuilt))
    return rebuild_check(selected_udid, plan_case / "feature-spec.json", pairs,
                         output, plan["ui_backend"], resume)
