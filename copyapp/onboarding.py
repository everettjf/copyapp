"""One-command entry for first-device setup and actionable capability checks."""

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pymobiledevice3.usbmux import list_devices

from copyapp.doctor import run_doctor


def _choose_device(devices: list, requested: Optional[str]) -> str:
    ids = sorted({item.serial for item in devices
                  if str(getattr(item, "connection_type", "")).lower().endswith("usb")})
    if requested:
        if requested not in ids:
            raise ValueError("requested UDID is not connected over USB; found: " +
                             (", ".join(ids) or "none"))
        return requested
    if not ids:
        raise ValueError("no USB iPhone is visible; unlock it, connect USB and accept Trust This Computer")
    if len(ids) > 1:
        raise ValueError("multiple USB devices are connected; choose --udid from: " +
                         ", ".join(ids))
    return ids[0]


def _prepare_ssh_key(identity: Path) -> bool:
    """Create only the host keypair; phone authorization remains a separate step."""
    if identity.exists():
        if not identity.is_file():
            raise ValueError("SSH identity path exists but is not a file")
        return False
    parent_existed = identity.parent.exists()
    identity.parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed:
        os.chmod(identity.parent, 0o700)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                    "-f", str(identity), "-C", "copyapp"], check=True)
    os.chmod(identity, 0o600)
    return True


def run_onboarding(udid: Optional[str] = None, output: Optional[Path] = None,
                   ssh_identity: Path = Path("cases/ssh/id_ed25519"),
                   ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
                   ssh_port: int = 22222, prepare_ssh: bool = True,
                   stage: str = "survey") -> tuple[Path, bool]:
    """Identify one device, prepare the local key and save a guided doctor case."""
    if stage not in ("survey", "analyze", "rebuild"):
        raise ValueError("stage must be survey, analyze or rebuild")
    devices = asyncio.run(list_devices())
    selected = _choose_device(devices, udid)
    if output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        output = Path("cases") / f"onboard-{stamp}-{uuid4().hex[:8]}"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite setup case: {output}")
    created_key = _prepare_ssh_key(ssh_identity) if prepare_ssh and stage != "survey" else False
    report, connected = run_doctor(selected, output, ssh_port, ssh_identity,
                                   ssh_known_hosts, survey_only=(stage == "survey"))
    record = json.loads((output / "device.json").read_text(encoding="utf-8"))
    survey_ready = (connected and
                    record["probes"].get("usb_screenshot", {}).get("status") == "available")
    analysis_ready = (survey_ready and
                      all(record["probes"].get(name, {}).get("status") == "available"
                          for name in ("ssh_mobile", "frida_usb", "ios_mcp")) and
                      record["host"]["xcode"]["status"] == "available")
    rebuild_ready = (analysis_ready and
                     all(record["host"][name]["status"] == "available"
                         for name in ("xcodegen", "ldid")))
    ready = {"survey": survey_ready, "analyze": analysis_ready,
             "rebuild": rebuild_ready}[stage]
    print(f"Device: {selected}")
    if created_key:
        print(f"Created dedicated Mac SSH key: {ssh_identity}")
    print(f"Setup report: {report}")
    print("First USB survey: " + ("ready" if survey_ready else "needs setup"))
    print("Deep analysis: " + ("not checked (rerun with --stage analyze)" if stage == "survey"
                               else "ready" if analysis_ready else "needs setup"))
    print("Runnable rebuild tools: " + ("not checked (rerun with --stage rebuild)"
                                        if stage == "survey" else "ready" if rebuild_ready
                                        else "needs setup"))
    relevant = {"survey": {"usb_lockdown", "usb_screenshot"},
                "analyze": {"usb_lockdown", "usb_screenshot", "ssh_mobile",
                            "frida_usb", "ios_mcp", "xcode", "theos_tweak"},
                "rebuild": None}[stage]
    for step in record["next_steps"]:
        if relevant is None or step["for"] in relevant:
            print(f"- {step['for']}: {step['action']}")
    if ready and stage == "survey":
        print(f"Next: .venv/bin/copyapp apps --udid {selected} --all")
        print(f"For full analysis: .venv/bin/copyapp onboard --udid {selected} --stage analyze")
    elif ready and stage in ("analyze", "rebuild"):
        print(f"For longer device runs, keep .venv/bin/copyapp tunnel --udid {selected} open in another terminal.")
    return report, ready
