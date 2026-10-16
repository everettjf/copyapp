"""Run selected original/rebuilt UI flows as one version-pinned device check."""

import asyncio
import hashlib
import io
import json
import math
import re
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from copyapp.compare_playbooks import _load_run, compare_playbooks
from copyapp.flow_capture import capture_flow, validate_flow_pair
from copyapp.install import _installed_app
from copyapp.investigate_flow import _files
from copyapp.playbook import run_playbook
from copyapp.verify import sha256_file, verify_case


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _identity(app: dict, bundle: str) -> dict:
    version = app.get("CFBundleShortVersionString")
    build = app.get("CFBundleVersion")
    path = app.get("Path")
    if (version is not None and (not isinstance(version, str) or not version) or
            not all(isinstance(value, str) and value for value in (build, path))):
        raise ValueError(f"installed app identity is incomplete: {bundle}")
    return {"bundle_id": bundle, "version": version, "build": build, "path": path}


def _preflight(spec_path: Path, pairs: List[Tuple[str, Path, Path]]) -> Tuple[dict, list]:
    spec = _read(spec_path)
    target = spec.get("target_bundle_id")
    rebuilt = spec.get("rebuilt_bundle_id")
    flows = spec.get("flows")
    if (spec.get("schema_version") != 1 or not isinstance(flows, list) or
            spec.get("review_status") == "needs_semantic_review" or
            any(isinstance(flow, dict) and flow.get("review_status") == "needs_semantic_review"
                for flow in flows) or
            not isinstance(target, str) or not isinstance(rebuilt, str) or
            target == rebuilt or not 1 <= len(pairs) <= 12):
        raise ValueError("invalid rebuild feature spec or pair count")
    known = {item.get("id") for item in flows if isinstance(item, dict)}
    if len(known) != len(flows):
        raise ValueError("feature spec has duplicate or invalid flow IDs")
    records = []
    flow_specs = {item["id"]: item for item in flows}
    for flow_id, original_path, rebuilt_path in pairs:
        if (not isinstance(flow_id, str) or
                not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", flow_id) or
                flow_id not in known or any(item["flow_id"] == flow_id for item in records)):
            raise ValueError(f"invalid, duplicate, or unspecified flow ID: {flow_id}")
        original = _read(original_path)
        clone = _read(rebuilt_path)
        final_view = flow_specs[flow_id].get("final_view")
        if final_view is not None:
            extra = final_view.get("also", []) if isinstance(final_view, dict) else None
            absent = final_view.get("absent", []) if isinstance(final_view, dict) else None
            if (not isinstance(extra, list) or len(extra) > 8 or
                    not isinstance(absent, list) or len(absent) > 8 or
                    any(not isinstance(item, dict) for item in extra + absent)):
                raise ValueError(f"invalid final view assertion: {flow_id}")
            for assertion in [final_view] + extra + absent:
                region = assertion.get("region_points") if isinstance(assertion, dict) else None
                if (not isinstance(assertion.get("text"), str) or
                        not assertion["text"] or not isinstance(region, list) or
                        len(region) != 4 or
                        any(type(value) not in (int, float) or not math.isfinite(value) or
                            not 0 <= value <= 10000 for value in region) or
                        not (region[0] < region[2] and region[1] < region[3])):
                    raise ValueError(f"invalid final view assertion: {flow_id}")
        first_steps, second_steps = original.get("steps"), clone.get("steps")
        if (original.get("schema_version") != 1 or clone.get("schema_version") != 1 or
                original.get("bundle_id") != target or clone.get("bundle_id") != rebuilt or
                original.get("scenario_id") != clone.get("scenario_id") or
                not original.get("scenario_id") or
                original.get("fresh_launch") is not True or
                clone.get("fresh_launch") is not True or
                original.get("visual_checks", []) != clone.get("visual_checks", []) or
                not isinstance(first_steps, list) or
                not isinstance(second_steps, list) or len(first_steps) != len(second_steps)):
            raise ValueError(f"paired scripts differ in app, scenario or steps: {flow_id}")
        screenshots = 0
        for index, (first, second) in enumerate(zip(first_steps, second_steps), 1):
            action = first.get("action")
            if action != second.get("action"):
                raise ValueError(f"action sequence differs in {flow_id} step {index}")
            if action == "tap_label" and first.get("label") != second.get("label"):
                raise ValueError(f"tap labels differ in {flow_id} step {index}")
            if action == "tap_label" and first.get("region_points") != second.get("region_points"):
                raise ValueError(f"tap label regions differ in {flow_id} step {index}")
            region = first.get("region_points") if action == "tap_label" else None
            if region is not None and (
                    not isinstance(region, list) or len(region) != 4 or
                    any(type(value) not in (int, float) or not math.isfinite(value)
                        for value in region) or
                    not 0 <= region[0] < region[2] <= 10000 or
                    not 0 <= region[1] < region[3] <= 10000):
                raise ValueError(f"invalid tap label region in {flow_id} step {index}")
            if action == "observe" and first.get("contains", []) != second.get("contains", []):
                raise ValueError(f"observation conditions differ in {flow_id} step {index}")
            if action == "observe" and first.get("exact_labels", []) != second.get("exact_labels", []):
                raise ValueError(f"exact observation labels differ in {flow_id} step {index}")
            if action == "tap" and (first.get("x"), first.get("y")) != (
                    second.get("x"), second.get("y")):
                raise ValueError(f"tap coordinates differ in {flow_id} step {index}")
            if action == "expect_foreground" and first.get("bundle_id") != second.get("bundle_id"):
                raise ValueError(f"handoff destination differs in {flow_id} step {index}")
            if action == "screenshot":
                screenshots += 1
                if first.get("ready_ocr_labels") != second.get("ready_ocr_labels"):
                    raise ValueError(f"screenshot visual labels differ in {flow_id} step {index}")
                for step in (first, second):
                    if step.get("stable") is not True or not step.get("ready_contains"):
                        raise ValueError(f"unverified screenshot in {flow_id} step {index}")
                    labels = step.get("ready_ocr_labels")
                    if labels is not None and (not isinstance(labels, list) or not labels or
                                               any(not isinstance(label, str) or not label.strip()
                                                   for label in labels)):
                        raise ValueError(f"invalid screenshot visual labels in {flow_id} step {index}")
        if not screenshots:
            raise ValueError(f"paired scripts have no comparable screenshot: {flow_id}")
        records.append({"flow_id": flow_id, "scenario_id": original["scenario_id"],
                        "final_view": final_view,
                        "original_script": str(original_path.resolve(strict=True)),
                        "original_script_sha256": sha256_file(original_path),
                        "rebuilt_script": str(rebuilt_path.resolve(strict=True)),
                        "rebuilt_script_sha256": sha256_file(rebuilt_path)})
    return spec, records


def _verified_run(path: Path, bundle: str, scenario: str, prefix: str,
                  backend: str, final_view: bool = False) -> bool:
    if not (path / "manifest.json").is_file():
        return False
    manifest = _read(path / "manifest.json")
    if manifest.get("status") != "complete":
        return False
    play_path = path / "playbook" if final_view else path
    if final_view:
        with redirect_stdout(io.StringIO()):
            if not verify_case(path) or not verify_case(path / "view-tree"):
                raise ValueError(f"saved final view evidence failed hash check: {path}")
        views = _read(path / "view-tree/manifest.json")
        play = _read(play_path / "manifest.json")
        validate_flow_pair(play, views, bundle, prefix, backend)
        if manifest.get("source_script_sha256") != sha256_file(play_path / "playbook.json"):
            raise ValueError(f"saved flow script identity differs: {path}")
    observed, _ = _load_run(play_path)
    if (observed.get("bundle_id") != bundle or observed.get("scenario_id") != scenario or
            observed.get("device_id_sha256_prefix") != prefix or
            observed.get("ui_backend") != backend):
        raise ValueError(f"existing playbook belongs to a different target: {path}")
    return True


def _prepare_run(path: Path, bundle: str, scenario: str, prefix: str,
                 backend: str, resume: bool, final_view: bool = False) -> bool:
    if not resume or not path.exists():
        return False
    if _verified_run(path, bundle, scenario, prefix, backend, final_view):
        return True
    attempts = path.parent / "attempts"
    attempts.mkdir(exist_ok=True)
    destination = attempts / f"{path.name}-{len(list(attempts.iterdir())) + 1:02d}"
    shutil.move(str(path), str(destination))
    return False


def check_final_view(flow_case: Path, assertion: dict) -> dict:
    """Check one visible UIKit text node within a bounded screen region."""
    tree_path = flow_case / "view-tree/view-tree.json"
    tree = _read(tree_path)
    nodes = tree.get("nodes")
    if not isinstance(nodes, list) or len(nodes) > 500:
        raise ValueError("invalid saved UIKit node list")
    def matches_for(expected: dict, include_button: bool) -> list:
        region = expected["region_points"]
        matches = []
        for index, node in enumerate(nodes):
            if not isinstance(node, dict) or node.get("id") != index:
                raise ValueError("UIKit node IDs are not ordered")
            class_name = str(node.get("class_name", ""))
            if (node.get("text") != expected["text"] or
                    not (class_name.endswith("UILabel") or
                         class_name in ("UITableViewLabel", "UITabBarButtonLabel",
                                        "MTUITimeView") or
                         (include_button and class_name == "UIButtonLabel"))):
                continue
            x = y = 0.0
            current = index
            seen = set()
            visible = True
            width = height = 0.0
            while current is not None:
                if current in seen or not 0 <= current < len(nodes):
                    raise ValueError("UIKit view ancestry is cyclic or invalid")
                seen.add(current)
                ancestor = nodes[current]
                frame = ancestor.get("frame")
                if (not isinstance(frame, dict) or
                        any(type(frame.get(key)) not in (int, float)
                            for key in ("x", "y", "width", "height"))):
                    raise ValueError("UIKit node frame is invalid")
                x += frame["x"]
                y += frame["y"]
                if current == index:
                    width, height = frame["width"], frame["height"]
                if ancestor.get("hidden") is True or ancestor.get("alpha", 1) <= 0.01:
                    visible = False
                current = ancestor.get("parent")
            center = (x + width / 2, y + height / 2)
            if (visible and width > 0 and height > 0 and
                    region[0] <= center[0] <= region[2] and
                    region[1] <= center[1] <= region[3]):
                matches.append({"node_id": index, "text": node["text"],
                                "class_name": node["class_name"],
                                "absolute_frame": {"x": x, "y": y,
                                                   "width": width, "height": height}})
        return matches

    matches = matches_for(assertion, False)
    also_checks = [{"expected": item, "matches": matches_for(item, True)}
                   for item in assertion.get("also", [])]
    for item in also_checks:
        item["passed"] = len(item["matches"]) == 1
    absent_checks = [{"expected": item, "matches": matches_for(item, True)}
                     for item in assertion.get("absent", [])]
    for item in absent_checks:
        item["passed"] = len(item["matches"]) == 0
    result = {"schema_version": 1, "kind": "final_uikit_text_check",
              "expected": assertion, "matches": matches,
              "also_checks": also_checks,
              "absent_checks": absent_checks,
              "passed": (len(matches) == 1 and
                         all(item["passed"] for item in also_checks + absent_checks)),
              "view_tree_sha256": sha256_file(tree_path),
              "flow_manifest_sha256": sha256_file(flow_case / "manifest.json")}
    return result


def _final_view_check(flow_case: Path, assertion: dict, output: Path) -> dict:
    result = check_final_view(flow_case, assertion)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return result


def _write_report(output: Path, record: dict) -> None:
    apps = record["installed_apps"]
    lines = ["# Copy APP 多流程真机对照", "",
             f"- 状态：`{record['status']}`",
             f"- 设备 ID 哈希前缀：`{record['device_id_sha256_prefix']}`",
             f"- UI 后端：`{record['ui_backend']}`",
             f"- 原版：`{apps[0]['bundle_id']}` {apps[0]['version']} ({apps[0]['build']})",
             f"- 复刻版：`{apps[1]['bundle_id']}` {apps[1]['version']} ({apps[1]['build']})",
             "- 功能规格：[本次固定副本](feature-spec.json)", "",
             "| 规格流程 | 场景 | 成对截图 | 最终 UIKit 文本 | 显式视觉检查 | 逐流程证据 |",
             "| --- | --- | ---: | --- | --- | --- |"]
    for item in record["flows"]:
        flow = item["flow_id"]
        final = item.get("final_view_status", "未设置")
        lines.append(f"| `{flow}` | `{item['scenario_id']}` | {item['screenshot_pairs']} | "
                     f"{final} | {item['checks_status']} | [对照报告](flows/{flow}/comparison/report.md) |")
    if record["status"] != "complete":
        error = record.get("error") or {}
        lines.extend(["", f"中断原因：{error.get('type', 'unknown')}：{error.get('message', '')}"])
    lines.extend(["", "`complete` 表示所选脚本执行、截图稳定/就绪检查和成对证据保存成功；"
                  "若视觉检查为 `unreviewed`，仍需审阅图片及功能结果。"
                  "像素差值和证据哈希不能单独证明整个 App 的行为等价。", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def rebuild_check(udid: str, spec_path: Path, pairs: List[Tuple[str, Path, Path]],
                  output: Path, backend: str = "ios-mcp", resume: bool = False) -> Tuple[Path, bool]:
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(f"output directory is not empty: {output}")
    spec, inputs = _preflight(spec_path, pairs)
    spec_hash = sha256_file(spec_path)
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    previous = None
    if resume:
        parent = output / "manifest.json"
        if not parent.is_file():
            raise ValueError("resume requires an existing rebuild check")
        with redirect_stdout(io.StringIO()):
            if not verify_case(output):
                raise ValueError("existing rebuild evidence hash mismatch")
        previous = _read(parent)
        if (previous.get("kind") != "rebuild_check" or previous.get("status") == "complete" or
                previous.get("device_id_sha256_prefix") != prefix or
                previous.get("ui_backend") != backend or
                previous.get("feature_spec_sha256") != spec_hash or
                previous.get("pairs") != inputs):
            raise ValueError("resume device, spec, backend or playbooks differ")
    original_id = _identity(asyncio.run(_installed_app(udid, spec["target_bundle_id"])),
                            spec["target_bundle_id"])
    rebuilt_id = _identity(asyncio.run(_installed_app(udid, spec["rebuilt_bundle_id"])),
                           spec["rebuilt_bundle_id"])
    if previous and previous.get("installed_apps") != [original_id, rebuilt_id]:
        raise ValueError("installed app identity changed since the prior attempt")
    output.mkdir(parents=True, exist_ok=True)
    saved_spec = output / "feature-spec.json"
    if not saved_spec.exists():
        shutil.copyfile(spec_path, saved_spec)
    if sha256_file(saved_spec) != spec_hash:
        raise ValueError("saved feature specification differs from current input")
    record = dict(previous) if previous else {
        "schema_version": 1, "kind": "rebuild_check", "started_at": _now(),
        "device_id_sha256_prefix": prefix, "ui_backend": backend,
        "feature_spec_sha256": spec_hash, "pairs": inputs,
        "installed_apps": [original_id, rebuilt_id]}
    if previous:
        record.setdefault("history", []).append({"at": _now(),
                                                   "previous_status": previous["status"]})
    record["status"] = "failed"
    record["flows"] = []
    record.pop("error", None)
    try:
        for item in inputs:
            flow_id = item["flow_id"]
            root = output / "flows" / flow_id
            original = root / "original"
            clone = root / "rebuilt"
            comparison = root / "comparison"
            for path, bundle, script_key in ((original, original_id["bundle_id"], "original_script"),
                                              (clone, rebuilt_id["bundle_id"], "rebuilt_script")):
                wants_view = item["final_view"] is not None
                if not _prepare_run(path, bundle, item["scenario_id"], prefix, backend,
                                    resume, wants_view):
                    if wants_view:
                        _, done = capture_flow(udid, backend, Path(item[script_key]), path)
                    else:
                        _, done = run_playbook(udid, backend, Path(item[script_key]), path)
                    if not done:
                        raise RuntimeError(f"{flow_id} {path.name} flow capture failed")
                play_path = path / "playbook" if wants_view else path
                if sha256_file(play_path / "playbook.json") != item[script_key + "_sha256"]:
                    raise ValueError(f"saved playbook differs from the selected script: {flow_id}")
                _verified_run(path, bundle, item["scenario_id"], prefix, backend, wants_view)
                if wants_view:
                    check = _final_view_check(path, item["final_view"],
                                              root / f"{path.name}-state-check.json")
                    if not check["passed"]:
                        raise ValueError(f"final UIKit text assertion failed for {flow_id} {path.name}")
            if comparison.exists():
                attempts = root / "attempts"
                attempts.mkdir(exist_ok=True)
                shutil.move(str(comparison), str(attempts / f"comparison-{len(list(attempts.iterdir())) + 1:02d}"))
            compare_playbooks(original / "playbook" if item["final_view"] else original,
                              clone / "playbook" if item["final_view"] else clone,
                              comparison)
            summary = _read(comparison / "report-index.json")
            if (summary.get("original_bundle_id") != original_id["bundle_id"] or
                    summary.get("rebuilt_bundle_id") != rebuilt_id["bundle_id"] or
                    summary.get("scenario_id") != item["scenario_id"] or
                    summary.get("device_id_sha256_prefix") != prefix or
                    summary.get("ui_backend") != backend or
                    summary.get("checks_status") == "failed"):
                raise ValueError(f"comparison identity or explicit visual check failed: {flow_id}")
            record["flows"].append({"flow_id": flow_id,
                                    "scenario_id": item["scenario_id"],
                                    "comparison_index": str((comparison / "report-index.json").relative_to(output)),
                                    "comparison_sha256": sha256_file(comparison / "report-index.json"),
                                    "checks_status": summary["checks_status"],
                                    "final_view_status": "passed" if item["final_view"] else "not_configured",
                                    "screenshot_pairs": len(summary["screenshots"])})
            current = [_identity(asyncio.run(_installed_app(udid, identity["bundle_id"])),
                                 identity["bundle_id"]) for identity in (original_id, rebuilt_id)]
            if current != [original_id, rebuilt_id]:
                raise ValueError("installed app identity changed during rebuild check")
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
    finally:
        record["finished_at"] = _now()
        _write_report(output, record)
        record["evidence"] = _files(output)
        (output / "manifest.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
