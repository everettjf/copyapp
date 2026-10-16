"""Bind source, IPA, device installation and selected UI checks to an agent task."""

import hashlib
import io
import json
import os
import shutil
import tarfile
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.agent_run import _source_files, _source_tree_hash
from copyapp.gestures import GESTURE_ACTIONS
from copyapp.verify import checked_path, sha256_file, verify_case


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _post_action_script_assertions(script: Path) -> list[str]:
    """Return explicit checks performed after a state-changing UI action."""
    steps = _read(script).get("steps")
    if steps is None:
        return []
    if not isinstance(steps, list):
        raise ValueError("implementation playbook has invalid steps")
    after_action = False
    checks = []
    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError("implementation playbook has an invalid step")
        action = step.get("action")
        if action in ("tap", "tap_label", *GESTURE_ACTIONS):
            after_action = True
        elif after_action and action == "observe":
            compare = step.get("compare_number")
            contains = step.get("contains")
            if isinstance(compare, dict) and compare.get("pattern") and compare.get("to"):
                checks.append(f"step-{index:02d}:numeric_change")
            elif isinstance(contains, (str, list)) and contains:
                checks.append(f"step-{index:02d}:visible_content")
        elif after_action and action == "expect_foreground" and step.get("bundle_id"):
            checks.append(f"step-{index:02d}:foreground")
    return checks


def _snapshot_source(project: Path, archive_path: Path) -> str:
    paths = _source_files(project)
    if not paths:
        raise ValueError("rebuild source project has no retained source files")
    with tarfile.open(archive_path, "w") as archive:
        for path in paths:
            relative = str(path.relative_to(project))
            info = tarfile.TarInfo(relative)
            info.size = path.stat().st_size
            info.mode = 0o644
            info.mtime = 0
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    return sha256_file(archive_path)


def source_snapshot_tree_hash(archive_path: Path) -> str:
    """Recompute the project hash from a saved tar without extracting files."""
    digest = hashlib.sha256()
    names = []
    with tarfile.open(archive_path, "r:") as archive:
        members = archive.getmembers()
        if len(members) > 10000:
            raise ValueError("source snapshot contains too many files")
        for member in members:
            parts = Path(member.name).parts
            if (not member.isfile() or not parts or
                    Path(member.name).is_absolute() or ".." in parts or
                    member.name in names):
                raise ValueError("source snapshot contains an unsafe path")
            names.append(member.name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("source snapshot file is missing")
            file_digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                file_digest.update(block)
            digest.update(member.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(file_digest.digest())
    if names != sorted(names):
        raise ValueError("source snapshot paths are not ordered")
    return digest.hexdigest()


def create_agent_delivery(task_case: Path, install_record: Path,
                          check_case: Path, output: Path,
                          run_case: Optional[Path] = None,
                          visual_review_case: Optional[Path] = None) -> Path:
    """Create a scoped delivery record only from matching current artifacts."""
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"delivery output is not empty: {output}")
    task_case = task_case.resolve(strict=True)
    install_record = install_record.resolve(strict=True)
    check_case = check_case.resolve(strict=True)
    if install_record.name != "install.json":
        raise ValueError("installation source must be an install.json record")
    with redirect_stdout(io.StringIO()):
        if not verify_case(task_case) or not verify_case(check_case):
            raise ValueError("task or rebuild check failed hash verification")
    task = _read(task_case / "task.json")
    install = _read(install_record)
    check = _read(check_case / "manifest.json")
    task_status = task.get("status")
    omitted = task.get("omitted_flow_ids", [])
    if (task_status not in ("ready_for_agent", "selected_flows_ready") or
            (task_status == "ready_for_agent" and omitted) or
            (task_status == "selected_flows_ready" and
             (not isinstance(task.get("flows"), list) or not task["flows"] or
              not isinstance(omitted, list) or not omitted or
              any(not isinstance(item, str) or not item for item in omitted) or
              len(set(omitted)) != len(omitted) or
              task.get("ready_count") != len(task.get("flows", [])) or
              task.get("needs_attention_count") != 0 or
              any(item.get("status") != "ready_for_implementation"
                  for item in task.get("flows", []) if isinstance(item, dict)) or
              any(not isinstance(item, dict) for item in task.get("flows", [])) or
              any(not isinstance(item.get("id"), str) or not item["id"]
                  for item in task.get("flows", []) if isinstance(item, dict)) or
              len({item.get("id") for item in task.get("flows", [])
                   if isinstance(item, dict)}) != len(task.get("flows", [])) or
              any(item.get("id") in omitted for item in task.get("flows", [])
                  if isinstance(item, dict)))) or
            check.get("kind") != "rebuild_check" or
            check.get("status") != "complete" or
            install.get("schema_version") != 1 or
            install.get("status") != "installed" or
            install.get("helper_exit_code") != 0 or
            install.get("staged_sha256") != install.get("ipa_sha256") or
            install.get("bundle_id") != task.get("rebuilt_bundle_id")):
        raise ValueError("task, installation or rebuild check is incomplete")
    ipa = Path(install["ipa"]).resolve(strict=True)
    if sha256_file(ipa) != install.get("ipa_sha256"):
        raise ValueError("installed IPA no longer matches the local artifact")
    udid = task.get("device_udid")
    installed_udid = install.get("device_id")
    if (not isinstance(installed_udid, str) or
            (udid is not None and udid != installed_udid) or
            check.get("device_id_sha256_prefix") != hashlib.sha256(
                installed_udid.encode()).hexdigest()[:16]):
        raise ValueError("installation and rebuild check belong to different devices")
    identities = check.get("installed_apps")
    expected_bundles = {task.get("target_bundle_id"), task.get("rebuilt_bundle_id")}
    if (not isinstance(identities, list) or len(identities) != 2 or
            {item.get("bundle_id") for item in identities if isinstance(item, dict)} != expected_bundles):
        raise ValueError("rebuild check installed App identities do not match task")
    rebuilt = next(item for item in identities if item["bundle_id"] == task["rebuilt_bundle_id"])
    if (rebuilt.get("version"), rebuilt.get("build")) != (
            install.get("version"), install.get("build")):
        raise ValueError("rebuild check used a different clone version than installation")
    project = Path(task["project_dir"]).resolve(strict=True)
    source_hash = _source_tree_hash(project)
    if source_hash is None:
        raise ValueError("rebuild source project does not exist")
    task_flows = task.get("flows")
    check_pairs = check.get("pairs")
    check_flows = check.get("flows")
    if (not isinstance(task_flows, list) or not task_flows or
            not isinstance(check_pairs, list) or not isinstance(check_flows, list) or
            len(task_flows) > len(check_pairs) or len(check_pairs) != len(check_flows)):
        raise ValueError("rebuild check does not cover every task flow")
    pairs = {item.get("flow_id"): item for item in check_pairs if isinstance(item, dict)}
    results = {item.get("flow_id"): item for item in check_flows if isinstance(item, dict)}
    expected_ids = {item.get("id") for item in task_flows if isinstance(item, dict)}
    if (len(pairs) != len(check_pairs) or len(results) != len(check_flows) or
            set(pairs) != set(results) or
            not expected_ids.issubset(set(pairs))):
        raise ValueError("rebuild check flow IDs differ from agent task")
    additional_check_flow_ids = sorted(set(pairs) - expected_ids)
    flow_results = []
    for flow in task_flows:
        flow_id = flow["id"]
        pair = pairs[flow_id]
        result = results[flow_id]
        original = Path(flow["original_script"]).resolve(strict=True)
        clone = Path(flow["rebuilt_script"]).resolve(strict=True)
        comparison = checked_path(check_case, result["comparison_index"])
        compared = _read(comparison)
        if (pair.get("original_script_sha256") != sha256_file(original) or
                pair.get("rebuilt_script_sha256") != sha256_file(clone) or
                result.get("comparison_sha256") != sha256_file(comparison) or
                pair.get("scenario_id") != flow.get("scenario_id") or
                compared.get("scenario_id") != flow.get("scenario_id") or
                compared.get("original_bundle_id") != task.get("target_bundle_id") or
                compared.get("rebuilt_bundle_id") != task.get("rebuilt_bundle_id") or
                compared.get("device_id_sha256_prefix") != check.get("device_id_sha256_prefix") or
                result.get("checks_status") != compared.get("checks_status") or
                not isinstance(result.get("screenshot_pairs"), int) or
                result["screenshot_pairs"] < 1):
            raise ValueError(f"comparison is stale or inconsistent: {flow_id}")
        script_checks = _post_action_script_assertions(original)
        flow_results.append({"id": flow_id,
                             "final_view_status": result.get("final_view_status"),
                             "script_assertions_status": "passed" if script_checks else "not_configured",
                             "script_assertions": script_checks,
                             "visual_checks_status": result.get("checks_status"),
                             "screenshot_pairs": result["screenshot_pairs"],
                             "comparison_index": str(comparison),
                             "comparison_sha256": sha256_file(comparison)})
    run_path = None
    run_status = None
    observed_source_change = None
    if run_case is not None:
        run_case = run_case.resolve(strict=True)
        with redirect_stdout(io.StringIO()):
            if not verify_case(run_case):
                raise ValueError("agent execution case failed hash verification")
        run = _read(run_case / "run.json")
        if (run.get("kind") != "agent_execution" or
                run.get("status") != "agent_exited_unverified" or
                Path(run.get("task_case", "")).resolve() != task_case or
                run.get("task_manifest_sha256") != sha256_file(task_case / "manifest.json") or
                run.get("project_dir") != str(project) or
                run.get("project_source_after_sha256") != source_hash):
            raise ValueError("agent run is not a matching completed source run")
        run_path = str(run_case)
        run_status = run["status"]
        observed_source_change = run.get("project_source_changed") is True
    review_path = None
    review_manifest_sha = None
    if visual_review_case is not None:
        visual_review_case = visual_review_case.resolve(strict=True)
        with redirect_stdout(io.StringIO()):
            if not verify_case(visual_review_case):
                raise ValueError("visual review failed source verification")
        review = _read(visual_review_case / "review.json")
        if (Path(review.get("rebuild_check_case", "")).resolve() != check_case or
                review.get("rebuild_check_manifest_sha256") !=
                sha256_file(check_case / "manifest.json")):
            raise ValueError("visual review belongs to a different rebuild check")
        review_by_flow = {}
        for row in review["pairs"]:
            review_by_flow.setdefault(row["flow_id"], []).append(row["verdict"])
        for item in flow_results:
            verdicts = review_by_flow.get(item["id"], [])
            if len(verdicts) != item["screenshot_pairs"]:
                raise ValueError(f"visual review lacks selected flow screenshots: {item['id']}")
            item["visual_review_status"] = (
                "major_difference" if "major_difference" in verdicts else
                "minor_difference" if "minor_difference" in verdicts else "match")
        review_path = str(visual_review_case)
        review_manifest_sha = sha256_file(visual_review_case / "manifest.json")
    asserted = sum(item["script_assertions_status"] == "passed" or
                   item["final_view_status"] == "passed" or
                   item["visual_checks_status"] == "passed" for item in flow_results)
    unreviewed = sum(item["visual_checks_status"] == "unreviewed" and
                     not item.get("visual_review_status") for item in flow_results)
    major = sum(item.get("visual_review_status") == "major_difference" for item in flow_results)
    minor = sum(item.get("visual_review_status") == "minor_difference" for item in flow_results)
    status = ("selected_behavior_verified_visual_gap" if asserted == len(flow_results) and major else
              "selected_behavior_verified_visual_reviewed_with_differences"
              if asserted == len(flow_results) and minor and not unreviewed else
              "selected_behavior_verified_visual_reviewed"
              if asserted == len(flow_results) and review_path and not unreviewed else
              "selected_behavior_verified_visual_unreviewed"
              if asserted == len(flow_results) and unreviewed else
              "selected_behavior_verified" if asserted == len(flow_results) else
              "execution_verified_visual_unreviewed")
    output.mkdir(parents=True, exist_ok=True)
    source_archive = output / "source-project.tar"
    ipa_archive = output / "installed.ipa"
    source_snapshot_sha = _snapshot_source(project, source_archive)
    if source_snapshot_tree_hash(source_archive) != source_hash:
        raise ValueError("saved source snapshot differs from live project")
    shutil.copyfile(ipa, ipa_archive)
    if sha256_file(ipa_archive) != install["ipa_sha256"]:
        raise ValueError("saved IPA differs from installed package hash")
    record = {"schema_version": 1, "kind": "agent_delivery", "status": status,
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "task_case": str(task_case),
              "task_manifest_sha256": sha256_file(task_case / "manifest.json"),
              "agent_run_case": run_path,
              "agent_run_manifest_sha256": sha256_file(Path(run_path) / "manifest.json") if run_path else None,
              "agent_run_status": run_status,
              "agent_observed_source_change": observed_source_change,
              "visual_review_case": review_path,
              "visual_review_manifest_sha256": review_manifest_sha,
              "installation_record": str(install_record),
              "installation_record_sha256": sha256_file(install_record),
              "rebuild_check_case": str(check_case),
              "rebuild_check_manifest_sha256": sha256_file(check_case / "manifest.json"),
              "device_id_sha256_prefix": check["device_id_sha256_prefix"],
              "source_project": str(project), "source_project_sha256": source_hash,
              "source_snapshot": "source-project.tar",
              "source_snapshot_sha256": source_snapshot_sha,
              "ipa": str(ipa), "ipa_sha256": sha256_file(ipa),
              "ipa_snapshot": "installed.ipa",
              "ipa_snapshot_sha256": sha256_file(ipa_archive),
              "target_bundle_id": task["target_bundle_id"],
              "rebuilt_bundle_id": task["rebuilt_bundle_id"],
              "rebuilt_version": install["version"], "rebuilt_build": install["build"],
              "task_status": task_status, "omitted_flow_ids": omitted,
              "additional_check_flow_ids": additional_check_flow_ids,
              "flow_results": flow_results, "asserted_flow_count": asserted,
              "visual_unreviewed_flow_count": unreviewed,
              "visual_major_difference_flow_count": major,
              "visual_minor_difference_flow_count": minor,
              "scope_limit": "Only listed flows and assertions are verified; full App equivalence and untested versions are not established."}
    _write(output / "delivery.json", record)
    def link(path: Path, label: str) -> str:
        return f"[{label}]({os.path.relpath(path, output)})"
    lines = ["# 复刻交付核验", "",
             f"- 状态：`{status}`。原版 `{task['target_bundle_id']}`；复刻版 "
             f"`{task['rebuilt_bundle_id']}` {install['version']} ({install['build']})。",
             f"- 设备 ID 哈希前缀：`{check['device_id_sha256_prefix']}`。"
             f"IPA SHA-256：`{record['ipa_sha256']}`；源码树 SHA-256：`{source_hash}`。",
             f"- 证据：{link(task_case / 'TASK.md', 'Agent 任务')} · "
             f"{link(install_record, '安装记录')} · "
             f"{link(check_case / 'report.md', '真机对照')} · "
             f"{link(source_archive, '源码快照')} · {link(ipa_archive, 'IPA 快照')}。", "",
             "| 流程 | 操作后脚本断言 | 末端 UIKit 断言 | 脚本视觉检查 | 逐图审阅 | 截图对 |",
             "| --- | --- | --- | --- | --- | ---: |"]
    for item in flow_results:
        lines.append(f"| `{item['id']}` | `{item['script_assertions_status']}` | "
                     f"`{item['final_view_status']}` | "
                     f"`{item['visual_checks_status']}` | "
                     f"`{item.get('visual_review_status', 'unreviewed')}` | "
                     f"{item['screenshot_pairs']} |")
    lines += ["", f"- 有显式通过断言的流程：{asserted}/{len(flow_results)}；"
              f"仍需视觉审阅：{unreviewed}/{len(flow_results)}；"
              f"逐图记录轻微差异：{minor}；重大差异：{major}。"]
    if review_path:
        lines.append(f"- 逐图审阅：{link(Path(review_path) / 'report.md', '审阅记录')}；"
                     "判断只针对保存的截图，不推断动画或未测页面。")
    if omitted:
        lines.append("- 本次未选的报告流程：" + "、".join(f"`{flow_id}`" for flow_id in omitted) + "。")
    if additional_check_flow_ids:
        lines.append("- 引用的真机对照还测试了其他流程：" +
                     "、".join(f"`{flow_id}`" for flow_id in additional_check_flow_ids) +
                     "；它们不计入本任务交付。")
    if run_path:
        lines.append(f"- Agent CLI：{link(Path(run_path) / 'run.json', '执行记录')}；"
                     f"运行期间观察到源码树变化：{observed_source_change}。")
    else:
        lines.append("- 未提供独立 Agent CLI 运行记录；源码生成者未由本核验确认。")
    lines += ["", "本记录只验证列出的脚本、已声明的行为断言、包与同一设备的安装身份。"
              "未审画面、已记录差异、规格未列出的交互、系统版本和完整 App 等价仍需继续检查。", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {
        "schema_version": 1, "kind": "agent_delivery", "status": status,
        "task_manifest_sha256": record["task_manifest_sha256"],
        "rebuild_check_manifest_sha256": record["rebuild_check_manifest_sha256"],
        "installation_record_sha256": record["installation_record_sha256"],
        "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                     for name in ("delivery.json", "report.md", "source-project.tar", "installed.ipa")],
    })
    return output / "report.md"
