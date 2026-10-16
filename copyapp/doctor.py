"""Record a capability baseline for one exact USB-connected iPhone."""

import asyncio
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
from pymobiledevice3.services.screenshot import ScreenshotService

from copyapp.ictrl import ICtrlClient, DEFAULT_CLIENT
from copyapp.ios_mcp import IOSMCPClient
from copyapp.ssh_acquire import _ssh_argv
from copyapp.usb_tunnel import ictrl_tunnel, ios_mcp_tunnel


def _error(exc: Exception) -> Dict[str, str]:
    return {"status": "unavailable", "error_type": type(exc).__name__,
            "reason": str(exc)[:400]}


def _record(output: Path, name: str, data: bytes, kind: str) -> Dict[str, str]:
    (output / name).write_bytes(data)
    return {"id": name.replace(".", "-"), "path": name,
            "sha256": hashlib.sha256(data).hexdigest(), "kind": kind}


async def _usb_probes(udid: str, output: Path, probes: Dict[str, Any],
                      evidence: list) -> Dict[str, Any]:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        actual = values.get("UniqueDeviceID")
        if actual != udid:
            raise RuntimeError("lockdown device identity does not match requested UDID")
        info = {name: values.get(name) for name in (
            "UniqueDeviceID", "DeviceName", "ProductType", "ProductVersion",
            "BuildVersion", "CPUArchitecture", "HardwareModel", "DeveloperModeStatus",
        )}
        probes["usb_lockdown"] = {"status": "available", "identity_verified": True}
        try:
            async with ScreenshotService(device) as screen:
                picture = await screen.take_screenshot()
            if not picture:
                raise RuntimeError("empty screenshot")
            suffix = ".png" if picture.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"
            evidence.append(_record(output, "screenshot" + suffix, picture, "image"))
            probes["usb_screenshot"] = {"status": "available", "bytes": len(picture)}
        except Exception as exc:
            probes["usb_screenshot"] = _error(exc)
        try:
            async with DvtProvider(device) as dvt, DeviceInfo(dvt) as fs:
                await fs.ls("/")
                probes["dvt_filesystem"] = {"status": "available"}
                try:
                    names = {entry.rsplit("/", 1)[-1] for entry in await fs.ls("/var/jb")}
                    probes["rootless_marker"] = {
                        "status": "observed", "var_jb_readable": True,
                        "dopamine_marker": ".installed_dopamine" in names,
                        "procursus_marker": ".procursus_strapped" in names,
                        "note": "Filesystem markers alone do not prove active jailbreak privileges.",
                    }
                except Exception as exc:
                    probes["rootless_marker"] = _error(exc)
        except Exception as exc:
            probes["dvt_filesystem"] = _error(exc)
            probes["rootless_marker"] = {"status": "not_probed", "reason": "DVT unavailable"}
        return info
    finally:
        await device.close()


def _ssh_probe(udid: str, port: int, identity: Path, known_hosts: Path) -> Dict[str, Any]:
    if not identity.is_file() or not known_hosts.is_file():
        return {"status": "not_configured", "reason": "SSH identity or pinned host key is missing"}
    try:
        argv = _ssh_argv(port, identity, known_hosts, "mobile")
        result = subprocess.run(argv + ["deviceinfo uniqueid"], capture_output=True,
                                text=True, timeout=15, check=False)
        if result.returncode:
            return {"status": "unavailable", "exit_code": result.returncode,
                    "reason": result.stderr.strip()[:300]}
        actual = result.stdout.strip()
        if actual != udid:
            return {"status": "identity_mismatch", "reason": "SSH endpoint belongs to another device"}
        return {"status": "available", "identity_verified": True, "user": "mobile"}
    except Exception as exc:
        return _error(exc)


def _frida_probe(udid: str) -> Dict[str, Any]:
    try:
        import frida
        devices = frida.get_device_manager().enumerate_devices()
        device = next((item for item in devices if item.id == udid and item.type == "usb"), None)
        if device is None:
            return {"status": "unavailable", "reason": "exact USB UDID absent from Frida inventory"}
        processes = device.enumerate_processes(scope="minimal")
        return {"status": "available", "identity_verified": True,
                "host_frida_version": frida.__version__, "process_count": len(processes)}
    except Exception as exc:
        return _error(exc)


def _ios_mcp_probe(udid: str) -> Dict[str, Any]:
    try:
        with ios_mcp_tunnel(udid) as port:
            health = IOSMCPClient(port=port).health()
        return {"status": "available", "server": health.get("server"),
                "version": health.get("version"), "protocol_versions": health.get("supportedProtocolVersions")}
    except Exception as exc:
        return _error(exc)


def _ictrl_probe(udid: str, client: Path) -> Dict[str, Any]:
    if not client.is_file():
        return {"status": "not_configured", "reason": "paired iCTRL client is missing"}
    try:
        with ictrl_tunnel(udid, client) as port:
            result = ICtrlClient(port=port, client=client).call_ui("logs", {"max_elements": 1})
        return {"status": "available", "paired_runner_reachable": True,
                "response_keys": sorted(result.keys())}
    except Exception as exc:
        return _error(exc)


def run_doctor(udid: str, output: Path, ssh_port: int = 22222,
               ssh_identity: Path = Path("cases/ssh/id_ed25519"),
               ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
               ictrl_client: Path = DEFAULT_CLIENT) -> Tuple[Path, bool]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite device baseline: {output}")
    output.mkdir(parents=True)
    probes: Dict[str, Any] = {}
    evidence = []
    try:
        device_info = asyncio.run(_usb_probes(udid, output, probes, evidence))
    except Exception as exc:
        probes["usb_lockdown"] = _error(exc)
        device_info = {"UniqueDeviceID": udid}
    if probes["usb_lockdown"]["status"] == "available":
        probes["ssh_mobile"] = _ssh_probe(udid, ssh_port, ssh_identity, ssh_known_hosts)
        probes["frida_usb"] = _frida_probe(udid)
        probes["ios_mcp"] = _ios_mcp_probe(udid)
        probes["ictrl"] = _ictrl_probe(udid, ictrl_client)
    else:
        for key in ("ssh_mobile", "frida_usb", "ios_mcp", "ictrl"):
            probes[key] = {"status": "not_probed", "reason": "exact USB lockdown device unavailable"}
    device_data = (json.dumps({"device": device_info, "probes": probes},
                              ensure_ascii=False, indent=2, default=str) + "\n").encode()
    evidence.append(_record(output, "device.json", device_data, "json"))
    lines = ["# Copy APP 设备能力基线", "",
             f"- 设备：`{device_info.get('ProductType', 'unknown')}` / iOS {device_info.get('ProductVersion', 'unknown')}",
             f"- UDID：`{udid}`", "",
             "| 能力 | 状态 | 说明 |", "| --- | --- | --- |"]
    for name, item in probes.items():
        detail = item.get("reason") or item.get("error_type") or ""
        lines.append(f"| `{name}` | {item['status']} | {str(detail).replace('|', '/')} |")
    lines += ["", "状态只证明本次探测结果；rootless 文件标记不单独证明越狱或工具兼容性。", ""]
    evidence.append(_record(output, "report.md", "\n".join(lines).encode(), "text"))
    manifest = {"schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": "device_doctor", "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                "device": device_info, "probes": probes, "evidence": evidence}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                                     default=str) + "\n")
    return output / "report.md", probes["usb_lockdown"]["status"] == "available"
