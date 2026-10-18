"""Record a capability baseline for one exact USB-connected iPhone."""

import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from pymobiledevice3.lockdown import create_using_usbmux
from copyapp.device_developer import take_screenshot, list_directory

from copyapp.ictrl import ICtrlClient, DEFAULT_CLIENT
from copyapp.ios_mcp import IOSMCPClient
from copyapp.source_root import source_root
from copyapp.ssh_acquire import _ssh_argv
from copyapp.usb_tunnel import ictrl_tunnel, ios_mcp_tunnel, ssh_tunnel


def _error(exc: Exception) -> Dict[str, str]:
    return {"status": "unavailable", "error_type": type(exc).__name__,
            "reason": str(exc)[:400]}


def _record(output: Path, name: str, data: bytes, kind: str) -> Dict[str, str]:
    (output / name).write_bytes(data)
    return {"id": name.replace(".", "-"), "path": name,
            "sha256": hashlib.sha256(data).hexdigest(), "kind": kind}


async def _usb_probes(udid: str, output: Path, probes: Dict[str, Any],
                      evidence: list, survey_only: bool = False) -> Dict[str, Any]:
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
            picture, route = await take_screenshot(device, udid, str(values.get("ProductVersion", "")))
            suffix = ".png" if picture.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg"
            evidence.append(_record(output, "screenshot" + suffix, picture, "image"))
            probes["usb_screenshot"] = {"status": "available", "bytes": len(picture),
                                        "route": route}
        except Exception as exc:
            probes["usb_screenshot"] = _error(exc)
        if survey_only:
            for name in ("dvt_filesystem", "rootless_marker"):
                probes[name] = {"status": "not_probed", "reason": "not needed for first USB survey"}
            return info
        try:
            version = str(values.get("ProductVersion", ""))
            _, route = await list_directory(device, udid, version, "/")
            probes["dvt_filesystem"] = {"status": "available", "route": route}
            try:
                names = {entry.rsplit("/", 1)[-1] for entry in
                         (await list_directory(device, udid, version, "/var/jb"))[0]}
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
            if "REMOTE HOST IDENTIFICATION HAS CHANGED" in result.stderr:
                return {"status": "host_key_mismatch",
                        "reason": "pinned SSH host key differs from the selected USB phone"}
            return {"status": "unavailable", "exit_code": result.returncode,
                    "reason": result.stderr.strip()[:300]}
        actual = result.stdout.strip()
        if actual != udid:
            return {"status": "identity_mismatch", "reason": "SSH endpoint belongs to another device"}
        return {"status": "available", "identity_verified": True, "user": "mobile"}
    except Exception as exc:
        return _error(exc)


def _roothide_marker_probe(port: int, identity: Path,
                           known_hosts: Path) -> Dict[str, Any]:
    """Check RootHide's SSH namespace when native DVT cannot read /var/jb."""
    try:
        argv = _ssh_argv(port, identity, known_hosts, "mobile")
        result = subprocess.run(argv + ["command -v jbroot; jbroot; test -d /rootfs/var/mobile/Media"],
                                capture_output=True, text=True, timeout=15)
        lines = result.stdout.splitlines()
        if result.returncode == 0 and len(lines) >= 2 and lines[0].endswith("/jbroot"):
            return {"status": "observed", "roothide_namespace": True,
                    "jbroot_path": lines[1],
                    "note": "SSH namespace markers alone do not prove every jailbreak capability."}
    except Exception:
        pass
    return {"status": "unavailable", "reason": "RootHide namespace marker not observed over SSH"}


def _frida_probe(udid: str) -> Dict[str, Any]:
    try:
        import frida
        from copyapp.frida_sidecar import configured_sidecar, sidecar_device

        sidecar = configured_sidecar(udid)
        if sidecar is not None:
            device = sidecar_device(udid)
            access = device.query_system_parameters().get("access")
            processes = device.enumerate_processes(scope="minimal")
            return {"status": "available" if access == "full" else "unavailable",
                    "identity_verified": True, "transport": "usb_roothide_sidecar",
                    "access": access or "unknown", "host_frida_version": frida.__version__,
                    "server_version": sidecar["version"], "process_count": len(processes)}
        devices = frida.get_device_manager().enumerate_devices()
        device = next((item for item in devices if item.id == udid and item.type == "usb"), None)
        if device is None:
            return {"status": "unavailable", "reason": "exact USB UDID absent from Frida inventory"}
        access = device.query_system_parameters().get("access")
        if access != "full":
            return {"status": "unavailable", "identity_verified": True,
                    "access": access or "unknown", "host_frida_version": frida.__version__,
                    "reason": "Frida sees this iPhone through jailed developer services; "
                              "install and start a compatible frida-server inside the active jailbreak"}
        processes = device.enumerate_processes(scope="minimal")
        return {"status": "available", "identity_verified": True,
                "access": access, "host_frida_version": frida.__version__,
                "process_count": len(processes)}
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


def _host_probes() -> Dict[str, Any]:
    result = {}
    for name, executable in (("xcodegen", "xcodegen"), ("ldid", "ldid"),
                             ("codex_cli", "codex"), ("claude_cli", "claude")):
        path = shutil.which(executable)
        result[name] = {"status": "available" if path else "not_configured",
                        "path": path}
    try:
        version = subprocess.run(["xcodebuild", "-version"], capture_output=True,
                                 text=True, timeout=8, check=False)
        result["xcode"] = {"status": "available" if version.returncode == 0
                           else "unavailable", "version": version.stdout.strip()[:100],
                           "reason": version.stderr.strip()[:150] if version.returncode else ""}
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["xcode"] = _error(exc)
    try:
        identities = subprocess.run(
            ["security", "find-identity", "-v", "-p", "codesigning"],
            capture_output=True, text=True, timeout=8, check=False)
        result["development_signing"] = {
            "status": "available" if identities.returncode == 0 and
                      "Apple Development:" in identities.stdout else "not_configured",
            "reason": "Apple Development identity only; the IPA still needs a matching provisioning profile and device registration"}
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["development_signing"] = _error(exc)
    theos = Path(os.environ["THEOS"]).expanduser() if os.environ.get("THEOS") else (
        source_root() / "toolchains" / "theos")
    result["theos"] = {"status": "available" if theos.is_dir() else "not_configured",
                       "path": str(theos) if theos.is_dir() else None}
    return result


def _next_steps(udid: str, probes: Dict[str, Any], host: Dict[str, Any],
                identity: Path, known_hosts: Path,
                ssh_port: int = 22222) -> list[Dict[str, str]]:
    """Return ordered, concrete repairs without treating optional tools as blockers."""
    steps = []
    if probes["usb_lockdown"]["status"] != "available":
        return [{"for": "usb_lockdown", "action":
                 "Unlock the iPhone, accept Trust This Computer, reconnect its USB cable, "
                 "then run .venv/bin/copyapp onboard again with the exact UDID."}]
    if probes.get("usb_screenshot", {}).get("status") != "available":
        steps.append({"for": "usb_screenshot", "action":
                      "Enable Developer Mode on the phone, select full Xcode with "
                      "xcode-select, and mount the matching Developer Disk Image."})
    if probes.get("dvt_filesystem", {}).get("status") == "unavailable":
        steps.append({"for": "dvt_filesystem_optional", "action":
                      "Developer file listing is unavailable on this device. "
                      "For App bundle and sandbox acquisition, use the pinned mobile SSH route; "
                      "this does not block SSH-backed analysis. If USB-only file listing is "
                      "needed, check Developer Mode and the matching Developer Disk Image."})
    if host["xcode"]["status"] != "available":
        steps.append({"for": "xcode", "action":
                      "Install and select full Xcode; check xcodebuild -version."})
    if probes["ssh_mobile"]["status"] == "identity_mismatch":
        steps.append({"for": "ssh_mobile", "action":
                      f"Stop the SSH forward on host port {ssh_port}; it reaches a different "
                      f"phone. Restart with .venv/bin/copyapp tunnel --udid {udid} --ssh-port {ssh_port}."})
    elif probes["ssh_mobile"]["status"] == "host_key_mismatch":
        steps.append({"for": "ssh_mobile", "action":
                      f"The key in {known_hosts} belongs to a different SSH endpoint. "
                      "Keep each phone's pinned host key in a separate file and use a "
                      f"dedicated --ssh-port {ssh_port} when both phones are connected. Verify the new "
                      f"fingerprint on the exact USB device {udid} before trusting it; "
                      "do not replace the existing trusted key."})
    elif probes["ssh_mobile"]["status"] != "available":
        if not identity.is_file():
            steps.append({"for": "ssh_mobile", "action":
                          f"Create a dedicated key: ssh-keygen -t ed25519 -f {identity} -C copyapp"})
        if not known_hosts.is_file():
            steps.append({"for": "ssh_mobile", "action":
                          f"Run .venv/bin/copyapp tunnel --udid {udid} --ssh-port {ssh_port} in another terminal. "
                          f"Then run ssh-keyscan -p {ssh_port} 127.0.0.1 > {known_hosts} and "
                          f"ssh-keygen -lf {known_hosts}. Compare that fingerprint with the phone "
                          "before trusting it. Then add the Mac public key to mobile's authorized_keys "
                          "as shown in README.md."})
        else:
            steps.append({"for": "ssh_mobile", "action":
                          "Install/start OpenSSH built for the phone's jailbreak (RootHide needs "
                          "a RootHide package); check mobile key login "
                          f"and the pinned host key with ssh -p {ssh_port} -i {identity} "
                          f"-o UserKnownHostsFile={known_hosts} -o StrictHostKeyChecking=yes "
                          "mobile@127.0.0.1 'deviceinfo uniqueid'. See README.md for the "
                          "one-time authorized_keys step."})
    if probes["frida_usb"]["status"] != "available":
        steps.append({"for": "frida_usb", "action":
                      "Run sh scripts/bootstrap-macos.sh --trace, then install/start a compatible "
                      "root-capable Frida server on the phone."})
    if (probes.get("rootless_marker", {}).get("roothide_namespace") and
            probes["frida_usb"].get("transport") != "usb_roothide_sidecar"):
        steps.append({"for": "frida_roothide", "action":
                      "For the tested iOS 17/26 RootHide runtime paths, install host frida==17.23.3 "
                      f"and run .venv/bin/copyapp setup frida-roothide --udid {udid} "
                      "--out cases/frida-roothide-setup with the pinned mobile SSH key. "
                      "A Frida process inventory alone does not prove system-App attach."})
    if probes["ios_mcp"]["status"] != "available":
        steps.append({"for": "ios_mcp", "action":
                      "Build and install device/ios-mcp with Theos on this jailbreak, then "
                      "reload SpringBoard. See device/ios-mcp/README.md."})
    if probes["ictrl"]["status"] != "available":
        steps.append({"for": "ictrl_optional", "action":
                      f"Optional: run .venv/bin/copyapp setup ictrl --udid {udid} --out "
                      "cases/ictrl-setup, then approve the matching pairing fingerprint."})
    if host["xcodegen"]["status"] != "available":
        steps.append({"for": "xcodegen_rebuild", "action":
                      "For a runnable clone, install XcodeGen (brew install xcodegen)."})
    if (host["ldid"]["status"] != "available" and
            host.get("development_signing", {}).get("status") != "available"):
        steps.append({"for": "signing_rebuild", "action":
                      "Choose an install route: install ldid for a supported TrollStore path, "
                      "or configure an Apple Development signing identity and a provisioning "
                      "profile covering the clone Bundle ID and this device for USB installation."})
    if (host.get("codex_cli", {}).get("status") != "available" and
            host.get("claude_cli", {}).get("status") != "available"):
        steps.append({"for": "agent_cli_optional", "action":
                      "For an independent-terminal run, install and sign in to Codex CLI or "
                      "Claude Code. An already active coding-agent session can use "
                      "--agent-provider current instead."})
    if (probes["ios_mcp"]["status"] != "available" and
            host["theos"]["status"] != "available"):
        steps.append({"for": "theos_tweak", "action":
                      "For the optional iOS MCP tweak, install Theos and the matching iPhoneOS "
                      "SDK. RootHide requires roothide/theos and THEOS_PACKAGE_SCHEME=roothide."})
    return steps


def run_doctor(udid: str, output: Path, ssh_port: int = 22222,
               ssh_identity: Path = Path("cases/ssh/id_ed25519"),
               ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
               ictrl_client: Path = DEFAULT_CLIENT,
               survey_only: bool = False) -> Tuple[Path, bool]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite device baseline: {output}")
    output.mkdir(parents=True)
    probes: Dict[str, Any] = {}
    evidence = []
    try:
        device_info = asyncio.run(_usb_probes(udid, output, probes, evidence, survey_only))
    except Exception as exc:
        probes["usb_lockdown"] = _error(exc)
        device_info = {"UniqueDeviceID": udid}
    if survey_only:
        for key in ("ssh_mobile", "frida_usb", "ios_mcp", "ictrl"):
            probes[key] = {"status": "not_probed", "reason": "not needed for first USB survey"}
    elif probes["usb_lockdown"]["status"] == "available":
        try:
            with socket.create_connection(("127.0.0.1", ssh_port), timeout=0.3):
                pass
            tunnel = nullcontext(ssh_port)
        except OSError:
            tunnel = ssh_tunnel(udid, ssh_port)
        try:
            with tunnel as active_port:
                probes["ssh_mobile"] = _ssh_probe(udid, active_port,
                                                   ssh_identity, ssh_known_hosts)
                if probes["ssh_mobile"]["status"] == "available":
                    marker = _roothide_marker_probe(active_port, ssh_identity,
                                                    ssh_known_hosts)
                    if marker["status"] == "observed":
                        probes["rootless_marker"] = {
                            **probes.get("rootless_marker", {}), **marker}
        except Exception as exc:
            probes["ssh_mobile"] = _error(exc)
        probes["frida_usb"] = _frida_probe(udid)
        probes["ios_mcp"] = _ios_mcp_probe(udid)
        probes["ictrl"] = _ictrl_probe(udid, ictrl_client)
    else:
        for key in ("ssh_mobile", "frida_usb", "ios_mcp", "ictrl"):
            probes[key] = {"status": "not_probed", "reason": "exact USB lockdown device unavailable"}
    host = _host_probes()
    next_steps = _next_steps(udid, probes, host, ssh_identity, ssh_known_hosts,
                             ssh_port)
    if survey_only:
        next_steps = [step for step in next_steps
                      if step["for"] in ("usb_lockdown", "usb_screenshot")]
    device_data = (json.dumps({"device": device_info, "probes": probes,
                               "host": host, "next_steps": next_steps},
                              ensure_ascii=False, indent=2, default=str) + "\n").encode()
    evidence.append(_record(output, "device.json", device_data, "json"))
    lines = ["# Copy APP device setup", "",
             f"- Probe scope: `{'first USB survey' if survey_only else 'full device baseline'}`",
             f"- Device: `{device_info.get('ProductType', 'unknown')}` / iOS {device_info.get('ProductVersion', 'unknown')}",
             f"- UDID: `{udid}`", "",
             "| Capability | Status | Detail |", "| --- | --- | --- |"]
    for name, item in probes.items():
        detail = item.get("reason") or item.get("error_type") or ""
        lines.append(f"| `{name}` | {item['status']} | {str(detail).replace('|', '/')} |")
    lines += ["", "## Mac tools", "", "| Tool | Status |", "| --- | --- |"]
    for name, item in host.items():
        if survey_only and name != "xcode":
            continue
        lines.append(f"| `{name}` | {item['status']} |")
    lines += ["", "## Next steps", ""]
    lines.extend(f"{index}. **{item['for']}**: {item['action']}"
                 for index, item in enumerate(next_steps, 1))
    if not next_steps:
        lines.append("The USB survey is ready. Choose an App with `copyapp apps --udid <UDID> --all`."
                     if survey_only else
                     "The probed channels are ready. Choose an App with `copyapp apps --udid <UDID> --all`.")
    lines += ["", "A green probe covers only this run; file markers alone do not prove jailbreak privileges or tool compatibility.", ""]
    evidence.append(_record(output, "report.md", "\n".join(lines).encode(), "text"))
    manifest = {"schema_version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "kind": "device_doctor", "probe_scope": "survey" if survey_only else "full",
                "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                "device": device_info, "probes": probes, "host": host,
                "next_steps": next_steps, "evidence": evidence}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                                     default=str) + "\n")
    return output / "report.md", probes["usb_lockdown"]["status"] == "available"
