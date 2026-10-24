"""Explicit jailbreak preparation for host-only IPA recovery; never log secrets."""

import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import secrets
import shlex
import shutil
import subprocess
import sys
from typing import Optional

from copyapp.fairplay_sources import CREDENTIAL_SOURCES, FAIRPLAY_REVISION
from copyapp.ios_cases import read_json, require_separate_trees, seal_case, write_json
from copyapp.ios_packages import verified_package
from copyapp.source_root import source_root
from copyapp.ssh_acquire import _ssh_argv
from copyapp.usb_tunnel import exact_ssh_tunnel
from copyapp.verify import sha256_file, verify_case


DEVICE_FILES = ("credential.ios", "driver.ios", "trigger.ios",
                "static-key-table.bin", "core4-word-table.bin")
ERRORS = {"tool_unavailable_or_modified", "tool_build_failed", "dependency_unavailable",
          "credential_store_unavailable", "device_unavailable", "ssh_unavailable",
          "device_identity_mismatch", "installed_app_mismatch", "unsupported_license",
          "package_account_mismatch", "daemon_restart_failed", "observation_failed",
          "retrieval_failed", "credential_validation_failed", "cleanup_failed", "interrupted"}
STAGES = ("native_identity_verified", "installed_license_supported", "account_matches_package",
          "fairplay_observation_complete", "credential_matches_installed_license",
          "credential_matches_package_license", "remote_cleanup_complete", "credential_saved")


class RetrievalError(RuntimeError):
    """A fixed diagnostic code, with no raw SSH, account or path output."""


def apply_credential_ssh_profile(args, argv: list) -> None:
    """New CLI defaults follow COPYAPP_SOURCE_ROOT even outside the checkout."""
    from copyapp.ssh_profile import apply_ssh_profile
    root = source_root()
    apply_ssh_profile(args, argv, root / "cases/ssh/profiles.json")
    for name in ("ssh_identity", "ssh_known_hosts"):
        flag = "--" + name.replace("_", "-")
        if not any(value == flag or value.startswith(flag + "=") for value in argv):
            setattr(args, name, root / getattr(args, name))


def _check_store(store: Path, alias: str, output: Path) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", alias):
        raise ValueError("credential reference must be an opaque local identifier")
    resolved, case = store.resolve(), output.resolve()
    if (resolved == case or resolved in case.parents or case in resolved.parents or
            store.is_symlink() or (store / (alias + ".bin")).exists() or
            (store / (alias + ".bin")).is_symlink()):
        raise RetrievalError("credential_store_unavailable")


def _save_credential(store: Path, alias: str, credential: bytes) -> None:
    if len(credential) != 16:
        raise RetrievalError("credential_validation_failed")
    store.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = os.open(store, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created = False
    try:
        os.fchmod(directory, 0o700)
        descriptor = os.open(alias + ".bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW, 0o600, dir_fd=directory)
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(credential)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if created:
            os.unlink(alias + ".bin", dir_fd=directory)
        raise
    finally:
        os.close(directory)


def _prepare_tool(source: Path, output: Path) -> dict:
    # Copy only reviewed bytes; never execute existing build products or extra files.
    for name, expected in CREDENTIAL_SOURCES.items():
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise RetrievalError("tool_unavailable_or_modified")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RetrievalError("tool_unavailable_or_modified")
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    try:
        result = subprocess.run(["make", "-rR", "-C", str(output / "credential-retrieval")],
                                capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise RetrievalError("tool_build_failed") from None
    if result.returncode:
        raise RetrievalError("tool_build_failed")
    bundle = output / "credential-retrieval/build/bundle"
    return {"revision": FAIRPLAY_REVISION, "sources": dict(CREDENTIAL_SOURCES),
            "helpers": {name: sha256_file(bundle / name) for name in DEVICE_FILES}}


@contextmanager
def _modules(tool: Path):
    """Load verified upstream modules without depending on cwd or stale imports."""
    saved = {name: sys.modules.get(name) for name in
             ("native_ssh", "_copyapp_fp_retrieve", "_copyapp_fp_core")}
    bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # dataclasses resolves annotations here
        spec.loader.exec_module(module)
        return module
    try:
        load("native_ssh", tool / "credential-retrieval/native_ssh.py")
        retrieve = load("_copyapp_fp_retrieve", tool / "credential-retrieval/retrieve.py")
        core = load("_copyapp_fp_core", tool / "core.py")
        yield retrieve, core
    finally:
        sys.dont_write_bytecode = bytecode
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


async def _target(udid: str, bundle: str) -> tuple:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise RetrievalError("device_identity_mismatch")
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle])
        app = apps.get(bundle, {})
        if app.get("CFBundleIdentifier") != bundle:
            raise RetrievalError("installed_app_mismatch")
        return ({key: values.get(key) for key in ("ProductType", "ProductVersion", "BuildVersion")}, app)
    finally:
        await device.close()


class CredentialDevice:
    """Pinned exact-device SSH, with physical paths for RootHide native helpers."""

    def __init__(self, command: list):
        self.command = command
        self.directories = []
        root = self.run("if command -v jbroot >/dev/null 2>&1; then jbroot /var/tmp; fi").decode().strip()
        if root and not re.fullmatch(r"/[A-Za-z0-9_./-]+", root):
            raise RetrievalError("ssh_unavailable")
        self.roothide = bool(root)
        self.ps = "/rootfs/bin/ps" if root else "ps"
        self.directory = (root or "/var/tmp") + "/fp-retrieve-" + secrets.token_hex(8)
        self.trigger_directory = (root or "/var/tmp") + "/fp-trigger-" + secrets.token_hex(8)
        try:
            for path, mode in ((self.directory, "700"), (self.trigger_directory, "755")):
                self.run("mkdir -m " + mode + " " + shlex.quote(path))
                self.directories.append(path)
        except BaseException:
            self.cleanup()
            raise

    def run(self, command: str, data: Optional[bytes] = None) -> bytes:
        result = subprocess.run(self.command + [command], input=data, capture_output=True, timeout=120)
        if result.returncode:
            raise RetrievalError("retrieval_failed")
        return result.stdout

    def processes(self) -> bytes:
        return self.run(shlex.quote(self.ps) + " -e -o pid,comm")

    def path(self, name: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("invalid remote filename")
        return self.directory + "/" + name

    def write(self, name: str, data, executable: bool = False) -> str:
        path = self.path(name)
        self.run("umask 077; cat > " + shlex.quote(path),
                 data.read_bytes() if isinstance(data, Path) else data)
        if executable:
            self.run("chmod 700 " + shlex.quote(path))
        return path

    def read(self, path: str) -> bytes:
        return self.run("cat " + shlex.quote(path))

    def cleanup(self) -> None:
        if self.directories:
            self.run("rm -rf -- " + shlex.join(self.directories))
            self.directories.clear()


def _collect(device, retrieve, core, udid: str, bundle: str, app: dict,
             package: Optional[Path], member: Optional[str], record: dict) -> bytes:
    stages = record["stages"]
    for name in DEVICE_FILES:
        device.write(name, retrieve.BUNDLE / name, executable=name.endswith(".ios"))
    program = device.path("credential.ios")
    identity = device.path("device-udid.bin")
    device.run(shlex.join([program, "device-udid", identity]))
    if device.read(identity) != retrieve.fairplay_device_id(udid):
        raise RetrievalError("device_identity_mismatch")
    stages["native_identity_verified"] = True
    path = app.get("Path")
    if (not isinstance(path, str) or not path.startswith("/") or
            ".." in PurePosixPath(path).parts or not path.endswith(".app")):
        raise RetrievalError("installed_app_mismatch")
    info = plistlib.loads(device.read(str(PurePosixPath(path) / "Info.plist")))
    executable = info.get("CFBundleExecutable", "")
    if (info.get("CFBundleIdentifier") != bundle or
            any(info.get(key) != app.get(key) for key in
                ("CFBundleVersion", "CFBundleShortVersionString", "CFBundleExecutable")) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", executable)):
        raise RetrievalError("installed_app_mismatch")
    license_data = device.read(str(PurePosixPath(path) / "SC_Info" / (executable + ".sinf")))
    if len(license_data) > retrieve.MAX_SINF_BYTES or not retrieve.supported_sinf(license_data):
        raise RetrievalError("unsupported_license")
    stages["installed_license_supported"] = True
    selected_license = license_data
    if package is not None:
        try:
            selected_license = retrieve.license_sinf(None, package / "input.ipa", member)
        except ValueError:
            raise RetrievalError("unsupported_license") from None
        if retrieve.sinf_field(license_data, b"user") != retrieve.sinf_field(selected_license, b"user"):
            raise RetrievalError("package_account_mismatch")
        stages["account_matches_package"] = True
    remote_license = device.write("license.sinf", selected_license)
    device.run("cp -R " + shlex.quote(path) + " " + shlex.quote(device.trigger_directory))
    trigger = str(PurePosixPath(device.trigger_directory) / PurePosixPath(path).name / executable)
    uid_layer = device.path("uid-layer.bin")
    record["error"] = "daemon_restart_failed"
    pid = retrieve.restart_fairplayd(device)
    record["error"] = "observation_failed"
    retrieve.observe_uid_layer(device, program, pid, uid_layer, device.path("trigger.ios"), trigger)
    stages["fairplay_observation_complete"] = True
    record["error"] = "retrieval_failed"
    remote_output = device.path("credential.bin")
    device.run(shlex.join([program, "retrieve", remote_license, uid_layer, remote_output]))
    credential = device.read(remote_output)
    record["error"] = "credential_validation_failed"
    core.derive_work16(credential, license_data)
    stages["credential_matches_installed_license"] = True
    if package is not None:
        core.derive_work16(credential, selected_license)
        stages["credential_matches_package_license"] = True
    return credential


def retrieve_credential(udid: str, bundle: str, alias: str, output: Path,
                        tool_dir: Optional[Path] = None, store: Optional[Path] = None,
                        package: Optional[Path] = None, sinf_member: Optional[str] = None,
                        ssh_port: int = 22222, ssh_identity: Path = Path("cases/ssh/id_ed25519"),
                        ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
                        ssh_user: str = "mobile") -> tuple:
    if (not re.fullmatch(r"(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{8}-[A-Fa-f0-9]{16})", udid) or
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", alias) or
            not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", bundle) or
            ssh_user not in ("mobile", "root") or not 1 <= ssh_port <= 65535 or
            (sinf_member is not None and package is None)):
        raise ValueError("invalid credential retrieval arguments")
    if package is not None:
        require_separate_trees(package, output)
    if output.exists():
        raise ValueError("credential retrieval output must be new")
    output.mkdir(parents=True)
    record = {"status": "failed", "device_id": udid, "bundle_id": bundle,
              "credential_ref": alias, "ssh_user": ssh_user, "stages": {key: False for key in STAGES},
              "error": "credential_store_unavailable"}
    try:
        store = store if store is not None else source_root() / "cases/credentials/fairplay"
        _check_store(store, alias, output)
        if package is not None:
            record["error"] = "unsupported_license"
            index = verified_package(package)
            if index["bundle_id"] != bundle:
                raise RetrievalError("installed_app_mismatch")
            shutil.copytree(package, output / "package")
            package = output / "package"
        record["package_selected"] = package is not None
        record["error"] = "tool_unavailable_or_modified"
        source = tool_dir if tool_dir is not None else source_root() / "toolchains/fairplay-decrypt-src"
        record["tool"] = _prepare_tool(source, output / "tool")
        record["error"] = "dependency_unavailable"
        with _modules(output / "tool") as (retrieve, core):
            record["error"] = "device_unavailable"
            system, app = asyncio.run(_target(udid, bundle))
            record["system"] = system
            record["app"] = {key: app.get(key) for key in
                             ("CFBundleShortVersionString", "CFBundleVersion", "CFBundleExecutable")}
            record["error"] = "ssh_unavailable"
            with exact_ssh_tunnel(udid, ssh_port, ssh_identity, ssh_known_hosts, ssh_user) as port:
                device = CredentialDevice(_ssh_argv(port, ssh_identity, ssh_known_hosts, ssh_user))
                record["route"] = "roothide_ssh" if device.roothide else "native_ssh"
                try:
                    record["error"] = "retrieval_failed"
                    credential = _collect(device, retrieve, core, udid, bundle, app,
                                          package, sinf_member, record)
                finally:
                    try:
                        device.cleanup()
                        record["stages"]["remote_cleanup_complete"] = True
                    except Exception:
                        raise RetrievalError("cleanup_failed") from None
        record["error"] = "credential_store_unavailable"
        _save_credential(store, alias, credential)
        record["stages"]["credential_saved"] = True
        record["status"] = "complete"
        record.pop("error")
    except (Exception, KeyboardInterrupt) as error:
        if isinstance(error, RetrievalError) and str(error) in ERRORS:
            record["error"] = str(error)
        elif isinstance(error, KeyboardInterrupt):
            record["error"] = "interrupted"
        # Raw exception/output may include account fields or private paths. Omit it.
    write_json(output / "retrieval.json", record)
    (output / "report.md").write_text(
        "# FairPlay credential preparation\n\n"
        f"Status: `{record['status']}`. App: `{bundle}`. Local alias: `{alias}`.\n\n"
        "A successful credential is stored separately with mode 0600 under a private 0700 directory. "
        "It is never copied into this case or represented by a content hash. "
        "The saved stage results record native device identity, supported license, SINF decoding "
        "and remote cleanup; case verification checks provenance and record consistency, "
        "without rereading the credential or certifying arbitrary-device support.\n" +
        (f"\nFailure: `{record['error']}`.\n" if record.get("error") else ""), encoding="utf-8")
    seal_case(output, "ios_fairplay_credential", status=record["status"], bundle_id=bundle)
    return output / "report.md", record["status"] == "complete"


def validate_credential_case(root: Path, manifest: dict) -> bool:
    record = read_json(root / "retrieval.json")
    allowed = {"status", "device_id", "bundle_id", "credential_ref", "ssh_user", "stages",
               "error", "package_selected", "tool", "system", "app", "route"}
    if (set(record) - allowed or manifest.get("status") != record.get("status") or
            manifest.get("bundle_id") != record.get("bundle_id") or
            record.get("ssh_user") not in ("mobile", "root") or
            not re.fullmatch(r"(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{8}-[A-Fa-f0-9]{16})", record.get("device_id", "")) or
            not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", record.get("bundle_id", "")) or
            not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", record.get("credential_ref", "")) or
            set(record.get("stages", {})) != set(STAGES) or
            any(type(value) is not bool for value in record["stages"].values())):
        return False
    allowed_paths = {"retrieval.json", "report.md", "manifest.json"}
    public_tool_paths = set(CREDENTIAL_SOURCES) | {
        "credential-retrieval/build/" + name for name in DEVICE_FILES if name.endswith(".ios")}
    public_tool_paths |= {"credential-retrieval/build/bundle/" + name for name in DEVICE_FILES}
    for path in root.rglob("*"):
        if path.is_file() and str(path.relative_to(root)) not in allowed_paths:
            relative = path.relative_to(root)
            if relative.parts[0] == "tool":
                if str(relative.relative_to("tool")) not in public_tool_paths:
                    return False
            elif relative.parts[0] != "package":
                return False
    tool = record.get("tool")
    if tool is not None:
        if (set(tool) != {"revision", "sources", "helpers"} or
                tool["revision"] != FAIRPLAY_REVISION or tool["sources"] != CREDENTIAL_SOURCES or
                set(tool["helpers"]) != set(DEVICE_FILES)):
            return False
        for name, expected in CREDENTIAL_SOURCES.items():
            if sha256_file(root / "tool" / name) != expected:
                return False
        for name, expected in tool["helpers"].items():
            if sha256_file(root / "tool/credential-retrieval/build/bundle" / name) != expected:
                return False
    if record.get("package_selected"):
        if not verify_case(root / "package"):
            return False
        if read_json(root / "package/package-index.json")["bundle_id"] != record["bundle_id"]:
            return False
    if record.get("status") == "complete":
        required = set(STAGES) - {"account_matches_package", "credential_matches_package_license"}
        if record.get("package_selected"):
            required = set(STAGES)
        return ("error" not in record and tool is not None and
                record.get("route") in ("roothide_ssh", "native_ssh") and
                set(record.get("system", {})) == {"ProductType", "ProductVersion", "BuildVersion"} and
                set(record.get("app", {})) == {"CFBundleShortVersionString", "CFBundleVersion", "CFBundleExecutable"} and
                all(record["stages"][key] for key in required))
    return (record.get("status") == "failed" and record.get("error") in ERRORS and
            record["stages"]["credential_saved"] is False)
