"""Operation-specific capability planning for standard and enhanced iPhones."""

import hashlib
import io
import re
from contextlib import redirect_stdout
from pathlib import Path

from copyapp.doctor import run_doctor
from copyapp.ictrl import DEFAULT_CLIENT
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.verify import verify_case


MODES = ("auto", "standard", "enhanced")


def capability_plan(baseline: dict, requested_mode: str, version: int = 3) -> dict:
    if requested_mode not in MODES:
        raise ValueError("mode must be auto, standard or enhanced")
    if type(version) is not int or version not in (1, 2, 3):
        raise ValueError("unsupported capability model version")
    probes, host = baseline["probes"], baseline["host"]

    def available(name):
        return probes.get(name, {}).get("status") == "available"

    actual_mode = requested_mode
    if actual_mode == "auto":
        actual_mode = ("enhanced" if available("ssh_mobile") and
                       (available("frida_usb") or available("ios_mcp")) else "standard")
    backend = ("ios-mcp" if actual_mode == "enhanced" and available("ios_mcp")
               else "ictrl")
    requirements = {
        "survey": ["usb_lockdown", "usb_screenshot"],
        "analyze": ["usb_lockdown", "usb_screenshot", "ios_mcp" if backend == "ios-mcp" else "ictrl"],
        "trace": ["usb_lockdown", "frida_usb"],
        "sandbox": ["usb_lockdown", "ssh_mobile"],
        "decrypt-device": ["usb_lockdown", "ssh_mobile", "frida_usb"],
    }
    if actual_mode == "enhanced":
        requirements["analyze"].append("ssh_mobile")
    if version == 2:
        requirements["decrypt-device"].append("frida_root_spawn")
    elif version >= 3:
        # Match decrypt_package's actual dispatch. RootHide's pinned helper
        # executes over authenticated mobile SSH, independently of Frida UID.
        requirements["decrypt-device"] = ["usb_lockdown", "ssh_mobile", "package_recovery_route"]
        if probes.get("package_recovery_route", {}).get("route") == "rootless_frida_root":
            requirements["decrypt-device"] += ["frida_usb", "frida_root_spawn"]
    operations = {}
    for name, needs in requirements.items():
        missing = [item for item in needs if not available(item)]
        if actual_mode == "standard" and name in ("trace", "sandbox", "decrypt-device"):
            missing = ["enhanced_mode_required"]
        operations[name] = {"ready_for_attempt": not missing, "missing": missing,
                            "required_probes": needs}
    missing_host = [name for name in ("xcode", "development_signing")
                    if host.get(name, {}).get("status") != "available"]
    operations["rebuild"] = {
        "ready_for_attempt": operations["analyze"]["ready_for_attempt"] and not missing_host,
        "missing": operations["analyze"]["missing"] + missing_host,
        "required_probes": requirements["analyze"],
        "required_host_tools": ["xcode", "development_signing"],
    }
    plan = {"requested_mode": requested_mode, "selected_mode": actual_mode,
            "ui_backend": backend, "operations": operations,
            "limitations": ["Readiness permits an attempt; it does not prove UI actions, signing profiles or delivery.",
                            "A service heartbeat does not establish a functioning XCTest session.",
                            "Package inputs and offline credentials are independent of device privilege."]}
    if version >= 2:
        plan["capability_model_version"] = version
    return plan


def _package_recovery_probe(udid: str, port: int, identity: Path, known_hosts: Path) -> dict:
    from copyapp.decrypt_package import _is_roothide_ssh
    from copyapp.ssh_acquire import _ssh_argv
    from copyapp.usb_tunnel import exact_ssh_tunnel

    result = {"status": "unavailable", "device_id": udid}
    try:
        with exact_ssh_tunnel(udid, port, identity, known_hosts) as active:
            roothide = _is_roothide_ssh(_ssh_argv(active, identity, known_hosts, "mobile"))
            result.update(status="available", identity_verified=True,
                          route="roothide_mobile_ssh" if roothide else "rootless_frida_root")
    except Exception as exc:
        result["error_type"] = type(exc).__name__
    return result


def _package_recovery_valid(probe: dict, udid: str, mode: str, probes: dict) -> bool:
    if not isinstance(probe, dict) or probe.get("device_id") != udid:
        return False
    prerequisites = mode != "standard" and all(
        probes.get(name, {}).get("status") == "available" for name in ("usb_lockdown", "ssh_mobile"))
    if not prerequisites:
        return probe == {"status": "not_probed", "device_id": udid,
                         "reason": "standard mode or required USB/SSH channel unavailable"}
    if probe.get("status") == "available":
        return (set(probe) == {"status", "device_id", "identity_verified", "route"} and
                probe["identity_verified"] is True and
                probe["route"] in ("roothide_mobile_ssh", "rootless_frida_root"))
    return (set(probe) == {"status", "device_id", "error_type"} and
            probe["status"] == "unavailable" and bool(probe["error_type"]))


def _root_spawn_probe(udid: str, port: int, identity: Path, known_hosts: Path) -> dict:
    """Observe a suspended child's UID, then kill it without executing its tool."""
    from copyapp.root_bridge import _spawned_effective_uid, resolve_jailbreak_executable
    from copyapp.ssh_acquire import _ssh_argv
    from copyapp.usb_tunnel import exact_ssh_tunnel
    import frida

    pid = None
    device = None
    result = {"status": "unavailable", "device_id": udid}
    try:
        with exact_ssh_tunnel(udid, port, identity, known_hosts) as active:
            executable = resolve_jailbreak_executable(_ssh_argv(active, identity, known_hosts, "mobile"),
                                                      "/bin/sh")
            device = frida.get_device_manager().get_device(udid, timeout=5)
            if device.id != udid or device.type != "usb":
                raise RuntimeError("root spawn probe did not resolve the exact USB phone")
            # Match root-run's shell entry rather than assuming an App's UID
            # or another executable's credentials establish this route.
            pid = device.spawn([executable, "-c", ":"])
            uid = _spawned_effective_uid(device, pid)
            result.update(effective_uid=uid, identity_verified=True,
                          status="available" if uid == 0 else "unavailable")
            if uid != 0:
                result["reason"] = "App tracing is available, but Frida spawns a non-root user"
    except Exception as exc:
        result.update(status="unavailable", error_type=type(exc).__name__)
    finally:
        if pid is not None:
            try:
                device.kill(pid)
                result["suspended_child_stopped"] = True
            except Exception as exc:
                result.update(status="unavailable", suspended_child_stopped=False,
                              cleanup_error_type=type(exc).__name__)
    return result


def _root_spawn_valid(probe: dict, udid: str, mode: str, probes: dict) -> bool:
    prerequisites = mode != "standard" and all(
        probes.get(name, {}).get("status") == "available"
        for name in ("usb_lockdown", "ssh_mobile", "frida_usb"))
    if not isinstance(probe, dict) or probe.get("device_id") != udid:
        return False
    if not prerequisites:
        return probe == {"status": "not_probed", "device_id": udid,
                         "reason": "standard mode or required USB/SSH/Frida channel unavailable"}
    if probe.get("status") == "available":
        return (type(probe.get("effective_uid")) is int and probe["effective_uid"] == 0 and
                probe.get("identity_verified") is True and probe.get("suspended_child_stopped") is True)
    return probe.get("status") == "unavailable" and (
        bool(probe.get("error_type")) or bool(probe.get("cleanup_error_type")) or
        (type(probe.get("effective_uid")) is int and probe["effective_uid"] != 0 and
         probe.get("identity_verified") is True and probe.get("suspended_child_stopped") is True))


def collect_capabilities(udid: str, output: Path, mode: str = "auto",
                         ssh_port: int = 22222,
                         ssh_identity: Path = Path("cases/ssh/id_ed25519"),
                         ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
                         ictrl_client: Path = DEFAULT_CLIENT) -> Path:
    if mode not in MODES:
        raise ValueError("mode must be auto, standard or enhanced")
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid USB device UDID")
    if output.exists():
        raise FileExistsError(output)
    output.mkdir(parents=True)
    run_doctor(udid, output / "baseline", ssh_port, ssh_identity, ssh_known_hosts,
               ictrl_client, standard_only=mode == "standard")
    baseline = read_json(output / "baseline/device.json")
    probes = baseline["probes"]
    root = (_root_spawn_probe(udid, ssh_port, ssh_identity, ssh_known_hosts)
            if mode != "standard" and all(probes.get(name, {}).get("status") == "available"
               for name in ("usb_lockdown", "ssh_mobile", "frida_usb")) else
            {"status": "not_probed", "device_id": udid,
             "reason": "standard mode or required USB/SSH/Frida channel unavailable"})
    write_json(output / "root-spawn.json", root)
    probes["frida_root_spawn"] = root
    recovery = (_package_recovery_probe(udid, ssh_port, ssh_identity, ssh_known_hosts)
                if mode != "standard" and all(probes.get(name, {}).get("status") == "available"
                   for name in ("usb_lockdown", "ssh_mobile")) else
                {"status": "not_probed", "device_id": udid,
                 "reason": "standard mode or required USB/SSH channel unavailable"})
    write_json(output / "package-recovery-route.json", recovery)
    probes["package_recovery_route"] = recovery
    plan = capability_plan(baseline, mode)
    record = {"device": baseline["device"], "probes": baseline["probes"],
              "host": baseline["host"], **plan}
    write_json(output / "capabilities.json", record)
    lines = ["# iPhone capability plan", "",
             f"- Requested mode: `{mode}`; selected mode: `{plan['selected_mode']}`.",
             f"- UI backend: `{plan['ui_backend']}`.", "",
             "| Operation | Ready for an attempt | Missing |", "| --- | --- | --- |"]
    lines += [f"| `{name}` | {value['ready_for_attempt']} | {', '.join(value['missing']) or 'none'} |"
              for name, value in plan["operations"].items()]
    lines += ["", *plan["limitations"], ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return seal_case(output, "ios_capabilities", status="complete",
                     device_id_sha256_prefix=hashlib.sha256(udid.encode()).hexdigest()[:16],
                     requested_mode=mode, selected_mode=plan["selected_mode"])


def validate_capabilities(root: Path, manifest: dict) -> bool:
    baseline = read_json(root / "baseline/device.json")
    with redirect_stdout(io.StringIO()):
        if not verify_case(root / "baseline"):
            return False
    record = read_json(root / "capabilities.json")
    udid = baseline.get("device", {}).get("UniqueDeviceID")
    if not isinstance(udid, str):
        return False
    mode = manifest["requested_mode"]
    version = record.get("capability_model_version", 1)
    if type(version) is not int or version not in (1, 2, 3):
        return False
    if version >= 2:
        root_probe = read_json(root / "root-spawn.json")
        if not _root_spawn_valid(root_probe, udid, mode, baseline["probes"]):
            return False
        baseline["probes"]["frida_root_spawn"] = root_probe
    elif (root / "root-spawn.json").exists():
        return False
    if version >= 3:
        recovery = read_json(root / "package-recovery-route.json")
        if not _package_recovery_valid(recovery, udid, mode, baseline["probes"]):
            return False
        baseline["probes"]["package_recovery_route"] = recovery
    elif (root / "package-recovery-route.json").exists():
        return False
    plan = capability_plan(baseline, mode, version=version)
    expected = {"device": baseline["device"], "probes": baseline["probes"],
                "host": baseline["host"], **plan}
    if mode == "standard" and any(baseline["probes"].get(name, {}).get("status") != "not_probed"
                                  for name in ("ssh_mobile", "frida_usb", "ios_mcp")):
        return False
    return (record == expected and manifest.get("status") == "complete" and
            manifest.get("selected_mode") == plan["selected_mode"] and
            manifest.get("device_id_sha256_prefix") == hashlib.sha256(udid.encode()).hexdigest()[:16])
