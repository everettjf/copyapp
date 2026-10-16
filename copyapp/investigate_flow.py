"""One bounded device flow through UI capture, method binding and REA."""

import hashlib
import io
import json
import os
import shutil
import zipfile
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from copyapp.candidates import build_candidates
from copyapp.experiment import _static_targets
from copyapp.flow_capture import capture_flow
from copyapp.ghidra_queue import decompile_candidate_queue
from copyapp.ipa import MAX_BINARY
from copyapp.method_scout import refine_scout_with_view_tree, scout_methods
from copyapp.native_disasm import disassemble_native_candidates
from copyapp.rea_queue import analyze_candidate_queue
from copyapp.trace import MAX_METHODS, parse_method
from copyapp.verify import sha256_file, verify_case
from copyapp.view_tree import capture_view_tree


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _files(root: Path) -> list:
    return [{"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
            for path in sorted(root.rglob("*"))
            if path.is_file() and path != root / "manifest.json"]


def write_review_brief(output: Path, plan: dict) -> Path:
    """Summarize directly checkable facts for the agent's semantic review."""
    trace_path = output / "flow/trace/trace.json"
    trace = _read(trace_path) if trace_path.is_file() else {"requested_methods": [], "steps": []}
    network_path = output / "flow/network/network.json"
    network = _read(network_path) if network_path.is_file() else None
    flow = _read(output / "flow/manifest.json")
    candidates_path = output / "candidates/candidates.json"
    candidates = _read(candidates_path) if candidates_path.is_file() else None
    queue = _read(output / "rea/queue.json") if (output / "rea/queue.json").is_file() else None
    direct_path = output / "direct-ghidra/queue.json"
    direct = _read(direct_path) if direct_path.is_file() else None
    native_path = output / "native/index.json"
    native = _read(native_path) if native_path.is_file() else None
    scout = _read(output / "method-scout.json")
    methods = trace["requested_methods"]
    lines = ["# 流程调查待审摘要", "",
             f"- App：`{flow['bundle_id']}`",
             f"- UI 后端：`{flow['ui_backend']}`",
             f"- 场景：`{flow.get('scenario_id') or '未命名'}`",
             f"- 二进制 SHA-256：`{candidates['binary_sha256'] if candidates else scout['binary_sha256']}`",
             f"- 入口选择：`{', '.join(methods) or '未选定'}`；依据 `{'运行时视图类与唯一动作方法' if scout.get('selection_basis') == 'runtime_visible_class_unique_action' else scout.get('selection_basis') or '未确定'}`，详见[方法候选](method-scout.json)",
             "- 界面结果：[脚本、截图和视图树](flow/manifest.json)",
             ("- 方法来源：[Frida 原始计数与钩子](flow/trace/trace.json)" if methods else
              "- 本次没有可唯一选定的 Objective-C 方法；保留 UI 证据，未进行方法跟踪。"), "",
             "## 点击窗口的调用", "",
             "| 脚本步骤 | 操作 | 当前 IMP 命中 | 主程序静态入口命中 | 原始参数 2（当前 / 静态） |",
             "| ---: | --- | --- | --- | --- |"]
    if (output / "entry-view/manifest.json").is_file():
        entry = _read(output / "entry-view/manifest.json")
        lines.insert(8, ("- 操作前视图：[运行时 UIKit 视图与截图](entry-view/manifest.json)；"
                         "仅用于筛选候选，点击跟踪才记录实际命中。" if
                         entry.get("status") == "complete" else
                         "- 操作前视图采集未完成；[失败记录](entry-view/manifest.json)；"
                         "继续保留后续 UI 证据。"))
    if network is not None:
        hosts = sorted({item["host"] for item in network.get("events", [])
                        if isinstance(item, dict) and isinstance(item.get("host"), str)})
        lines.insert(8, f"- 网络观察：[URLSession resume 事件](flow/network/network.json)；"
                        f"{len(network.get('events', []))} 条，"
                        f"主机 {', '.join(hosts) or '未观察到'}。"
                        "事件数不等于去重请求数；点击窗口内同现不证明因果。")
    actions = plan.get("steps", [])
    for item in trace["steps"]:
        index = item["index"]
        action = actions[index - 1] if 1 <= index <= len(actions) else {}
        detail = action.get("label") if item["action"] == "tap_label" else None
        if detail is None and item["action"] == "tap":
            detail = f"({action.get('x')}, {action.get('y')})"
        description = (item["action"] + " " + str(detail or "")).replace("|", "\\|").replace("\n", " ")
        current = ", ".join(f"`{method}` {count}" for method, count in
                            zip(methods, item["call_counts"]))
        static = ", ".join(f"`{method}` {count}" for method, count in
                           zip(methods, item["static_call_counts"]))
        hits = item.get("arg2_u32_hits", [])
        raw = ", ".join(f"{methods[hit['index']]}: {hit['value']} "
                        f"({'静态' if hit['type'] == 'static_hit' else '当前'})"
                        for hit in hits)
        if item.get("arg2_u32_truncated"):
            raw += " [截断]"
        lines.append(f"| {index} | {description} | {current} | {static} | {raw} |")
    lines.extend(["", "## 静态函数证据", ""])
    for result in queue["results"] if queue else []:
        if result["status"] == "complete":
            summary = _read(output / "rea" / result["summary"])
            lines.append(f"- `{result['address']}`：`{summary['resolved_procedure'].get('name')}`；"
                         f"{queue['provider']}；Evidence ID `{result['evidence_id']}`；"
                         f"[伪代码](rea/{Path(result['summary']).parent}/pseudocode.txt)")
    if direct is not None:
        for index, result in enumerate(direct.get("results", [])):
            if result["status"] == "complete":
                summary = _read(output / "direct-ghidra" / result["summary"])
                selected = direct["selected"][index]
                chain = (f"从 `{selected['source_address']}` 的直接调用/分支静态跟随；"
                         if selected.get("origin") == "native_direct_follow" else "")
                facts = output / "direct-ghidra" / Path(result["summary"]).parent / "function-facts.json"
                facts_link = (f" · [函数关系](direct-ghidra/"
                              f"{Path(result['summary']).parent}/function-facts.json)"
                              if facts.is_file() else "")
                lines.append(f"- `{result['address']}`：`{summary['function_name']}`；"
                             f"{chain}Copy APP 直连 Ghidra；"
                             f"[伪代码](direct-ghidra/{Path(result['summary']).parent}/pseudocode.txt)"
                             f"{facts_link}")
    if queue is None and direct is None:
        lines.append("- 本次未请求反编译；函数体和深层调用语义仍需结合运行时实验或其他可用工具验证。")
    if native is not None:
        for result in native.get("results", []) + native.get("followed", []):
            if result.get("status") == "complete":
                summary = _read(output / "native" / result["summary"])
                lines.append(f"- `{result['address']}`："
                             + (f"从 `{result['source_address']}` 的直接分支/调用静态跟随；"
                                if result.get("source_address") else "") +
                             f"[有界 ARM64 汇编](native/{Path(result['summary']).parent}/assembly.txt)；"
                             f"{summary['instruction_count']} 条指令；"
                             f"{'窗口截断' if summary['truncated'] else '到下一函数起点'}。")
                selectors = [call["objc_selector_stub"] for call in
                             summary.get("direct_calls", []) if call.get("objc_selector_stub")]
                if selectors:
                    lines.append("  - 直接 `bl` 到 Objective-C 消息发送桩：" +
                                 "、".join(f"`{item}`" for item in selectors[:12]) +
                                 ("（截断）" if len(selectors) > 12 else "") + "。")
                if summary.get("direct_branches"):
                    lines.append(f"  - 直接分支指令：{len(summary['direct_branches'])} 条；"
                                 "计算跳转 `br` 的目标不由本证据自动恢复。")
        if native.get("status") != "complete":
            lines.append(f"- 原生反汇编状态：`{native['status']}`；失败项见 [队列](native/index.json)。")
    lines.extend(["", "## 解释边界", "",
                  "以上仅列出保存的运行时命中、原始参数、静态地址、可用的有界汇编和反编译结果。原始参数 2 的类型和含义需要另证；点击窗口内命中不单独证明因果；模块路径和偏移不证明内存代码与采集文件逐字节相同；静态 `bl` 边不证明运行时调用；汇编和伪代码都不是原作者源码。",
                  "下一步应沿入口的被调用函数解释状态、数据和可见结果，再把结论及未知项写入带证据引用的报告与复刻规格。", ""])
    path = output / "review-brief.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _resolve_target(analysis: Path, udid: str, bundle: str,
                    output: Path, reuse_existing: bool = False) -> Tuple[Path, Path, str]:
    with redirect_stdout(io.StringIO()):
        if not verify_case(analysis):
            raise ValueError("analysis case evidence hash mismatch")
    analysis_index = _read(analysis / "analysis-index.json")
    if not all(analysis_index.get("steps", {}).get(stage, {}).get("ok")
               for stage in ("survey", "bundle")):
        raise ValueError("analysis case survey or bundle stage is incomplete")
    survey = _read(analysis / "survey/manifest.json")
    app = _read(analysis / "survey/app.json")
    acquisition = _read(analysis / "acquired/acquisition.json")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    remote = acquisition.get("remote_bundle_path")
    executable = app.get("CFBundleExecutable")
    if (survey.get("bundle_id") != bundle or acquisition.get("bundle_id") != bundle or
            app.get("CFBundleIdentifier") != bundle or
            survey.get("device_id_sha256_prefix") != prefix or
            acquisition.get("device_id_sha256_prefix") != prefix or
            not isinstance(remote, str) or not isinstance(executable, str) or
            not executable or "/" in executable or executable in (".", "..")):
        raise ValueError("analysis case belongs to another app or device")
    app_dir = Path(remote).name
    if not app_dir.endswith(".app") or app_dir in (".app", "..app"):
        raise ValueError("analysis case has an invalid app directory")
    decrypted_index = analysis / "decrypted/static/objc-index.json"
    if decrypted_index.is_file():
        if not analysis_index.get("steps", {}).get("decryption", {}).get("ok"):
            raise ValueError("decrypted method index has no completed decryption stage")
        decryption = _read(analysis / "decrypted/decryption.json")
        if decryption.get("all_macho_headers_decrypted") is not True:
            raise ValueError("analysis package is not fully decrypted")
        index = decrypted_index
        ipa = analysis / "decrypted/analysis.ipa"
        member = f"Payload/{app_dir}/{executable}"
        ipa_index = _read(analysis / "decrypted/static/ipa-index.json")
        matches = [item for item in ipa_index.get("binaries", [])
                   if item.get("path") == member]
        if len(matches) != 1:
            raise ValueError("decrypted main executable is missing or ambiguous")
        target = output / "sources" / app_dir / executable
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not reuse_existing:
            raise FileExistsError(f"extracted binary already exists: {target}")
        if not target.exists():
            with zipfile.ZipFile(ipa) as archive:
                info = archive.getinfo(member)
                if not 0 < info.file_size <= MAX_BINARY:
                    raise ValueError("decrypted main executable exceeds size limit")
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        if sha256_file(target) != matches[0].get("sha256"):
            raise ValueError("extracted main executable hash differs from decrypted index")
        source_kind = "decrypted_ipa_member"
    else:
        index = analysis / "acquired/static/objc-index.json"
        target = analysis / "acquired/bundle" / app_dir / executable
        ipa_index = _read(analysis / "acquired/static/ipa-index.json")
        member = f"Payload/{app_dir}/{executable}"
        matches = [item for item in ipa_index.get("binaries", [])
                   if item.get("path") == member]
        if len(matches) != 1:
            raise ValueError("acquired main executable is missing or ambiguous")
        encryption = matches[0].get("encryption_info") or {}
        if matches[0].get("encrypted_on_disk") is True or encryption.get("cryptid", 0) != 0:
            raise ValueError("acquired main executable remains encrypted; run analyze --decrypt")
        source_kind = "acquired_bundle"
    if not target.is_file() or not index.is_file():
        raise ValueError("main executable or Objective-C index is unavailable")
    indexed = _read(index)
    if indexed.get("binary_sha256") != sha256_file(target) or \
            matches[0].get("sha256") != sha256_file(target):
        raise ValueError("selected main executable does not match Objective-C index")
    return target, index, source_kind


def investigate_flow(udid: str, analysis: Path, script: Path, output: Path,
                     backend: str = "ios-mcp", methods: Optional[list[str]] = None,
                     provider: str = "none", rea_limit: int = 4,
                     rea_script: Optional[Path] = None,
                     ghidra_dir: Optional[Path] = None,
                     java_home: Optional[Path] = None,
                     timeout: int = 240, resume: bool = False,
                     disabled_analyzer: Optional[str] = None,
                     network: bool = False) -> Tuple[Path, bool]:
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    if provider not in ("none", "ghidra-direct", "ghidra", "hopper"):
        raise ValueError("unsupported analysis provider")
    if disabled_analyzer is not None and provider != "ghidra-direct":
        raise ValueError("--ghidra-disable-analyzer requires ghidra-direct provider")
    if provider == "ghidra-direct":
        ghidra_dir = ghidra_dir or (Path(os.environ["GHIDRA_INSTALL_DIR"])
                                    if os.environ.get("GHIDRA_INSTALL_DIR") else None)
        java_home = java_home or (Path(os.environ["JAVA_HOME"])
                                  if os.environ.get("JAVA_HOME") else None)
        if ghidra_dir is None or java_home is None:
            raise ValueError("ghidra-direct requires Ghidra and JDK paths before device work")
        from copyapp.ghidra_direct import check_direct_ghidra
        check_direct_ghidra(ghidra_dir, java_home, disabled_analyzer)
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(f"output directory is not empty: {output}")
    plan = _read(script)
    bundle = plan.get("bundle_id")
    if not isinstance(bundle, str) or not bundle:
        raise ValueError("playbook has no Bundle ID")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    analysis_hash = sha256_file(analysis / "analysis-index.json")
    script_hash = sha256_file(script)
    prior = None
    if resume:
        prior_path = output / "manifest.json"
        if not prior_path.is_file():
            raise ValueError("resume requires an existing investigation manifest")
        with redirect_stdout(io.StringIO()):
            if not verify_case(output):
                raise ValueError("existing investigation evidence hash mismatch")
        prior = _read(prior_path)
        if (prior.get("status") == "complete" or
                prior.get("kind") != "investigated_ui_flow" or
                prior.get("bundle_id") != bundle or
                prior.get("device_id_sha256_prefix") != prefix or
                prior.get("ui_backend") != backend or
                prior.get("provider") != provider or
                bool(prior.get("network_requested")) != network or
                prior.get("disabled_analyzer") != disabled_analyzer or
                prior.get("analysis_index_sha256") != analysis_hash or
                prior.get("source_script_sha256") != script_hash):
            raise ValueError("resume target, script, provider or analysis identity differs")
    output.mkdir(parents=True, exist_ok=True)
    record = dict(prior) if prior else {"schema_version": 1, "kind": "investigated_ui_flow",
                                         "bundle_id": bundle,
                                         "device_id_sha256_prefix": prefix,
                                         "ui_backend": backend, "provider": provider,
                                         "analysis_index_sha256": analysis_hash,
                                         "source_script_sha256": script_hash,
                                         "started_at": _now()}
    if disabled_analyzer is not None:
        record["disabled_analyzer"] = disabled_analyzer
    if network:
        record["network_requested"] = True
    if prior:
        record.setdefault("history", []).append({"at": _now(),
                                                   "previous_status": prior["status"],
                                                   "previous_error": prior.get("error")})
    record["status"] = "failed"
    record.pop("error", None)
    record.pop("reason", None)
    stage = "resolve_analysis"
    try:
        binary, index, source_kind = _resolve_target(analysis, udid, bundle, output,
                                                     reuse_existing=resume)
        record.update({"binary_sha256": sha256_file(binary), "binary_source": source_kind,
                       "objc_index_sha256": sha256_file(index)})
        stage = "method_scout"
        tap_labels = [step["label"] for step in plan.get("steps", [])
                      if isinstance(step, dict) and step.get("action") == "tap_label"
                      and isinstance(step.get("label"), str)]
        scout = scout_methods(index, tap_labels=tap_labels)
        if scout["binary_sha256"] != record["binary_sha256"]:
            raise ValueError("method scout index belongs to another binary")
        if methods is None and provider in ("none", "ghidra-direct") and not scout["selected_methods"] and tap_labels:
            stage = "entry_view"
            entry_dir = output / "entry-view"
            if resume and (entry_dir / "manifest.json").is_file():
                entry_record = _read(entry_dir / "manifest.json")
                if entry_record.get("status") == "complete":
                    from copyapp.report import _validate_view_tree
                    _validate_view_tree(entry_dir, bundle, prefix)
                    entry_ok = True
                else:
                    with redirect_stdout(io.StringIO()):
                        if not verify_case(entry_dir):
                            raise ValueError("existing entry view evidence hash mismatch")
                    entry_ok = False
            elif entry_dir.exists():
                raise ValueError("existing entry view is incomplete")
            else:
                _, entry_ok = capture_view_tree(udid, bundle, entry_dir,
                                                backend=backend, launch=True)
            record["entry_view_status"] = "complete" if entry_ok else "unavailable"
            record["entry_view_manifest_sha256"] = sha256_file(entry_dir / "manifest.json")
            if entry_ok:
                scout = refine_scout_with_view_tree(scout, index,
                                                    entry_dir / "view-tree.json", tap_labels)
            stage = "method_scout"
        if methods is None:
            selected = scout["selected_methods"]
            record["method_selection"] = ("runtime_view_heuristic" if
                                          scout.get("selection_basis") ==
                                          "runtime_visible_class_unique_action" else "heuristic")
        else:
            parsed = [parse_method(item) for item in methods]
            if not parsed or len(parsed) > MAX_METHODS or len(set(parsed)) != len(parsed):
                raise ValueError("provide 1–32 unique methods")
            selected = methods
            record["method_selection"] = "explicit"
        scout["used_methods"] = selected
        scout_path = output / "method-scout.json"
        if resume and scout_path.is_file():
            previous_scout = _read(scout_path)
            if previous_scout.get("binary_sha256") != scout["binary_sha256"]:
                raise ValueError("resume method selection differs from saved case")
            if previous_scout.get("used_methods") != selected:
                if (not prior or prior.get("status") != "needs_review" or
                        previous_scout.get("used_methods") != [] or methods is None or
                        (output / "flow").exists()):
                    raise ValueError("resume method selection differs from saved case")
                shutil.copy2(scout_path, output / "method-scout-before-review.json")
                scout_path.write_text(json.dumps(scout, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
        else:
            scout_path.write_text(json.dumps(scout, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
        if not selected and provider in ("ghidra", "hopper"):
            record["status"] = "needs_review"
            record["reason"] = "no uniquely ranked action method; select a method from method-scout.json"
            return output / "manifest.json", False
        if selected:
            _static_targets(binary, index, [parse_method(item) for item in selected])
        record["selected_methods"] = selected
        stage = "flow_capture"
        flow_dir = output / "flow"
        capture_needed = False
        if resume and (flow_dir / "manifest.json").is_file():
            saved_flow = _read(flow_dir / "manifest.json")
            if saved_flow.get("status") == "complete":
                from copyapp.report import _validate_flow_capture
                _validate_flow_capture(flow_dir, bundle, prefix, {record["binary_sha256"]})
                flow_ok = True
            elif (saved_flow.get("status") == "failed" and
                  prior.get("error", {}).get("stage") == "flow_capture"):
                with redirect_stdout(io.StringIO()):
                    if not verify_case(flow_dir):
                        raise ValueError("failed flow capture evidence hash mismatch")
                archive = output / "attempts" / (
                    "flow-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
                archive.parent.mkdir(exist_ok=True)
                shutil.move(str(flow_dir), str(archive))
                record.setdefault("history", []).append({
                    "at": _now(), "archived_failed_flow": str(archive.relative_to(output)),
                    "manifest_sha256": sha256_file(archive / "manifest.json")})
                capture_needed = True
            else:
                raise ValueError("existing flow capture is incomplete or unrelated to failure")
        elif flow_dir.exists():
            raise ValueError("existing flow is incomplete; retain it and start a new investigation")
        else:
            capture_needed = True
        if capture_needed:
            # Preserve the raw ObjC argument for button actions. It remains an
            # uninterpreted uint32 until static/runtime evidence identifies it.
            arg_methods = [spec for spec in selected
                           if parse_method(spec)[1] == "buttonPressed:"]
            _, flow_ok = capture_flow(udid, backend, script, flow_dir,
                                      methods=selected or None,
                                      binary=binary if selected else None,
                                      objc_index=index if selected else None,
                                      arg2_u32_methods=arg_methods,
                                      **({"network": True} if network else {}))
        record["flow_status"] = "complete" if flow_ok else "failed"
        if not flow_ok:
            raise RuntimeError("flow capture failed; inspect flow/manifest.json")
        if not selected:
            record["candidate_status"] = "not_requested"
            record["rea_status"] = "not_requested"
            record["native_status"] = "not_requested"
            if provider == "ghidra-direct":
                record["direct_ghidra_status"] = "not_requested"
            stage = "review_brief"
            write_review_brief(output, plan)
            record["status"] = "complete"
            return output / "manifest.json", True
        stage = "candidates"
        candidate_dir = output / "candidates"
        if resume and (candidate_dir / "manifest.json").is_file():
            with redirect_stdout(io.StringIO()):
                if not verify_case(candidate_dir):
                    raise ValueError("existing candidate evidence hash mismatch")
            candidate = _read(candidate_dir / "candidates.json")
            if (candidate.get("bundle_id") != bundle or
                    candidate.get("device_id_sha256_prefix") != prefix or
                    candidate.get("binary_sha256") != record["binary_sha256"] or
                    sha256_file(candidate_dir / "sources/flow-01/manifest.json") !=
                    sha256_file(flow_dir / "manifest.json")):
                raise ValueError("existing candidate source differs from saved flow")
            candidates_ok = bool(candidate.get("candidates"))
        elif candidate_dir.exists():
            raise ValueError("existing candidate output is incomplete")
        else:
            _, candidates_ok = build_candidates(udid, bundle, binary, index,
                                                 [flow_dir], candidate_dir)
        record["candidate_status"] = "complete" if candidates_ok else "no_candidates"
        if not candidates_ok and provider in ("ghidra", "hopper"):
            raise RuntimeError("flow observed no valid static method candidate")
        stage = "rea_queue"
        rea_dir = output / "rea"
        if provider in ("none", "ghidra-direct"):
            if rea_dir.exists():
                raise ValueError("REA evidence is unexpected in a no-REA investigation")
            record["rea_status"] = "not_requested"
            native_dir = output / "native"
            if candidates_ok:
                if resume and (native_dir / "index.json").is_file():
                    with redirect_stdout(io.StringIO()):
                        if not verify_case(native_dir):
                            raise ValueError("existing native evidence hash mismatch")
                    native = _read(native_dir / "index.json")
                    if (native.get("candidate_case_sha256") !=
                            sha256_file(candidate_dir / "candidates.json") or
                            native.get("binary_sha256") != record["binary_sha256"]):
                        raise ValueError("existing native disassembly belongs to another candidate")
                elif native_dir.exists():
                    raise ValueError("existing native disassembly is incomplete")
                else:
                    disassemble_native_candidates(candidate_dir, native_dir,
                                                  limit=rea_limit)
                    native = _read(native_dir / "index.json")
                record["native_status"] = native["status"]
            else:
                record["native_status"] = "not_requested"
            if provider == "ghidra-direct" and candidates_ok:
                stage = "direct_ghidra_queue"
                direct_dir = output / "direct-ghidra"
                if resume and (direct_dir / "manifest.json").is_file():
                    saved = _read(direct_dir / "queue.json")
                    if (saved.get("kind") != "ghidra_direct_candidate_queue" or
                            saved.get("binary_sha256") != record["binary_sha256"] or
                            saved.get("candidate_case_sha256") !=
                            sha256_file(candidate_dir / "candidates.json")):
                        raise ValueError("existing direct Ghidra queue belongs to another candidate")
                    with redirect_stdout(io.StringIO()):
                        if not verify_case(direct_dir):
                            raise ValueError("existing direct Ghidra queue hash mismatch")
                    if saved.get("status") == "complete":
                        from copyapp.report import _validate_ghidra_direct_queue
                        _validate_ghidra_direct_queue(
                            direct_dir, bundle, prefix, {record["binary_sha256"]})
                        direct_ok = True
                    else:
                        archive = output / "attempts" / (
                            "direct-ghidra-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
                        archive.parent.mkdir(exist_ok=True)
                        shutil.move(str(direct_dir), str(archive))
                        direct_ok = decompile_candidate_queue(
                            candidate_dir, direct_dir, ghidra_dir, rea_limit,
                            java_home, max(timeout, 60), disabled_analyzer,
                            native_dir if (native_dir / "index.json").is_file() else None)[1]
                elif direct_dir.exists():
                    raise ValueError("existing direct Ghidra queue is incomplete")
                else:
                    direct_ok = decompile_candidate_queue(
                        candidate_dir, direct_dir, ghidra_dir, rea_limit,
                        java_home, max(timeout, 60), disabled_analyzer,
                        native_dir if (native_dir / "index.json").is_file() else None)[1]
                record["direct_ghidra_status"] = "complete" if direct_ok else "failed"
                if not direct_ok:
                    raise RuntimeError("direct Ghidra queue failed; inspect direct-ghidra/queue.json")
            elif provider == "ghidra-direct":
                record["direct_ghidra_status"] = "not_requested"
            rea_ok = True
        elif resume and (rea_dir / "manifest.json").is_file():
            saved_queue = _read(rea_dir / "queue.json")
            if (saved_queue.get("kind") != "rea_candidate_queue" or
                    saved_queue.get("provider") != provider or
                    saved_queue.get("binary_sha256") != record["binary_sha256"] or
                    saved_queue.get("candidate_case_sha256") !=
                    sha256_file(candidate_dir / "candidates.json")):
                raise ValueError("existing REA queue belongs to another candidate or binary")
            with redirect_stdout(io.StringIO()):
                if not verify_case(rea_dir):
                    raise ValueError("existing REA queue evidence hash mismatch")
            if saved_queue.get("status") == "complete":
                from copyapp.report import _validate_rea_queue
                _validate_rea_queue(rea_dir, bundle, prefix, {record["binary_sha256"]})
                rea_ok = True
            else:
                archive = output / "attempts" / (
                    "rea-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
                archive.parent.mkdir(exist_ok=True)
                shutil.move(str(rea_dir), str(archive))
                record.setdefault("history", []).append({
                    "at": _now(), "archived_failed_rea": str(archive.relative_to(output)),
                    "manifest_sha256": sha256_file(archive / "manifest.json")})
                _, rea_ok = analyze_candidate_queue(candidate_dir, provider,
                                                     rea_dir, rea_limit, rea_script,
                                                     ghidra_dir, java_home, timeout)
        elif rea_dir.exists():
            raise ValueError("existing REA queue is incomplete; retain it and use a new output")
        else:
            _, rea_ok = analyze_candidate_queue(candidate_dir, provider,
                                                 rea_dir, rea_limit, rea_script,
                                                 ghidra_dir, java_home, timeout)
        record["rea_status"] = ("not_requested" if provider in ("none", "ghidra-direct") else
                                "complete" if rea_ok else "failed")
        if not rea_ok:
            raise RuntimeError("REA candidate queue failed; inspect rea/queue.json")
        stage = "review_brief"
        write_review_brief(output, plan)
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"stage": stage, "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        record["finished_at"] = _now()
        record["evidence"] = _files(output)
        (output / "manifest.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
