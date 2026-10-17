"""Install a local IPA on an exact USB iPhone via signing or TrollStore."""

import asyncio
import json
import re
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ipa import analyze_ipa
from copyapp.root_bridge import run_root_command
from copyapp.ssh_acquire import _ssh_argv
from copyapp.usb_tunnel import exact_ssh_tunnel


async def _installed_app(udid: str, bundle_id: str) -> Dict[str, Any]:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle_id])
        return apps.get(bundle_id) or {}
    finally:
        await device.close()


def install_trollstore_ipa(udid: str, ipa: Path, output: Path, ssh_port: int,
                           identity: Path, known_hosts: Path) -> Path:
    """Install through a verified, short-lived SSH forward to the selected USB phone."""
    with exact_ssh_tunnel(udid, ssh_port, identity, known_hosts):
        return _install_trollstore_ipa_via_ssh(udid, ipa, output, ssh_port,
                                                identity, known_hosts)


def _install_trollstore_ipa_via_ssh(udid: str, ipa: Path, output: Path,
                                   ssh_port: int, identity: Path,
                                   known_hosts: Path) -> Path:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    package = analyze_ipa(ipa)
    bundle_id = package.get("bundle_id")
    if not isinstance(bundle_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id):
        raise ValueError("IPA has no valid bundle ID")
    output.mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device_id": udid,
        "ipa": str(ipa.resolve(strict=True)),
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
        actual_udid = subprocess.run(ssh + ["deviceinfo uniqueid"], capture_output=True,
                                     timeout=10, check=True).stdout.decode().strip()
        if actual_udid != udid:
            raise RuntimeError("SSH is connected to a different device")
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
        subprocess.run(scp + [str(ipa), f"mobile@127.0.0.1:{remote_ipa}"],
                       capture_output=True, timeout=120, check=True)
        remote_hash = subprocess.run(ssh + ["sha256sum " + shlex.quote(remote_ipa)],
                                     capture_output=True, timeout=10, check=True).stdout.decode().split()[0]
        record["staged_sha256"] = remote_hash
        if remote_hash != package["ipa_sha256"]:
            raise RuntimeError("staged IPA hash mismatch")
        run = run_root_command(udid, [helpers[0], "install", "custom", remote_ipa],
                               output / "device-run", ssh_port, identity, known_hosts, timeout=120)
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
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    package = analyze_ipa(ipa)
    bundle_id = package.get("bundle_id")
    if not isinstance(bundle_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle_id):
        raise ValueError("IPA has no valid bundle ID")
    output.mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {
        "schema_version": 1,
        "transport": "usb",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device_id": udid,
        "ipa": str(ipa.resolve(strict=True)),
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
                await proxy.install_from_local(ipa)
                apps = await proxy.get_apps(application_type="Any",
                                            bundle_identifiers=[bundle_id])
            return apps.get(bundle_id) or {}
        finally:
            await device.close()

    try:
        installed = asyncio.run(install())
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
