"""First collector identity observation without claiming ChatComputer readiness."""

import shutil
from pathlib import Path
from uuid import UUID

from copyapp.macos.bridge import Collector
from copyapp.macos.case import Case, digest
from copyapp.macos.environment import VM_FILES
from copyapp.macos.observation import validate_reply
from copyapp.macos.report import read, text


def probe_record(root: Path, vm_directory: str) -> dict:
    from copyapp.verify import verify_case
    build = root / "collector-build"
    if not verify_case(build) or read(build, "manifest.json").get("kind") != "mac_collector_build":
        raise ValueError("a verified collector build is required")
    metadata = read(build, "collector-build.json")
    spec = read(root / "vm", "spec.json")
    UUID(spec["id"])
    first, second = read(root, "health-1.json"), read(root, "health-2.json")
    guest_id = first["response"]["guest_machine_id"]
    UUID(guest_id)
    environment = {"collector_sha256": metadata["executable_sha256"], "guest_machine_id": guest_id}
    instance = first["response"]["collector_instance"]
    for value in (first, second):
        if (not validate_reply(value, environment, "health", instance) or value["request"]["params"] != {} or
                value["request"]["session_id"] != first["request"]["session_id"]):
            raise ValueError("collector health responses differ in source, instance or session")
        result = value["response"]["result"]
        text(result["os_version"])
        if (result["guest_machine_id"] != guest_id or type(result["accessibility_granted"]) is not bool or
                type(result["pid"]) is not int or not 0 < result["pid"] <= 0x7fffffff or
                result["capabilities"] != metadata["self_test"]["methods"]):
            raise ValueError("collector health does not match its verified build")
    before, after = first["response"]["result"], second["response"]["result"]
    if (first["request"]["request_id"] == second["request"]["request_id"] or
            any(before.get(key) != after.get(key) for key in ("pid", "os_version", "install_root", "accessibility_granted"))):
        raise ValueError("collector changed across the two fresh observations")
    return {"schema_version": 2, "platform": "macos", "scope": "shared_collector_identity_probe",
            "vm_directory": vm_directory, "vm_id": spec["id"], "setup_stage": spec["stage"],
            "public_vm_files": {name: digest(root / "vm" / name) for name in VM_FILES},
            "collector_build_manifest_sha256": digest(build / "manifest.json"),
            "collector_sha256": metadata["executable_sha256"], "guest_machine_id": guest_id,
            "guest_machine_id_binding": "first_observed_on_this_shared_root", "guest_os": before["os_version"],
            "accessibility_granted": before["accessibility_granted"],
            "chatcomputer_transport_verified": False, "desktop_control_verified": False,
            "app_behavior_verified": False, "complete_environment_acceptance": False}


def probe_collector(vm: Path, build: Path, output: Path, timeout: float = 30) -> Path:
    from copyapp.verify import verify_case
    vm, build = vm.resolve(strict=True), build.resolve(strict=True)
    if any(output.resolve() == path or path in output.resolve().parents for path in (vm, build)):
        raise ValueError("probe must be outside the VM and build")
    if not verify_case(build) or read(build, "manifest.json").get("kind") != "mac_collector_build":
        raise ValueError("a verified collector build is required")
    case = Case(output, "mac_collector_probe")
    try:
        for name in VM_FILES:
            path = vm / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1 << 20:
                raise ValueError("invalid public VM identity file")
            case.add("vm/" + name, path.read_bytes(), binary=True)
        shutil.copytree(build, case.root / "collector-build", symlinks=True)
        case.record("collector-build/manifest.json")
        shared = vm / "Shared"
        if any(not path.is_dir() or path.resolve() != path for path in (shared, shared / "inbox", shared / "outbox")):
            raise ValueError("guest shared root is linked")
        with Collector(shared, read(build, "collector-build.json")["executable_sha256"], timeout) as collector:
            case.add("health-1.json", collector.call("health"))
            case.add("health-2.json", collector.call("health"))
        record = probe_record(case.root, str(vm))
        if any(digest(vm / name) != record["public_vm_files"][name] for name in VM_FILES):
            raise ValueError("VM identity/configuration changed during probe")
        case.add("probe.json", record)
        case.finish("complete", scope="shared_collector_identity_probe")
        if not verify_case(case.root): raise ValueError("probe source consistency failed")
        return case.root
    except BaseException as exc:
        if isinstance(getattr(exc, "collector_evidence", None), dict): case.add("failed-collector.json", exc.collector_evidence)
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="shared_collector_identity_probe")
        raise


def validate_probe(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "shared_collector_identity_probe" or
            not {"probe.json", "collector-build/manifest.json", "health-1.json", "health-2.json",
                 *{"vm/" + name for name in VM_FILES}}.issubset(names)):
        return False
    saved = read(root, "probe.json")
    return Path(saved["vm_directory"]).is_absolute() and saved == probe_record(root, saved["vm_directory"])
