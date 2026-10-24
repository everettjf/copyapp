"""Small, evidence-first USB survey for one installed iOS app."""

import argparse
import asyncio
import hashlib
import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
from pymobiledevice3.services.house_arrest import HouseArrestService
from pymobiledevice3.services.installation_proxy import InstallationProxyService
from pymobiledevice3.services.springboard import SpringBoardServicesService
from pymobiledevice3.usbmux import list_devices

from copyapp.ipa import analyze_ipa, write_ipa_report
from copyapp.device_developer import launch_app, take_screenshot, list_directory
from copyapp.acquire import acquire_bundle
from copyapp.ssh_acquire import acquire_bundle_ssh
from copyapp.ios_mcp import IOSMCPClient
from copyapp.usb_tunnel import exact_ssh_tunnel, ios_mcp_tunnel
from copyapp.sandbox import index_sandbox_ssh
from copyapp.sandbox_capture import capture_sandbox_files
from copyapp.sandbox_diff import compare_sandbox
from copyapp.sqlite_schema import create_sqlite_schema
from copyapp.plist_schema import create_plist_schema
from copyapp.usb_ax import usb_ax
from copyapp.analyze import analyze_case
from copyapp.objc import index_objc, write_objc_report
from copyapp.verify import verify_case
from copyapp.ui_evidence import ui_attribution
from copyapp.ictrl import ICtrlClient, DEFAULT_CLIENT
from copyapp.ictrl_setup import setup_ictrl
from copyapp.frida_sidecar import setup_roothide_sidecar
from copyapp.trace import parse_branch_register, trace_methods
from copyapp.experiment import trace_tap
from copyapp.decrypt_verify import inspect_decrypted_ipa, write_decryption_check
from copyapp.decrypt import decrypt_main, decrypt_extension
from copyapp.assemble import assemble_analysis_ipa
from copyapp.root_bridge import run_root_command
from copyapp.decrypt_package import decrypt_package
from copyapp.ghidra_direct import decompile_ghidra_function
from copyapp.hopper_direct import decompile_hopper_function
from copyapp.hopper_queue import decompile_hopper_queue
from copyapp.ghidra_queue import decompile_candidate_queue
from copyapp.indirect_follow import follow_indirect
from copyapp.native_disasm import (disassemble_native_candidates,
                                   disassemble_native_function)
from copyapp.investigate_app import investigate_app
from copyapp.rebuild_check import rebuild_check
from copyapp.draft_analysis import draft_analysis
from copyapp.prepare_analysis import prepare_analysis
from copyapp.prepare_app import prepare_app
from copyapp.copy_workflow import copy_app
from copyapp.output_paths import copy_paths
from copyapp.prepare_rebuild import prepare_rebuild
from copyapp.install import install_trollstore_ipa, install_usb_ipa
from copyapp.report import compose_report
from copyapp.report_portfolio import create_report_portfolio
from copyapp.host_ocr import recognize_screenshot
from copyapp.ocr_file import ocr_file
from copyapp.ui_capture import capture_stable
from copyapp.playbook import run_playbook
from copyapp.playbook_auto import run_playbook_auto
from copyapp.discover_check import check_discovered_flows, accepted_playbooks
from copyapp.compare_playbooks import compare_playbooks
from copyapp.doctor import run_doctor
from copyapp.onboarding import run_onboarding
from copyapp.ssh_profile import apply_ssh_profile, remember_verified_doctor_case
from copyapp.tunnels import run_tunnels
from copyapp.candidates import build_candidates
from copyapp.view_tree import capture_view_tree
from copyapp.flow_capture import capture_flow
from copyapp.network_flow import run_network_flow
from copyapp.branch_map import build_branch_map
from copyapp.rebuild_plan import create_rebuild_plan
from copyapp.rebuild_task_check import rebuild_task_check
from copyapp.agent_task import create_agent_task
from copyapp.agent_run import run_agent_task
from copyapp.agent_delivery import create_agent_delivery
from copyapp.coverage import create_coverage_plan, create_coverage_delivery
from copyapp.analysis_delivery import create_analysis_delivery
from copyapp.visual_audit import create_visual_audit
from copyapp.visual_review import create_visual_review
from copyapp.investigate_flow import investigate_flow


APP_FIELDS = (
    "CFBundleIdentifier", "CFBundleDisplayName", "CFBundleName",
    "CFBundleShortVersionString", "CFBundleVersion", "CFBundleExecutable",
    "MinimumOSVersion", "ApplicationType", "Path", "Container",
    "UIBackgroundModes", "CFBundleURLTypes", "NSAppTransportSecurity",
    "UIRequiredDeviceCapabilities", "DTSDKName", "DTXcode",
)
DEVICE_FIELDS = ("ProductType", "ProductVersion", "BuildVersion", "CPUArchitecture")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> str:
    data = (json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def save_evidence(out: Path, name: str, payload: Any, kind: str) -> Dict[str, str]:
    path = out / name
    if kind == "json":
        digest = write_json(path, payload)
    else:
        path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
    return {"id": name.replace(".", "-"), "path": name, "sha256": digest, "kind": kind}


async def installed_apps(device, bundle: Optional[str] = None,
                         include_system: bool = False) -> Dict[str, Dict[str, Any]]:
    async with InstallationProxyService(device) as proxy:
        return await proxy.get_apps(
            application_type="Any" if bundle or include_system else "User",
            bundle_identifiers=[bundle] if bundle else None,
        )


async def sandbox_top_level(device, bundle: str) -> Dict[str, Any]:
    async with await HouseArrestService.create(device, bundle) as afc:
        entries = []
        for name in sorted(await afc.listdir("/")):
            if name in (".", ".."):
                continue
            stat = await afc.stat("/" + name)
            entries.append({
                "name": name, "type": stat.get("st_ifmt"), "size": stat.get("st_size")
            })
        return {"scope": "app data container, top level only", "entries": entries}


async def bundle_index(device, udid: str, ios_version: str,
                       app_path: Optional[str]) -> Dict[str, Any]:
    if not app_path:
        return {"status": "安装路径未返回", "entries": []}
    entries = []
    root_items, route = await list_directory(device, udid, ios_version, app_path)
    entries.extend(root_items[:500])
    for directory in ("Frameworks", "PlugIns", "Library"):
        subpath = app_path.rstrip("/") + "/" + directory
        if subpath in root_items:
            try:
                children, _ = await list_directory(device, udid, ios_version, subpath)
                entries.extend(children[:500])
            except Exception:
                pass
    return {
        "status": "已采集",
        "scope": "bundle root and Frameworks/PlugIns/Library direct children",
        "route": route,
        "entries": sorted(set(entries)),
    }


async def jailbreak_markers(device, udid: str, ios_version: str) -> Dict[str, Any]:
    try:
        entries, route = await list_directory(device, udid, ios_version, "/var/jb")
        names = {path.rsplit("/", 1)[-1] for path in entries}
        return {
            "var_jb_readable": True,
            "route": route,
            "dopamine_marker": ".installed_dopamine" in names,
            "procursus_marker": ".procursus_strapped" in names,
        }
    except Exception as exc:
        return {"var_jb_readable": False, "error": type(exc).__name__}


def report_text(manifest: Dict[str, Any], app: Dict[str, Any], sandbox: Dict[str, Any],
                bundle_index_data: Dict[str, Any], ui: Dict[str, Any]) -> str:
    name = app.get("CFBundleDisplayName") or app.get("CFBundleName") or manifest["bundle_id"]
    entitlements = app.get("entitlement_keys", [])
    sandbox_lines = [
        "| " + str(e["name"]) + " | " + str(e.get("type", "?")) + " | " + str(e.get("size", "?")) + " |"
        for e in sandbox.get("entries", [])
    ]
    captions = [e.get("caption", "") for e in ui.get("elements", []) if e.get("caption")]
    bundle_names = [entry.rsplit("/", 1)[-1] for entry in bundle_index_data.get("entries", [])]
    libraries = sorted(name for name in bundle_names if name.endswith((".dylib", ".framework")))
    extensions = sorted(name for name in bundle_names if name.endswith(".appex"))
    backup_name = str(app.get("CFBundleExecutable", "")) + "_TROLLSTORE_BACKUP"
    persistence_helper = ".TrollStorePersistenceHelper" in bundle_names and backup_name in bundle_names
    markers = manifest["jailbreak_markers"]
    marker_summary = (f"`/var/jb` 可列出：{markers['var_jb_readable']}；Dopamine 标记：{markers.get('dopamine_marker', False)}"
                      if markers.get("var_jb_readable") else
                      "普通开发者文件服务无法读取越狱目录；不能据此判断越狱状态或类型")
    lines = [
        "# " + name + " · Copy APP 初步采集报告", "",
        "> 本报告只陈述本次设备采集能证实的内容；尚未取得的 IPA、类、方法和运行轨迹标为未采集。", "",
        "## 目标与设备", "",
        f"- Bundle ID：`{manifest['bundle_id']}`",
        f"- App 版本：{app.get('CFBundleShortVersionString', '未知')}（构建 {app.get('CFBundleVersion', '未知')}）",
        f"- 设备：{manifest['device']['ProductType']} / iOS {manifest['device']['ProductVersion']}",
        f"- 越狱目录：{marker_summary}",
        f"- 采集时间：{manifest['created_at']}", "",
        "## 安装包线索", "",
        f"- 主程序：`{app.get('CFBundleExecutable', '未知')}`",
        f"- 安装路径：`{app.get('Path', '未知')}`",
        f"- 最低系统版本：{app.get('MinimumOSVersion', '未知')}",
        f"- SDK：{app.get('DTSDKName', '未知')}",
        f"- 后台模式：{', '.join(app.get('UIBackgroundModes', [])) or '未声明'}",
        f"- 可见权限键：{', '.join(entitlements) or '未返回'}", "",
        "## 包文件索引", "",
        f"状态：{bundle_index_data.get('status', '未知')}，索引 {len(bundle_names)} 个路径。完整路径见 `bundle.json`。", "",
        f"- 可见动态库/Framework 名称：{', '.join(libraries) or '未在索引范围发现'}",
        f"- 可见扩展：{', '.join(extensions) or '未在索引范围发现'}", "",
        *([f"**入口变更线索**：包内同时存在 `.TrollStorePersistenceHelper` 与 `{backup_name}`。当前图标可能启动 TrollStore Helper，不能把该界面当作原始 App。", ""] if persistence_helper else []),
        "## 沙盒顶层索引", "",
        f"状态：{sandbox.get('status', '已采集')}。未读取文件正文。", "",
        "| 名称 | 类型 | 大小（字节） |", "| --- | --- | ---: |",
        *(sandbox_lines or ["| 无可见条目 | — | — |"]), "",
        "## 当前界面", "",
        "界面归属：" + ({
            "verified_frontmost": "iOS MCP 在截图前后均确认目标 App 位于前台。",
            "different_app_frontmost": "iOS MCP 发现截图前后前台 App 与目标不一致；本次界面证据不得归给目标 App。",
            "different_app_system_permission": "发现其他 App 的系统权限弹窗；本次截图/无障碍树不得归给目标 App。",
            "system_permission_for_target": "目标 App 的系统权限弹窗覆盖界面；可确认弹窗归属，底层页面仍需单独核对。",
        }.get(manifest.get("ui_attribution", {}).get("status"),
              "未由工具验证。截图和无障碍元素只代表采集瞬间的前台页面，需人工确认是否为目标 App。")), "",
        f"截图：`{'screenshot.jpg' if manifest.get('ui_backend') == 'ios-mcp' else 'screenshot.png'}`（{manifest['capabilities'].get('screenshot', '不可用')}）",
        f"无障碍元素：{len(ui.get('elements', []))} 个（{ui.get('status', '已采集')}）", "",
        *(f"- {caption}" for caption in captions[:30]), "",
        "## 能力与证据边界", "",
        "- AFC2 越狱文件服务：本次采集未调用；可另行安装/检测。",
        f"- IPA/解密主程序：未采集；目前不能判断加密状态、动态库依赖、ObjC/Swift 类或核心实现。",
        "- Frida 跟踪、网络和功能流程：未采集。", "",
        "## 证据索引", "",
        *(f"- `{e['id']}` → `{e['path']}` · SHA-256 `{e['sha256']}`" for e in manifest["evidence"]), "",
    ]
    return "\n".join(lines)


async def command_devices() -> int:
    devices = await list_devices()
    for item in devices:
        print(item)
    return 0


async def command_apps(udid: str, include_system: bool = False) -> int:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        apps = await installed_apps(device, include_system=include_system)
        for bundle, info in sorted(apps.items()):
            print("\t".join((
                bundle,
                str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or ""),
                str(info.get("CFBundleShortVersionString") or ""),
            )))
    finally:
        await device.close()
    return 0


async def usb_screenshot(udid: str) -> bytes:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("lockdown device identity does not match requested UDID")
        picture, _ = await take_screenshot(device, udid, str(values.get("ProductVersion", "")))
        return picture
    finally:
        await device.close()


async def command_survey(udid: str, bundle: str, output: Path, launch: bool,
                         ui_backend: str = "usb") -> int:
    if ui_backend == "ios-mcp":
        with ios_mcp_tunnel(udid) as port:
            return await _command_survey(udid, bundle, output, launch,
                                         ui_backend, IOSMCPClient(port=port))
    return await _command_survey(udid, bundle, output, launch, ui_backend, None)


async def _command_survey(udid: str, bundle: str, output: Path, launch: bool,
                          ui_backend: str, mcp: Optional[IOSMCPClient]) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid bundle id")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("lockdown device identity does not match requested UDID")
        device_info = {field: values.get(field) for field in DEVICE_FIELDS}
        apps = await installed_apps(device, bundle)
        if bundle not in apps:
            raise ValueError(f"app not installed: {bundle}")
        raw = apps[bundle]
        app = {field: raw[field] for field in APP_FIELDS if field in raw}
        app["entitlement_keys"] = sorted(raw.get("Entitlements", {}).keys())
        evidence = [save_evidence(output, "app.json", app, "json")]
        capabilities: Dict[str, Any] = {}

        if mcp is not None:
            mcp.initialize()
        if launch:
            if mcp is not None:
                mcp.call_ui("launch_app", {"bundle_id": bundle})
            else:
                await launch_app(device, udid, str(device_info.get("ProductVersion", "")), bundle)
            await asyncio.sleep(2)

        try:
            bundle_data = await bundle_index(device, udid,
                                             str(device_info.get("ProductVersion", "")),
                                             app.get("Path"))
            capabilities["bundle_index"] = True
        except Exception as exc:
            bundle_data = {"status": f"不可用：{type(exc).__name__}", "entries": []}
            capabilities["bundle_index"] = False
        evidence.append(save_evidence(output, "bundle.json", bundle_data, "json"))
        markers = await jailbreak_markers(device, udid,
                                           str(device_info.get("ProductVersion", "")))
        evidence.append(save_evidence(output, "jailbreak.json", markers, "json"))

        try:
            sandbox = await sandbox_top_level(device, bundle)
            sandbox["status"] = "已采集"
            capabilities["sandbox"] = True
        except Exception as exc:
            sandbox = {"status": f"不可用：{type(exc).__name__}: {str(exc)[:160]}", "entries": []}
            capabilities["sandbox"] = False
        evidence.append(save_evidence(output, "sandbox.json", sandbox, "json"))

        before_frontmost = after_frontmost = None
        if mcp is not None:
            try:
                arguments = {"include_ocr": False, "include_screenshot": False}
                before = IOSMCPClient.text_json(mcp.call_ui("describe_screen", arguments))
                screenshot = IOSMCPClient.image_bytes(mcp.call_ui("screenshot"))
                after = IOSMCPClient.text_json(mcp.call_ui("describe_screen", arguments))
                before_frontmost = before.get("frontmost", {}).get("bundleId")
                after_frontmost = after.get("frontmost", {}).get("bundleId")
                evidence.append(save_evidence(output, "screenshot.jpg", screenshot, "binary"))
                capabilities["screenshot"] = "已采集（iOS MCP）"
                elements = [{**item, "caption": item.get("text", "")}
                            for item in after.get("elements", [])]
                ui = {"status": "已采集", "source": "ios-mcp",
                      "frontmost_before": before.get("frontmost"),
                      "frontmost_after": after.get("frontmost"), "elements": elements}
                capabilities["accessibility"] = True
            except Exception as exc:
                capabilities["screenshot"] = f"不可用：{type(exc).__name__}"
                capabilities["accessibility"] = False
                ui = {"status": f"不可用：{type(exc).__name__}", "elements": []}
        else:
            try:
                screenshot, route = await take_screenshot(
                    device, udid, str(device_info.get("ProductVersion", "")))
                evidence.append(save_evidence(output, "screenshot.png", screenshot, "binary"))
                capabilities["screenshot"] = "已采集（" + route + "）"
            except Exception as exc:
                capabilities["screenshot"] = f"不可用：{type(exc).__name__}"
            try:
                async with AccessibilityAudit(device) as audit:
                    elements = [element.to_dict() async for element in audit.iter_elements()]
                ui = {"status": "已采集", "elements": elements}
                capabilities["accessibility"] = True
            except Exception as exc:
                ui = {"status": f"不可用：{type(exc).__name__}", "elements": []}
                capabilities["accessibility"] = False
        evidence.append(save_evidence(output, "ui.json", ui, "json"))
        attribution = ui_attribution(
            ui, str(app.get("CFBundleDisplayName") or app.get("CFBundleName") or bundle))
        if mcp is not None and attribution["status"] == "unverified":
            if before_frontmost == after_frontmost == bundle:
                attribution = {"status": "verified_frontmost", "observed_bundle_id": bundle}
            elif before_frontmost or after_frontmost:
                attribution = {"status": "different_app_frontmost",
                               "before_bundle_id": before_frontmost,
                               "after_bundle_id": after_frontmost}

        capabilities["afc2"] = "not_probed"
        manifest = {
            "schema_version": 1, "created_at": utc_now(), "bundle_id": bundle,
            "ui_backend": ui_backend,
            "device": device_info,
            "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
            "jailbreak_markers": markers, "capabilities": capabilities, "evidence": evidence,
            "ui_attribution": attribution,
        }
        write_json(output / "manifest.json", manifest)
        (output / "report.md").write_text(
            report_text(manifest, app, sandbox, bundle_data, ui), encoding="utf-8"
        )
        print(output / "report.md")
        return 0
    finally:
        await device.close()


def command_mode_analysis(args) -> tuple[Path, bool]:
    """Use the new UI-first contract while leaving unflagged v1 commands intact."""
    from copyapp.ios_analysis import collect_ios_analysis, enhancement_settings

    if getattr(args, "no_launch", False):
        raise ValueError("UI-first analysis requires fresh-launch playbooks; --no-launch is incompatible")
    if getattr(args, "provider", "none") != "none" or getattr(args, "network", False):
        raise ValueError("UI-first collection does not silently run function/network investigations; "
                         "use explicit enhanced investigation commands for these evidence types")
    if args.mode == "standard" and args.decrypt:
        raise ValueError("--decrypt requests device recovery and requires enhanced mode; "
                         "offline package recovery is a separate host input")
    mode = "enhanced" if args.decrypt and args.mode == "auto" else args.mode
    survey_collector = lambda udid, bundle, output, launch: command_survey(
        udid, bundle, output, launch, args.ui_backend)

    def enhanced(output):
        return asyncio.run(analyze_case(
            args.udid, args.bundle, output, True, args.ssh_port, args.ssh_user,
            args.ssh_identity, args.ssh_known_hosts, survey_collector, args.decrypt,
            args.decrypt_helper, output.exists()))

    return collect_ios_analysis(
        args.udid, args.bundle, args.script, args.out, mode, args.resume, args.retry_failed,
        ssh_port=args.ssh_port, ssh_identity=args.ssh_identity,
        ssh_known_hosts=args.ssh_known_hosts, enhanced_collector=enhanced,
        package_cases=args.package_case,
        enhancement_request=enhancement_settings(
            args.decrypt, args.ui_backend, args.ssh_port, args.ssh_user,
            args.ssh_identity, args.ssh_known_hosts, args.decrypt_helper) if mode != "standard" else None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy APP: iOS workflows and macOS App support")
    sub = parser.add_subparsers(dest="command", required=True)
    mac = sub.add_parser("mac", help="macOS App support through ChatComputer")
    from copyapp.macos.cli import configure as configure_mac
    configure_mac(mac)
    sub.add_parser("devices", help="list connected USB devices")
    imported_package = sub.add_parser("package-import", help="retain and index an external iOS IPA without requiring a phone")
    imported_package.add_argument("--ipa", required=True, type=Path)
    imported_package.add_argument("--bundle")
    imported_package.add_argument("--out", required=True, type=Path)
    store_package = sub.add_parser("store-download", help="download an account-owned iOS package through authenticated ipatool")
    store_package.add_argument("--bundle", required=True)
    store_package.add_argument("--ipatool", type=Path)
    store_package.add_argument("--external-version-id")
    store_package.add_argument("--acquire-license", action="store_true",
                               help="explicitly request a free App license if needed; ipatool cannot purchase paid Apps")
    store_package.add_argument("--timeout", type=int, default=600)
    store_package.add_argument("--out", required=True, type=Path)
    offline_package = sub.add_parser("decrypt-offline", help="recover a host-side package with a pinned decoder and optional local credential")
    offline_package.add_argument("--package", required=True, type=Path)
    offline_package.add_argument("--tool-dir", type=Path,
                                 help="default: pinned sources under the COPYAPP_SOURCE_ROOT checkout")
    offline_package.add_argument("--credential-ref", help="opaque alias for a 16-byte .bin in the local credential store; never put the key itself here")
    offline_package.add_argument("--credential-store", type=Path,
                                 help="default: ignored cases/credentials/fairplay under the source checkout")
    offline_package.add_argument("--timeout", type=int, default=600)
    offline_package.add_argument("--out", required=True, type=Path)
    offline_cross = sub.add_parser("offline-cross-check",
                                   help="compare offline recovered code with a separately verified device recovery")
    offline_cross.add_argument("--offline", required=True, type=Path)
    offline_cross.add_argument("--device", required=True, type=Path)
    offline_cross.add_argument("--out", required=True, type=Path)
    onboard = sub.add_parser("onboard", help="identify one phone and print exact setup repairs")
    onboard.add_argument("--udid", help="required when more than one USB device is connected")
    onboard.add_argument("--out", type=Path, help="new setup case; defaults to a dated cases/ directory")
    onboard.add_argument("--stage", choices=("survey", "analyze", "rebuild"),
                         default="survey", help="show repairs for the chosen setup milestone")
    onboard.add_argument("--mode", choices=("auto", "standard", "enhanced"),
                         help="operation-specific setup; omit to retain the historical jailbreak workflow")
    onboard.add_argument("--ssh-port", type=int, default=22222)
    onboard.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    onboard.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    onboard.add_argument("--no-keygen", action="store_true",
                         help="leave local SSH key creation to the user")
    tunnel = sub.add_parser("tunnel", help="keep SSH and iOS MCP USB forwards in one terminal")
    tunnel.add_argument("--udid", required=True)
    tunnel.add_argument("--ssh-port", type=int, default=22222)
    tunnel.add_argument("--mcp-port", type=int, default=22223)
    modes = tunnel.add_mutually_exclusive_group()
    modes.add_argument("--ssh-only", action="store_true")
    modes.add_argument("--mcp-only", action="store_true")
    setup = sub.add_parser("setup", help="build, install and pair optional device tooling")
    setup.add_argument("component", choices=("ictrl", "frida-roothide"))
    setup.add_argument("--udid", required=True)
    setup.add_argument("--out", required=True, type=Path)
    setup.add_argument("--runner-ipa", type=Path,
                       help="use an already signed runner IPA instead of building it")
    setup.add_argument("--frida-deb", type=Path,
                       help="use the SHA-256 pinned official Frida package already downloaded")
    setup.add_argument("--reinstall", action="store_true",
                       help="reinstall the runner even when its Bundle ID is already installed")
    setup.add_argument("--transport", choices=("auto", "usb"), default="auto",
                       help="usb forbids SSH/TrollStore installation fallback for the runner")
    setup.add_argument("--auto-approve-first-pair", action="store_true",
                       help="on iOS 17+, let the development runner approve one local USB pairing")
    setup.add_argument("--ssh-port", type=int, default=22222)
    setup.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    setup.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    doctor = sub.add_parser("doctor", help="record capability baseline for one exact USB iPhone")
    doctor.add_argument("--udid", required=True)
    doctor.add_argument("--out", required=True, type=Path)
    doctor.add_argument("--ssh-port", type=int, default=22222)
    doctor.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    doctor.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    doctor.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    doctor.add_argument("--mode", choices=("auto", "standard", "enhanced"),
                        help="write an operation-specific v2 capability case; standard skips jailbreak probes")
    verify = sub.add_parser("verify", help="verify saved evidence hashes")
    verify.add_argument("case", type=Path)
    ocr_saved = sub.add_parser("ocr-file", help="run hash-pinned macOS Vision OCR on a saved screenshot")
    ocr_saved.add_argument("file", type=Path)
    ocr_saved.add_argument("--roi", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"))
    ocr_saved.add_argument("--out", required=True, type=Path)
    views = sub.add_parser("view-tree", help="capture a bounded UIKit subview tree from a running app")
    views.add_argument("--udid", required=True)
    views.add_argument("--bundle", required=True)
    views.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    views.add_argument("--port", type=int)
    views.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    views.add_argument("--no-launch", action="store_true",
                       help="scan only if the target is already frontmost; preserve its current page")
    views.add_argument("--out", required=True, type=Path)
    flow = sub.add_parser("flow-capture", help="replay one UI flow and capture its resulting view tree")
    flow.add_argument("--udid", required=True)
    flow.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    flow.add_argument("--script", required=True, type=Path)
    flow.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    flow.add_argument("--method", action="append", dest="methods",
                      help="trace ClassName::selector: during each tap; repeat for more methods")
    flow.add_argument("--arg2-u32-method", action="append", dest="arg2_u32_methods",
                      help="save raw third Objective-C argument for this traced method; repeat as needed")
    flow.add_argument("--branch-offset", action="append", type=lambda value: int(value, 0),
                      dest="branch_offsets", help="also count a selected app-image function offset")
    flow.add_argument("--branch-return-u32-offset", action="append",
                      type=lambda value: int(value, 0), dest="branch_return_u32_offsets",
                      help="save raw low 32 return bits for a selected --branch-offset")
    flow.add_argument("--branch-register", action="append", type=parse_branch_register,
                      dest="branch_registers",
                      help="at a selected --branch-offset, map one x0–x30 pointer to an app-image offset; OFFSET:xN")
    flow.add_argument("--binary", type=Path, help="acquired app Mach-O for static entry binding")
    flow.add_argument("--objc-index", type=Path, help="matching Objective-C index")
    flow.add_argument("--network", action="store_true",
                      help="observe bounded URLSession metadata during the same UI steps")
    flow.add_argument("--out", required=True, type=Path)
    branch_map = sub.add_parser("branch-map", help="correlate verified raw method arguments with branch hits")
    branch_map.add_argument("--flow", required=True, action="append", type=Path,
                            help="completed flow-capture case; repeat for more flows")
    branch_map.add_argument("--method", required=True, help="ClassName::selector: captured with raw argument 2")
    branch_map.add_argument("--binary", required=True, type=Path,
                            help="exact acquired Mach-O used for static Frida entry binding")
    branch_map.add_argument("--out", required=True, type=Path)
    investigate = sub.add_parser("investigate-flow",
                                 help="investigate one UI flow with native assembly or direct Ghidra/Hopper")
    investigate.add_argument("--udid", required=True)
    investigate.add_argument("--analysis", required=True, type=Path)
    investigate.add_argument("--script", required=True, type=Path)
    investigate.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    investigate.add_argument("--method", action="append", dest="methods",
                             help="override heuristic method choice; repeat for more methods")
    investigate.add_argument("--provider", choices=("none", "ghidra-direct", "hopper-direct"), default="none")
    investigate.add_argument("--function-limit", dest="rea_limit",
                             type=int, default=4, metavar="N",
                             help="maximum observed entry functions; direct Ghidra may also follow bounded native calls")
    investigate.add_argument("--ghidra-dir", type=Path)
    investigate.add_argument("--hopper-app", type=Path)
    investigate.add_argument("--java-home", type=Path)
    investigate.add_argument("--ghidra-disable-analyzer")
    investigate.add_argument("--network", action="store_true",
                             help="include URLSession metadata in the same investigated UI flow")
    investigate.add_argument("--timeout", type=int, default=240)
    investigate.add_argument("--resume", action="store_true",
                             help="reuse hash-verified completed stages without repeating device taps")
    investigate.add_argument("--out", required=True, type=Path)
    app_investigate = sub.add_parser("investigate-app",
                                    help="run several verified UI investigations for one app")
    app_investigate.add_argument("--udid", required=True)
    app_investigate.add_argument("--analysis", required=True, type=Path)
    app_investigate.add_argument("--script", required=True, action="append", type=Path,
                                 help="bounded playbook; repeat for each selected flow")
    app_investigate.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    app_investigate.add_argument("--provider", choices=("none", "ghidra-direct", "hopper-direct"), default="none")
    app_investigate.add_argument("--function-limit", dest="rea_limit",
                                 type=int, default=4, metavar="N",
                                 help="maximum observed entry functions; direct Ghidra may also follow bounded native calls")
    app_investigate.add_argument("--ghidra-dir", type=Path)
    app_investigate.add_argument("--hopper-app", type=Path)
    app_investigate.add_argument("--java-home", type=Path)
    app_investigate.add_argument("--ghidra-disable-analyzer")
    app_investigate.add_argument("--network", action="store_true",
                                 help="include URLSession metadata in each investigated UI flow")
    app_investigate.add_argument("--timeout", type=int, default=240)
    app_investigate.add_argument("--resume", action="store_true")
    app_investigate.add_argument("--out", required=True, type=Path)
    draft = sub.add_parser("draft-analysis",
                           help="compose a fact-only provisional report from a verified app investigation")
    draft.add_argument("--analysis", required=True, type=Path)
    draft.add_argument("--investigation", required=True, type=Path)
    draft.add_argument("--rebuilt-bundle", default="")
    draft.add_argument("--out", required=True, type=Path)
    prepare = sub.add_parser("prepare-analysis",
                             help="resume selected flow investigations and prepare a verified coding-agent review task")
    prepare.add_argument("--udid", required=True)
    prepare.add_argument("--analysis", required=True, type=Path)
    prepare.add_argument("--script", required=True, action="append", type=Path)
    prepare.add_argument("--investigation", type=Path,
                         help="reuse an already completed, verified investigation")
    prepare.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    prepare.add_argument("--provider", choices=("none", "ghidra-direct", "hopper-direct"), default="none")
    prepare.add_argument("--function-limit", dest="rea_limit",
                         type=int, default=4, metavar="N",
                         help="maximum observed entry functions; direct Ghidra may also follow bounded native calls")
    prepare.add_argument("--ghidra-dir", type=Path)
    prepare.add_argument("--hopper-app", type=Path)
    prepare.add_argument("--java-home", type=Path)
    prepare.add_argument("--ghidra-disable-analyzer")
    prepare.add_argument("--network", action="store_true",
                         help="include URLSession metadata in each investigated UI flow")
    prepare.add_argument("--timeout", type=int, default=240)
    prepare.add_argument("--rebuilt-bundle", default="")
    prepare.add_argument("--resume", action="store_true")
    prepare.add_argument("--out", required=True, type=Path)
    prepare_app_parser = sub.add_parser(
        "prepare-app", help="collect an installed App and prepare a verified analysis review task")
    prepare_app_parser.add_argument("--udid", required=True)
    prepare_app_parser.add_argument("--bundle", required=True)
    prepare_app_parser.add_argument("--mode", choices=("auto", "standard", "enhanced"),
                                    help="UI-first collection without mandatory package or jailbreak evidence")
    prepare_app_parser.add_argument("--package-case", type=Path, action="append", default=[],
                                    help="optional verified external package/offline case, separately attributed from UI")
    prepare_app_parser.add_argument("--retry-failed", action="store_true",
                                    help="with --resume, retry retained failed flows after reviewing device state")
    prepare_app_parser.add_argument("--script", required=True, action="append", type=Path)
    prepare_app_parser.add_argument("--out", required=True, type=Path)
    prepare_app_parser.add_argument("--no-launch", action="store_true")
    prepare_app_parser.add_argument("--ui-backend", choices=("usb", "ios-mcp"), default="ios-mcp")
    prepare_app_parser.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    prepare_app_parser.add_argument("--decrypt", action="store_true")
    prepare_app_parser.add_argument("--decrypt-helper", type=Path,
                                    default=Path("../toolchains/ipadecrypt-helper-arm64"))
    prepare_app_parser.add_argument("--ssh-port", type=int, default=22222)
    prepare_app_parser.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    prepare_app_parser.add_argument("--ssh-identity", type=Path,
                                    default=Path("cases/ssh/id_ed25519"))
    prepare_app_parser.add_argument("--ssh-known-hosts", type=Path,
                                    default=Path("cases/ssh-known-hosts"))
    prepare_app_parser.add_argument("--provider", choices=("none", "ghidra-direct", "hopper-direct"), default="none")
    prepare_app_parser.add_argument("--function-limit", dest="rea_limit",
                                    type=int, default=4, metavar="N",
                                    help="maximum observed entry functions; direct Ghidra may also follow bounded native calls")
    prepare_app_parser.add_argument("--ghidra-dir", type=Path)
    prepare_app_parser.add_argument("--hopper-app", type=Path)
    prepare_app_parser.add_argument("--java-home", type=Path)
    prepare_app_parser.add_argument("--ghidra-disable-analyzer")
    prepare_app_parser.add_argument("--network", action="store_true",
                                    help="include URLSession metadata in each investigated UI flow")
    prepare_app_parser.add_argument("--timeout", type=int, default=240)
    prepare_app_parser.add_argument("--rebuilt-bundle", default="")
    prepare_app_parser.add_argument("--resume", action="store_true")
    copy_parser = sub.add_parser("copy",
                                 help="run the source-verified Analyze → Rebuild workflow with an external CLI or the current coding agent")
    copy_parser.add_argument("--udid", required=True)
    copy_parser.add_argument("--bundle", required=True)
    copy_parser.add_argument("--mode", choices=("auto", "standard", "enhanced"),
                             help="UI-first workflow for --agent-provider current; omit for the historical strict workflow")
    copy_parser.add_argument("--package-case", type=Path, action="append", default=[])
    copy_parser.add_argument("--retry-failed", action="store_true",
                             help="with --resume, retry failed collection only after reviewing phone state")
    copy_scripts = copy_parser.add_mutually_exclusive_group(required=True)
    copy_scripts.add_argument("--script", action="append", type=Path)
    copy_scripts.add_argument("--discovery", type=Path,
                              help="verified discover-check case containing three or more replayed flows")
    copy_scripts.add_argument("--auto-discover", action="store_true",
                              help="discover and replay representative flows; current mode pauses for this session")
    copy_parser.add_argument("--project", type=Path,
                             help="independent source directory (default <output-dir>/project)")
    copy_parser.add_argument("--rebuilt-bundle", required=True)
    copy_outputs = copy_parser.add_mutually_exclusive_group()
    copy_outputs.add_argument("--output-dir", type=Path,
                             help="job directory containing project/ and evidence/ (default output/<bundle>-<UTC>-<unique-id>)")
    copy_outputs.add_argument("--out", type=Path,
                             help="legacy evidence case directory; requires --project")
    copy_parser.add_argument("--workspace", type=Path)
    copy_parser.add_argument("--backend", choices=("ios-mcp", "ictrl"),
                             help="historical default ios-mcp; UI-first mode derives a route unless explicitly constrained")
    copy_parser.add_argument("--ui-backend", choices=("usb", "ios-mcp"), default="ios-mcp")
    copy_parser.add_argument("--analysis-provider",
                             choices=("none", "ghidra-direct", "hopper-direct"),
                             default="none")
    copy_parser.add_argument("--agent-provider", choices=("codex", "claude", "current"),
                             default="codex",
                             help="current pauses for this coding-agent session to complete each task")
    copy_parser.add_argument("--no-decrypt", action="store_true")
    copy_parser.add_argument("--no-network", action="store_true")
    copy_parser.add_argument("--flow", action="append", dest="flow_ids")
    copy_parser.add_argument("--decrypt-helper", type=Path,
                             default=Path("../toolchains/ipadecrypt-helper-arm64"))
    copy_parser.add_argument("--ssh-port", type=int, default=22222)
    copy_parser.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    copy_parser.add_argument("--ssh-identity", type=Path,
                             default=Path("cases/ssh/id_ed25519"))
    copy_parser.add_argument("--ssh-known-hosts", type=Path,
                             default=Path("cases/ssh-known-hosts"))
    copy_parser.add_argument("--ghidra-dir", type=Path)
    copy_parser.add_argument("--hopper-app", type=Path)
    copy_parser.add_argument("--java-home", type=Path)
    copy_parser.add_argument("--ghidra-disable-analyzer")
    copy_parser.add_argument("--analysis-timeout", type=int, default=240)
    copy_parser.add_argument("--agent-timeout-seconds", type=int, default=7200)
    copy_parser.add_argument("--resume", action="store_true")
    rebuild_plan = sub.add_parser("rebuild-plan",
                                  help="derive paired rebuild playbooks from a verified deep report")
    rebuild_plan.add_argument("--report", required=True, type=Path)
    rebuild_plan.add_argument("--flow", action="append", dest="flow_ids",
                              help="spec flow ID to include; omit to consider every flow")
    rebuild_plan.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    rebuild_plan.add_argument("--out", required=True, type=Path)
    agent_task = sub.add_parser("agent-task",
                                help="prepare a source-linked coding-agent task from a verified report and rebuild plan")
    agent_task.add_argument("--report", required=True, type=Path)
    agent_task.add_argument("--plan", required=True, type=Path)
    agent_task.add_argument("--udid")
    agent_task.add_argument("--project", type=Path)
    agent_task.add_argument("--out", required=True, type=Path)
    prepare_rebuild_parser = sub.add_parser("prepare-rebuild",
                                            help="resume a verified report-to-plan-to-agent-task handoff")
    prepare_rebuild_parser.add_argument("--report", required=True, type=Path)
    prepare_rebuild_parser.add_argument("--flow", action="append", dest="flow_ids")
    prepare_rebuild_parser.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    prepare_rebuild_parser.add_argument("--udid")
    prepare_rebuild_parser.add_argument("--project", type=Path)
    prepare_rebuild_parser.add_argument("--resume", action="store_true")
    prepare_rebuild_parser.add_argument("--out", required=True, type=Path)
    task_check = sub.add_parser("rebuild-task-check",
                                help="run every selected paired flow from a verified implementation task")
    task_check.add_argument("--task", required=True, type=Path)
    task_check.add_argument("--udid", help="required only when the task did not pin a device")
    task_check.add_argument("--resume", action="store_true")
    task_check.add_argument("--out", required=True, type=Path)
    agent_run = sub.add_parser("agent-run",
                               help="launch a verified semantic-review or full-scope implementation task through Codex or Claude Code")
    agent_run.add_argument("--task", required=True, type=Path)
    agent_run.add_argument("--provider", choices=("codex", "claude"), default="codex")
    agent_run.add_argument("--workspace", type=Path)
    agent_run.add_argument("--timeout-seconds", type=int, default=7200)
    agent_run.add_argument("--dry-run", action="store_true")
    verified_mode = agent_run.add_mutually_exclusive_group()
    verified_mode.add_argument("--verify-analysis", action="store_true",
                               help="for a semantic review task, require a report at <out>/reviewed-report and validate its flow coverage")
    verified_mode.add_argument("--verify-rebuild", action="store_true",
                               help="for an implementation task, require install, device comparison and visual review evidence under <out>")
    agent_run.add_argument("--out", required=True, type=Path)
    agent_delivery = sub.add_parser("agent-delivery",
                                    help="bind rebuilt source, installed IPA and complete device comparisons")
    agent_delivery.add_argument("--task", required=True, type=Path)
    agent_delivery.add_argument("--install", required=True, type=Path)
    agent_delivery.add_argument("--check", required=True, type=Path)
    agent_delivery.add_argument("--run", type=Path)
    agent_delivery.add_argument("--visual-review", type=Path)
    agent_delivery.add_argument("--out", required=True, type=Path)
    fidelity_plan = sub.add_parser("fidelity-plan", help="freeze a bounded reconstruction grade target for an iOS task or Mac plan")
    fidelity_plan.add_argument("--task", required=True, type=Path)
    fidelity_plan.add_argument("--fidelity", type=int, default=80, help="reviewed selected-scope grade, 0–100 (default 80); not image similarity percent")
    fidelity_plan.add_argument("--max-iterations", type=int, default=3, help="implementation/check cycles including the first (default 3)")
    fidelity_plan.add_argument("--out", required=True, type=Path)
    fidelity_template = sub.add_parser("fidelity-template", help="write a grade review template bound to verified images")
    fidelity_template.add_argument("--plan", required=True, type=Path)
    fidelity_template.add_argument("--evidence", required=True, type=Path, help="Mac visual-review or iOS agent-delivery with full visual review")
    fidelity_template.add_argument("--out", required=True, type=Path, help="new review JSON file")
    fidelity_check = sub.add_parser("fidelity-check", help="record target_met, continue or iteration_limit without relaxing strict delivery")
    fidelity_check.add_argument("--plan", required=True, type=Path)
    fidelity_check.add_argument("--evidence", required=True, type=Path)
    fidelity_check.add_argument("--review", required=True, type=Path)
    fidelity_check.add_argument("--previous", type=Path, help="previous cycle of this frozen plan; required after the first")
    fidelity_check.add_argument("--out", required=True, type=Path)
    coverage_plan = sub.add_parser("coverage-plan",
                                   help="freeze a weighted, revisable known-capability target")
    coverage_plan.add_argument("--report", required=True, type=Path)
    coverage_plan.add_argument("--plan", required=True, action="append", type=Path,
                               help="verified rebuild plan; repeat for larger milestones")
    coverage_plan.add_argument("--inventory", required=True, type=Path)
    coverage_plan.add_argument("--previous", type=Path,
                               help="previous verified target to revise without overwriting")
    coverage_plan.add_argument("--out", required=True, type=Path)
    coverage_delivery = sub.add_parser("coverage-delivery",
                                       help="measure reviewed capability coverage from device deliveries")
    coverage_delivery.add_argument("--plan", required=True, type=Path)
    coverage_delivery.add_argument("--delivery", required=True, action="append", type=Path)
    coverage_delivery.add_argument("--review", required=True, type=Path)
    coverage_delivery.add_argument("--out", required=True, type=Path)
    analysis_delivery = sub.add_parser("analysis-delivery",
                                       help="bind a verified deep report to every flow in a semantic-review task")
    analysis_delivery.add_argument("--task", required=True, type=Path)
    analysis_delivery.add_argument("--report", required=True, type=Path)
    analysis_delivery.add_argument("--run", type=Path)
    analysis_delivery.add_argument("--out", required=True, type=Path)
    portfolio = sub.add_parser("report-portfolio",
                               help="combine verified reports for one exact device and App build")
    portfolio.add_argument("--report", required=True, action="append", type=Path)
    portfolio.add_argument("--out", required=True, type=Path)
    discovery_check = sub.add_parser("discover-check",
                                     help="replay and verify 3–12 agent-authored original-App UI flows")
    discovery_check.add_argument("--udid", required=True)
    discovery_check.add_argument("--bundle", required=True)
    discovery_check.add_argument("--script", required=True, action="append", type=Path)
    discovery_check.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    discovery_check.add_argument("--resume", action="store_true")
    discovery_check.add_argument("--mode", choices=("standard", "enhanced"))
    discovery_check.add_argument("--out", required=True, type=Path)
    visual_audit = sub.add_parser("visual-audit",
                                  help="measure every saved rebuild screenshot pair in a declared region")
    visual_audit.add_argument("--check", required=True, type=Path)
    visual_audit.add_argument("--roi", required=True, nargs=4, type=int,
                              metavar=("X1", "Y1", "X2", "Y2"))
    visual_audit.add_argument("--max-mean", required=True, type=float)
    visual_audit.add_argument("--max-changed", required=True, type=float)
    visual_audit.add_argument("--difference-threshold", type=int, default=24)
    visual_audit.add_argument("--out", required=True, type=Path)
    visual_review = sub.add_parser("visual-review",
                                   help="bind explicit per-image judgments to verified rebuild screenshots")
    visual_review.add_argument("--check", required=True, type=Path)
    visual_review.add_argument("--judgments", required=True, type=Path)
    visual_review.add_argument("--reviewer", required=True)
    visual_review.add_argument("--out", required=True, type=Path)
    rebuild = sub.add_parser("rebuild-check",
                             help="run selected original and rebuilt playbooks as one device check")
    rebuild.add_argument("--udid", required=True)
    rebuild.add_argument("--feature-spec", required=True, type=Path)
    rebuild.add_argument("--pair", action="append", nargs=3, required=True,
                         metavar=("FLOW_ID", "ORIGINAL_SCRIPT", "REBUILT_SCRIPT"))
    rebuild.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    rebuild.add_argument("--resume", action="store_true")
    rebuild.add_argument("--out", required=True, type=Path)
    ipa = sub.add_parser("ipa", help="index an existing local IPA and its Mach-O load commands")
    ipa.add_argument("file", type=Path)
    ipa.add_argument("--out", required=True, type=Path)
    check_ipa = sub.add_parser("check-ipa", help="check encryption headers in a candidate decrypted IPA")
    check_ipa.add_argument("file", type=Path)
    check_ipa.add_argument("--bundle")
    check_ipa.add_argument("--out", required=True, type=Path)
    decrypt = sub.add_parser("decrypt-main", help="recover an encrypted main executable from its running app")
    decrypt.add_argument("--udid", required=True)
    decrypt.add_argument("--bundle", required=True)
    decrypt.add_argument("--out", required=True, type=Path)
    decrypt.add_argument("--ssh-port", type=int, default=22222)
    decrypt.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    decrypt.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    decrypt.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    extension = sub.add_parser("decrypt-extension", help="recover one active system-hosted app extension executable")
    extension.add_argument("--udid", required=True)
    extension.add_argument("--bundle", required=True)
    extension.add_argument("--appex", required=True, help="extension folder name without .appex")
    extension.add_argument("--out", required=True, type=Path)
    extension.add_argument("--ssh-port", type=int, default=22222)
    extension.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    extension.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    extension.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    package = sub.add_parser("decrypt-package", help="recover and independently verify all encrypted Mach-O in an installed app")
    package.add_argument("--udid", required=True)
    package.add_argument("--bundle", required=True)
    package.add_argument("--snapshot", required=True, type=Path)
    package.add_argument("--helper", type=Path, default=Path("../toolchains/ipadecrypt-helper-arm64"))
    package.add_argument("--out", required=True, type=Path)
    package.add_argument("--ssh-port", type=int, default=22222)
    package.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    package.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    ghidra_direct = sub.add_parser("ghidra-function",
                                   help="decompile one pinned function with Ghidra directly; no REA")
    ghidra_direct.add_argument("--file", required=True, type=Path)
    ghidra_direct.add_argument("--sha256", required=True)
    ghidra_direct.add_argument("--address", required=True)
    ghidra_direct.add_argument("--ghidra-dir", required=True, type=Path)
    ghidra_direct.add_argument("--java-home", type=Path)
    ghidra_direct.add_argument("--timeout", type=int, default=600)
    ghidra_direct.add_argument("--disable-analyzer",
                               help="disable one named Ghidra analyzer before auto-analysis")
    ghidra_direct.add_argument("--out", required=True, type=Path)
    hopper_direct = sub.add_parser("hopper-function",
                                   help="decompile one pinned function with Hopper directly")
    hopper_direct.add_argument("--file", required=True, type=Path)
    hopper_direct.add_argument("--sha256", required=True)
    hopper_direct.add_argument("--address", required=True)
    hopper_direct.add_argument("--hopper-app", type=Path)
    hopper_direct.add_argument("--timeout", type=int, default=600)
    hopper_direct.add_argument("--out", required=True, type=Path)
    hopper_queue = sub.add_parser("hopper-queue",
                                  help="decompile a verified candidate queue with Hopper directly")
    hopper_queue.add_argument("--candidates", required=True, type=Path)
    hopper_queue.add_argument("--hopper-app", type=Path)
    hopper_queue.add_argument("--limit", type=int, default=4)
    hopper_queue.add_argument("--timeout", type=int, default=600)
    hopper_queue.add_argument("--out", required=True, type=Path)
    ghidra_queue = sub.add_parser("ghidra-queue",
                                  help="decompile a verified candidate queue with Ghidra directly; no REA")
    ghidra_queue.add_argument("--candidates", required=True, type=Path)
    ghidra_queue.add_argument("--native", type=Path,
                              help="verified native queue whose unique direct followers should also be decompiled")
    ghidra_queue.add_argument("--branch-flow", type=Path,
                              help="verified Frida flow with a BLR register target; requires --native")
    ghidra_queue.add_argument("--ghidra-dir", required=True, type=Path)
    ghidra_queue.add_argument("--java-home", type=Path)
    ghidra_queue.add_argument("--limit", type=int, default=4)
    ghidra_queue.add_argument("--timeout", type=int, default=600)
    ghidra_queue.add_argument("--disable-analyzer",
                              help="disable one named Ghidra analyzer before auto-analysis")
    ghidra_queue.add_argument("--out", required=True, type=Path)
    indirect_follow = sub.add_parser("ghidra-indirect",
                                     help="replay BLR sites from one verified investigation and decompile observed callbacks without REA")
    indirect_follow.add_argument("--udid", required=True)
    indirect_follow.add_argument("--investigation", required=True, type=Path)
    indirect_follow.add_argument("--objc-index", required=True, type=Path)
    indirect_follow.add_argument("--ghidra-dir", required=True, type=Path)
    indirect_follow.add_argument("--java-home", required=True, type=Path)
    indirect_follow.add_argument("--function-limit", type=int, default=4)
    indirect_follow.add_argument("--branch-limit", type=int, default=8)
    indirect_follow.add_argument("--timeout", type=int, default=900)
    indirect_follow.add_argument("--disable-analyzer")
    indirect_follow.add_argument("--resume", action="store_true",
                                 help="reuse the verified branch replay after a Ghidra failure")
    indirect_follow.add_argument("--out", required=True, type=Path)
    native = sub.add_parser("native-disasm", help="save bounded ARM64 assembly without REA")
    native.add_argument("--file", required=True, type=Path)
    native.add_argument("--sha256", required=True)
    native.add_argument("--address", required=True)
    native.add_argument("--max-bytes", type=int, default=1024)
    native.add_argument("--timeout", type=int, default=30)
    native.add_argument("--out", required=True, type=Path)
    native_queue = sub.add_parser("native-queue",
                                  help="disassemble bounded candidate windows without REA")
    native_queue.add_argument("--candidates", required=True, type=Path)
    native_queue.add_argument("--limit", type=int, default=4)
    native_queue.add_argument("--max-bytes", type=int, default=1024)
    native_queue.add_argument("--timeout", type=int, default=30)
    native_queue.add_argument("--follow-limit", type=int, default=4)
    native_queue.add_argument("--follow-depth", type=int, default=2)
    native_queue.add_argument("--out", required=True, type=Path)
    candidates = sub.add_parser("candidates", help="link Frida counts to exact Objective-C binary addresses")
    candidates.add_argument("--udid", required=True)
    candidates.add_argument("--bundle", required=True)
    candidates.add_argument("--binary", required=True, type=Path)
    candidates.add_argument("--objc-index", required=True, type=Path)
    candidates.add_argument("--experiment", "--flow", required=True, action="append",
                            type=Path, help="completed tap experiment or traced flow; repeat as needed")
    candidates.add_argument("--out", required=True, type=Path)
    root = sub.add_parser("root-run", help="run one command on a named USB device via its existing root Frida server")
    root.add_argument("--udid", required=True)
    root.add_argument("--out", required=True, type=Path)
    root.add_argument("--timeout", type=int, default=60)
    root.add_argument("--ssh-port", type=int, default=22222)
    root.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    root.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    root.add_argument("argv", nargs=argparse.REMAINDER, help="-- /absolute/executable [arguments...] ")
    install = sub.add_parser("install", help="install a local IPA through USB signing or TrollStore")
    install.add_argument("--udid", required=True)
    install.add_argument("--ipa", required=True, type=Path)
    install.add_argument("--out", required=True, type=Path)
    install.add_argument("--transport", choices=("trollstore", "usb"), default="trollstore",
                         help="use USB InstallationProxy for a development-signed IPA")
    install.add_argument("--ssh-port", type=int, default=22222)
    install.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    install.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    assemble = sub.add_parser("assemble-ipa", help="insert a recovered main binary into an analysis IPA and audit every Mach-O")
    assemble.add_argument("--snapshot", required=True, type=Path)
    assemble.add_argument("--recovered", required=True, type=Path, action="append",
                          help="recovered main or extension case; repeat for each binary")
    assemble.add_argument("--out", required=True, type=Path)
    objc = sub.add_parser("objc", help="index locally defined Objective-C classes and method addresses in a Mach-O")
    objc.add_argument("file", type=Path)
    objc.add_argument("--out", required=True, type=Path)
    trace = sub.add_parser("trace", help="count calls to named Objective-C methods in a running app")
    trace.add_argument("--udid", required=True)
    trace.add_argument("--bundle", required=True)
    trace.add_argument("--method", action="append", required=True,
                       help="ClassName::selector: (repeat for multiple methods)")
    trace.add_argument("--seconds", type=int, default=10)
    trace.add_argument("--out", required=True, type=Path)
    experiment = sub.add_parser("experiment", help="launch, trace one method set, tap, and capture before/after screens")
    experiment.add_argument("--udid", required=True)
    experiment.add_argument("--bundle", required=True)
    experiment.add_argument("--method", action="append", required=True,
                            help="ClassName::selector: (repeat for multiple methods)")
    experiment.add_argument("--x", type=float, required=True)
    experiment.add_argument("--y", type=float, required=True)
    experiment.add_argument("--seconds", type=float, default=2.0)
    experiment.add_argument("--backend", choices=("ios-mcp", "ictrl"), default="ios-mcp")
    experiment.add_argument("--port", type=int,
                            help="optional existing backend tunnel; default opens a private tunnel to --udid")
    experiment.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    experiment.add_argument("--binary", type=Path,
                            help="exact acquired .app executable for simultaneous static-entry trace")
    experiment.add_argument("--objc-index", type=Path,
                            help="Objective-C index of the exact executable")
    experiment.add_argument("--out", required=True, type=Path)
    playbook = sub.add_parser("playbook", help="replay a bounded UI script with either paired backend")
    playbook.add_argument("--udid", required=True)
    playbook.add_argument("--backend", choices=("ios-mcp", "ictrl"), required=True)
    playbook.add_argument("--script", required=True, type=Path)
    playbook.add_argument("--out", required=True, type=Path)
    playbook.add_argument("--port", type=int)
    playbook.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    playbook.add_argument("--mode", choices=("standard", "enhanced"),
                          help="standard owns XCTest and skips jailbreak identity helpers")
    network_flow = sub.add_parser("network-flow", help="observe URLSession starts during a bounded UI playbook")
    network_flow.add_argument("--udid", required=True)
    network_flow.add_argument("--backend", choices=("ios-mcp", "ictrl"), required=True)
    network_flow.add_argument("--script", required=True, type=Path)
    network_flow.add_argument("--out", required=True, type=Path)
    network_flow.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    auto_playbook = sub.add_parser("playbook-auto", help="retry a UI playbook with another backend only before any touch")
    auto_playbook.add_argument("--udid", required=True)
    auto_playbook.add_argument("--primary", choices=("ios-mcp", "ictrl"), required=True)
    auto_playbook.add_argument("--fallback", choices=("ios-mcp", "ictrl"), required=True)
    auto_playbook.add_argument("--script", required=True, type=Path)
    auto_playbook.add_argument("--out", required=True, type=Path)
    auto_playbook.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    comparison = sub.add_parser("compare-playbooks", help="compare two verified same-device UI playbooks")
    comparison.add_argument("--original", required=True, type=Path)
    comparison.add_argument("--rebuilt", required=True, type=Path)
    comparison.add_argument("--out", required=True, type=Path)
    acquire = sub.add_parser("acquire", help="copy an installed app bundle via USB-forwarded SSH or AFC2")
    acquire.add_argument("--udid", required=True)
    acquire.add_argument("--bundle", required=True)
    acquire.add_argument("--out", required=True, type=Path)
    acquire.add_argument("--transport", choices=("ssh", "afc2"), default="ssh")
    acquire.add_argument("--ssh-port", type=int, default=22222)
    acquire.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    acquire.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    acquire.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    sandbox = sub.add_parser("sandbox", help="inventory an installed app data container over USB SSH")
    sandbox.add_argument("--udid", required=True)
    sandbox.add_argument("--bundle", required=True)
    sandbox.add_argument("--out", required=True, type=Path)
    sandbox.add_argument("--depth", type=int, default=8)
    sandbox.add_argument("--ssh-port", type=int, default=22222)
    sandbox.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    sandbox.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    sandbox.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    sandbox_file = sub.add_parser("sandbox-file", help="read bounded files named in a verified app sandbox index")
    sandbox_file.add_argument("--udid", required=True)
    sandbox_file.add_argument("--analysis", required=True, type=Path)
    sandbox_file.add_argument("--path", action="append", required=True,
                              help="indexed app-container relative file path; repeat up to four times")
    sandbox_file.add_argument("--out", required=True, type=Path)
    sandbox_file.add_argument("--ssh-port", type=int, default=22222)
    sandbox_file.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    sandbox_file.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    sandbox_file.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    sandbox_diff = sub.add_parser("sandbox-diff", help="compare two same-app sandbox metadata snapshots")
    sandbox_diff.add_argument("--before", required=True, type=Path)
    sandbox_diff.add_argument("--after", required=True, type=Path)
    sandbox_diff.add_argument("--action", type=Path,
                              help="optional verified same-app playbook between the snapshots")
    sandbox_diff.add_argument("--out", required=True, type=Path)
    sqlite_schema = sub.add_parser("sqlite-schema", help="inspect one verified captured SQLite file without rows")
    sqlite_schema.add_argument("--case", required=True, type=Path,
                               help="source case whose evidence list contains the SQLite file")
    sqlite_schema.add_argument("--path", required=True,
                               help="relative path to the recorded SQLite file inside the source case")
    sqlite_schema.add_argument("--out", required=True, type=Path)
    plist_schema = sub.add_parser("plist-schema", help="inspect one verified captured property list without values")
    plist_schema.add_argument("--case", required=True, type=Path)
    plist_schema.add_argument("--path", required=True,
                              help="relative path to the recorded plist file inside the source case")
    plist_schema.add_argument("--out", required=True, type=Path)
    apps = sub.add_parser("apps", help="list installed user apps; add --all for system apps")
    apps.add_argument("--udid", required=True)
    apps.add_argument("--all", action="store_true", help="include system apps")
    survey = sub.add_parser("survey", help="capture one app's installation, sandbox and current UI evidence")
    survey.add_argument("--udid", required=True)
    survey.add_argument("--bundle", required=True)
    survey.add_argument("--out", required=True, type=Path)
    survey.add_argument("--launch", action="store_true", help="open the target app before UI capture")
    survey.add_argument("--ui-backend", choices=("usb", "ios-mcp"), default="usb")
    analyze = sub.add_parser("analyze", help="run USB survey, app bundle acquisition and sandbox index as one case")
    analyze.add_argument("--udid", required=True)
    analyze.add_argument("--bundle", required=True)
    analyze.add_argument("--mode", choices=("auto", "standard", "enhanced"),
                         help="UI-first analysis; omit for the historical SSH collection contract")
    analyze.add_argument("--package-case", type=Path, action="append", default=[],
                         help="optional verified external package/offline case; requires --mode")
    analyze.add_argument("--script", type=Path, action="append", default=[],
                         help="representative playbook for UI-first analysis; repeat up to 12 times")
    analyze.add_argument("--retry-failed", action="store_true",
                         help="with --resume, retry retained failed flows after reviewing device state")
    analyze.add_argument("--out", required=True, type=Path)
    analyze.add_argument("--launch", action="store_true")
    analyze.add_argument("--resume", action="store_true", help="continue this case; preserve prior partial stage files under attempts/")
    analyze.add_argument("--decrypt", action="store_true", help="recover and verify all encrypted Mach-O after acquisition")
    analyze.add_argument("--decrypt-helper", type=Path, default=Path("../toolchains/ipadecrypt-helper-arm64"))
    analyze.add_argument("--ui-backend", choices=("usb", "ios-mcp"), default="usb")
    analyze.add_argument("--ssh-port", type=int, default=22222)
    analyze.add_argument("--ssh-user", choices=("root", "mobile"), default="mobile")
    analyze.add_argument("--ssh-identity", type=Path, default=Path("cases/ssh/id_ed25519"))
    analyze.add_argument("--ssh-known-hosts", type=Path, default=Path("cases/ssh-known-hosts"))
    report = sub.add_parser("report", help="compose a cited deep report from a verified case and selected evidence")
    report.add_argument("--case", required=True, type=Path)
    report.add_argument("--findings", required=True, type=Path)
    report.add_argument("--evidence", action="append", default=[], metavar="ID=PATH",
                        help="verified analysis dossier, completed experiment, or file; repeat as needed")
    report.add_argument("--feature-spec", type=Path)
    report.add_argument("--out", required=True, type=Path)
    ui = sub.add_parser("ui", help="control one UI backend through a localhost USB tunnel")
    ui.add_argument("action", choices=("health", "observe", "ocr", "screenshot", "tap", "launch", "wake"))
    ui.add_argument("--backend", choices=("ios-mcp", "ictrl", "usb"), default="ios-mcp")
    ui.add_argument("--udid", help="exact device ID for the USB screenshot backend")
    ui.add_argument("--port", type=int)
    ui.add_argument("--ictrl-client", type=Path, default=DEFAULT_CLIENT)
    ui.add_argument("--out", type=Path, help="screenshot destination")
    ui.add_argument("--x", type=float)
    ui.add_argument("--y", type=float)
    ui.add_argument("--ref", help="iCTRL element reference for a targeted tap")
    ui.add_argument("--bundle")
    ax = sub.add_parser("ax", help="observe or activate an exact accessibility element over USB")
    ax.add_argument("action", choices=("observe", "press"))
    ax.add_argument("--udid", required=True)
    ax.add_argument("--caption", default="", help="exact current accessibility caption for press")
    args = parser.parse_args()
    try:
        apply_ssh_profile(args, sys.argv[1:])
        if args.command == "mac":
            from copyapp.macos.cli import run as run_mac
            code = run_mac(args)
        elif args.command == "devices":
            code = asyncio.run(command_devices())
        elif args.command == "package-import":
            from copyapp.ios_packages import import_package
            print(import_package(args.ipa, args.out, args.bundle))
            code = 0
        elif args.command == "store-download":
            from copyapp.ios_packages import download_package
            path, complete = download_package(args.bundle, args.out, args.ipatool,
                                               args.external_version_id, args.acquire_license, args.timeout)
            print(path)
            code = 0 if complete else 1
        elif args.command == "decrypt-offline":
            from copyapp.ios_offline import decrypt_offline
            path, complete = decrypt_offline(args.package, args.out, args.tool_dir,
                                              args.credential_ref, args.credential_store, args.timeout)
            print(path)
            code = 0 if complete else 1
        elif args.command == "offline-cross-check":
            from copyapp.ios_cross_check import cross_check_offline
            print(cross_check_offline(args.offline, args.device, args.out))
            code = 0
        elif args.command == "onboard":
            report, ready = run_onboarding(args.udid, args.out, args.ssh_identity,
                                           args.ssh_known_hosts, args.ssh_port,
                                           not args.no_keygen, args.stage, args.mode)
            if args.mode is None:
                remember_verified_doctor_case(report.parent, args.ssh_port,
                                              args.ssh_identity, args.ssh_known_hosts)
            code = 0 if ready else 1
        elif args.command == "tunnel":
            code = run_tunnels(args.udid, args.ssh_port, args.mcp_port,
                               args.ssh_only, args.mcp_only)
        elif args.command == "setup":
            if args.component == "frida-roothide":
                print(setup_roothide_sidecar(args.udid, args.out,
                                             args.ssh_identity, args.ssh_known_hosts,
                                             args.frida_deb))
                code = 0
            else:
                path, ready = setup_ictrl(args.udid, args.out, args.ssh_port,
                                          args.ssh_identity, args.ssh_known_hosts,
                                          args.runner_ipa, args.reinstall,
                                          args.auto_approve_first_pair, args.transport)
                print(path)
                code = 0 if ready else 1
        elif args.command == "doctor":
            if args.mode is not None:
                from copyapp.ios_capabilities import collect_capabilities
                path = collect_capabilities(args.udid, args.out, args.mode, args.ssh_port,
                                             args.ssh_identity, args.ssh_known_hosts, args.ictrl_client)
                connected = json.loads((args.out / "capabilities.json").read_text())["probes"].get(
                    "usb_lockdown", {}).get("status") == "available"
            else:
                path, connected = run_doctor(args.udid, args.out, args.ssh_port,
                                             args.ssh_identity, args.ssh_known_hosts,
                                             args.ictrl_client)
                remember_verified_doctor_case(path.parent, args.ssh_port,
                                              args.ssh_identity, args.ssh_known_hosts)
            print(path)
            code = 0 if connected else 1
        elif args.command == "verify":
            code = 0 if verify_case(args.case) else 1
        elif args.command == "ocr-file":
            print(ocr_file(args.file, args.out, args.roi))
            code = 0
        elif args.command == "view-tree":
            path, complete = capture_view_tree(args.udid, args.bundle, args.out,
                                               args.backend, args.port, args.ictrl_client,
                                               not args.no_launch)
            print(path)
            code = 0 if complete else 1
        elif args.command == "flow-capture":
            path, complete = capture_flow(args.udid, args.backend, args.script,
                                          args.out, args.ictrl_client, args.methods,
                                          args.binary, args.objc_index,
                                          args.arg2_u32_methods, args.branch_offsets,
                                          args.branch_return_u32_offsets,
                                          args.branch_registers, args.network)
            print(path)
            code = 0 if complete else 1
        elif args.command == "branch-map":
            print(build_branch_map(args.flow, args.method, args.binary, args.out))
            code = 0
        elif args.command == "investigate-flow":
            path, complete = investigate_flow(args.udid, args.analysis, args.script,
                                              args.out, args.backend, args.methods,
                                              args.provider, args.rea_limit,
                                              None, args.ghidra_dir,
                                              args.java_home, args.timeout, args.resume,
                                              disabled_analyzer=args.ghidra_disable_analyzer,
                                              network=args.network, hopper_app=args.hopper_app)
            print(path)
            code = 0 if complete else 1
        elif args.command == "investigate-app":
            path, complete = investigate_app(args.udid, args.analysis, args.script,
                                             args.out, args.backend, args.provider,
                                             args.rea_limit, None,
                                             args.ghidra_dir, args.java_home,
                                             args.timeout, args.resume,
                                             disabled_analyzer=args.ghidra_disable_analyzer,
                                             network=args.network, hopper_app=args.hopper_app)
            print(path)
            code = 0 if complete else 1
        elif args.command == "draft-analysis":
            path, complete = draft_analysis(args.analysis, args.investigation,
                                            args.out, args.rebuilt_bundle)
            print(path)
            code = 0 if complete else 1
        elif args.command == "prepare-analysis":
            path, complete = prepare_analysis(
                args.udid, args.analysis, args.script, args.out,
                args.backend, args.provider, args.rea_limit,
                None, args.ghidra_dir, args.java_home,
                args.timeout, args.rebuilt_bundle, args.resume,
                args.investigation, disabled_analyzer=args.ghidra_disable_analyzer,
                network=args.network, hopper_app=args.hopper_app)
            print(path)
            code = 0 if complete else 1
        elif args.command == "prepare-app":
            if args.mode is not None:
                path, complete = command_mode_analysis(args)
                print(path)
                raise SystemExit(0 if complete else 1)
            if args.package_case or args.retry_failed:
                raise ValueError("--package-case and --retry-failed require --mode")
            survey_collector = lambda udid, bundle, output, launch: command_survey(
                udid, bundle, output, launch, args.ui_backend)
            path, complete = asyncio.run(prepare_app(
                args.udid, args.bundle, args.script, args.out, survey_collector,
                launch=not args.no_launch, ui_backend=args.ui_backend,
                backend=args.backend, decrypt=args.decrypt,
                decrypt_helper=args.decrypt_helper, ssh_port=args.ssh_port,
                ssh_user=args.ssh_user, ssh_identity=args.ssh_identity,
                ssh_known_hosts=args.ssh_known_hosts, provider=args.provider,
                rea_limit=args.rea_limit,
                ghidra_dir=args.ghidra_dir, java_home=args.java_home,
                timeout=args.timeout, rebuilt_bundle_id=args.rebuilt_bundle,
                resume=args.resume,
                disabled_analyzer=args.ghidra_disable_analyzer,
                network=args.network, hopper_app=args.hopper_app))
            print(path)
            code = 0 if complete else 1
        elif args.command == "copy":
            if args.mode is not None:
                if args.agent_provider != "current" or args.analysis_provider != "none":
                    raise ValueError("UI-first copy requires --agent-provider current and --analysis-provider none; "
                                     "function investigations remain explicit enhanced workflows")
            elif args.package_case or args.retry_failed:
                raise ValueError("--package-case and --retry-failed require --mode")
            workspace, output, project = copy_paths(
                args.bundle, workspace=args.workspace, output_dir=args.output_dir,
                output=args.out, project=args.project, resume=args.resume)
            print(f"Project: {project}", flush=True)
            print(f"Evidence: {output}", flush=True)
            resume_paths = (["--out", str(output), "--project", str(project)]
                            if args.out is not None else
                            ["--output-dir", str(output.parent), "--project", str(project)])
            print("Resume: retain the other settings and use " +
                  shlex.join(resume_paths + ["--resume"]), flush=True)
            survey_collector = lambda udid, bundle, output, launch: command_survey(
                udid, bundle, output, launch, args.ui_backend)
            if args.mode is not None:
                from copyapp.ios_workflow import copy_ios
                from copyapp.ios_analysis import enhancement_settings

                def enhanced(output):
                    return asyncio.run(analyze_case(
                        args.udid, args.bundle, output, True, args.ssh_port, args.ssh_user,
                        args.ssh_identity, args.ssh_known_hosts, survey_collector, not args.no_decrypt,
                        args.decrypt_helper, output.exists()))

                path, complete = copy_ios(
                    args.udid, args.bundle, args.script or [], project, args.rebuilt_bundle, output,
                    args.mode, discovery=args.discovery, auto_discover=args.auto_discover,
                    packages=args.package_case, flow_ids=args.flow_ids, resume=args.resume,
                    backend=args.backend,
                    retry_failed=args.retry_failed, enhanced_collector=enhanced, ssh_port=args.ssh_port,
                    enhancement_request=enhancement_settings(
                        not args.no_decrypt, args.ui_backend, args.ssh_port, args.ssh_user,
                        args.ssh_identity, args.ssh_known_hosts, args.decrypt_helper) if args.mode != "standard" else None,
                    ssh_identity=args.ssh_identity, ssh_known_hosts=args.ssh_known_hosts)
                print(path)
                raise SystemExit(0 if complete else 1)
            args.backend = args.backend or "ios-mcp"
            scripts = (accepted_playbooks(args.discovery, args.udid, args.bundle,
                                          args.backend) if args.discovery else (args.script or []))
            path, complete = asyncio.run(copy_app(
                args.udid, args.bundle, scripts, project,
                args.rebuilt_bundle, output, survey_collector,
                workspace=workspace, backend=args.backend,
                ui_backend=args.ui_backend, analysis_provider=args.analysis_provider,
                agent_provider=args.agent_provider, decrypt=not args.no_decrypt,
                network=not args.no_network, flow_ids=args.flow_ids,
                decrypt_helper=args.decrypt_helper, ssh_port=args.ssh_port,
                ssh_user=args.ssh_user, ssh_identity=args.ssh_identity,
                ssh_known_hosts=args.ssh_known_hosts,
                ghidra_dir=args.ghidra_dir, java_home=args.java_home,
                disabled_analyzer=args.ghidra_disable_analyzer,
                analysis_timeout=args.analysis_timeout,
                agent_timeout=args.agent_timeout_seconds,
                discovery_case=args.discovery, auto_discover=args.auto_discover,
                resume=args.resume, hopper_app=args.hopper_app))
            print(path)
            code = 0 if complete else 1
        elif args.command == "rebuild-plan":
            print(create_rebuild_plan(args.report, args.out, args.backend, args.flow_ids))
            code = 0
        elif args.command == "agent-task":
            print(create_agent_task(args.report, args.plan, args.out,
                                    args.udid, args.project))
            code = 0
        elif args.command == "prepare-rebuild":
            path, ready = prepare_rebuild(args.report, args.out, args.backend,
                                          args.flow_ids, args.udid, args.project,
                                          args.resume)
            print(path)
            code = 0 if ready else 1
        elif args.command == "rebuild-task-check":
            path, complete = rebuild_task_check(args.task, args.out, args.udid,
                                                args.resume)
            print(path)
            code = 0 if complete else 1
        elif args.command == "agent-run":
            path, complete = run_agent_task(args.task, args.out, args.provider,
                                            args.workspace, args.timeout_seconds,
                                            dry_run=args.dry_run,
                                            verify_analysis=args.verify_analysis,
                                            verify_rebuild=args.verify_rebuild)
            print(path)
            delivery = args.out / "analysis-delivery" / "report.md"
            if args.verify_analysis and complete and delivery.is_file():
                print(delivery)
            rebuilt_delivery = args.out / "agent-delivery" / "report.md"
            if args.verify_rebuild and rebuilt_delivery.is_file():
                print(rebuilt_delivery)
            code = 0 if complete else 1
        elif args.command == "agent-delivery":
            print(create_agent_delivery(args.task, args.install, args.check,
                                        args.out, args.run, args.visual_review))
            code = 0
        elif args.command == "fidelity-plan":
            from copyapp.fidelity import create_plan
            print(create_plan(args.task, args.out, args.fidelity, args.max_iterations))
            code = 0
        elif args.command == "fidelity-template":
            from copyapp.fidelity import require, read, visual_context, review_template
            require(args.plan, {"fidelity_plan"})
            context = visual_context(args.evidence, read(args.plan, "fidelity-plan.json")["contract"], live_source=True)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8") as stream:
                json.dump(review_template(context), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            print(args.out)
            code = 0
        elif args.command == "fidelity-check":
            from copyapp.fidelity import create_check, read
            path = create_check(args.plan, args.evidence, args.review, args.out, args.previous)
            print(path)
            decision = read(path, "fidelity-check.json")["result"]["decision"]
            print(decision)
            code = {"target_met": 0, "continue": 2, "iteration_limit": 3}[decision]
        elif args.command == "coverage-plan":
            print(create_coverage_plan(args.report, args.plan, args.inventory,
                                       args.out, args.previous))
            code = 0
        elif args.command == "coverage-delivery":
            print(create_coverage_delivery(args.plan, args.delivery, args.review,
                                           args.out))
            code = 0
        elif args.command == "analysis-delivery":
            print(create_analysis_delivery(args.task, args.report, args.out,
                                           args.run))
            code = 0
        elif args.command == "report-portfolio":
            print(create_report_portfolio(args.report, args.out))
            code = 0
        elif args.command == "discover-check":
            path, complete = check_discovered_flows(
                args.udid, args.bundle, args.script, args.out,
                args.backend, args.resume, mode=args.mode)
            print(path)
            code = 0 if complete else 1
        elif args.command == "visual-audit":
            print(create_visual_audit(args.check, args.out, args.roi,
                                      args.max_mean, args.max_changed,
                                      args.difference_threshold))
            code = 0
        elif args.command == "visual-review":
            print(create_visual_review(args.check, args.judgments, args.out,
                                       args.reviewer))
            code = 0
        elif args.command == "rebuild-check":
            pairs = [(flow_id, Path(original), Path(rebuilt))
                     for flow_id, original, rebuilt in args.pair]
            path, complete = rebuild_check(args.udid, args.feature_spec, pairs,
                                           args.out, args.backend, args.resume)
            print(path)
            code = 0 if complete else 1
        elif args.command == "ipa":
            write_ipa_report(analyze_ipa(args.file), args.out)
            print(args.out / "ipa-report.md")
            code = 0
        elif args.command == "check-ipa":
            result = inspect_decrypted_ipa(args.file, args.bundle)
            print(write_decryption_check(result, args.out))
            code = 0 if result["header_check_passed"] else 1
        elif args.command == "decrypt-main":
            print(decrypt_main(args.udid, args.bundle, args.out, args.ssh_port,
                               args.ssh_identity, args.ssh_known_hosts, args.ssh_user))
            code = 0
        elif args.command == "decrypt-extension":
            print(decrypt_extension(args.udid, args.bundle, args.appex, args.out,
                                    args.ssh_port, args.ssh_identity,
                                    args.ssh_known_hosts, args.ssh_user))
            code = 0
        elif args.command == "decrypt-package":
            print(decrypt_package(args.udid, args.bundle, args.snapshot, args.helper,
                                  args.out, args.ssh_port, args.ssh_identity,
                                  args.ssh_known_hosts))
            code = 0
        elif args.command == "ghidra-function":
            print(decompile_ghidra_function(args.file, args.sha256, args.address,
                                            args.out, args.ghidra_dir,
                                            args.java_home, args.timeout,
                                            args.disable_analyzer))
            code = 0
        elif args.command == "hopper-function":
            print(decompile_hopper_function(args.file, args.sha256, args.address,
                                            args.out, args.hopper_app, args.timeout))
            code = 0
        elif args.command == "hopper-queue":
            path, complete = decompile_hopper_queue(
                args.candidates, args.out, args.hopper_app,
                args.limit, args.timeout)
            print(path)
            code = 0 if complete else 1
        elif args.command == "ghidra-queue":
            path, complete = decompile_candidate_queue(
                args.candidates, args.out, args.ghidra_dir,
                args.limit, args.java_home, args.timeout,
                args.disable_analyzer, args.native, args.branch_flow)
            print(path)
            code = 0 if complete else 1
        elif args.command == "ghidra-indirect":
            path, complete = follow_indirect(
                args.udid, args.investigation, args.objc_index, args.out,
                args.ghidra_dir, args.java_home, args.function_limit,
                args.branch_limit, args.timeout, args.disable_analyzer,
                args.resume)
            print(path)
            code = 0 if complete else 1
        elif args.command == "candidates":
            path, has_candidates = build_candidates(args.udid, args.bundle, args.binary,
                                                    args.objc_index, args.experiment, args.out)
            print(path)
            code = 0 if has_candidates else 1
        elif args.command == "native-disasm":
            print(disassemble_native_function(args.file, args.sha256,
                                              args.address, args.out,
                                              args.max_bytes, timeout=args.timeout))
            code = 0
        elif args.command == "native-queue":
            print(disassemble_native_candidates(args.candidates, args.out,
                                                args.limit, args.max_bytes,
                                                args.timeout, args.follow_limit,
                                                args.follow_depth))
            code = 0
        elif args.command == "root-run":
            command = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
            with exact_ssh_tunnel(args.udid, args.ssh_port, args.ssh_identity,
                                  args.ssh_known_hosts):
                result = run_root_command(args.udid, command, args.out, args.ssh_port,
                                          args.ssh_identity, args.ssh_known_hosts, args.timeout)
            print(args.out / "result.json")
            code = 0 if result["exit_code"] == 0 else 1
        elif args.command == "install":
            if args.transport == "usb":
                print(install_usb_ipa(args.udid, args.ipa, args.out))
            else:
                print(install_trollstore_ipa(args.udid, args.ipa, args.out, args.ssh_port,
                                             args.ssh_identity, args.ssh_known_hosts))
            code = 0
        elif args.command == "assemble-ipa":
            print(assemble_analysis_ipa(args.snapshot, args.recovered, args.out))
            code = 0
        elif args.command == "objc":
            print(write_objc_report(index_objc(args.file), args.out))
            code = 0
        elif args.command == "trace":
            path, complete = trace_methods(
                args.udid, args.bundle, args.method, args.seconds, args.out)
            print(path)
            code = 0 if complete else 1
        elif args.command == "experiment":
            path, complete = trace_tap(
                args.udid, args.bundle, args.method, args.x, args.y,
                args.seconds, args.out, args.port, args.backend, args.ictrl_client,
                args.binary, args.objc_index)
            print(path)
            code = 0 if complete else 1
        elif args.command == "playbook":
            path, complete = run_playbook(args.udid, args.backend, args.script,
                                          args.out, args.port, args.ictrl_client, mode=args.mode)
            print(path)
            code = 0 if complete else 1
        elif args.command == "network-flow":
            path, complete = run_network_flow(args.udid, args.backend, args.script,
                                              args.out, args.ictrl_client)
            print(path)
            code = 0 if complete else 1
        elif args.command == "playbook-auto":
            path, complete = run_playbook_auto(args.udid, args.primary, args.fallback,
                                               args.script, args.out, args.ictrl_client)
            print(path)
            code = 0 if complete else 1
        elif args.command == "compare-playbooks":
            print(compare_playbooks(args.original, args.rebuilt, args.out))
            code = 1 if json.loads((args.out / "report-index.json").read_text())[
                "checks_status"] == "failed" else 0
        elif args.command == "acquire":
            if args.transport == "ssh":
                with exact_ssh_tunnel(args.udid, args.ssh_port, args.ssh_identity,
                                      args.ssh_known_hosts, args.ssh_user):
                    print(asyncio.run(acquire_bundle_ssh(
                        args.udid, args.bundle, args.out, args.ssh_port,
                        args.ssh_identity, args.ssh_known_hosts, args.ssh_user,
                    )))
            else:
                print(asyncio.run(acquire_bundle(args.udid, args.bundle, args.out)))
            code = 0
        elif args.command == "apps":
            code = asyncio.run(command_apps(args.udid, args.all))
        elif args.command == "sandbox":
            with exact_ssh_tunnel(args.udid, args.ssh_port, args.ssh_identity,
                                  args.ssh_known_hosts, args.ssh_user):
                print(asyncio.run(index_sandbox_ssh(
                    args.udid, args.bundle, args.out, args.ssh_port,
                    args.ssh_identity, args.ssh_known_hosts, args.ssh_user,
                    depth=args.depth,
                )))
            code = 0
        elif args.command == "sandbox-file":
            with exact_ssh_tunnel(args.udid, args.ssh_port, args.ssh_identity,
                                  args.ssh_known_hosts, args.ssh_user):
                print(asyncio.run(capture_sandbox_files(
                    args.udid, args.analysis, args.path, args.out, args.ssh_port,
                    args.ssh_identity, args.ssh_known_hosts, args.ssh_user)))
            code = 0
        elif args.command == "sandbox-diff":
            print(compare_sandbox(args.before, args.after, args.out, args.action))
            code = 0
        elif args.command == "sqlite-schema":
            print(create_sqlite_schema(args.case, args.path, args.out))
            code = 0
        elif args.command == "plist-schema":
            print(create_plist_schema(args.case, args.path, args.out))
            code = 0
        elif args.command == "ui":
            if args.backend == "usb":
                if args.action not in ("ocr", "screenshot"):
                    raise ValueError("USB backend supports only ocr and screenshot")
                if not args.udid:
                    raise ValueError("USB backend requires --udid")
                image = asyncio.run(usb_screenshot(args.udid))
                if args.out is not None:
                    args.out.parent.mkdir(parents=True, exist_ok=True)
                    args.out.write_bytes(image)
                elif args.action == "screenshot":
                    raise ValueError("screenshot requires --out")
                if args.action == "ocr":
                    value = recognize_screenshot(image)
                    value["screenshot_source"] = "usb"
                    value["screenshot_sha256"] = hashlib.sha256(image).hexdigest()
                    if args.out is not None:
                        value["screenshot_path"] = str(args.out)
                else:
                    value = {"path": str(args.out), "sha256": hashlib.sha256(image).hexdigest()}
            elif args.backend == "ictrl":
                client = ICtrlClient(port=args.port if args.port is not None else 22224,
                                     client=args.ictrl_client)
                if args.action == "health":
                    client.call_ui("logs", {"max_elements": 1})
                    value = {"backend": "ictrl", "status": "ok"}
                elif args.action == "observe":
                    value = client.call_ui("page_source", {"visible_only": True, "max_children": 50})
                elif args.action == "ocr":
                    value = client.call_ui("screen_text")
                elif args.action == "screenshot":
                    if args.out is None:
                        raise ValueError("screenshot requires --out")
                    path = client.screenshot(args.out)
                    value = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                elif args.action == "tap":
                    if args.ref:
                        value = client.call_ui("tap", {"ref": args.ref})
                    elif args.x is not None and args.y is not None:
                        value = client.call_ui("tap", {"x": args.x, "y": args.y})
                    else:
                        raise ValueError("tap requires --ref or both --x and --y")
                elif args.action == "wake":
                    raise ValueError("wake is currently supported only by ios-mcp")
                else:
                    if not args.bundle or not re.fullmatch(r"[A-Za-z0-9_.-]+", args.bundle):
                        raise ValueError("launch requires a valid --bundle")
                    value = client.call_ui("launch_app", {"bundle_id": args.bundle})
            else:
                if args.ref:
                    raise ValueError("--ref requires --backend ictrl")
                client = IOSMCPClient(port=args.port if args.port is not None else 22223)
                if args.action == "health":
                    value = client.health()
                else:
                    client.initialize()
                    if args.action == "observe":
                        value = IOSMCPClient.text_json(client.call_ui(
                            "describe_screen", {"include_ocr": False, "include_screenshot": False}
                        ))
                    elif args.action == "ocr":
                        before_app = IOSMCPClient.text_json(client.call_ui("get_frontmost_app"))
                        image, stability = capture_stable(
                            lambda: IOSMCPClient.image_bytes(client.call_ui("screenshot")))
                        value = recognize_screenshot(image)
                        value["screenshot_sha256"] = hashlib.sha256(image).hexdigest()
                        value["screenshot_source"] = "ios-mcp"
                        value["capture_stability"] = stability
                        after_app = IOSMCPClient.text_json(client.call_ui("get_frontmost_app"))
                        value["frontmost_before"] = before_app.get("bundleId")
                        value["frontmost_after"] = after_app.get("bundleId")
                        value["frontmost_stable"] = (before_app.get("bundleId") == after_app.get("bundleId")
                                                     and bool(after_app.get("bundleId")))
                        if args.out is not None:
                            args.out.parent.mkdir(parents=True, exist_ok=True)
                            args.out.write_bytes(image)
                            value["screenshot_path"] = str(args.out)
                        try:
                            screen = IOSMCPClient.text_json(client.call_ui("get_screen_info"))
                            value["screen_ready"] = bool(screen.get("screen_on")) and not bool(screen.get("locked"))
                            width, height = value["image"]["width"], value["image"]["height"]
                            if screen.get("width") == width and screen.get("height") == height:
                                value["coordinate_space"] = "fixed_screen_points"
                                value["point_mapping_verified"] = True
                            else:
                                value["point_mapping_verified"] = False
                                value["screen_info"] = screen
                        except Exception as exc:
                            value["point_mapping_verified"] = False
                            value["screen_info_error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
                    elif args.action == "screenshot":
                        if args.out is None:
                            raise ValueError("screenshot requires --out")
                        image = IOSMCPClient.image_bytes(client.call_ui("screenshot"))
                        args.out.parent.mkdir(parents=True, exist_ok=True)
                        args.out.write_bytes(image)
                        value = {"path": str(args.out), "sha256": hashlib.sha256(image).hexdigest()}
                    elif args.action == "tap":
                        if args.x is None or args.y is None:
                            raise ValueError("tap requires --x and --y")
                        value = IOSMCPClient.text_json(client.call_ui(
                            "tap_screen", {"x": args.x, "y": args.y}
                        ))
                    elif args.action == "wake":
                        value = IOSMCPClient.text_json(client.call_ui("wake_and_home"))
                    else:
                        if not args.bundle or not re.fullmatch(r"[A-Za-z0-9_.-]+", args.bundle):
                            raise ValueError("launch requires a valid --bundle")
                        value = IOSMCPClient.text_json(client.call_ui(
                            "launch_app", {"bundle_id": args.bundle}
                        ))
            print(json.dumps({"backend": args.backend, "observed_at": utc_now(),
                              "result": value}, ensure_ascii=False, indent=2))
            code = 0
        elif args.command == "ax":
            value = asyncio.run(usb_ax(args.udid, args.action, args.caption))
            print(json.dumps(value, ensure_ascii=False, indent=2))
            code = 0
        elif args.command == "analyze":
            if args.mode is not None:
                path, complete = command_mode_analysis(args)
                print(path)
                raise SystemExit(0 if complete else 1)
            if args.package_case or args.retry_failed or args.script:
                raise ValueError("--script, --package-case and --retry-failed require --mode")
            survey_collector = lambda udid, bundle, output, launch: command_survey(
                udid, bundle, output, launch, args.ui_backend)
            completed = asyncio.run(analyze_case(
                args.udid, args.bundle, args.out, args.launch,
                args.ssh_port, args.ssh_user, args.ssh_identity,
                args.ssh_known_hosts, survey_collector, args.decrypt,
                args.decrypt_helper, args.resume,
            ))
            code = 0 if completed else 1
        elif args.command == "report":
            print(compose_report(args.case, args.findings, args.evidence,
                                 args.out, args.feature_spec))
            code = 0
        else:
            code = asyncio.run(command_survey(args.udid, args.bundle, args.out,
                                              args.launch, args.ui_backend))
    except Exception as exc:
        print(f"copyapp: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
