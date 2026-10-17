"""Build, install and pair the vendored iCTRL runner for one USB iPhone."""

import asyncio
import hashlib
import json
import os
import plistlib
import re
import select
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
from zipfile import ZipFile

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ictrl import ICtrlClient, DEFAULT_CLIENT
from copyapp.install import _installed_app, install_trollstore_ipa
from copyapp.source_root import source_root
from copyapp.usb_tunnel import configured_ictrl_runner_bundle, ictrl_xcuitest_session


ROOT = source_root()
SOURCE = ROOT / "vendor" / "ictrl"
REVISION = "d88bbf0b3a5addead31b4298d605d7ac7a87d6e7"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def _device(udid: str) -> Dict[str, str]:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("USB device identity does not match --udid")
        return {key: str(values.get(key, "")) for key in
                ("UniqueDeviceID", "ProductType", "ProductVersion", "BuildVersion")}
    finally:
        await device.close()


async def _install_usb_ipa(udid: str, ipa: Path) -> None:
    """Install a properly signed runner through the exact device's USB service."""
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        if (await device.get_value()).get("UniqueDeviceID") != udid:
            raise RuntimeError("USB installation target identity does not match --udid")
        async with InstallationProxyService(device) as proxy:
            await proxy.install_from_local(ipa)
    finally:
        await device.close()


async def _stop_runner(udid: str, bundle: str) -> None:
    """Stop a running runner before installing or launching its replacement."""
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl

    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RuntimeError("USB runner target identity does not match --udid")
        if sys.platform == "darwin" and int(str(values.get("ProductVersion", "0")).split(".")[0]) >= 17:
            command = [sys.executable, "-m", "pymobiledevice3", "developer", "dvt",
                       "process-id-for-bundle-id", "--native", "--udid", udid, bundle]
            result = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=45)
            if result.returncode:
                raise RuntimeError("native runner process lookup failed: " +
                                   stderr.decode(errors="replace").strip()[-250:])
            pid_text = stdout.decode().strip()
            if not pid_text.isdigit():
                raise RuntimeError("native runner process lookup returned invalid PID")
            if int(pid_text):
                command = [sys.executable, "-m", "pymobiledevice3", "developer", "dvt",
                           "signal", "--native", "--udid", udid, pid_text, "9"]
                result = await asyncio.create_subprocess_exec(
                    *command, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                _, stderr = await asyncio.wait_for(result.communicate(), timeout=45)
                if result.returncode:
                    raise RuntimeError("native runner stop failed: " +
                                       stderr.decode(errors="replace").strip()[-250:])
            return
        async with DvtProvider(device) as provider, ProcessControl(provider) as control:
            pid = await control.process_identifier_for_bundle_identifier(bundle)
            if pid:
                await control.kill(pid)
    finally:
        await device.close()


def _bundle_from_ipa(ipa: Path) -> Tuple[str, str]:
    with ZipFile(ipa) as archive:
        matches = [name for name in archive.namelist()
                   if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", name)]
        if len(matches) != 1:
            raise ValueError("runner IPA must have one app Info.plist")
        info = plistlib.loads(archive.read(matches[0]))
    bundle = info.get("CFBundleIdentifier")
    minimum = info.get("MinimumOSVersion")
    if not isinstance(bundle, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("runner IPA has invalid Bundle ID")
    if not isinstance(minimum, str) or not re.fullmatch(r"\d+(?:\.\d+){0,2}", minimum):
        raise ValueError("runner IPA has invalid minimum iOS version")
    return bundle, minimum


def _version(value: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _save_bundle(udid: str, bundle: str) -> None:
    path = ROOT / "toolchains" / "ictrl-runners.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    values = json.loads(path.read_text()) if path.is_file() else {}
    values[udid] = bundle
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(values, indent=2) + "\n")
    temporary.replace(path)


def _build_client() -> Path:
    if not (ROOT / "scripts" / "build-ictrl-client.sh").is_file():
        raise FileNotFoundError(
            "Copy APP source checkout is required for iCTRL setup; "
            "set COPYAPP_SOURCE_ROOT when running from a wheel")
    subprocess.run(["sh", str(ROOT / "scripts" / "build-ictrl-client.sh")],
                   cwd=ROOT, check=True, timeout=90)
    if not DEFAULT_CLIENT.is_file():
        raise RuntimeError("iCTRL Mac client build produced no executable")
    return DEFAULT_CLIENT


def _build_runner(ios_version: str, output: Path) -> Path:
    if not (SOURCE / "LICENSE").is_file():
        raise FileNotFoundError("vendored iCTRL source is missing")
    if not shutil.which("xcodegen"):
        raise FileNotFoundError("xcodegen is required; install it and rerun setup")
    if not shutil.which("xcodebuild"):
        raise FileNotFoundError("Xcode command-line tools are required")
    major = _version(ios_version)[0]
    if major < 16:
        raise ValueError("this iCTRL setup supports iOS 16 or newer")
    env = os.environ.copy()
    if major == 16:
        env["COPYAPP_IOS_TARGET"] = "16.0"
    else:
        env.pop("COPYAPP_IOS_TARGET", None)
    print("Building signed iCTRL runner from vendored source; Xcode may fetch the pinned IDevice framework.", flush=True)
    subprocess.run(["make", "ipa"], cwd=SOURCE, env=env, check=True, timeout=1800)
    built = SOURCE / "iCTRLUITests-Runner.ipa"
    if not built.is_file():
        raise RuntimeError("iCTRL build produced no runner IPA")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, output)
    return output


@contextmanager
def _usb_forward(udid: str, device_port: int, local_port: Optional[int] = None,
                 reuse_existing: bool = False) -> Iterator[int]:
    if local_port is None:
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            local_port = reserved.getsockname()[1]
    elif reuse_existing:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", local_port))
            except OSError:
                # install_trollstore_ipa checks the exact remote UDID over SSH.
                yield local_port
                return
    command = [sys.executable, "-m", "pymobiledevice3", "usbmux", "forward",
               str(local_port), str(device_port), "--serial", udid]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"USB forward to device port {device_port} exited")
            try:
                with socket.create_connection(("127.0.0.1", local_port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise TimeoutError(f"USB forward to device port {device_port} did not start")
        yield local_port
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def _runner_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/whoami", timeout=1) as response:
            return response.status == 200 and bool(json.load(response))
    except (OSError, ValueError):
        return False


def _launch_runner(udid: str, port: int, force: bool = False) -> None:
    if not force and _runner_ready(port):
        return
    subprocess.run([sys.executable, "-m", "copyapp.ictrl_runner_launch", udid],
                   cwd=ROOT, capture_output=True, check=True, timeout=35)
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if _runner_ready(port):
            return
        time.sleep(0.4)
    raise TimeoutError("iCTRL runner did not answer /whoami; check Developer Disk Image and notification permission")


def _paired_health(port: int, client: Path) -> bool:
    try:
        ICtrlClient(port=port, client=client).call_ui("logs", {"max_elements": 1})
        return True
    except Exception:
        return False


def _pair(port: int, client: Path) -> None:
    process = subprocess.Popen([str(client), "--host", f"127.0.0.1:{port}",
                                "pair", "--name", "Copy APP"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert process.stderr is not None
        readable, _, _ = select.select([process.stderr], [], [], 5)
        if readable:
            first = process.stderr.readline()
            match = re.fullmatch(
                r"key fingerprint: ([0-9a-fA-F]{8})  \(verify it matches the on-device prompt\)\n?",
                first)
            if match:
                print(f"iCTRL pairing fingerprint: {match.group(1)}; approve the matching prompt on the iPhone.",
                      flush=True)
            else:
                print("Approve the iCTRL pairing prompt on the iPhone.", flush=True)
        else:
            print("Approve the iCTRL pairing prompt on the iPhone.", flush=True)
        # Keep stdout private: upstream prints the new token identifier there.
        process.communicate(timeout=75)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise TimeoutError("iCTRL pairing timed out; inspect the phone prompt before retrying") from exc
    if process.returncode:
        # Pairing output may contain a token. Keep it out of case files and errors.
        raise RuntimeError("iCTRL pairing was not approved or completed; approve the phone prompt and rerun setup")
    if not _paired_health(port, client):
        raise RuntimeError("pair command completed but authenticated iCTRL health failed")


def _record(output: Path, state: Dict[str, Any]) -> None:
    report = output / "setup.json"
    report.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    records = [{"id": "setup", "path": "setup.json", "kind": "json",
                "sha256": _hash(report)}]
    for relative, kind in (("iCTRLUITests-Runner.ipa", "ipa"),
                           ("install/install.json", "json"),
                           ("xcuitest.log", "text")):
        path = output / relative
        if path.is_file():
            records.append({"id": relative.replace("/", "-"), "path": relative,
                            "kind": kind, "sha256": _hash(path)})
    manifest = {"schema_version": 1, "kind": "ictrl_setup", "status": state["status"],
                "device_id_sha256_prefix": hashlib.sha256(state["device_id"].encode()).hexdigest()[:16],
                "evidence": records}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def setup_ictrl(udid: str, output: Path, ssh_port: int = 22222,
                ssh_identity: Path = Path("cases/ssh/id_ed25519"),
                ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
                runner_ipa: Optional[Path] = None, reinstall: bool = False,
                auto_approve_first_pair: bool = False) -> Tuple[Path, bool]:
    if not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid):
        raise ValueError("invalid device UDID")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    state: Dict[str, Any] = {"schema_version": 1, "status": "failed", "device_id": udid,
                             "started_at": _now(), "upstream_revision": REVISION, "stages": []}
    try:
        device = asyncio.run(_device(udid))
        ios_version = device["ProductVersion"]
        state["device"] = device
        state["stages"].append("usb_identity_verified")
        client = _build_client()
        state["client_sha256"] = _hash(client)
        state["stages"].append("client_built_and_selftested")
        supplied = runner_ipa.resolve(strict=True) if runner_ipa else None
        if supplied:
            bundle, supplied_minimum = _bundle_from_ipa(supplied)
            if _version(supplied_minimum) > _version(ios_version):
                raise RuntimeError(f"runner needs iOS {supplied_minimum}, device has {ios_version}")
        else:
            bundle = configured_ictrl_runner_bundle(udid)
        previous_bundle = configured_ictrl_runner_bundle(udid)
        installed = asyncio.run(_installed_app(udid, bundle)) if bundle else {}
        was_installed = bool(installed)
        runner_installed_now = not installed or reinstall
        if runner_installed_now:
            if supplied:
                ipa = output / "iCTRLUITests-Runner.ipa"
                if supplied != ipa.resolve():
                    shutil.copy2(supplied, ipa)
            else:
                ipa = _build_runner(ios_version, output / "iCTRLUITests-Runner.ipa")
            bundle, minimum = _bundle_from_ipa(ipa)
            if _version(minimum) > _version(ios_version):
                raise RuntimeError(f"runner needs iOS {minimum}, device has {ios_version}")
            state["runner_ipa_sha256"] = _hash(ipa)
            state["runner_minimum_ios"] = minimum
            state["runner_bundle_id"] = bundle
            state["stages"].append("runner_built_or_supplied")
            try:
                asyncio.run(_install_usb_ipa(udid, ipa))
                state["stages"].append("runner_usb_installed")
            except Exception as usb_exc:
                if not ssh_identity.is_file() or not ssh_known_hosts.is_file():
                    raise RuntimeError("USB installation failed (" +
                                       f"{type(usb_exc).__name__}: {str(usb_exc)[:180]}); " +
                                       "TrollStore fallback needs an SSH identity and pinned host key") from usb_exc
                with _usb_forward(udid, 22, ssh_port, reuse_existing=True):
                    install_trollstore_ipa(udid, ipa, output / "install", ssh_port,
                                           ssh_identity, ssh_known_hosts)
                state["stages"].append("runner_trollstore_installed")
            installed = asyncio.run(_installed_app(udid, bundle))
            if not installed:
                raise RuntimeError("runner is absent after installation")
            if previous_bundle and (previous_bundle != bundle or reinstall):
                asyncio.run(_stop_runner(udid, previous_bundle))
                state["stages"].append("previous_runner_stopped")
            _save_bundle(udid, bundle)
            state["stages"].append("runner_migrated" if previous_bundle and previous_bundle != bundle
                                   else "runner_reinstalled" if was_installed else "runner_installed")
        else:
            state["runner_bundle_id"] = bundle
            state["stages"].append("runner_already_installed")
            if previous_bundle != bundle:
                _save_bundle(udid, bundle)
                state["stages"].append("runner_registered")
        with _usb_forward(udid, 8200) as port:
            native_test = (_version(ios_version)[0] >= 17 and
                           (runner_installed_now or not _runner_ready(port)))
            runner_session = (ictrl_xcuitest_session(udid, bundle, output / "xcuitest.log",
                                                    auto_approve_first_pair) if native_test
                              else nullcontext(None))
            with runner_session as test_process:
                if test_process is None:
                    _launch_runner(udid, port, force=runner_installed_now)
                else:
                    state["stages"].append("xcuitest_session_started")
                    deadline = time.monotonic() + 65
                    while time.monotonic() < deadline:
                        if _runner_ready(port):
                            break
                        if test_process.poll() is not None:
                            raise RuntimeError("iCTRL XCTest session exited before /whoami was reachable")
                        time.sleep(0.4)
                    else:
                        raise TimeoutError("iCTRL XCTest session did not expose /whoami")
                state["stages"].append("runner_reachable")
                if not _paired_health(port, client):
                    _pair(port, client)
                    state["stages"].append("pairing_approved")
                state["stages"].append("authenticated_health_passed")
        state["status"] = "ready"
    except Exception as exc:
        state["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
    finally:
        state["finished_at"] = _now()
        _record(output, state)
    return output / "setup.json", state["status"] == "ready"
