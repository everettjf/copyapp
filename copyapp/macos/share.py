"""A manual guest-Finder byte probe, usable before control permissions exist."""

import hashlib
import os
import shutil
from pathlib import Path
from uuid import UUID, uuid4

from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.environment import VM_FILES
from copyapp.macos.report import read, text


def shared(vm: Path) -> Path:
    vm = vm.resolve(strict=True)
    root = vm / "Shared"
    for path in (root, root / "inbox", root / "outbox"):
        if not path.is_dir() or path.resolve(strict=True) != path:
            raise ValueError("probe requires real existing VM shared inbox/outbox directories")
    return root


def task(record: dict) -> str:
    return ("# Guest shared-file probe\n\n"
            "In this ChatComputer guest's Finder, copy the single file\n\n`/Volumes/My Shared Files/inbox/" + record["filename"] +
            "`\n\nto `/Volumes/My Shared Files/outbox/`, retaining its exact name.\n\n"
            "Copy it once, then inspect the host outbox before any new action. Do not\n"
            "execute software, grant permissions, replace files or modify App data.\n\n"
            "This probe checks byte exchange only. It does not establish collector\n"
            "identity, App identity, input lease, screenshot or snapshot acceptance.\n")


def request_record(root: Path, vm_directory: str, probe_id: str) -> dict:
    UUID(probe_id)
    spec = read(root / "vm", "spec.json")
    UUID(spec["id"])
    return {"schema_version": 2, "platform": "macos", "scope": "shared_file_request",
            "vm_directory": vm_directory, "vm_id": spec["id"], "setup_stage": spec["stage"],
            "vm_files": {name: digest(root / "vm" / name) for name in VM_FILES},
            "probe_id": probe_id, "filename": "copyapp-probe-" + probe_id + ".txt",
            "payload_sha256": digest(root / "payload.txt"), "guest_runtime_identity_verified": False}


def share_request(vm: Path, output: Path) -> Path:
    vm = vm.resolve(strict=True)
    root = shared(vm)
    if output.resolve() == vm or vm in output.resolve().parents:
        raise ValueError("probe case must be outside its VM")
    probe_id = str(uuid4())
    case = Case(output, "mac_share_request")
    try:
        for name in VM_FILES:
            path = vm / name
            if not path.is_file() or path.is_symlink() or path.stat().st_size > 1 << 20:
                raise ValueError("invalid public VM identity file")
            case.add("vm/" + name, path.read_bytes(), binary=True)
        payload = ("Copy APP shared-file probe\nnonce=" + probe_id + "\n").encode("ascii")
        case.add("payload.txt", payload, binary=True)
        record = request_record(case.root, str(vm), probe_id)
        case.add("request.json", record)
        case.add("GUEST_TASK.md", task(record).encode("utf-8"), binary=True)
        destination = root / "inbox" / record["filename"]
        if (root / "outbox" / record["filename"]).exists():
            raise FileExistsError("probe response already exists")
        temporary = destination.with_name("." + record["filename"] + ".pending")
        with temporary.open("xb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        # Atomic no-replacement publication on the host; guest interruption and
        # cache recovery remain separate live acceptance work.
        os.link(temporary, destination)
        temporary.unlink()
        if digest(destination) != record["payload_sha256"]:
            raise ValueError("published probe bytes differ")
        case.finish("complete", scope="shared_file_request")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="shared_file_request")
        raise


def share_result(request: Path, output: Path, reviewer: str, notes: str) -> Path:
    from copyapp.verify import verify_case
    request = request.resolve(strict=True)
    if not verify_case(request) or read(request, "manifest.json").get("kind") != "mac_share_request":
        raise ValueError("a verified shared-file request is required")
    if output.resolve() == request or request in output.resolve().parents:
        raise ValueError("probe result must be outside its request")
    text(reviewer); text(notes)
    record = read(request, "request.json")
    vm = Path(record["vm_directory"])
    root = shared(vm)
    if any(digest(vm / name) != record["vm_files"][name] for name in VM_FILES):
        raise ValueError("VM identity/configuration changed during probe; preserve it and review a new attempt")
    reply = root / "outbox" / record["filename"]
    if reply.is_symlink() or not reply.is_file() or reply.stat().st_size > 4096:
        raise ValueError("probe reply is absent, linked or too large")
    before = reply.stat()
    data = reply.read_bytes()
    after = reply.stat()
    if ((before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns) or
            data != (request / "payload.txt").read_bytes()):
        raise ValueError("probe reply changed or differs from the published nonce")
    case = Case(output, "mac_share_result")
    try:
        shutil.copytree(request, case.root / "request", symlinks=True)
        case.record("request/manifest.json")
        case.add("reply.txt", data, binary=True)
        case.add("result.json", {"schema_version": 2, "platform": "macos", "scope": "shared_byte_roundtrip",
                                 "request_manifest_sha256": digest(request / "manifest.json"),
                                 "payload_sha256": hashlib.sha256(data).hexdigest(),
                                 "reviewer": reviewer, "notes": notes, "transfer_actor": "guest_finder_self_declared",
                                 "guest_runtime_identity_verified": False, "complete_environment_acceptance": False})
        case.finish("complete", scope="shared_byte_roundtrip")
        if not verify_case(case.root):
            raise ValueError("copied probe evidence changed")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="shared_byte_roundtrip")
        raise


def validate_request(root: Path, manifest: dict, names: set) -> bool:
    required = {"request.json", "payload.txt", "GUEST_TASK.md", *{"vm/" + name for name in VM_FILES}}
    if manifest.get("status") != "complete" or manifest.get("scope") != "shared_file_request" or not required.issubset(names):
        return False
    saved = read(root, "request.json")
    expected = request_record(root, saved["vm_directory"], saved["probe_id"])
    payload = ("Copy APP shared-file probe\nnonce=" + saved["probe_id"] + "\n").encode("ascii")
    return (Path(saved["vm_directory"]).is_absolute() and canonical(saved) == canonical(expected) and
            (root / "payload.txt").read_bytes() == payload and (root / "GUEST_TASK.md").read_text() == task(expected))


def validate_result(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    if (manifest.get("status") != "complete" or manifest.get("scope") != "shared_byte_roundtrip" or
            not {"request/manifest.json", "reply.txt", "result.json"}.issubset(names) or
            not verify_case(root / "request") or read(root / "request", "manifest.json").get("kind") != "mac_share_request"):
        return False
    record = read(root, "result.json")
    text(record["reviewer"]); text(record["notes"])
    return (type(record.get("schema_version")) is int and record["schema_version"] == 2 and record.get("platform") == "macos" and
            record.get("scope") == "shared_byte_roundtrip" and record.get("transfer_actor") == "guest_finder_self_declared" and
            record.get("request_manifest_sha256") == digest(root / "request/manifest.json") and
            record.get("payload_sha256") == digest(root / "reply.txt") == digest(root / "request/payload.txt") and
            (root / "reply.txt").read_bytes() == (root / "request/payload.txt").read_bytes() and
            record.get("guest_runtime_identity_verified") is False and record.get("complete_environment_acceptance") is False)
