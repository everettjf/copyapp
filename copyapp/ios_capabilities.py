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


def capability_plan(baseline: dict, requested_mode: str) -> dict:
    if requested_mode not in MODES:
        raise ValueError("mode must be auto, standard or enhanced")
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
    return {"requested_mode": requested_mode, "selected_mode": actual_mode,
            "ui_backend": backend, "operations": operations,
            "limitations": ["Readiness permits an attempt; it does not prove UI actions, signing profiles or delivery.",
                            "A service heartbeat does not establish a functioning XCTest session.",
                            "Package inputs and offline credentials are independent of device privilege."]}


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
    plan = capability_plan(baseline, mode)
    expected = {"device": baseline["device"], "probes": baseline["probes"],
                "host": baseline["host"], **plan}
    if mode == "standard" and any(baseline["probes"].get(name, {}).get("status") != "not_probed"
                                  for name in ("ssh_mobile", "frida_usb", "ios_mcp")):
        return False
    return (record == expected and manifest.get("status") == "complete" and
            manifest.get("selected_mode") == plan["selected_mode"] and
            manifest.get("device_id_sha256_prefix") == hashlib.sha256(udid.encode()).hexdigest()[:16])
