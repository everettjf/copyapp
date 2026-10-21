"""ChatComputer-owned snapshots with bounded public metadata and fresh sessions.

Copy APP never swaps VM disks, reads pairing secrets, deletes snapshots or
restores without the upstream safety snapshot. Metadata is not a disk hash.
"""

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from copyapp.macos.bridge import Collector
from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.chatcomputer import ChatComputer, UnknownCompletion
from copyapp.macos.doctor import executable_facts
from copyapp.macos.environment import VM_FILES, vm_identity
from copyapp.macos.observation import validate_reply
from copyapp.macos.report import read, text


def uid(value):
    result = str(UUID(value))
    if value.lower() != result:
        raise ValueError("expected a canonical UUID spelling")
    return result


def public_json(path: Path):
    if path.is_symlink() or not path.is_file() or path.resolve() != path or path.stat().st_size > 1 << 20:
        raise ValueError("snapshot metadata must be a bounded nonlinked JSON file")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    stamp = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if stamp(before) != stamp(after) or len(data) != before.st_size:
        raise ValueError("snapshot metadata changed during inspection")
    import json
    return json.loads(data)


def validate_metadata(value: dict):
    required = {"id", "name", "kind", "createdAt", "isProtected", "overlayCount", "hasThumbnail"}
    if (not isinstance(value, dict) or not required.issubset(value) or
            not set(value).issubset(required | {"parentID", "memoryBytes"}) or
            value["kind"] not in {"initial", "manual", "safety"} or
            type(value["isProtected"]) is not bool or type(value["hasThumbnail"]) is not bool or
            type(value["overlayCount"]) is not int or not 1 <= value["overlayCount"] <= 32):
        raise ValueError("unsupported snapshot metadata schema")
    uid(value["id"]); text(value["name"])
    if len(value["name"]) > 1024 or "\0" in value["name"]:
        raise ValueError("snapshot name exceeds the bound")
    date = datetime.fromisoformat(value["createdAt"].replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("snapshot creation time lacks a timezone")
    if value.get("parentID") is not None: uid(value["parentID"])
    if value.get("memoryBytes") is not None and (type(value["memoryBytes"]) is not int or not 0 <= value["memoryBytes"] <= 1 << 40):
        raise ValueError("snapshot memory metadata exceeds the bound")


def validate_catalog(value: dict):
    if (not isinstance(value, dict) or set(value) != {"snapshots", "state", "current_id", "snapshot_directory_present",
                                                    "incomplete_directories", "restore_in_progress"} or
            type(value["snapshot_directory_present"]) is not bool or type(value["restore_in_progress"]) is not bool or
            not isinstance(value["snapshots"], list) or len(value["snapshots"]) > 512 or
            not isinstance(value["incomplete_directories"], list) or len(value["incomplete_directories"]) > 1024):
        raise ValueError("invalid bounded snapshot catalog")
    identifiers = []
    for row in value["snapshots"]:
        validate_metadata(row)
        identifiers.append(uid(row["id"]))
    if identifiers != sorted(set(identifiers)):
        raise ValueError("snapshot IDs are duplicated or unsorted")
    state = value["state"]
    if state is not None and (not isinstance(state, dict) or not set(state).issubset({"currentID"})):
        raise ValueError("invalid snapshot state metadata")
    current = uid(state["currentID"]) if state and state.get("currentID") is not None else None
    if value["current_id"] != current:
        raise ValueError("snapshot current ID differs from saved state")
    incomplete = value["incomplete_directories"]
    if (any(not isinstance(name, str) or not name or len(name) > 255 or "/" in name or "\0" in name for name in incomplete) or
            incomplete != sorted(set(incomplete)) or
            (not value["snapshot_directory_present"] and (state is not None or identifiers or incomplete or value["restore_in_progress"]))):
        raise ValueError("invalid incomplete snapshot directory record")


def catalog(vm: Path) -> dict:
    root = vm / "Snapshots"
    value = {"snapshots": [], "state": None, "current_id": None, "snapshot_directory_present": root.exists(),
             "incomplete_directories": [], "restore_in_progress": False}
    if root.is_symlink():
        raise ValueError("snapshot root is linked")
    if not root.exists(): return value
    if not root.is_dir() or root.resolve() != root:
        raise ValueError("snapshot root is not a canonical directory")
    paths = sorted(root.iterdir())
    observed = []

    def read_metadata(path):
        result = public_json(path)
        observed.append((path, result))
        return result
    if len(paths) > 1024:
        raise ValueError("snapshot directory count exceeds the bound")
    for path in paths:
        if path.name == "state.json":
            value["state"] = read_metadata(path)
        elif path.name == ".restore":
            value["restore_in_progress"] = True
        elif path.name.startswith(".staging-"):
            value["incomplete_directories"].append(path.name)
        else:
            try: snapshot_id = uid(path.name)
            except ValueError: continue
            if path.is_symlink() or not path.is_dir() or not (path / "snapshot.json").exists():
                value["incomplete_directories"].append(path.name)
                continue
            row = read_metadata(path / "snapshot.json")
            validate_metadata(row)
            if uid(row["id"]) != snapshot_id:
                raise ValueError("snapshot directory and metadata IDs differ")
            value["snapshots"].append(row)
    value["snapshots"].sort(key=lambda row: uid(row["id"]))
    state = value["state"]
    value["current_id"] = uid(state["currentID"]) if state and state.get("currentID") is not None else None
    validate_catalog(value)
    # A concurrent upstream capture is not silently accepted as one observation.
    if ([path.name for path in paths] != sorted(path.name for path in root.iterdir()) or
            any(public_json(path) != value for path, value in observed)):
        raise ValueError("snapshot catalog changed during inspection")
    return value


def quiet_catalog(value: dict):
    validate_catalog(value)
    ids = {uid(row["id"]) for row in value["snapshots"]}
    if (value["incomplete_directories"] or value["restore_in_progress"] or (value["current_id"] and value["current_id"] not in ids) or
            any(row.get("parentID") is not None and uid(row["parentID"]) not in ids for row in value["snapshots"])):
        raise ValueError("snapshot metadata needs inspection; no take/restore was requested")


def inventory_record(root: Path, vm: str) -> dict:
    spec = read(root / "vm", "spec.json")
    uid(spec["id"])
    value = read(root, "catalog.json")
    validate_catalog(value)
    return {"schema_version": 2, "platform": "macos", "scope": "snapshot_public_metadata_only",
            "vm_directory": vm, "vm_id": uid(spec["id"]), "setup_stage": spec["stage"],
            "public_vm_files": {name: digest(root / "vm" / name) for name in VM_FILES},
            "snapshot_count": len(value["snapshots"]), "current_id": value["current_id"],
            "disk_or_memory_bytes_verified": False, "guest_runtime_identity_verified": False}


def snapshot_inventory(vm: Path, output: Path) -> Path:
    vm = vm.resolve(strict=True)
    if output.resolve() == vm or vm in output.resolve().parents:
        raise ValueError("inventory case must be outside the VM")
    case = Case(output, "mac_snapshot_inventory")
    try:
        for name in VM_FILES:
            path = vm / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1 << 20:
                raise ValueError("invalid bounded public VM file")
            case.add("vm/" + name, path.read_bytes(), binary=True)
        case.add("catalog.json", catalog(vm))
        case.add("inventory.json", inventory_record(case.root, str(vm)))
        case.finish("complete", scope="snapshot_public_metadata_only")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="snapshot_public_metadata_only")
        raise


def validate_inventory(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "snapshot_public_metadata_only" or
            not {"inventory.json", "catalog.json", *{"vm/" + name for name in VM_FILES}}.issubset(names)):
        return False
    saved = read(root, "inventory.json")
    return Path(saved["vm_directory"]).is_absolute() and saved == inventory_record(root, saved["vm_directory"])


def pinned_environment(record: dict) -> Path:
    vm = Path(record["vm_directory"])
    if vm_identity(vm) != record["vm"] or executable_facts(record["chatcomputer"]["path"]) != record["chatcomputer"]:
        raise ValueError("VM configuration or ChatComputer build changed; review a new registration")
    return vm


def health_matches(health: dict, record: dict):
    if not validate_reply(health, record, "health"):
        raise ValueError("collector health is not bound to this environment")
    guest = health["response"]["result"]
    if guest.get("os_version") != record["guest_os"] or guest.get("install_root") != record.get("install_root"):
        raise ValueError("guest OS/user install root changed across snapshot operation")


def traced(case: Case, name: str, computer, tool: str, arguments=None):
    result = computer.call(tool, arguments)
    case.add(name, computer.evidence())
    return result


def phase(case: Case, prefix: str, computer, collector, record):
    traced(case, prefix + "/status.json", computer, "status")
    shot = traced(case, prefix + "/screenshot-rpc.json", computer, "screenshot")
    data, mime = computer.image(shot)
    case.add(prefix + ("/screen.png" if mime == "image/png" else "/screen.jpg"), data, binary=True)
    health = collector.call("health")
    case.add(prefix + "/health.json", health)
    health_matches(health, record)
    return health


def check_catalog_tools(catalog: dict, action: str):
    tools = {row["name"]: row for row in catalog["tools"]}
    selected = {"move": {"x": "integer", "y": "integer"},
                "snapshot_take": {"name": "string"},
                "snapshot_restore": {"snapshot": "string", "save_current": "boolean"}}
    for name in ("move", "snapshot_" + action):
        schema = tools[name]["inputSchema"]
        if schema.get("type") != "object" or any(schema["properties"].get(key, {}).get("type") != kind
                                                   for key, kind in selected[name].items()):
            raise ValueError("installed snapshot/input MCP schema is incompatible")


def transition(before: dict, after: dict, action: str, chosen: dict = None, label: str = None) -> tuple:
    quiet_catalog(before); quiet_catalog(after)
    old = {uid(row["id"]): row for row in before["snapshots"]}
    new = {uid(row["id"]): row for row in after["snapshots"]}
    if any(key not in new or new[key] != row for key, row in old.items()):
        raise ValueError("an existing snapshot changed or disappeared during the operation")
    additions = [new[key] for key in sorted(set(new) - set(old))]
    initials = [row for row in additions if row["kind"] == "initial"]
    if initials:
        if (len(initials) != 1 or any(row["kind"] == "initial" for row in old.values()) or not initials[0]["isProtected"] or
                initials[0].get("parentID") is not None):
            raise ValueError("unexpected initial snapshot transition")
    parent = before["current_id"] or (uid(initials[0]["id"]) if initials else None)
    if action == "take":
        candidates = [row for row in additions if row["kind"] == "manual" and row["name"] == label]
        if len(candidates) != 1 or len(additions) != len(initials) + 1:
            raise ValueError("take did not produce exactly one uniquely named manual snapshot")
        chosen = candidates[0]
        safety = None
    else:
        if chosen is None or old.get(uid(chosen["id"])) != chosen:
            raise ValueError("target snapshot differs from the pinned take case")
        candidates = [row for row in additions if row["kind"] == "safety"]
        if len(candidates) != 1 or len(additions) != len(initials) + 1:
            raise ValueError("restore did not retain exactly one new safety snapshot")
        safety = candidates[0]
    child = chosen if action == "take" else safety
    if (child["isProtected"] or (uid(child["parentID"]) if child.get("parentID") is not None else None) != parent or
            after["current_id"] != uid(chosen["id"])):
        raise ValueError("snapshot ancestry or final current ID differs from the operation")
    return chosen, safety


def operation_record(environment: Path, before: dict, after: dict, first: dict, last: dict,
                     action: str, chosen: dict, safety: dict, label: str) -> dict:
    return {"schema_version": 2, "platform": "macos", "scope": "snapshot_metadata_and_reconnect",
            "operation": action, "label": label, "snapshot": chosen, "safety_snapshot": safety,
            "environment_manifest_sha256": digest(environment / "manifest.json"),
            "before_catalog_sha256": hashlib.sha256(canonical(before)).hexdigest(),
            "after_catalog_sha256": hashlib.sha256(canonical(after)).hexdigest(),
            "before_session": first["request"]["session_id"], "after_session": last["request"]["session_id"],
            "collector_instance_changed": first["response"]["collector_instance"] != last["response"]["collector_instance"],
            "takeover_guard": "preflight_input_lease_only", "atomic_takeover_exclusion_verified": False,
            "shared_data_reset": False, "behavior_restoration_verified": False,
            "disk_or_memory_bytes_verified": False, "action_retried": False}


def snapshot_operation(source: Path, output: Path, action: str, timeout: float = 120) -> Path:
    from copyapp.verify import verify_case
    source = source.resolve(strict=True)
    expected = "mac_environment" if action == "take" else "mac_snapshot_take"
    if (action not in {"take", "restore"} or not verify_case(source) or read(source, "manifest.json").get("kind") != expected or
            output.resolve() == source or source in output.resolve().parents):
        raise ValueError("take needs a verified environment; restore needs a verified Copy APP snapshot take case")
    environment = source if action == "take" else source / "environment"
    record = read(environment, "environment.json")
    vm = pinned_environment(record)
    if output.resolve() == vm or vm in output.resolve().parents:
        raise ValueError("snapshot operation evidence must be outside the VM")
    chosen = None if action == "take" else read(source, "snapshot-operation.json")["snapshot"]
    label = "copyapp-" + str(uuid4()) if action == "take" else None
    case = Case(output, "mac_snapshot_" + action)
    submitted = False
    try:
        child = "environment" if action == "take" else "snapshot"
        shutil.copytree(source, case.root / child, symlinks=True)
        case.record(child + "/manifest.json")
        saved_environment = case.root / "environment" if action == "take" else case.root / "snapshot/environment"
        with Collector(vm / "Shared", record["collector_sha256"], min(timeout, 120)) as collector:
            before = catalog(vm)
            case.add("before/catalog.json", before)
            quiet_catalog(before)
            if chosen is not None and chosen not in before["snapshots"]:
                raise ValueError("pinned snapshot metadata changed or is absent; restore was not requested")
            with ChatComputer(record["chatcomputer"]["path"], timeout, vm.parent) as computer:
                case.add("mcp-catalog.json", computer.catalog)
                check_catalog_tools(computer.catalog, action)
                first = phase(case, "before", computer, collector, record)
                traced(case, "control.json", computer, "move", {"x": 0, "y": 0})
                # A takeover already active here blocks the normal input lease.
                # Upstream snapshots have no atomic expected-lease precondition;
                # do not claim this closes a later human-takeover race.
                submitted = True
                arguments = {"name": label} if action == "take" else {"snapshot": chosen["id"], "save_current": True}
                traced(case, "operation.json", computer, "snapshot_" + action, arguments)
            # Keep the same exclusive collector lock across both the VM action
            # and this fresh protocol epoch. Old outbox files are left untouched.
            collector.new_session()
            pinned_environment(record)
            with ChatComputer(record["chatcomputer"]["path"], timeout, vm.parent) as computer:
                last = phase(case, "after", computer, collector, record)
            after = catalog(vm)
            case.add("after/catalog.json", after)
            chosen, safety = transition(before, after, action, chosen, label)
        case.add("snapshot-operation.json", operation_record(saved_environment, before, after, first, last, action, chosen, safety, label))
        case.finish("complete", scope="snapshot_metadata_and_reconnect", operation=action)
        if not verify_case(case.root):
            raise ValueError("snapshot operation evidence failed revalidation")
        return case.root
    except BaseException as exc:
        for attribute, name in (("chatcomputer_evidence", "failed-mcp.json"), ("collector_evidence", "failed-collector.json")):
            if isinstance(getattr(exc, attribute, None), dict): case.add(name, getattr(exc, attribute))
        try: case.add("failure-catalog.json", catalog(vm))
        except BaseException as inspection:
            case.add("failure-catalog-error.json", {"error": type(inspection).__name__, "message": str(inspection)})
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc),
                                  "action_submitted": submitted, "needs_inspection": True,
                                  "completion_unknown": isinstance(exc, UnknownCompletion), "action_retried": False})
        case.finish("failed", scope="snapshot_metadata_and_reconnect", operation=action)
        raise


def mcp_result(value: dict, tool: str, arguments: dict, record: dict):
    uid(value["transport_id"])
    request, reply = value["request"], value["response"]
    if (value["server_info"] != record["mcp_server_info"] or
            request.get("jsonrpc") != "2.0" or request.get("method") != "tools/call" or
            request.get("params") != {"name": tool, "arguments": arguments} or type(request.get("id")) is not int or
            reply.get("jsonrpc") != "2.0" or type(reply.get("id")) is not int or reply["id"] != request["id"] or "error" in reply):
        raise ValueError("snapshot MCP request/response binding differs")
    result = reply["result"]
    if result.get("isError", False) is not False or not isinstance(result.get("content"), list):
        raise ValueError("snapshot MCP action is incomplete or failed")
    return result


def validate_operation(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    action = manifest.get("operation")
    if action not in {"take", "restore"} or manifest.get("kind") != "mac_snapshot_" + action:
        return False
    child = "environment" if action == "take" else "snapshot"
    required = {child + "/manifest.json", "mcp-catalog.json", "before/catalog.json", "after/catalog.json", "control.json",
                "operation.json", "snapshot-operation.json", *{phase + "/" + name for phase in ("before", "after")
                    for name in ("status.json", "screenshot-rpc.json", "health.json")}}
    if (manifest.get("status") != "complete" or manifest.get("scope") != "snapshot_metadata_and_reconnect" or
            not required.issubset(names) or not verify_case(root / child)):
        return False
    if read(root / child, "manifest.json").get("kind") != ("mac_environment" if action == "take" else "mac_snapshot_take"):
        return False
    environment = root / "environment" if action == "take" else root / "snapshot/environment"
    record, saved = read(environment, "environment.json"), read(root, "snapshot-operation.json")
    check_catalog_tools(read(root, "mcp-catalog.json"), action)
    before, after = read(root, "before/catalog.json"), read(root, "after/catalog.json")
    label = saved["label"]
    if action == "take":
        if not isinstance(label, str) or not label.startswith("copyapp-"): return False
        uid(label[len("copyapp-"):])
        chosen = None
    else:
        if label is not None: return False
        chosen = read(root / "snapshot", "snapshot-operation.json")["snapshot"]
    chosen, safety = transition(before, after, action, chosen, label)
    transports, healths = [], []
    for prefix in ("before", "after"):
        status, shot = read(root, prefix + "/status.json"), read(root, prefix + "/screenshot-rpc.json")
        mcp_result(status, "status", {}, record)
        raw = mcp_result(shot, "screenshot", {}, record)
        if status["transport_id"] != shot["transport_id"]: return False
        data, mime = ChatComputer.image(raw)
        image = prefix + ("/screen.png" if mime == "image/png" else "/screen.jpg")
        if image not in names or hashlib.sha256(data).hexdigest() != digest(root / image): return False
        from PIL import Image
        import io
        with Image.open(io.BytesIO(data)) as opened: opened.verify()
        health = read(root, prefix + "/health.json")
        health_matches(health, record)
        transports.append(status["transport_id"]); healths.append(health)
    if transports[0] == transports[1] or healths[0]["request"]["session_id"] == healths[1]["request"]["session_id"]:
        return False
    control, operation = read(root, "control.json"), read(root, "operation.json")
    mcp_result(control, "move", {"x": 0, "y": 0}, record)
    arguments = {"name": label} if action == "take" else {"snapshot": chosen["id"], "save_current": True}
    mcp_result(operation, "snapshot_" + action, arguments, record)
    if any(value["transport_id"] != transports[0] for value in (control, operation)): return False
    if not (read(root, "before/status.json")["request"]["id"] < read(root, "before/screenshot-rpc.json")["request"]["id"] <
            control["request"]["id"] < operation["request"]["id"]): return False
    return saved == operation_record(environment, before, after, *healths, action, chosen, safety, label)
