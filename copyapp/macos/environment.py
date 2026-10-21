"""Register and recheck one exact ChatComputer VM without reading its secrets."""

import json
import shutil
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from copyapp.macos.bridge import Collector
from copyapp.macos.case import Case, digest
from copyapp.macos.chatcomputer import ChatComputer
from copyapp.macos.doctor import executable_facts


VM_FILES = ("spec.json", "MachineIdentifier.bin", "HardwareModel.bin")


def vm_identity(vm: Path) -> dict:
    vm = vm.resolve(strict=True)
    spec = json.loads((vm / "spec.json").read_text())
    UUID(spec["id"])
    if spec.get("stage") != "ready":
        raise ValueError("ChatComputer VM has not completed onboarding")
    if not all(type(spec.get(key)) is int and spec[key] > 0
               for key in ("displayWidth", "displayHeight", "cpuCount", "memoryBytes")):
        raise ValueError("invalid VM configuration")
    # These identify the VM and fixed test settings. Live disks, NVRAM, transient
    # state and the secrets file must not be hashed or copied as identity inputs.
    return {"vm_id": spec["id"], "machine_identifier_sha256": digest(vm / "MachineIdentifier.bin"),
            "hardware_model_sha256": digest(vm / "HardwareModel.bin"),
            "display_width": spec["displayWidth"], "display_height": spec["displayHeight"],
            "cpu_count": spec["cpuCount"], "memory_bytes": spec["memoryBytes"],
            "guest_release": spec.get("guestRelease", "27"),
            "restore_build": spec.get("restoreImageBuild")}


def register_environment(vm: Path, build: Path, output: Path,
                         executable: str = "chatcomputer", timeout: float = 30) -> Path:
    from copyapp.verify import verify_case
    vm = vm.resolve(strict=True)
    build = build.resolve(strict=True)
    destination = output.resolve()
    if any(destination == source or source in destination.parents for source in (vm, build)):
        raise ValueError("environment case must be outside the VM and collector build")
    if not verify_case(build):
        raise ValueError("collector build case is not verified")
    build_manifest = json.loads((build / "manifest.json").read_text())
    if build_manifest.get("kind") != "mac_collector_build" or build_manifest.get("status") != "complete":
        raise ValueError("a completed collector build is required")
    vm_facts = vm_identity(vm)
    tool = executable_facts(executable)
    if not tool.get("available") or tool.get("bundle_id") != "app.chatcomputer.ChatComputer":
        raise ValueError("expected the installed ChatComputer application executable")
    collector_build = json.loads((build / "collector-build.json").read_text())
    case = Case(output, "mac_environment")
    try:
        for name in VM_FILES:
            case.add("vm/" + name, (vm / name).read_bytes(), binary=True)
        # Preserve the complete verified build, allowing later inspection without
        # depending on a mutable external build directory.
        shutil.copytree(build, case.root / "collector-build", symlinks=True)
        case.record("collector-build/manifest.json")
        with ChatComputer(str(tool["path"]), timeout, vm.parent) as computer:
            status = computer.call("status")
            case.add("mcp-status.json", status)
            shot = computer.call("screenshot")
            image, mime = computer.image(shot)
            case.add("mcp-screenshot.json", shot)
            case.add("screen.png" if mime == "image/png" else "screen.jpg", image, binary=True)
            with Collector(vm / "Shared", collector_build["executable_sha256"], timeout) as collector:
                health = collector.call("health")
                case.add("collector-health.json", health)
        guest = health["response"]["result"]
        machine = guest.get("guest_machine_id")
        UUID(machine)
        record = {"schema_version": 2, "platform": "macos", "execution_environment": "chatcomputer_vm",
                  "vm_directory": str(vm), "vm": vm_facts,
                  "chatcomputer": tool, "collector_sha256": collector_build["executable_sha256"],
                  "guest_machine_id": machine, "guest_os": guest["os_version"],
                  "collector_build_manifest_sha256": digest(case.root / "collector-build/manifest.json"),
                  "scope": "environment_registration", "app_identity_ready": False}
        if isinstance(guest.get("install_root"), str):
            record["install_root"] = guest["install_root"]
        case.add("environment.json", record)
        case.finish("complete", scope="environment_registration")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="environment_registration")
        raise


def validate_environment(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    required = {"environment.json", "vm/spec.json", "vm/MachineIdentifier.bin", "vm/HardwareModel.bin",
                "collector-build/manifest.json", "collector-health.json", "mcp-status.json", "mcp-screenshot.json"}
    if (manifest.get("status") != "complete" or manifest.get("scope") != "environment_registration" or
            not required.issubset(names)):
        return False
    record = json.loads((root / "environment.json").read_text())
    build = root / "collector-build"
    metadata = json.loads((build / "collector-build.json").read_text())
    response = json.loads((root / "collector-health.json").read_text())
    request, reply = response["request"], response["response"]
    from copyapp.macos.case import canonical
    import hashlib
    if (reply.get("status") != "complete" or request.get("method") != "health" or
            reply.get("request_sha256") != hashlib.sha256(canonical(request)).hexdigest() or
            reply.get("session_id") != request.get("session_id") or
            reply.get("request_id") != request.get("request_id") or
            reply.get("collector_sha256") != record.get("collector_sha256")):
        return False
    guest = reply["result"]
    UUID(record["guest_machine_id"])
    UUID(reply["collector_instance"])
    raw = json.loads((root / "mcp-screenshot.json").read_text())
    data, mime = ChatComputer.image(raw)
    image_path = "screen.png" if mime == "image/png" else "screen.jpg"
    if image_path not in names or hashlib.sha256(data).hexdigest() != digest(root / image_path):
        return False
    from PIL import Image
    import io
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    return (record.get("schema_version") == 2 and record.get("platform") == "macos" and
            record.get("execution_environment") == "chatcomputer_vm" and
            record.get("scope") == "environment_registration" and record.get("app_identity_ready") is False and
            record.get("vm") == vm_identity(root / "vm") and
            record.get("chatcomputer", {}).get("bundle_id") == "app.chatcomputer.ChatComputer" and
            record.get("collector_build_manifest_sha256") == digest(build / "manifest.json") and
            record.get("collector_sha256") == metadata.get("executable_sha256") and
            record.get("guest_machine_id") == guest.get("guest_machine_id") == reply.get("guest_machine_id") and
            record.get("guest_os") == guest.get("os_version") and
            record.get("install_root") == guest.get("install_root") and verify_case(build))


@contextmanager
def environment_session(environment: Path, timeout: float = 30):
    """Recheck identity after every reconnect or snapshot restore."""
    from copyapp.verify import verify_case
    if not verify_case(environment):
        raise ValueError("environment case is not verified")
    manifest = json.loads((environment / "manifest.json").read_text())
    if manifest.get("kind") != "mac_environment":
        raise ValueError("expected a registered Mac environment")
    record = json.loads((environment / "environment.json").read_text())
    vm = Path(record["vm_directory"])
    if vm_identity(vm) != record["vm"]:
        raise ValueError("VM identity or test configuration changed; register a new environment")
    tool = executable_facts(record["chatcomputer"]["path"])
    if tool != record["chatcomputer"]:
        raise ValueError("ChatComputer changed; review and register the new build")
    with ChatComputer(tool["path"], timeout, vm.parent) as computer:
        with Collector(vm / "Shared", record["collector_sha256"], timeout) as collector:
            health = collector.call("health")
            guest = health["response"]["result"]
            if (guest.get("guest_machine_id") != record["guest_machine_id"] or
                    guest.get("os_version") != record["guest_os"] or guest.get("install_root") != record.get("install_root")):
                raise ValueError("collector answered from another guest or OS build")
            yield computer, collector, record, health
