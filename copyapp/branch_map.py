"""Correlate verified raw button arguments with bounded branch-entry hits."""

import io
import json
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from copyapp.flow_capture import validate_flow_pair, validate_flow_trace_pair
from copyapp.verify import sha256_file, verify_case


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _safe(value: object) -> str:
    return " ".join(str(value).split()).replace("|", "/")[:80]


def summarize_mappings(observations: list[dict]) -> list[dict]:
    """Treat an uninstrumented offset as unknown, never as a negative hit."""
    grouped = defaultdict(list)
    for item in observations:
        if item["status"] == "correlated":
            grouped[item["raw_argument"]].append(item)
    mappings = []
    for value, rows in sorted(grouped.items()):
        signatures = {tuple(sorted(row["branch_hits"])) for row in rows}
        observed = {offset for row in rows for offset in row["branch_hits"]}
        if not observed:
            status, branch = "no_instrumented_branch", None
        elif len(observed) > 1:
            status, branch = "multiple_branches", None
        else:
            branch = next(iter(observed))
            if all(branch not in row["instrumented_offsets"] or
                   row["branch_hits"].get(branch, 0) > 0 for row in rows):
                status = "single_observed_branch"
            else:
                status, branch = "inconsistent_or_partial", None
        mappings.append({"raw_argument": value, "labels": sorted({row["label"] for row in rows
                                                                      if row["label"]}),
                         "steps": len(rows), "status": status,
                         "candidate_branch_offset": branch,
                         "observed_signatures": [list(signature) for signature in sorted(signatures)]})
    return mappings


def build_branch_map(flows: list[Path], method: str, binary: Path,
                     output: Path) -> Path:
    """Create an observation map; ambiguous steps never become single dispatch claims."""
    if not flows or len(flows) > 32:
        raise ValueError("provide 1–32 flow cases")
    if len({path.resolve() for path in flows}) != len(flows):
        raise ValueError("flow cases must be unique")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    binary = binary.resolve(strict=True)
    digest = sha256_file(binary)
    identity = None
    cases = []
    observations = []
    for source in flows:
        source = source.resolve(strict=True)
        with redirect_stdout(io.StringIO()):
            if not verify_case(source):
                raise ValueError(f"flow evidence hash mismatch: {source}")
            for child in ("playbook", "trace", "view-tree"):
                if not verify_case(source / child):
                    raise ValueError(f"flow child evidence hash mismatch: {source / child}")
        manifest = _read(source / "manifest.json")
        play = _read(source / "playbook/manifest.json")
        plan = _read(source / "playbook/playbook.json")
        trace = _read(source / "trace/trace.json")
        views = _read(source / "view-tree/manifest.json")
        bundle = manifest.get("bundle_id")
        device = manifest.get("device_id_sha256_prefix")
        backend = manifest.get("ui_backend")
        if manifest.get("status") != "complete" or not all(
                isinstance(item, str) and item for item in (bundle, device, backend)):
            raise ValueError(f"flow identity or completion is invalid: {source}")
        if (sha256_file(source / "playbook/playbook.json") !=
                manifest.get("source_script_sha256") or
                plan.get("bundle_id") != bundle or
                len(plan.get("steps", [])) != len(play.get("steps", []))):
            raise ValueError(f"flow playbook binding is invalid: {source}")
        validate_flow_pair(play, views, bundle, device, backend)
        validate_flow_trace_pair(play, trace, bundle, device, {digest})
        if (trace.get("static_binary_sha256") != digest or
                method not in trace.get("arg2_u32_methods", []) or
                not trace.get("branch_requested_offsets")):
            raise ValueError(f"raw argument, branches or binary binding missing: {source}")
        current = (bundle, device, digest, method)
        if identity is None:
            identity = current
        elif current != identity:
            raise ValueError("flow cases do not share app, device, binary and method")
        method_index = trace["requested_methods"].index(method)
        offsets = trace["branch_requested_offsets"]
        cases.append({"path": str(source), "manifest_sha256": sha256_file(source / "manifest.json"),
                      "scenario_id": manifest.get("scenario_id"), "ui_backend": backend,
                      "branch_offsets": offsets})
        for step in trace["steps"]:
            index = step["index"]
            action = plan["steps"][index - 1]
            raw = step.get("arg2_u32_hits", [])
            static_values = [hit["value"] for hit in raw
                             if hit["type"] == "static_hit" and hit["index"] == method_index]
            current_values = [hit["value"] for hit in raw
                              if hit["type"] == "method_hit" and hit["index"] == method_index]
            branches = {offset: count for offset, count in
                        zip(offsets, step["branch_call_counts"]) if count}
            if step.get("arg2_u32_truncated"):
                status, value = "truncated", None
            elif len(static_values) != 1 or len(current_values) != 1:
                status, value = "multiple_or_missing_calls", None
            elif static_values[0] != current_values[0]:
                status, value = "hook_disagreement", None
            else:
                status, value = "correlated", static_values[0]
            observations.append({"case": len(cases) - 1, "step": index,
                                 "action": step["action"],
                                 "label": _safe(action.get("label", "")) if step["action"] == "tap_label" else None,
                                 "raw_argument": value, "status": status,
                                 "static_values": static_values,
                                 "current_values": current_values,
                                 "instrumented_offsets": offsets,
                                 "branch_hits": branches})
    mappings = summarize_mappings(observations)
    output.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "kind": "branch_observation_map",
              "bundle_id": identity[0], "device_id_sha256_prefix": identity[1],
              "binary_sha256": digest, "binary_path": str(binary),
              "method": method, "sources": cases,
              "observations": observations, "mappings": mappings,
              "limitation": "Temporal, selected-entry observations only. Raw argument type, dispatch causality, complete branches and function semantics require independent evidence."}
    (output / "branch-map.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    lines = ["# 分支观测映射", "", f"- App：`{identity[0]}`；方法：`{method}`",
             f"- 主程序 SHA-256：`{digest}`；设备 ID 前缀：`{identity[1]}`",
             f"- 来源：{len(cases)} 份已校验流程，{len(observations)} 次点击窗口。", "",
             "| 原始参数 | 标签 | 步数 | 观测状态 | 单一分支候选 |",
             "| ---: | --- | ---: | --- | --- |"]
    for item in mappings:
        lines.append(f"| {item['raw_argument']} | {_safe(', '.join(item['labels']))} | "
                     f"{item['steps']} | `{item['status']}` | "
                     f"`{item['candidate_branch_offset'] or '—'}` |")
    lines.extend(["", "以上是限定点击窗口和所选分支入口的时间相关性；原始参数类型、调用因果、"
                  "未挂钩分支和函数语义仍需独立证据。逐步计数与来源哈希见 `branch-map.json`。", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {"schema_version": 1, "kind": "branch_observation_map",
                "status": "complete", "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "bundle_id": identity[0], "device_id_sha256_prefix": identity[1],
                "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                             for name in ("branch-map.json", "report.md")]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    return output / "manifest.json"


def validate_branch_map(path: Path, bundle: str, device_prefix: str,
                        binary_hashes: set[str]) -> dict:
    """Recompute an imported map from its pinned source flows before citing it."""
    path = path.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("branch map or source evidence hash mismatch")
    manifest = _read(path / "manifest.json")
    mapped = _read(path / "branch-map.json")
    files = {item.get("path") for item in manifest.get("evidence", [])
             if isinstance(item, dict)}
    if (manifest.get("kind") != "branch_observation_map" or
            manifest.get("status") != "complete" or
            manifest.get("bundle_id") != bundle or
            manifest.get("device_id_sha256_prefix") != device_prefix or
            mapped.get("bundle_id") != bundle or
            mapped.get("device_id_sha256_prefix") != device_prefix or
            mapped.get("binary_sha256") not in binary_hashes or
            files != {"branch-map.json", "report.md"} or
            not isinstance(mapped.get("method"), str) or
            not isinstance(mapped.get("sources"), list)):
        raise ValueError("branch map identity, binary or evidence list differs")
    sources = [Path(item["path"]) for item in mapped["sources"]]
    with TemporaryDirectory() as scratch:
        build_branch_map(sources, mapped["method"], Path(mapped["binary_path"]),
                         Path(scratch) / "recomputed")
        recomputed = _read(Path(scratch) / "recomputed/branch-map.json")
        if recomputed != mapped:
            raise ValueError("branch map does not match its source flow observations")
    return {"manifest": manifest, "record": mapped,
            "files": ["branch-map.json", "report.md", "manifest.json"],
            "source_paths": sources, "binary_path": Path(mapped["binary_path"])}
