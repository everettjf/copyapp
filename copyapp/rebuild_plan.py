"""Derive paired rebuild playbooks from a verified analysis report."""

import io
import json
import re
import shlex
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.compare_playbooks import _load_run
from copyapp.rebuild_check import _preflight, check_final_view
from copyapp.verify import checked_path, sha256_file, verify_case


FLOW_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _captured_candidate(root: Path, kind: str, flow_id: str, target: str,
                        final_view: Optional[dict]) -> dict:
    play = root / "playbook" if kind == "flow_capture" else root
    with redirect_stdout(io.StringIO()):
        # A cited run may be valid evidence without satisfying the stricter
        # readiness contract required for an original/rebuilt comparison.
        manifest, script = _load_run(play, require_comparable=False)
    if (manifest.get("bundle_id") != target or script.get("bundle_id") != target or
            script.get("fresh_launch") is not True):
        raise ValueError(f"cited playbook target or initial state differs: {root}")
    final_view_passed = None
    if final_view is not None and kind == "flow_capture":
        final_view_passed = check_final_view(root, final_view)["passed"]
    return {"kind": kind, "script_path": play / "playbook.json",
            "script_sha256": sha256_file(play / "playbook.json"),
            "scenario_id": script["scenario_id"],
            "exact_scenario": script["scenario_id"] == flow_id,
            "final_view_passed": final_view_passed}


def _candidates(report: Path, entry: dict, flow_id: str, target: str,
                final_view: Optional[dict]) -> list[dict]:
    kind = entry.get("kind")
    if kind in ("playbook", "flow_capture"):
        root = checked_path(report, entry["path"]).parent
        return [_captured_candidate(root, kind, flow_id, target, final_view)]
    if kind != "app_investigation":
        return []
    root = checked_path(report, entry["path"]).parent
    manifest = _read(root / "manifest.json")
    if (manifest.get("kind") != "investigated_app" or
            manifest.get("bundle_id") != target or
            manifest.get("status") != "complete" or
            not isinstance(manifest.get("flows"), list)):
        raise ValueError(f"cited app investigation identity differs: {root}")
    found = []
    for index, flow in enumerate(manifest["flows"], 1):
        child_name = f"flows/flow-{index:02d}"
        if (not isinstance(flow, dict) or flow.get("index") != index or
                flow.get("status") != "complete" or
                flow.get("manifest") != child_name + "/manifest.json"):
            raise ValueError(f"cited app investigation flow differs: {root}")
        child = root / child_name
        child_manifest = _read(child / "manifest.json")
        if (sha256_file(child / "manifest.json") != flow.get("manifest_sha256") or
                child_manifest.get("source_script_sha256") != flow.get("script_sha256") or
                child_manifest.get("bundle_id") != target or
                child_manifest.get("status") != "complete"):
            raise ValueError(f"cited app investigation child differs: {child}")
        captured = _captured_candidate(child / "flow", "flow_capture",
                                       flow_id, target, final_view)
        if captured["script_sha256"] != flow["script_sha256"]:
            raise ValueError(f"cited app investigation script differs: {child}")
        captured["source_flow_index"] = index
        found.append(captured)
    return found


def create_rebuild_plan(report: Path, output: Path, backend: str = "ios-mcp",
                        flow_ids: Optional[list[str]] = None) -> Path:
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    report = report.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(report):
            raise ValueError("analysis report evidence hash mismatch")
    index = _read(report / "report-index.json")
    spec = _read(report / "feature-spec.json")
    target = spec.get("target_bundle_id")
    rebuilt = spec.get("rebuilt_bundle_id")
    flows = spec.get("flows")
    if (index.get("target_bundle_id") != target or
            spec.get("schema_version") != 1 or
            spec.get("review_status") == "needs_semantic_review" or
            not isinstance(target, str) or not target or
            not isinstance(rebuilt, str) or not rebuilt or rebuilt == target or
            not isinstance(flows, list) or not flows):
        raise ValueError("report has no reviewed rebuild specification or bundle identity")
    known = {item.get("id"): item for item in flows if isinstance(item, dict)}
    if len(known) != len(flows) or any(not isinstance(key, str) or not FLOW_ID.fullmatch(key)
                                      for key in known):
        raise ValueError("feature specification has invalid or duplicate flow IDs")
    selected = flow_ids or list(known)
    if (not selected or len(selected) > 12 or len(set(selected)) != len(selected) or
            any(item not in known for item in selected)):
        raise ValueError("provide 1–12 unique flow IDs from the report")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report / "feature-spec.json", output / "feature-spec.json")
    entries = index.get("evidence", {})
    records = []
    pairs = []
    for flow_id in selected:
        flow = known[flow_id]
        if flow.get("review_status") == "needs_semantic_review":
            raise ValueError(f"flow still needs semantic review: {flow_id}")
        candidates = []
        for evidence_id in flow.get("evidence", []):
            entry = entries.get(evidence_id)
            if not isinstance(entry, dict):
                raise ValueError(f"flow cites missing report evidence: {flow_id} {evidence_id}")
            for found in _candidates(report, entry, flow_id, target,
                                     flow.get("final_view")):
                found["evidence_id"] = evidence_id
                candidates.append(found)
        if flow.get("source_script_sha256"):
            candidates = [item for item in candidates if
                          item["script_sha256"] == flow["source_script_sha256"]]
        if not candidates:
            records.append({"flow_id": flow_id, "status": "needs_original_playbook",
                            "reason": "no cited playbook or flow capture in the report"})
            continue
        final_matches = [item for item in candidates if item["final_view_passed"] is True]
        if flow.get("final_view") is not None and any(
                item["kind"] == "flow_capture" for item in candidates) and not final_matches:
            records.append({"flow_id": flow_id, "status": "no_matching_final_view",
                            "reason": "cited captured final UIKit state does not match the feature specification"})
            continue
        exact = [item for item in candidates if item["exact_scenario"]]
        pool = final_matches or exact or candidates
        hashes = {item["script_sha256"] for item in pool}
        if len(hashes) != 1:
            records.append({"flow_id": flow_id, "status": "ambiguous_playbooks",
                            "candidates": [{"evidence_id": item["evidence_id"],
                                            "script_sha256": item["script_sha256"]}
                                           for item in pool]})
            continue
        source = next((item for item in pool if item["kind"] == "flow_capture"), pool[0])
        original = _read(source["script_path"])
        screenshots = [step for step in original.get("steps", [])
                       if isinstance(step, dict) and step.get("action") == "screenshot"]
        if (not screenshots or any(step.get("stable") is not True or
                not isinstance(step.get("ready_contains"), str) or
                not step["ready_contains"] for step in screenshots)):
            records.append({"flow_id": flow_id,
                            "status": "needs_verified_screenshot",
                            "source_evidence_id": source["evidence_id"],
                            "source_script_sha256": source["script_sha256"],
                            "reason": "cited playbook needs a stable screenshot with ready_contains; recapture it before paired comparison"})
            continue
        clone = dict(original)
        clone["bundle_id"] = rebuilt
        root = output / "flows" / flow_id
        first = root / "original.json"
        second = root / "rebuilt.json"
        _write(first, original)
        _write(second, clone)
        pairs.append((flow_id, first, second))
        records.append({"flow_id": flow_id, "status": "ready_for_implementation",
                        "source_evidence_id": source["evidence_id"],
                        **({"source_flow_index": source["source_flow_index"]}
                           if "source_flow_index" in source else {}),
                        "source_script_sha256": source["script_sha256"],
                        "scenario_id": source["scenario_id"],
                        "original_script": str(first.relative_to(output)),
                        "rebuilt_script": str(second.relative_to(output)),
                        "note": "The rebuilt playbook only changes the Bundle ID; its UI labels and assertions must be implemented by the new app."})
    if pairs:
        _preflight(output / "feature-spec.json", pairs)
    argv = ["copyapp", "rebuild-check", "--udid", "<UDID>",
            "--feature-spec", str(output / "feature-spec.json"),
            "--backend", backend]
    for flow_id, first, second in pairs:
        argv.extend(["--pair", flow_id, str(first), str(second)])
    argv.extend(["--out", "<NEW_CASE>"])
    plan = {"schema_version": 1, "kind": "rebuild_plan",
            "status": "complete", "target_bundle_id": target,
            "rebuilt_bundle_id": rebuilt, "ui_backend": backend,
            "source_report_index_sha256": sha256_file(report / "report-index.json"),
            "feature_spec_sha256": sha256_file(output / "feature-spec.json"),
            "ready_count": len(pairs), "needs_attention_count": len(records) - len(pairs),
            "flows": records, "rebuild_check_argv": argv,
            "limitation": "A structurally valid paired script is an implementation target, not proof that a rebuilt app exists or behaves the same."}
    _write(output / "rebuild-plan.json", plan)
    lines = ["# 复刻实施交接", "", f"- 原版：`{target}`；复刻 Bundle ID：`{rebuilt}`",
             f"- 可直接用于结构检查的成对脚本：{len(pairs)}；需要补充或澄清证据：{len(records)-len(pairs)}。",
             "- 已复制所选原版脚本，并仅替换顶层 Bundle ID 生成复刻脚本草案；",
             "  复刻 App 需要实现相同的界面标签、状态和截图就绪条件。", "",
             "| 规格流程 | 状态 | 来源证据 |", "| --- | --- | --- |"]
    lines.extend(f"| `{item['flow_id']}` | `{item['status']}` | "
                 f"`{item.get('source_evidence_id', '—')}` |" for item in records)
    lines.extend(["", "安装并确认复刻 App 在目标设备可启动后，再运行：", "",
                  "```sh", " ".join(shlex.quote(value) for value in argv), "```", "",
                  "执行后仍需逐张检查视觉差异，并补测规格中未覆盖的状态。", ""])
    (output / "runbook.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {"schema_version": 1, "kind": "rebuild_plan", "status": "complete",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source_report_index_sha256": plan["source_report_index_sha256"],
                "evidence": [{"path": str(path.relative_to(output)), "sha256": sha256_file(path)}
                             for path in sorted(output.rglob("*")) if path.is_file()]}
    _write(output / "manifest.json", manifest)
    return output / "manifest.json"
