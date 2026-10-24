"""Bind a reviewed report to every source flow in a semantic-review task."""

import io
import json
import os
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.verify import sha256_file, verify_case


def _read(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _covered_flows(task: dict, draft_spec: dict, final_spec: dict) -> list:
    """Check immutable script lineage and reject unchanged provisional scenarios."""
    required = task.get("flows")
    draft = draft_spec.get("flows")
    final = final_spec.get("flows")
    if (not isinstance(required, list) or not required or
            not isinstance(draft, list) or len(draft) != len(required) or
            not isinstance(final, list) or not final):
        raise ValueError("analysis task or reviewed report has no complete flow list")
    draft_by_hash = {flow.get("source_script_sha256"): flow for flow in draft
                     if isinstance(flow, dict)}
    final_by_hash = {flow.get("source_script_sha256"): flow for flow in final
                     if isinstance(flow, dict) and flow.get("source_script_sha256")}
    required_hashes = {flow.get("source_script_sha256") for flow in required
                       if isinstance(flow, dict)}
    if (len(required_hashes) != len(required) or len(draft_by_hash) != len(draft) or
            len(final_by_hash) != sum(bool(flow.get("source_script_sha256"))
                                      for flow in final if isinstance(flow, dict)) or
            None in required_hashes or set(draft_by_hash) != required_hashes):
        raise ValueError("source script hashes are missing or duplicated")
    covered = []
    for item in required:
        digest = item["source_script_sha256"]
        old = draft_by_hash[digest]
        reviewed = final_by_hash.get(digest)
        if reviewed is None:
            raise ValueError(f"reviewed report omits investigated flow: {item['id']}")
        expected = reviewed.get("expected")
        evidence = reviewed.get("evidence")
        if (reviewed.get("review_status") == "needs_semantic_review" or
                not isinstance(reviewed.get("id"), str) or not reviewed["id"] or
                not isinstance(expected, list) or not expected or
                any(not isinstance(value, str) or not value.strip() or
                    "待审阅" in value for value in expected) or
                expected == old.get("expected") or
                not isinstance(reviewed.get("verification"), str) or
                not reviewed["verification"].strip() or
                not isinstance(evidence, list) or "app.all" not in evidence):
            raise ValueError(f"flow lacks concrete reviewed assertions: {item['id']}")
        covered.append({"task_flow_id": item["id"],
                        "report_flow_id": reviewed["id"],
                        "source_script_sha256": digest,
                        "assertion_count": len(expected),
                        "has_final_view_assertion": isinstance(reviewed.get("final_view"), dict)})
    return covered


def validate_analysis_delivery(task_case: Path, report_case: Path,
                               run_case: Optional[Path] = None) -> dict:
    task_case = task_case.resolve(strict=True)
    report_case = report_case.resolve(strict=True)
    if task_case == report_case:
        raise ValueError("task and reviewed report must be separate cases")
    with redirect_stdout(io.StringIO()):
        if not verify_case(task_case) or not verify_case(report_case):
            raise ValueError("analysis task or reviewed report failed hash verification")
    task = _read(task_case / "task.json")
    index = _read(report_case / "report-index.json")
    draft = _read(task_case / "feature-spec.json")
    spec = _read(report_case / "feature-spec.json")
    findings = _read(report_case / "findings.json")
    investigation = index.get("evidence", {}).get("app.all", {})
    if (task.get("kind") != "agent_semantic_review_task" or
            task.get("status") != "needs_semantic_review" or
            index.get("target_bundle_id") != task.get("target_bundle_id") or
            spec.get("target_bundle_id") != task.get("target_bundle_id") or
            findings.get("target_bundle_id") != task.get("target_bundle_id") or
            index.get("source_case_index_sha256") != task.get("analysis_index_sha256") or
            Path(index.get("source_case", "")).resolve() !=
            Path(task.get("analysis_case", "")).resolve() or
            investigation.get("kind") != "app_investigation" or
            investigation.get("sha256") != task.get("app_investigation_sha256") or
            spec.get("review_status") == "needs_semantic_review" or
            findings.get("review_status") == "needs_semantic_review"):
        raise ValueError("reviewed report is provisional or has a different source identity")
    covered = _covered_flows(task, draft, spec)
    run_record = None
    if run_case is not None:
        run_case = run_case.resolve(strict=True)
        with redirect_stdout(io.StringIO()):
            if not verify_case(run_case):
                raise ValueError("agent run failed hash verification")
        run = _read(run_case / "run.json")
        if (run.get("kind") != "agent_execution" or
                run.get("status") != "agent_exited_unverified" or
                run.get("task_kind") != "agent_semantic_review_task" or
                Path(run.get("task_case", "")).resolve() != task_case or
                run.get("task_manifest_sha256") != sha256_file(task_case / "manifest.json")):
            raise ValueError("agent run does not belong to this semantic review task")
        run_record = {"case": str(run_case),
                      "manifest_sha256": sha256_file(run_case / "manifest.json"),
                      "provider": run.get("provider"),
                      "agent_session_id": run.get("agent_session_id")}
    return {"task_case": str(task_case),
            "task_manifest_sha256": sha256_file(task_case / "manifest.json"),
            "report_case": str(report_case),
            "report_index_sha256": sha256_file(report_case / "report-index.json"),
            "target_bundle_id": task["target_bundle_id"],
            "source_analysis_sha256": task["analysis_index_sha256"],
            "source_investigation_sha256": task["app_investigation_sha256"],
            "flow_coverage": covered,
            "agent_run": run_record}


def create_analysis_delivery(task_case: Path, report_case: Path, output: Path,
                             run_case: Optional[Path] = None) -> Path:
    """Record source-linked report coverage without claiming semantic correctness."""
    if _read(task_case / "manifest.json").get("kind") == "ios_analysis":
        if run_case is not None:
            raise ValueError("UI behavior delivery records the current review; external deep-agent runs are a separate contract")
        from copyapp.ios_delivery import create_behavior_delivery
        return create_behavior_delivery(task_case, report_case, output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"analysis delivery output is not empty: {output}")
    result = validate_analysis_delivery(task_case, report_case, run_case)
    output.mkdir(parents=True, exist_ok=True)
    report = Path(result["report_case"])
    shutil.copyfile(report / "findings.json", output / "reviewed-findings.json")
    shutil.copyfile(report / "feature-spec.json", output / "reviewed-feature-spec.json")
    result.update({"schema_version": 1, "kind": "analysis_delivery",
                   "status": "source_linked_report_ready_for_review",
                   "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "findings_sha256": sha256_file(output / "reviewed-findings.json"),
                   "feature_spec_sha256": sha256_file(output / "reviewed-feature-spec.json"),
                   "scope_limit": "Script lineage and report hashes are checked; correctness of reverse-engineered function semantics and unobserved app behavior require review."})
    _write(output / "delivery.json", result)
    def link(path: Path, label: str) -> str:
        return f"[{label}]({os.path.relpath(path, output)})"
    lines = ["# 深度分析交付核验", "",
             f"- App：`{result['target_bundle_id']}`；状态：`{result['status']}`。",
             f"- 调查流程覆盖：{len(result['flow_coverage'])}/{len(result['flow_coverage'])}。",
             f"- 来源：{link(Path(result['task_case']) / 'TASK.md', 'Agent 审阅任务')} · "
             f"{link(report / 'report.md', '正式报告')} · "
             f"{link(output / 'reviewed-feature-spec.json', '规格快照')} · "
             f"{link(output / 'reviewed-findings.json', '结论快照')}。", "",
             "| 调查流程 | 报告流程 | 可检验结果数 | 末端视图断言 |",
             "| --- | --- | ---: | --- |"]
    for flow in result["flow_coverage"]:
        lines.append(f"| `{flow['task_flow_id']}` | `{flow['report_flow_id']}` | "
                     f"{flow['assertion_count']} | "
                     f"{'有' if flow['has_final_view_assertion'] else '无'} |")
    if result["agent_run"] is None:
        lines.extend(["", "未附独立 Coding Agent 的运行记录；报告作者未由此核验确认。"])
    else:
        lines.extend(["", f"Agent CLI：{link(Path(result['agent_run']['case']) / 'run.json', '运行记录')}。"])
    lines.extend(["", "已核对来源分析、调查、原版脚本、正式报告及每条规格的证据归属。"
                  "函数解释的正确性、视觉完整性和未调查页面仍需审阅或补充真机实验。", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {
        "schema_version": 1, "kind": "analysis_delivery", "status": result["status"],
        "task_manifest_sha256": result["task_manifest_sha256"],
        "report_index_sha256": result["report_index_sha256"],
        "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                     for name in ("delivery.json", "report.md", "reviewed-findings.json",
                                  "reviewed-feature-spec.json")],
    })
    return output / "report.md"
