"""Replay a verified investigation at its local BLR sites without REA."""

import hashlib
import io
import json
import re
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from copyapp.flow_capture import capture_flow
from copyapp.ghidra_direct import check_direct_ghidra
from copyapp.ghidra_queue import decompile_candidate_queue
from copyapp.native_disasm import is_arm64_blr, rank_native_candidates
from copyapp.objc import MachOImage
from copyapp.report import (_validate_flow_capture, _validate_ghidra_direct_queue,
                            _validate_native_candidate_queue)
from copyapp.verify import checked_path, sha256_file, verify_case


BLR = re.compile(r"^([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s+blr\s+(x(?:[0-9]|[12][0-9]|30))\b",
                 re.MULTILINE | re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _files(root: Path) -> list:
    return [{"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
            for path in sorted(root.rglob("*"))
            if path.is_file() and path != root / "manifest.json"]


def discover_blr_sites(source: dict, native_dir: Path, native_record: dict,
                       observed: list, limit: int = 8) -> list[dict]:
    """Find bounded BLR instructions in selected observed/direct-follow functions."""
    if not 1 <= limit <= 32:
        raise ValueError("branch limit must be between 1 and 32")
    image = MachOImage(Path(source["binary_path"]).read_bytes())
    roots = {int(item["static_address"], 16) for item in observed}
    sites = []
    seen = set()
    for item in native_record.get("results", []) + native_record.get("followed", []):
        if item.get("status") != "complete":
            continue
        root = item.get("root_address", item.get("address"))
        if int(root, 16) not in roots:
            continue
        summary_path = checked_path(native_dir, item["summary"])
        summary = _read(summary_path)
        assembly = checked_path(native_dir,
                                str(Path(item["summary"]).parent / "assembly.txt"))
        start = int(summary["address"], 16)
        stop = int(summary["stop_address"], 16)
        for match in BLR.finditer(assembly.read_text(encoding="utf-8")):
            address = int(match.group(1), 16)
            register = match.group(3).lower()
            if not start <= address < stop or address < image.base:
                raise ValueError("native BLR site is outside its verified function")
            if (image.unpack("<I", address)[0] != int(match.group(2), 16) or
                    not is_arm64_blr(image, address, register)):
                raise ValueError("native BLR site differs from acquired Mach-O bytes")
            key = (address, register)
            if key in seen:
                continue
            seen.add(key)
            sites.append({"address": f"0x{address:x}",
                          "offset": address - image.base,
                          "register": register,
                          "source_address": item["address"]})
            if len(sites) > limit:
                raise ValueError("too many indirect call sites for one bounded replay")
    return sites


def follow_indirect(udid: str, investigation: Path, objc_index: Path,
                    output: Path, ghidra_dir: Path, java_home: Path,
                    function_limit: int = 4, branch_limit: int = 8,
                    timeout: int = 900,
                    disabled_analyzer: Optional[str] = None,
                    resume: bool = False) -> Tuple[Path, bool]:
    """Use one repeat playbook to resolve selected BLR targets and decompile them."""
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(f"output directory is not empty: {output}")
    target_root = output.resolve()
    source_root = investigation.resolve(strict=True)
    index_root = objc_index.resolve(strict=True)
    if (target_root == source_root or target_root in source_root.parents or
            source_root in target_root.parents or target_root == index_root or
            target_root in index_root.parents):
        raise ValueError("indirect output must be separate from source investigation")
    with redirect_stdout(io.StringIO()):
        if not verify_case(investigation):
            raise ValueError("investigation evidence hash mismatch")
    case = _read(investigation / "manifest.json")
    candidate_dir = investigation / "candidates"
    native_dir = investigation / "native"
    source = _read(candidate_dir / "candidates.json")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    binary = Path(source["binary_path"])
    digest = source["binary_sha256"]
    methods = case.get("selected_methods")
    backend = case.get("ui_backend")
    script = investigation / "flow/playbook/playbook.json"
    index = _read(objc_index)
    if (case.get("kind") != "investigated_ui_flow" or
            case.get("status") != "complete" or
            source.get("kind") != "runtime_static_candidates" or
            source.get("bundle_id") != case.get("bundle_id") or
            source.get("device_id_sha256_prefix") != prefix or
            case.get("device_id_sha256_prefix") != prefix or
            case.get("binary_sha256") != digest or
            case.get("source_script_sha256") != sha256_file(script) or
            index.get("binary_sha256") != digest or
            not binary.is_file() or sha256_file(binary) != digest or
            not isinstance(methods, list) or not methods or
            backend not in ("ios-mcp", "ictrl") or
            not 1 <= function_limit <= 32):
        raise ValueError("indirect follow sources do not describe one verified device and binary")
    with redirect_stdout(io.StringIO()):
        if not verify_case(candidate_dir):
            raise ValueError("indirect candidate hash mismatch")
    native = _validate_native_candidate_queue(
        native_dir, source, candidate_dir / "candidates.json", {digest})["record"]
    observed = rank_native_candidates(source["candidates"], digest, function_limit)
    sites = discover_blr_sites(source, native_dir, native, observed, branch_limit)
    if not sites:
        raise ValueError("selected native functions have no local BLR call site")
    identity = {"bundle_id": case["bundle_id"],
                "device_id_sha256_prefix": prefix, "binary_sha256": digest,
                "source_investigation_manifest_sha256":
                    sha256_file(investigation / "manifest.json"),
                "objc_index_sha256": sha256_file(objc_index),
                "source_script_sha256": sha256_file(script),
                "function_limit": function_limit, "branch_limit": branch_limit,
                "selected_sites": sites, "disabled_analyzer": disabled_analyzer}
    has_prior = resume and output.exists() and any(output.iterdir())
    if has_prior:
        saved = _read(output / "manifest.json")
        record = _read(output / "run.json")
        if (saved.get("kind") != "ghidra_indirect_follow" or
                saved.get("status") != record.get("status") or
                saved.get("evidence") != _files(output) or
                record.get("schema_version") != 1 or
                record.get("kind") != "ghidra_indirect_follow" or
                any(record.get(key) != value for key, value in identity.items()) or
                sha256_file(output / "sources/objc-index.json") !=
                identity["objc_index_sha256"] or
                sha256_file(output / "sources/investigation-manifest.json") !=
                identity["source_investigation_manifest_sha256"]):
            raise ValueError("indirect follow resume source or saved evidence differs")
        if record["status"] == "complete":
            with redirect_stdout(io.StringIO()):
                if not verify_case(output):
                    raise ValueError("completed indirect follow failed semantic verification")
            return output / "manifest.json", True
        if (record["status"] != "failed" or
                record.get("error", {}).get("stage") != "direct_ghidra_queue"):
            raise ValueError("only a completed branch replay can be reused")
        record.setdefault("history", []).append({
            "at": _now(), "previous_error": record.get("error")})
        record.pop("error", None)
    else:
        record = {"schema_version": 1, "kind": "ghidra_indirect_follow",
                  "status": "failed", **identity, "started_at": _now()}
    check_direct_ghidra(ghidra_dir, java_home, disabled_analyzer)
    if not has_prior:
        output.mkdir(parents=True, exist_ok=True)
        (output / "sources").mkdir()
        shutil.copyfile(objc_index, output / "sources/objc-index.json")
        shutil.copyfile(investigation / "manifest.json",
                        output / "sources/investigation-manifest.json")
    stage = "branch_flow"
    try:
        flow_dir = output / "branch-flow"
        if not has_prior:
            _, complete = capture_flow(
                udid, backend, script, flow_dir, methods=methods,
                binary=binary, objc_index=objc_index,
                branch_offsets=[item["offset"] for item in sites],
                branch_registers=[(item["offset"], item["register"]) for item in sites])
            if not complete:
                raise RuntimeError("indirect branch replay failed")
        capture = _validate_flow_capture(flow_dir, case["bundle_id"], prefix, {digest})
        trace = capture["trace"]
        if (trace is None or trace.get("requested_methods") != methods or
                trace.get("static_binary_sha256") != digest or
                trace.get("branch_requested_offsets") !=
                [f"0x{item['offset']:x}" for item in sites] or
                trace.get("branch_registers") !=
                [{"offset": f"0x{item['offset']:x}", "register": item["register"]}
                 for item in sites]):
            raise ValueError("indirect replay differs from selected native BLR sites")
        stage = "direct_ghidra_queue"
        queue_dir = output / "queue"
        if has_prior and queue_dir.exists():
            archive = output / "attempts" / (
                "queue-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
            archive.parent.mkdir(exist_ok=True)
            shutil.move(str(queue_dir), str(archive))
            record["history"][-1]["archived_queue"] = str(archive.relative_to(output))
        _, complete = decompile_candidate_queue(
            candidate_dir, queue_dir, ghidra_dir, function_limit,
            java_home, timeout, disabled_analyzer, native_dir, flow_dir)
        if not complete:
            raise RuntimeError("direct Ghidra indirect queue failed")
        queue = _validate_ghidra_direct_queue(
            output / "queue", case["bundle_id"], prefix, {digest})["record"]
        record["function_count"] = len(queue["selected"])
        record["runtime_indirect_count"] = sum(
            item.get("origin") == "runtime_indirect_target" for item in queue["selected"])
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"stage": stage, "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        record["finished_at"] = _now()
        (output / "run.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "ghidra_indirect_follow",
            "status": record["status"], "binary_sha256": digest,
            "evidence": _files(output)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
