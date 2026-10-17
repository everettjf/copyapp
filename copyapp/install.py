"""Install a local IPA on an exact USB iPhone via signing or TrollStore."""

import asyncio
import json
import plistlib
import re
import shlex
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ipa import analyze_ipa
from copyapp.ictrl import DEFAULT_CLIENT, ICtrlClient
from copyapp.root_bridge import run_root_command
from copyapp.ssh_acquire import _ssh_argv
from copyapp.usb_tunnel import (configured_ictrl_runner_bundle, exact_ssh_tunnel,
                                ictrl_tunnel)


async def _installed_app(udid: str, bundle_id: str) -> Dict[str, Any]:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle_id])
        return apps.get(bundle_id) or {}
    finally:
        await device.close()


def _stop_running_app(udid: str, bundle_id: str) -> Dict[str, str]:
    """Ask the paired UI runner to stop only the app being replaced, if available."""
    if not DEFAULT_CLIENT.is_file() or not configured_ictrl_runner_bundle(udid):
        return {"status": "unavailable", "reason": "paired iCTRL runner not configured"}
    try:
        with ictrl_tunnel(udid) as port:
            ICtrlClient(port=port).call_ui("terminate_app", {"bundle_id": bundle_id})
        return {"status": "requested", "backend": "ictrl", "bundle_id": bundle_id}
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        return {"status": "unavailable", "reason": f"{type(exc).__name__}: {str(exc)[:180]}"}


def _stop_stale_mobile_processes(udid: str, ssh: list, bundle_id: str,
                                 executable: str) -> Dict[str, Any]:
    """Stop every mobile process whose on-device app plist has the exact Bundle ID."""
    if not isinstance(executable, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", executable):
        return {"status": "unavailable", "reason": "invalid executable name"}
    try:
        import frida

        device = frida.get_device_manager().get_device(udid, timeout=5)
        if device.id != udid or device.type != "usb":
            raise RuntimeError("Frida did not resolve the requested USB device")
        pattern = re.compile(
            r"/(?:private/)?var/containers/Bundle/Application/"
            r"[0-9A-Fa-f-]{36}/[^/]+\.app/" + re.escape(executable))
        candidates = [(process.pid, path) for process in device.enumerate_processes(scope="full")
                      if isinstance((path := process.parameters.get("path")), str)
                      and pattern.fullmatch(path)]
        if len(candidates) > 32:
            raise RuntimeError("too many matching app processes")
        stopped = 0
        for pid, path in candidates:
            info_path = path.rsplit("/", 1)[0] + "/Info.plist"
            result = subprocess.run(ssh + ["cat " + shlex.quote(info_path)],
                                    capture_output=True, timeout=8, check=False)
            if result.returncode:
                continue
            try:
                info = plistlib.loads(result.stdout)
            except (ValueError, TypeError):
                continue
            if info.get("CFBundleIdentifier") != bundle_id:
                continue
            device.kill(pid)
            stopped += 1
        if stopped:
            time.sleep(0.5)
        return {"status": "stopped" if stopped else "clear", "count": stopped,
                "identity": "installed Info.plist Bundle ID"}
    except Exception as exc:
        return {"status": "unavailable", "reason": f"{type(exc).__name__}: {str(exc)[:180]}"}


def install_trollstore_ipa(udid: str, ipa: Path, output: Path, ssh_port: int,
                           identity: Path, known_hosts: Path) -> Path:
    """Install through a verified, short-lived SSH forward to the selected USB phone."""
    with exact_ssh_tunnel(udid, ssh_port, identity, known_hosts):
        return _install_trollstore_ipa_via_ssh(udid, ipa, output, ssh_port,
                                                identity, known_hosts)


def _snapshot_ipa(ipa: Path, output: Path) -> Tuple[Path, Path]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    source = ipa.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=True)
    saved = output / "input.ipa"
    shutil.copy2(source, saved)
    return saved.resolve(strict=True), source


def _install_trollstore_ipa_via_ssh(udid: str, ipa: Path, output: Path,
                                   ssh_port: int, identity: Path,
                                   known_hosts: Path) -> Path:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    saved_ipa, source_ipa = _snapshot_ipa(ipa, output)
    package = analyze_ipa(saved_ipa)
    bundle_id = package.get("bundle_id")
    if not isinstance(bundle_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id):
        raise ValueError("IPA has no valid bundle ID")
    record: Dict[str, Any] = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device_id": udid,
        "ipa": str(saved_ipa),
        "source_ipa": str(source_ipa),
        "ipa_sha256": package["ipa_sha256"],
        "bundle_id": bundle_id,
        "version": package.get("version"),
        "build": package.get("build"),
        "status": "failed",
    }
    result_path = output / "install.json"
    ssh = _ssh_argv(ssh_port, identity, known_hosts, "mobile")
    remote_ipa = f"/var/mobile/Media/copyapp-install-{uuid.uuid4().hex}.ipa"
    try:
        record["preinstall_termination"] = _stop_running_app(udid, bundle_id)
        actual_udid = subprocess.run(ssh + ["deviceinfo uniqueid"], capture_output=True,
                                     timeout=10, check=True).stdout.decode().strip()
        if actual_udid != udid:
            raise RuntimeError("SSH is connected to a different device")
        record["stale_process_cleanup"] = _stop_stale_mobile_processes(
            udid, ssh, bundle_id, package.get("executable"))
        discovery = subprocess.run(ssh + [
            "find /var/containers/Bundle/Application -maxdepth 3 -type f "
            "-name trollstorehelper -print 2>/dev/null"
        ], capture_output=True, timeout=15, check=True).stdout.decode().splitlines()
        helpers = [path for path in discovery if re.fullmatch(
            r"/var/containers/Bundle/Application/[0-9A-Fa-f-]{36}/TrollStore\.app/trollstorehelper",
            path)]
        if len(helpers) != 1:
            raise RuntimeError(f"expected one installed TrollStore helper; found {len(helpers)}")
        record["helper"] = helpers[0]
        scp = ["scp", "-P", str(ssh_port), "-i", str(identity),
               "-o", f"UserKnownHostsFile={known_hosts}",
               "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes",
               "-o", "IdentitiesOnly=yes"]
        subprocess.run(scp + [str(saved_ipa), f"mobile@127.0.0.1:{remote_ipa}"],
                       capture_output=True, timeout=120, check=True)
        remote_hash = subprocess.run(ssh + ["sha256sum " + shlex.quote(remote_ipa)],
                                     capture_output=True, timeout=10, check=True).stdout.decode().split()[0]
        record["staged_sha256"] = remote_hash
        if remote_hash != package["ipa_sha256"]:
            raise RuntimeError("staged IPA hash mismatch")
        try:
            run = run_root_command(udid, [helpers[0], "install", "custom", remote_ipa],
                                   output / "device-run", ssh_port, identity, known_hosts,
                                   timeout=120)
        except TimeoutError:
            try:
                observed = asyncio.run(asyncio.wait_for(
                    _installed_app(udid, bundle_id), timeout=15))
                record["installed_after_timeout"] = {
                    "present": bool(observed),
                    "version": observed.get("CFBundleShortVersionString"),
                    "build": observed.get("CFBundleVersion"),
                    "path": observed.get("Path"),
                }
            except Exception as probe_error:
                record["installed_after_timeout_error"] = (
                    f"{type(probe_error).__name__}: {str(probe_error)[:180]}")
            raise
        record["helper_exit_code"] = run["exit_code"]
        if run["exit_code"] != 0:
            raise RuntimeError(f"TrollStore helper exited {run['exit_code']}; inspect device-run/output.txt")
        installed = asyncio.run(_installed_app(udid, bundle_id))
        if not installed:
            raise RuntimeError("installer returned success but app is absent from InstallationProxy")
        if (str(installed.get("CFBundleShortVersionString")) != str(package.get("version")) or
                str(installed.get("CFBundleVersion")) != str(package.get("build"))):
            raise RuntimeError("installed app version/build does not match the IPA")
        record["installed_path"] = installed.get("Path")
        record["status"] = "installed"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
        raise
    finally:
        try:
            cleanup = subprocess.run(ssh + ["rm -f " + shlex.quote(remote_ipa)],
                                     capture_output=True, timeout=10)
            if cleanup.returncode != 0:
                record["cleanup_warning"] = "staged IPA removal was not confirmed"
        except (OSError, subprocess.TimeoutExpired):
            record["cleanup_warning"] = "staged IPA removal was not confirmed"
        record["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return result_path


def install_usb_ipa(udid: str, ipa: Path, output: Path) -> Path:
    """Install a development-signed IPA through USB InstallationProxy."""
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    saved_ipa, source_ipa = _snapshot_ipa(ipa, output)
    package = analyze_ipa(saved_ipa)
    bundle_id = package.get("bundle_id")
    if not isinstance(bundle_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id):
        raise ValueError("IPA has no valid bundle ID")
    record: Dict[str, Any] = {
        "schema_version": 1,
        "transport": "usb",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device_id": udid,
        "ipa": str(saved_ipa),
        "source_ipa": str(source_ipa),
        "ipa_sha256": package["ipa_sha256"],
        "bundle_id": bundle_id,
        "version": package.get("version"),
        "build": package.get("build"),
        "usb_install_completed": False,
        "status": "failed",
    }

    async def install() -> Dict[str, Any]:
        device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
        try:
            values = await device.get_value()
            if values.get("UniqueDeviceID") != udid:
                raise RuntimeError("USB installation target identity does not match --udid")
            async with InstallationProxyService(device) as proxy:
                await proxy.install_from_local(saved_ipa)
                apps = await proxy.get_apps(application_type="Any",
                                            bundle_identifiers=[bundle_id])
            return apps.get(bundle_id) or {}
        finally:
            await device.close()

    try:
        record["preinstall_termination"] = _stop_running_app(udid, bundle_id)
        installed = asyncio.run(asyncio.wait_for(install(), timeout=120))
        record["usb_install_completed"] = True
        if not installed:
            raise RuntimeError("InstallationProxy completed but app is absent from its database")
        if (str(installed.get("CFBundleShortVersionString")) != str(package.get("version")) or
                str(installed.get("CFBundleVersion")) != str(package.get("build"))):
            raise RuntimeError("installed app version/build does not match the IPA")
        if installed.get("ProfileValidated") is not True:
            raise RuntimeError("installed app profile is not validated")
        record["installed_path"] = installed.get("Path")
        record["installed_profile_validated"] = True
        record["status"] = "installed"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
        raise
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result_path = output / "install.json"
        result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return result_path
