"""Compose the existing read-only collectors into a reproducible case."""

import asyncio
import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Dict

from copyapp.sandbox import index_sandbox_ssh
from copyapp.ssh_acquire import acquire_bundle_ssh
from copyapp.ui_evidence import ui_attribution
from copyapp.decrypt_package import decrypt_package
from copyapp.verify import verify_case


STAGE_PATHS = {
    "survey": Path("survey"),
    "bundle": Path("acquired"),
    "sandbox": Path("sandbox-index.json"),
    "decryption": Path("decrypted"),
}
STAGE_KEYS = {
    "survey": Path("survey/manifest.json"),
    "bundle": Path("acquired/acquisition.json"),
    "sandbox": Path("sandbox-index.json"),
    "decryption": Path("decrypted/decryption.json"),
}
STAGE_ARTIFACTS = {
    "survey": ("survey/app.json", "survey/ui.json", "survey/report.md",
               "survey/screenshot.jpg", "survey/screenshot.png"),
    "bundle": ("acquired/static/ipa-index.json", "acquired/static/ipa-report.md",
               "acquired/static/objc-index.json", "acquired/static/objc-report.md"),
    "sandbox": (),
    "decryption": ("decrypted/analysis.ipa", "decrypted/static/ipa-index.json",
                   "decrypted/static/ipa-report.md", "decrypted/static/objc-index.json",
                   "decrypted/static/objc-report.md"),
}


def _artifact_hashes(output: Path, name: str) -> dict:
    return {relative: _sha256(output / relative) for relative in STAGE_ARTIFACTS[name]
            if (output / relative).is_file()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _save_state(output: Path, state: dict) -> None:
    state["updated_at"] = _now()
    target = output / "run-state.json"
    temporary = output / "run-state.json.tmp"
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def _stage_valid(output: Path, name: str, record: dict, udid: str, bundle: str) -> bool:
    if not record.get("ok"):
        return False
    key = output / STAGE_KEYS[name]
    if not key.is_file() or not record.get("key_sha256") or _sha256(key) != record["key_sha256"]:
        return False
    saved_artifacts = record.get("artifact_hashes")
    if saved_artifacts is not None and (not isinstance(saved_artifacts, dict) or
                                        _artifact_hashes(output, name) != saved_artifacts):
        return False
    try:
        data = json.loads(key.read_text(encoding="utf-8"))
        _assert_stage_identity(output, name, data, udid, bundle)
        if name in ("survey", "bundle"):
            with redirect_stdout(io.StringIO()):
                return verify_case(output / STAGE_PATHS[name])
        if name == "decryption":
            snapshot = output / "acquired/bundle-snapshot.ipa"
            analysis_ipa = output / "decrypted/analysis.ipa"
            return (data.get("all_macho_headers_decrypted") is True and
                    snapshot.is_file() and _sha256(snapshot) == data.get("source_snapshot_sha256") and
                    analysis_ipa.is_file() and _sha256(analysis_ipa) == data.get("analysis_ipa_sha256") and
                    (output / "decrypted/static/ipa-index.json").is_file())
        return name == "sandbox" and isinstance(data.get("entries"), list)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _assert_stage_identity(output: Path, name: str, data: dict,
                           udid: str, bundle: str) -> None:
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    if data.get("bundle_id") != bundle or data.get("device_id_sha256_prefix") != prefix:
        raise ValueError(f"{name} identity differs from the selected device or app")
    if name == "survey":
        return
    survey_app = output / "survey/app.json"
    if survey_app.is_file():
        app = json.loads(survey_app.read_text(encoding="utf-8"))
        for survey_key, stage_key in (("CFBundleShortVersionString", "installed_version"),
                                      ("CFBundleVersion", "installed_build")):
            if app.get(survey_key) is not None and data.get(stage_key) is not None and \
                    str(app[survey_key]) != str(data[stage_key]):
                raise ValueError(f"{name} app version differs from the saved survey")
    if name in ("sandbox", "decryption"):
        acquisition = output / "acquired/acquisition.json"
        if acquisition.is_file():
            acquired = json.loads(acquisition.read_text(encoding="utf-8"))
            for key in ("installed_version", "installed_build"):
                if acquired.get(key) is not None and data.get(key) is not None and \
                        str(acquired[key]) != str(data[key]):
                    raise ValueError(f"{name} app version differs from acquired bundle")


def _archive_stage(output: Path, name: str) -> str:
    source = output / STAGE_PATHS[name]
    if not source.exists():
        return ""
    attempts = output / "attempts"
    attempts.mkdir(exist_ok=True)
    number = 1
    while (attempts / f"{name}-{number:02d}").exists():
        number += 1
    destination = attempts / f"{name}-{number:02d}"
    destination.mkdir()
    source.rename(destination / source.name)
    return str((destination / source.name).relative_to(output))


def _error_text(exc: Exception) -> str:
    return " ".join(f"{type(exc).__name__}: {exc}".split())[:240]


def _retain_attempt(state: dict, name: str, previous: dict, archived_path: str) -> None:
    if previous:
        state.setdefault("history", []).append({"stage": name, **previous,
                                                   "archived_path": archived_path})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_overview(output: Path, steps: Dict[str, dict]) -> Path:
    """Write a case index without treating missing collectors as empty evidence."""
    artifacts = {}
    for name, relative in (
        ("survey", "survey/manifest.json"),
        ("bundle", "acquired/acquisition.json"),
        ("static", "acquired/static/ipa-index.json"),
        ("objc", "acquired/static/objc-index.json"),
        ("sandbox", "sandbox-index.json"),
        ("decryption", "decrypted/decryption.json"),
        ("decrypted_static", "decrypted/static/ipa-index.json"),
        ("decrypted_objc", "decrypted/static/objc-index.json"),
    ):
        path = output / relative
        stage = ("survey" if name == "survey" else "bundle" if name in ("bundle", "static", "objc")
                 else "sandbox" if name == "sandbox" else "decryption")
        if path.is_file() and steps.get(stage, {}).get("ok"):
            artifacts[name] = {"path": relative, "sha256": _sha256(path)}
    index = {"schema_version": 1, "steps": steps, "artifacts": artifacts}
    index_path = output / "analysis-index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Copy APP 分析案例", "", "## 采集状态", ""]
    labels = [("survey", "USB 设备与界面"), ("bundle", "App 包与静态索引"),
              ("sandbox", "沙盒元数据")]
    if "decryption" in steps:
        labels.append(("decryption", "整包解密与复核"))
    for name, label in labels:
        entry = steps[name]
        state = "完成" if entry["ok"] else "失败"
        lines.append(f"- {label}：{state}" + (f"（{entry['error']}）" if not entry["ok"] else ""))
    lines.extend(["", "## 结果", ""])
    if "survey" in artifacts:
        lines.append("- [USB 初步采集报告](survey/report.md)")
        survey = json.loads((output / "survey" / "manifest.json").read_text(encoding="utf-8"))
        attribution = survey.get("ui_attribution", {}).get("status")
        if not attribution and (output / "survey" / "ui.json").is_file():
            app = json.loads((output / "survey" / "app.json").read_text(encoding="utf-8"))
            ui = json.loads((output / "survey" / "ui.json").read_text(encoding="utf-8"))
            target = str(app.get("CFBundleDisplayName") or app.get("CFBundleName") or survey.get("bundle_id"))
            attribution = ui_attribution(ui, target)["status"]
        if attribution == "different_app_system_permission":
            lines.append("- **界面证据不属于目标 App**：采集时出现其他 App 的系统权限弹窗，需重新采集目标前台界面。")
        elif attribution == "different_app_frontmost":
            lines.append("- **界面证据归属不符**：iOS MCP 在截图前后发现其他前台 App，需重新采集。")
        elif attribution == "verified_frontmost":
            lines.append("- iOS MCP 在截图前后均确认目标 App 位于前台。")
        elif attribution != "system_permission_for_target":
            lines.append("- 界面归属未验证，需核对截图和无障碍树。")
    if "static" in artifacts:
        lines.append("- [IPA 静态索引](acquired/static/ipa-report.md)")
    if "objc" in artifacts:
        lines.append("- [Objective-C 类与方法索引](acquired/static/objc-report.md)")
    if "decryption" in artifacts:
        lines.append("- [整包解密校验](decrypted/decryption.json)")
    if "decrypted_static" in artifacts:
        lines.append("- [解密后 IPA 静态索引](decrypted/static/ipa-report.md)")
    if "decrypted_objc" in artifacts:
        lines.append("- [解密后 Objective-C 类与方法索引](decrypted/static/objc-report.md)")
    if "sandbox" in artifacts:
        lines.append("- [沙盒元数据](sandbox-index.json)：仅路径、类型、大小和修改时间")
    if "survey" in artifacts:
        app = json.loads((output / "survey" / "app.json").read_text(encoding="utf-8"))
        lines.extend(["", "## 目标与运行环境", "",
                      f"- Bundle ID：`{survey.get('bundle_id', '未知')}`",
                      f"- 名称与版本：{app.get('CFBundleDisplayName') or app.get('CFBundleName') or '未知'} "
                      f"{app.get('CFBundleShortVersionString') or '未知'} "
                      f"(构建 {app.get('CFBundleVersion') or '未知'})",
                      f"- 设备：{survey.get('device', {}).get('ProductType') or '未知'} / "
                      f"iOS {survey.get('device', {}).get('ProductVersion') or '未知'}",
                      f"- 最低系统：{app.get('MinimumOSVersion') or '未知'}；"
                      f"SDK：{app.get('DTSDKName') or '未知'}",
                      f"- 权限键：{', '.join(app.get('entitlement_keys', [])) or '设备记录未返回'}",
                      "- 上述权限键来自安装服务的可见字段，不是完整签名权限审计。", ""])
        ui = json.loads((output / "survey" / "ui.json").read_text(encoding="utf-8"))
        lines.extend(["## 界面观察", "",
                      f"- 可访问元素：{len(ui.get('elements', []))} 个；"
                      f"截图状态：{survey.get('capabilities', {}).get('screenshot', '未知')}",
                      f"- 归属判断：{attribution or '未验证'}。此处不自动推断页面结构或交互流程。", ""])
    if "static" in artifacts:
        static = json.loads((output / "acquired" / "static" / "ipa-index.json").read_text(encoding="utf-8"))
        acquisition = json.loads((output / "acquired" / "acquisition.json").read_text(encoding="utf-8"))
        app_name = Path(acquisition["remote_bundle_path"]).name
        main_path = "Payload/" + app_name + "/" + str(static.get("executable", ""))
        main = next((item for item in static.get("binaries", []) if item.get("path") == main_path), {})
        libraries = main.get("linked_libraries", [])
        private = [item for item in libraries if "/PrivateFrameworks/" in item]
        lines.extend(["## 安装包与二进制", "",
                      f"- 分析快照包含 {static.get('file_count', 0)} 个 App 包路径；"
                      f"嵌入 Framework {len(static.get('frameworks', []))} 个，"
                      f"扩展 {len(static.get('extensions', []))} 个。",
                      f"- 主程序 SHA-256：`{main.get('sha256', '未取得')}`",
                      f"- 加密命令状态：`{main.get('encryption_status', '未知')}`。"
                      "这里不推断已由本工具脱壳。",
                      f"- 链接的动态库/Framework：{len(libraries)} 个；"
                      f"其中 PrivateFrameworks {len(private)} 个。", ""])
        for library in libraries:
            lines.append(f"  - `{library}`")
        lines.extend(["", "链接关系不等于运行时调用证据；具体功能仍需方法分析和实机跟踪。", ""])
    if "objc" in artifacts:
        objc = json.loads((output / "acquired" / "static" / "objc-index.json").read_text(encoding="utf-8"))
        classes = objc.get("classes", [])
        method_count = sum(len(item.get("instance_methods", [])) + len(item.get("class_methods", []))
                           for item in classes)
        lines.extend(["## Objective-C 元数据", "",
                      f"- 主程序本地定义 {len(classes)} 个类、{method_count} 个方法。"
                      "不包含导入类，也不包含函数体实现。", "",
                      "| 类 | 实例方法 | 类方法 |", "| --- | ---: | ---: |"])
        for item in classes:
            lines.append(f"| `{item['name']}` | {len(item.get('instance_methods', []))} | "
                         f"{len(item.get('class_methods', []))} |")
        lines.append("")
    if "decryption" in artifacts:
        decrypted = json.loads((output / "decrypted" / "decryption.json").read_text(encoding="utf-8"))
        lines.extend(["## 解密后分析包", "",
                      f"- 核查 Mach-O：{decrypted['checked_macho_count']} 个；"
                      f"恢复原加密二进制：{len(decrypted['recovered_binaries'])} 个。",
                      f"- 解密后主程序本地 Objective-C 类：{decrypted.get('objc_class_count')}；"
                      f"方法：{decrypted.get('objc_method_count')}。",
                      f"- 分析 IPA SHA-256：`{decrypted['analysis_ipa_sha256']}`。",
                      "- 分析 IPA 已修改可执行文件，代码签名无效；这里不判断能否安装。", ""])
    if "sandbox" in artifacts:
        sandbox = json.loads((output / "sandbox-index.json").read_text(encoding="utf-8"))
        entries = sandbox.get("entries", [])
        top = sorted({item["relative"].split("/", 1)[0] for item in entries if item.get("relative")})
        lines.extend(["## 数据容器", "",
                      f"- 深度上限：{sandbox.get('depth_limit', '未知')}；"
                      f"记录 {len(entries)} 个路径。",
                      f"- 顶层名称：{', '.join(f'`{name}`' for name in top) or '无可见条目'}。",
                      "- 只读取了元数据；文件正文、数据库结构与实际读写行为尚未验证。", ""])
    lines.extend(["", "## 证据边界", "",
                  "包快照是从已安装 `.app` 重新打包的分析材料，不等同于原始 IPA。",
                  ("本次已执行整包解密与校验；尚未执行方法反编译、动态跟踪或自动复刻。"
                   if "decryption" in artifacts else
                   "本次未执行脱壳、方法反编译、动态跟踪或自动复刻。") +
                  "截图仍需人工核对具体内容。",
                  "每项完成情况和关键文件哈希见 `analysis-index.json`。", ""])
    report_path = output / "analysis.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


async def analyze_case(udid: str, bundle: str, output: Path, launch: bool,
                       ssh_port: int, ssh_user: str, ssh_identity: Path,
                       ssh_known_hosts: Path,
                       survey: Callable[..., Awaitable[int]],
                       decrypt: bool = False,
                       decrypt_helper: Path = Path("../toolchains/ipadecrypt-helper-arm64"),
                       resume: bool = False) -> bool:
    state_path = output / "run-state.json"
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    if resume:
        if not state_path.is_file():
            raise FileNotFoundError("run-state.json is required for --resume")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if (state.get("schema_version") != 1 or state.get("bundle_id") != bundle or
                state.get("device_id_sha256_prefix") != prefix):
            raise ValueError("resume target does not match saved device and bundle")
        if state.get("decrypt_requested") and not decrypt:
            raise ValueError("resume must retain --decrypt from the original run")
        state["decrypt_requested"] = decrypt
    else:
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"output directory is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        state = {"schema_version": 1, "bundle_id": bundle,
                 "device_id_sha256_prefix": prefix,
                 "decrypt_requested": decrypt, "created_at": _now(),
                 "steps": {}, "history": []}
        _save_state(output, state)
    steps = {}
    for name, collector in (
        ("survey", lambda: survey(udid, bundle, output / "survey", launch)),
        ("bundle", lambda: acquire_bundle_ssh(
            udid, bundle, output / "acquired", ssh_port,
            ssh_identity, ssh_known_hosts, ssh_user)),
        ("sandbox", lambda: index_sandbox_ssh(
            udid, bundle, output / "sandbox-index.json", ssh_port,
            ssh_identity, ssh_known_hosts, ssh_user)),
    ):
        previous = state["steps"].get(name, {})
        if resume and _stage_valid(output, name, previous, udid, bundle):
            steps[name] = dict(previous, reused=True)
            continue
        archived = _archive_stage(output, name) if resume else ""
        _retain_attempt(state, name, previous, archived)
        attempt = int(previous.get("attempt", 0)) + 1
        state["steps"][name] = {"ok": False, "status": "running",
                                "attempt": attempt, "started_at": _now()}
        _save_state(output, state)
        try:
            await collector()
            key = output / STAGE_KEYS[name]
            if not key.is_file():
                raise FileNotFoundError(f"{name} evidence manifest missing")
            _assert_stage_identity(output, name, json.loads(key.read_text(encoding="utf-8")),
                                   udid, bundle)
            steps[name] = {"ok": True, "status": "complete", "attempt": attempt,
                           "key_sha256": _sha256(key),
                           "artifact_hashes": _artifact_hashes(output, name)}
        except Exception as exc:
            steps[name] = {"ok": False, "status": "failed", "attempt": attempt,
                           "error": _error_text(exc)}
        state["steps"][name] = steps[name]
        _save_state(output, state)
    if decrypt:
        if not steps["bundle"]["ok"]:
            steps["decryption"] = {"ok": False, "error": "bundle acquisition failed"}
        else:
            previous = state["steps"].get("decryption", {})
            if resume and _stage_valid(output, "decryption", previous, udid, bundle):
                steps["decryption"] = dict(previous, reused=True)
            else:
                archived = _archive_stage(output, "decryption") if resume else ""
                _retain_attempt(state, "decryption", previous, archived)
                attempt = int(previous.get("attempt", 0)) + 1
                state["steps"]["decryption"] = {"ok": False, "status": "running",
                                                 "attempt": attempt, "started_at": _now()}
                _save_state(output, state)
                try:
                    await asyncio.to_thread(
                        decrypt_package, udid, bundle, output / "acquired" / "bundle-snapshot.ipa",
                        decrypt_helper, output / "decrypted", ssh_port,
                        ssh_identity, ssh_known_hosts)
                    key = output / STAGE_KEYS["decryption"]
                    if not key.is_file():
                        raise FileNotFoundError("decryption evidence manifest missing")
                    _assert_stage_identity(output, "decryption",
                                           json.loads(key.read_text(encoding="utf-8")),
                                           udid, bundle)
                    steps["decryption"] = {"ok": True, "status": "complete", "attempt": attempt,
                                           "key_sha256": _sha256(key),
                                           "artifact_hashes": _artifact_hashes(output, "decryption")}
                except Exception as exc:
                    steps["decryption"] = {"ok": False, "status": "failed", "attempt": attempt,
                                           "error": _error_text(exc)}
                state["steps"]["decryption"] = steps["decryption"]
                _save_state(output, state)
        state["steps"]["decryption"] = steps["decryption"]
        _save_state(output, state)
    print(write_overview(output, steps))
    return all(item["ok"] for item in steps.values())
