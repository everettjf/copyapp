"""Decompile a bounded, observed candidate queue using Copy APP's Ghidra adapter."""

import io
import json
import re
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from copyapp.ghidra_direct import decompile_ghidra_batch, decompile_ghidra_function
from copyapp.ipa import MAX_BINARY
from copyapp.native_disasm import (_bounds, _function_starts, is_arm64_blr,
                                   rank_native_candidates)
from copyapp.objc import MachOImage
from copyapp.verify import checked_path, sha256_file, verify_case


def _files(root: Path) -> list:
    return [{"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
            for path in sorted(root.rglob("*"))
            if path.is_file() and path != root / "manifest.json"]


def select_ghidra_targets(options: list, digest: str, limit: int,
                          native_record: Optional[dict] = None,
                          indirect_targets: Optional[list] = None) -> list:
    """Keep observed entries first, then verified local direct-call followers."""
    observed = rank_native_candidates(options, digest, limit)
    if native_record is None:
        return [{"address": item["static_address"], "class": item.get("class"),
                 "selector": item.get("selector")} for item in observed]
    selected = [{"address": item["static_address"], "class": item.get("class"),
                 "selector": item.get("selector"), "origin": "runtime_observed"}
                for item in observed]
    roots = {int(item["address"], 16) for item in selected}
    seen = set(roots)
    for item in native_record.get("followed", []):
        if item.get("status") != "complete" or int(item["root_address"], 16) not in roots:
            continue
        address = int(item["address"], 16)
        if address in seen:
            continue
        if len(selected) >= 32:
            break
        selected.append({"address": f"0x{address:x}", "class": None,
                         "selector": None, "origin": "native_direct_follow",
                         "root_address": item["root_address"],
                         "source_address": item["source_address"],
                         "depth": item["depth"],
                         "native_summary": item["summary"]})
        seen.add(address)
    for item in indirect_targets or []:
        if int(item["address"], 16) not in seen and len(selected) < 32:
            selected.append(item)
            seen.add(int(item["address"], 16))
    return selected


def verified_indirect_targets(source: dict, native_dir: Path, native_record: dict,
                              trace: dict, observed: list) -> list:
    """Bind a tap-window BLR target to an exact local function start."""
    binary = Path(source["binary_path"])
    image = MachOImage(binary.read_bytes())
    starts = set(_function_starts(image))
    roots = {int(item["static_address"], 16): item for item in observed}
    static_indices = set()
    for entry in trace.get("static_entries", []):
        offset = entry.get("module_offset")
        if (entry.get("status") != "hooked" or not isinstance(offset, str) or
                not offset.startswith("0x")):
            continue
        address = image.base + int(offset, 16)
        option = roots.get(address)
        if (option is not None and (entry.get("class"), entry.get("selector")) ==
                (option.get("class"), option.get("selector"))):
            static_indices.add(entry["index"])
    if not static_indices:
        raise ValueError("indirect flow has no selected runtime entry hook")
    native_functions = []
    for item in native_record.get("results", []) + native_record.get("followed", []):
        if item.get("status") != "complete":
            continue
        root = item.get("root_address", item.get("address"))
        if int(root, 16) not in roots:
            continue
        summary_path = checked_path(native_dir, item["summary"])
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assembly = (summary_path.parent / "assembly.txt").read_text(encoding="utf-8")
        native_functions.append((item["address"], summary, assembly))
    chosen = []
    seen = set(roots)
    for register in trace.get("branch_registers", []):
        offset, name = int(register["offset"], 16), register["register"]
        site = image.base + offset
        pattern = re.compile(rf"^{site:x}:\s+[0-9a-fA-F]{{8}}\s+blr\s+{re.escape(name)}\b",
                             re.MULTILINE | re.IGNORECASE)
        matches = [(address, summary) for address, summary, assembly in native_functions
                   if int(summary["address"], 16) <= site <
                   int(summary["stop_address"], 16) and pattern.search(assembly)]
        if len(matches) != 1:
            raise ValueError("indirect branch does not match one verified local BLR instruction")
        if not is_arm64_blr(image, site, name):
            raise ValueError("indirect BLR instruction differs from acquired Mach-O bytes")
        branch_index = trace["branch_requested_offsets"].index(register["offset"])
        for step in trace["steps"]:
            if (step["branch_call_counts"][branch_index] < 1 or
                    not any(step["static_call_counts"][index] > 0
                            for index in static_indices)):
                continue
            for hit in step.get("branch_register_hits", []):
                if (hit.get("index") != branch_index or
                        hit.get("register") != name or
                        hit.get("status") != "app_image"):
                    continue
                target = image.base + int(hit["target_offset"], 16)
                if target not in starts:
                    raise ValueError("indirect target is not an exact Mach-O function start")
                _bounds(image, target, 16)
                if target in seen:
                    continue
                seen.add(target)
                chosen.append({"address": f"0x{target:x}", "class": None,
                               "selector": None, "origin": "runtime_indirect_target",
                               "source_address": matches[0][0],
                               "branch_site": f"0x{site:x}",
                               "register": name, "flow_step": step["index"],
                               "target_offset": hit["target_offset"]})
                if len(chosen) >= 4:
                    return chosen
    if not chosen:
        raise ValueError("indirect flow recorded no app-image target in a selected tap window")
    return chosen


def decompile_candidate_queue(candidates_dir: Path, output: Path,
                              ghidra_dir: Path, limit: int = 4,
                              java_home: Optional[Path] = None,
                              timeout: int = 600,
                              disabled_analyzer: Optional[str] = None,
                              native_dir: Optional[Path] = None,
                              branch_flow: Optional[Path] = None) -> Tuple[Path, bool]:
    """Keep candidate source and each exact-address Ghidra result in one case."""
    if not 1 <= limit <= 32:
        raise ValueError("limit must be between 1 and 32")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    with redirect_stdout(io.StringIO()):
        if not verify_case(candidates_dir):
            raise ValueError("candidate evidence hash mismatch")
    source = json.loads((candidates_dir / "candidates.json").read_text(encoding="utf-8"))
    source_manifest = json.loads((candidates_dir / "manifest.json").read_text(encoding="utf-8"))
    digest = source.get("binary_sha256")
    binary = Path(source.get("binary_path", ""))
    if (source_manifest.get("kind") != "runtime_static_candidates" or
            source.get("kind") != "runtime_static_candidates" or
            not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest) or
            not binary.is_file() or not 0 < binary.stat().st_size <= MAX_BINARY or
            sha256_file(binary) != digest):
        raise ValueError("candidate case has no matching analysis binary")
    options = source.get("candidates")
    if not isinstance(options, list) or not options:
        raise ValueError("candidate case has no function addresses")
    native_record = None
    if native_dir is not None:
        from copyapp.report import _validate_native_candidate_queue
        native_record = _validate_native_candidate_queue(
            native_dir, source, candidates_dir / "candidates.json", {digest})["record"]
    indirect = None
    if branch_flow is not None:
        if native_dir is None or native_record is None:
            raise ValueError("indirect flow requires a verified native queue")
        from copyapp.report import _validate_flow_capture
        capture = _validate_flow_capture(
            branch_flow, source["bundle_id"], source["device_id_sha256_prefix"], {digest})
        if capture["trace"] is None or capture["trace"].get("static_binary_sha256") != digest:
            raise ValueError("indirect flow has no matching binary trace")
        indirect = verified_indirect_targets(
            source, native_dir, native_record, capture["trace"],
            rank_native_candidates(options, digest, limit))
    selected = select_ghidra_targets(options, digest, limit, native_record, indirect)
    output.mkdir(parents=True, exist_ok=True)
    copied = output / "sources/candidates"
    copied.mkdir(parents=True)
    shutil.copyfile(candidates_dir / "manifest.json", copied / "manifest.json")
    for item in source_manifest.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("candidate evidence list is invalid")
        relative = item["path"]
        source_file = checked_path(candidates_dir, relative)
        target = copied / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, target)
    if native_dir is not None:
        native_manifest = json.loads((native_dir / "manifest.json").read_text(encoding="utf-8"))
        native_copy = output / "sources/native"
        native_copy.mkdir()
        shutil.copyfile(native_dir / "manifest.json", native_copy / "manifest.json")
        for item in native_manifest["evidence"]:
            relative = item["path"]
            target = native_copy / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked_path(native_dir, relative), target)
    if branch_flow is not None:
        flow_manifest = json.loads((branch_flow / "manifest.json").read_text(encoding="utf-8"))
        flow_copy = output / "sources/branch-flow"
        flow_copy.mkdir()
        shutil.copyfile(branch_flow / "manifest.json", flow_copy / "manifest.json")
        for item in flow_manifest["evidence"]:
            relative = item["path"]
            target = flow_copy / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked_path(branch_flow, relative), target)
    record = {"schema_version": 1, "kind": "ghidra_direct_candidate_queue",
              "status": "failed", "binary_sha256": digest,
              "candidate_case_sha256": sha256_file(candidates_dir / "candidates.json"),
              "limit": limit, "selected": selected,
              "results": [], "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if native_dir is not None:
        record["native_case_sha256"] = sha256_file(native_dir / "index.json")
    if branch_flow is not None:
        record["branch_flow_manifest_sha256"] = sha256_file(branch_flow / "manifest.json")
    record["execution"] = "single_import" if len(selected) > 1 else "single_function"
    if disabled_analyzer is not None:
        record["disabled_analyzer"] = disabled_analyzer
    try:
        if len(selected) > 1:
            summaries = decompile_ghidra_batch(
                binary, digest, [item["address"] for item in selected],
                output, ghidra_dir, java_home, timeout, disabled_analyzer)
        else:
            summaries = [decompile_ghidra_function(
                binary, digest, selected[0]["address"],
                output / "targets/function-01", ghidra_dir, java_home,
                timeout, disabled_analyzer)]
        for index, (item, summary) in enumerate(zip(selected, summaries), 1):
            result = json.loads(summary.read_text(encoding="utf-8"))
            if (result.get("binary_sha256") != digest or
                    int(result.get("address", "0x0"), 16) !=
                    int(item["address"], 16)):
                raise ValueError("Ghidra function does not match selected candidate")
            record["results"].append({"index": index,
                                      "address": item["address"],
                                      "status": "complete",
                                      "summary": str(summary.relative_to(output))})
        record["status"] = "complete"
    except Exception as exc:
        for index, item in enumerate(selected[len(record["results"]):],
                                     len(record["results"]) + 1):
            record["results"].append({"index": index,
                                      "address": item["address"],
                                      "status": "failed",
                                      "error": {"type": type(exc).__name__,
                                                "message": str(exc)[:400]}})
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (output / "queue.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "ghidra_direct_candidate_queue",
            "status": record["status"], "binary_sha256": digest,
            "evidence": _files(output)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
