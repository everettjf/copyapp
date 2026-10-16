"""Join a collected case with selected runtime and decompiler evidence."""

import json
import io
import math
import re
import shutil
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from copyapp.verify import checked_path, sha256_file, verify_case
from copyapp.sandbox_diff import compute_sandbox_changes
from copyapp.compare_playbooks import _load_run
from copyapp.ocr_file import verify_ocr_source
from copyapp.flow_capture import validate_flow_pair, validate_flow_trace_pair
from copyapp.network_flow import validate_network_flow, validate_network_trace_files
from copyapp.ghidra_direct import validate_function_facts
from copyapp.rea_bridge import bridge_callees
from copyapp.branch_map import validate_branch_map
from copyapp.sqlite_schema import validate_sqlite_schema_case
from copyapp.plist_schema import validate_plist_schema_case
from copyapp.sandbox_capture import validate_sandbox_file_capture


EVIDENCE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,79}\Z")
CONFIDENCE = {"observed": "直接观察", "inferred": "多证据推断", "unknown": "待验证"}


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _copy_file(source: Path, target: Path, root: Path, records: Dict[str, dict], key: str) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    records[key] = {"path": str(target.relative_to(root)),
                    "sha256": sha256_file(target)}


def _main_and_embedded_hashes(case: Path) -> set:
    for relative in ("decrypted/static/ipa-index.json", "acquired/static/ipa-index.json"):
        path = case / relative
        if path.is_file():
            return {item["sha256"] for item in _read_json(path).get("binaries", [])
                    if item.get("sha256")}
    return set()


def _validate_ipa_static(path: Path, bundle: str, case: Path) -> dict:
    """Bind a standalone resource index to this case's acquired or recovered IPA."""
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("IPA static evidence hash or source mismatch")
    manifest = _read_json(path / "manifest.json")
    index = _read_json(path / "ipa-index.json")
    allowed = {sha256_file(case / relative) for relative in
               ("acquired/bundle-snapshot.ipa", "decrypted/analysis.ipa")
               if (case / relative).is_file()}
    catalogs = index.get("asset_catalogs")
    if (manifest.get("kind") != "ipa_static_index" or
            index.get("schema_version") != 1 or
            index.get("bundle_id") != bundle or
            index.get("ipa_sha256") not in allowed or
            not isinstance(catalogs, list)):
        raise ValueError("IPA static evidence belongs to another App or package")
    for catalog in catalogs:
        if not isinstance(catalog, dict):
            raise ValueError("IPA catalog record is not an object")
        if catalog.get("status") == "indexed":
            assets = catalog.get("assets")
            if (not isinstance(assets, list) or catalog.get("asset_count") != len(assets) or
                    not all(isinstance(item, dict) and isinstance(item.get("name"), str)
                            for item in assets) or
                    [item["name"] for item in assets] !=
                    sorted({item["name"] for item in assets})):
                raise ValueError("IPA catalog names or count differ")
    return {"index": index, "files": ["manifest.json", "ipa-index.json", "ipa-report.md"]}


def _validate_rea(path: Path, binary_hashes: set) -> dict:
    summary = _read_json(path / "summary.json")
    evidence = _read_json(path / "evidence.json")
    digest = summary.get("binary_sha256")
    if digest not in binary_hashes or digest != evidence.get("subject", {}).get("digest", {}).get("sha256"):
        raise ValueError(f"REA binary does not match acquired case: {path}")
    result = evidence.get("normalized_result", {})
    if (summary.get("evidence_id") != evidence.get("evidence_id") or
            summary.get("provider") != evidence.get("provider") or
            summary.get("analysis_profile_digest") != evidence.get("analysis_profile", {}).get("digest") or
            summary.get("requested_procedure") != evidence.get("parameters", {}).get("procedure") or
            summary.get("resolved_procedure") != result.get("procedure") or
            not isinstance(result.get("pseudocode"), str) or
            (path / "pseudocode.txt").read_text(encoding="utf-8") != result["pseudocode"] or
            summary.get("pseudocode_is_original_source") is not False):
        raise ValueError(f"REA evidence identity mismatch: {path}")
    return summary


def _validate_native_disassembly(path: Path, binary_hashes: set) -> dict:
    """Admit only bounded assembly for an acquired binary, without claiming decompilation."""
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("native disassembly evidence hash mismatch")
    manifest = _read_json(path / "manifest.json")
    summary = _read_json(path / "summary.json")
    assembly = (path / "assembly.txt").read_text(encoding="utf-8")
    from copyapp.native_disasm import (INSTRUCTION, MAX_TOOL_OUTPUT,
                                       direct_branches, direct_calls)
    addresses = [int(item, 16) for item in INSTRUCTION.findall(assembly)]
    calls, calls_truncated = direct_calls(assembly)
    branches = direct_branches(assembly)
    try:
        start = int(summary["address"], 16)
        stop = int(summary["stop_address"], 16)
        limit = summary["max_bytes"]
    except (KeyError, TypeError, ValueError):
        raise ValueError("native disassembly address metadata is invalid")
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "native_disassembly" or
            manifest.get("status") != "complete" or
            listed != {"summary.json", "assembly.txt"} or
            summary.get("schema_version") != 1 or
            summary.get("kind") != "native_disassembly" or
            summary.get("status") != "complete" or
            summary.get("binary_sha256") not in binary_hashes or
            summary.get("tool_name") != "llvm-objdump" or
            summary.get("boundary") not in ("next_function_start", "bounded_window") or
            summary.get("truncated") is not (summary.get("boundary") == "bounded_window") or
            type(limit) is not int or not 16 <= limit <= 4096 or limit % 4 or
            not 0 < stop - start <= limit or start % 4 or stop % 4 or
            len(assembly.encode("utf-8")) > MAX_TOOL_OUTPUT or
            summary.get("assembly_sha256") != sha256_file(path / "assembly.txt") or
            summary.get("instruction_count") != len(addresses) or
            summary.get("direct_calls") != calls or
            summary.get("direct_calls_truncated") is not calls_truncated or
            summary.get("direct_branches") != branches or
            not addresses or addresses[0] != start or
            addresses != sorted(set(addresses)) or
            any(item < start or item >= stop or item % 4 for item in addresses)):
        raise ValueError("native disassembly identity or instruction range differs")
    return {"summary": summary, "files": ["manifest.json", "summary.json", "assembly.txt"]}


def _validate_ghidra_direct(path: Path, binary_hashes: set) -> dict:
    """Bind a Copy APP owned Ghidra result to its script and acquired binary."""
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("direct Ghidra evidence hash mismatch")
    manifest = _read_json(path / "manifest.json")
    summary = _read_json(path / "summary.json")
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    required = {"CopyAppDecompile.java", "address.txt", "name.txt",
                "language.txt", "launcher.log", "pseudocode.txt", "summary.json",
                "report.md"}
    launcher_path = path / "launcher.log"
    if launcher_path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("direct Ghidra launcher log exceeded limit")
    application_log = path / "ghidra.log"
    if application_log.is_file() and application_log.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("direct Ghidra application log exceeded limit")
    logs = launcher_path.read_bytes() + (application_log.read_bytes()
                                        if application_log.is_file() else b"")
    if (b"Analysis timed out at" in logs or
            b"Processing not completed for file" in logs):
        raise ValueError("direct Ghidra auto-analysis timed out; pseudocode is partial")
    disabled = summary.get("disabled_analyzer")
    if disabled is not None:
        required |= {"CopyAppAnalysisOptions.java", "analysis-options.txt"}
    facts_version = summary.get("facts_schema_version")
    if facts_version in (1, 2):
        required.add("function-facts.json")
        if summary.get("rea_license_sha256") is not None:
            required.add("REA-LICENSE.txt")
    source = Path(summary.get("binary", ""))
    try:
        address = int(summary["address"], 16)
        returned = int((path / "address.txt").read_text(encoding="utf-8").strip(), 16)
    except (KeyError, ValueError, OSError) as exc:
        raise ValueError("direct Ghidra function address is invalid") from exc
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "ghidra_direct_decompilation" or
            manifest.get("status") != "complete" or
            summary.get("schema_version") != 1 or
            summary.get("kind") != "ghidra_direct_decompilation" or
            summary.get("status") != "complete" or
            summary.get("binary_sha256") not in binary_hashes or
            manifest.get("binary_sha256") != summary.get("binary_sha256") or
            manifest.get("address") != summary.get("address") or
            address != returned or
            not required <= listed or
            summary.get("script_sha256") !=
            sha256_file(path / "CopyAppDecompile.java") or
            manifest.get("script_sha256") != summary.get("script_sha256") or
            summary.get("pseudocode_sha256") != sha256_file(path / "pseudocode.txt") or
            manifest.get("facts_schema_version") != facts_version or
            (facts_version not in (None, 1, 2)) or
            (facts_version is None and "function-facts.json" in listed) or
            (facts_version in (1, 2) and (
                summary.get("facts_sha256") != sha256_file(path / "function-facts.json") or
                manifest.get("rea_license_sha256") != summary.get("rea_license_sha256") or
                (summary.get("rea_license_sha256") is not None and
                 summary.get("rea_license_sha256") !=
                 sha256_file(path / "REA-LICENSE.txt")) or
                (summary.get("rea_license_sha256") is None and
                 "REA-LICENSE.txt" in listed) or
                validate_function_facts(path / "function-facts.json",
                                        summary["address"], summary.get("function_name"))
                .get("schema_version") != facts_version)) or
            manifest.get("disabled_analyzer") != disabled or
            (disabled is not None and (not isinstance(disabled, str) or
             summary.get("options_script_sha256") !=
             sha256_file(path / "CopyAppAnalysisOptions.java") or
             manifest.get("options_script_sha256") != summary.get("options_script_sha256") or
             (path / "analysis-options.txt").read_text(encoding="utf-8") !=
             disabled + "=false\n")) or
            (disabled is None and ("analysis-options.txt" in listed or
             "CopyAppAnalysisOptions.java" in listed)) or
            summary.get("function_name") !=
            (path / "name.txt").read_text(encoding="utf-8").strip() or
            summary.get("language") !=
            (path / "language.txt").read_text(encoding="utf-8").strip() or
            not source.is_file() or sha256_file(source) != summary.get("binary_sha256") or
            (path / "pseudocode.txt").stat().st_size > 2 * 1024 * 1024):
        raise ValueError("direct Ghidra result differs from script, function or acquired binary")
    return {"summary": summary, "files": sorted(listed | {"manifest.json"})}


def _validate_ghidra_direct_queue(path: Path, bundle: str,
                                  device_prefix: str, binary_hashes: set) -> dict:
    """Recompute the candidate order and bind every direct Ghidra result."""
    path = path.resolve(strict=True)
    source_dir = path / "sources/candidates"
    with redirect_stdout(io.StringIO()):
        if not verify_case(path) or not verify_case(source_dir):
            raise ValueError("direct Ghidra queue or candidate source hash mismatch")
    manifest = _read_json(path / "manifest.json")
    record = _read_json(path / "queue.json")
    source = _read_json(source_dir / "candidates.json")
    digest = source.get("binary_sha256")
    limit = record.get("limit")
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "ghidra_direct_candidate_queue" or
            manifest.get("status") != "complete" or
            record.get("schema_version") != 1 or
            record.get("kind") != "ghidra_direct_candidate_queue" or
            record.get("status") != "complete" or
            source.get("kind") != "runtime_static_candidates" or
            source.get("bundle_id") != bundle or
            source.get("device_id_sha256_prefix") != device_prefix or
            digest not in binary_hashes or
            record.get("binary_sha256") != digest or
            manifest.get("binary_sha256") != digest or
            record.get("candidate_case_sha256") !=
            sha256_file(source_dir / "candidates.json") or
            type(limit) is not int or not 1 <= limit <= 32 or
            not isinstance(source.get("candidates"), list) or
            not isinstance(record.get("selected"), list) or
            not isinstance(record.get("results"), list)):
        raise ValueError("direct Ghidra queue identity or status differs")
    native_record = None
    native_source = path / "sources/native"
    native_digest = record.get("native_case_sha256")
    if native_digest is not None:
        if (not isinstance(native_digest, str) or
                native_digest != sha256_file(native_source / "index.json")):
            raise ValueError("direct Ghidra native source hash mismatch")
        native_record = _validate_native_candidate_queue(
            native_source, source, source_dir / "candidates.json", binary_hashes)["record"]
    elif native_source.exists():
        raise ValueError("direct Ghidra queue has an unbound native source")
    from copyapp.ghidra_queue import select_ghidra_targets, verified_indirect_targets
    branch_source = path / "sources/branch-flow"
    branch_digest = record.get("branch_flow_manifest_sha256")
    indirect = None
    if branch_digest is not None:
        if native_record is None or branch_digest != sha256_file(branch_source / "manifest.json"):
            raise ValueError("direct Ghidra indirect source hash mismatch")
        capture = _validate_flow_capture(branch_source, bundle, device_prefix, binary_hashes)
        if capture["trace"] is None or capture["trace"].get("static_binary_sha256") != digest:
            raise ValueError("direct Ghidra indirect source binary differs")
        from copyapp.native_disasm import rank_native_candidates
        indirect = verified_indirect_targets(
            source, native_source, native_record, capture["trace"],
            rank_native_candidates(source["candidates"], digest, limit))
    elif branch_source.exists():
        raise ValueError("direct Ghidra queue has an unbound indirect source")
    chosen = select_ghidra_targets(source["candidates"], digest, limit,
                                   native_record, indirect)
    if len(chosen) != len(record["selected"]) or len(chosen) != len(record["results"]):
        raise ValueError("direct Ghidra candidate count differs")
    execution = record.get("execution")
    if execution not in (None, "single_function", "single_import") or (
            execution == "single_function" and len(chosen) != 1) or (
            execution == "single_import" and len(chosen) < 2):
        raise ValueError("direct Ghidra execution mode differs from candidate count")
    required = {"queue.json", "sources/candidates/manifest.json",
                "sources/candidates/candidates.json"}
    if native_record is not None:
        required.add("sources/native/manifest.json")
        native_manifest = _read_json(native_source / "manifest.json")
        required |= {"sources/native/" + item["path"]
                     for item in native_manifest.get("evidence", [])}
    if indirect is not None:
        required.add("sources/branch-flow/manifest.json")
        branch_manifest = _read_json(branch_source / "manifest.json")
        required |= {"sources/branch-flow/" + item["path"]
                     for item in branch_manifest.get("evidence", [])}
    if execution == "single_import":
        required.add("launcher.log")
    for index, (expected, selected, result) in enumerate(
            zip(chosen, record["selected"], record["results"]), 1):
        summary_name = f"targets/function-{index:02d}/summary.json"
        if (selected != expected or result.get("index") != index or
                result.get("address") != expected["address"] or
                result.get("status") != "complete" or
                result.get("summary") != summary_name):
            raise ValueError("direct Ghidra result differs from ranked candidate")
        checked_path(path, summary_name)
        target = path / f"targets/function-{index:02d}"
        function = _validate_ghidra_direct(target, binary_hashes)
        if (function["summary"].get("binary_sha256") != digest or
                function["summary"].get("disabled_analyzer") !=
                record.get("disabled_analyzer") or
                (execution == "single_import" and (
                 function["summary"].get("batch_size") != len(chosen) or
                 function["summary"].get("batch_index") != index or
                 sha256_file(target / "launcher.log") !=
                 sha256_file(path / "launcher.log"))) or
                int(function["summary"].get("address", "0x0"), 16) !=
                int(expected["address"], 16)):
            raise ValueError("direct Ghidra target differs from selected function")
        required |= {str(target.relative_to(path) / name) for name in function["files"]}
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    if not required <= listed:
        raise ValueError("direct Ghidra queue evidence list is incomplete")
    return {"manifest": manifest, "record": record,
            "files": sorted(listed | {"manifest.json"})}


def _validate_native_candidate_queue(path: Path, candidates: dict,
                                     candidates_path: Path,
                                     binary_hashes: set) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("native candidate queue hash mismatch")
    manifest = _read_json(path / "manifest.json")
    record = _read_json(path / "index.json")
    results = record.get("results")
    decisions = record.get("decisions")
    followed = record.get("followed")
    options = candidates.get("candidates")
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "native_candidate_queue" or
            manifest.get("status") not in ("complete", "partial", "unavailable") or
            record.get("schema_version") != 1 or
            record.get("kind") != "native_candidate_queue" or
            record.get("status") != manifest["status"] or
            record.get("candidate_case_sha256") != sha256_file(candidates_path) or
            record.get("binary_sha256") not in binary_hashes or
            record.get("binary_sha256") != candidates.get("binary_sha256") or
            type(record.get("limit")) is not int or not 1 <= record["limit"] <= 32 or
            type(record.get("max_bytes")) is not int or
            type(record.get("follow_limit")) is not int or
            not 0 <= record["follow_limit"] <= 16 or
            type(record.get("follow_depth")) is not int or
            not 0 <= record["follow_depth"] <= 4 or
            not isinstance(decisions, list) or not isinstance(followed, list) or
            len(followed) > record["follow_limit"] or
            not isinstance(options, list) or not isinstance(results, list) or
            len(results) != min(record["limit"], len(options))):
        raise ValueError("native candidate queue source or status differs")
    from copyapp.native_disasm import rank_native_candidates
    selected = rank_native_candidates(options, record["binary_sha256"], record["limit"])
    complete = 0
    summaries = {}
    for index, result in enumerate(results, 1):
        address = str(result.get("address", "")).lower()
        option = selected[index - 1]
        if (address != option["static_address"].lower() or result.get("index") != index or
                result.get("class") != option.get("class") or
                result.get("selector") != option.get("selector") or
                result.get("status") not in ("complete", "unavailable")):
            raise ValueError("native candidate result differs from source")
        if result["status"] == "complete":
            summary_name = result.get("summary")
            if summary_name != f"function-{index:02d}/summary.json":
                raise ValueError("native candidate summary path differs")
            native = _validate_native_disassembly(path / f"function-{index:02d}",
                                                  binary_hashes)
            if (native["summary"].get("binary_sha256") != record["binary_sha256"] or
                    native["summary"].get("address", "").lower() != address or
                    native["summary"].get("max_bytes") != record["max_bytes"]):
                raise ValueError("native candidate assembly belongs to another function")
            complete += 1
            summaries[address] = native["summary"]
        elif (result.get("summary") is not None or
              (path / f"function-{index:02d}").exists() or
              not isinstance(result.get("error"), dict)):
            raise ValueError("unavailable native result has unexpected output")
    from copyapp.native_disasm import _function_starts, local_direct_targets
    from copyapp.objc import MachOImage
    source_binary = Path(candidates.get("binary_path", ""))
    from copyapp.ipa import MAX_BINARY
    if (not source_binary.is_file() or source_binary.stat().st_size > MAX_BINARY or
            sha256_file(source_binary) != record["binary_sha256"]):
        raise ValueError("native candidate queue analysis binary differs")
    image = MachOImage(source_binary.read_bytes())
    starts = set(_function_starts(image))
    seen = {int(item["static_address"], 16) for item in selected}
    decision_index = followed_index = 0
    for root in results:
        if root["status"] != "complete":
            continue
        source_address = root["address"].lower()
        depth = 0
        while True:
            if decision_index >= len(decisions):
                raise ValueError("native follow decision is missing")
            summary = summaries[source_address]
            eligible = local_direct_targets(image, starts, summary, seen)
            if summary.get("direct_calls_truncated"):
                status = "truncated_calls"
            elif depth >= record["follow_depth"]:
                status = "depth_limit"
            elif len(eligible) > 1:
                status = "ambiguous"
            elif not eligible:
                status = "none"
            elif followed_index >= record["follow_limit"]:
                status = "function_limit"
            else:
                status = "followed"
            decision = decisions[decision_index]
            decision_index += 1
            if (decision.get("root_address", "").lower() != root["address"].lower() or
                    decision.get("source_address", "").lower() != source_address or
                    decision.get("depth") != depth or
                    decision.get("eligible_targets") !=
                    [f"0x{item:x}" for item in eligible] or
                    decision.get("status") != status):
                raise ValueError("native follow decision differs from assembly")
            if status != "followed":
                break
            if followed_index >= len(followed):
                raise ValueError("native followed function is missing")
            item = followed[followed_index]
            followed_index += 1
            target_address = f"0x{eligible[0]:x}"
            seen.add(eligible[0])
            if (item.get("root_address", "").lower() != root["address"].lower() or
                    item.get("source_address", "").lower() != source_address or
                    item.get("address", "").lower() != target_address or
                    item.get("depth") != depth + 1 or
                    item.get("status") not in ("complete", "unavailable")):
                raise ValueError("native followed function identity differs")
            child_dir = path / f"followed-{followed_index:02d}"
            if item["status"] == "complete":
                if item.get("summary") != f"followed-{followed_index:02d}/summary.json":
                    raise ValueError("native followed summary path differs")
                child = _validate_native_disassembly(child_dir, binary_hashes)
                if (child["summary"].get("binary_sha256") != record["binary_sha256"] or
                        child["summary"].get("address", "").lower() != target_address or
                        child["summary"].get("max_bytes") != record["max_bytes"]):
                    raise ValueError("native followed assembly belongs to another function")
                summaries[target_address] = child["summary"]
                complete += 1
                source_address = target_address
                depth += 1
            else:
                if (item.get("summary") is not None or child_dir.exists() or
                        not isinstance(item.get("error"), dict)):
                    raise ValueError("unavailable native follow has unexpected output")
                break
    if decision_index != len(decisions) or followed_index != len(followed):
        raise ValueError("native follow traversal has extra evidence")
    expected = ("complete" if complete == len(results) + len(followed) else
                "partial" if complete else "unavailable")
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    actual = {str(item.relative_to(path)) for item in path.rglob("*")
              if item.is_file() and item != path / "manifest.json"}
    if expected != record["status"] or listed != actual or "index.json" not in listed:
        raise ValueError("native candidate queue file list or status differs")
    return {"record": record, "complete_count": complete}


def _validate_experiment(path: Path, bundle: str, device_prefix: str,
                         binary_hashes: Optional[set] = None) -> dict:
    record = _read_json(path / "experiment.json")
    if (record.get("status") != "complete" or record.get("bundle_id") != bundle or
            record.get("frontmost_before") != bundle or
            not device_prefix or record.get("device_id_sha256_prefix") != device_prefix):
        raise ValueError(f"experiment did not complete on target app: {path}")
    methods, counts = record.get("methods", []), record.get("call_counts", [])
    requested = record.get("requested_methods", [])
    if (not methods or len(methods) != len(counts) or len(methods) != len(requested) or
            any(item.get("status") != "hooked" for item in methods) or
            any(type(count) is not int or count < 0 for count in counts) or
            any(item.get("class", "") + "::" + item.get("selector", "") != requested[index]
                for index, item in enumerate(methods))):
        raise ValueError(f"experiment method counts are incomplete: {path}")
    for name in ("before.jpg", "after.jpg"):
        expected = record.get("screenshot_" + name.split(".")[0] + "_sha256")
        if not expected or sha256_file(path / name) != expected:
            raise ValueError(f"experiment screenshot hash mismatch: {path / name}")
    if binary_hashes is not None and record.get("static_binary_sha256") is not None:
        if record["static_binary_sha256"] not in binary_hashes:
            raise ValueError("experiment static entry belongs to another binary")
    return record


def _validate_playbook(path: Path, bundle: str, device_prefix: str) -> dict:
    manifest, plan = _load_run(path, require_comparable=False)
    if (manifest.get("bundle_id") != bundle or
            manifest.get("device_id_sha256_prefix") != device_prefix):
        raise ValueError("playbook belongs to another app or device")
    files = {"manifest.json", "playbook.json"}
    for item in manifest.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("playbook evidence list is invalid")
        checked_path(path, item["path"])
        files.add(item["path"])
    return {"manifest": manifest, "plan": plan, "files": sorted(files)}


def _validate_view_tree(path: Path, bundle: str, device_prefix: str) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("view tree evidence hash mismatch")
    manifest = _read_json(path / "manifest.json")
    tree = _read_json(path / "view-tree.json")
    if (manifest.get("schema_version") != 1 or manifest.get("kind") != "uikit_view_tree" or
            manifest.get("status") != "complete" or
            manifest.get("bundle_id") != bundle or
            manifest.get("device_id_sha256_prefix") != device_prefix or
            manifest.get("frontmost_before") != bundle or
            manifest.get("frontmost_after") != bundle or
            tree.get("type") != "view_tree"):
        raise ValueError("view tree belongs to another app or device, or is incomplete")
    names = {item.get("path") for item in manifest.get("evidence", [])
             if isinstance(item, dict)}
    if not {"screenshot.jpg", "scan.js", "view-tree.json"} <= names:
        raise ValueError("view tree lacks screenshot, probe source or tree evidence")
    nodes = tree.get("nodes")
    roots = tree.get("roots")
    if (not isinstance(nodes, list) or not 1 <= len(nodes) <= 500 or
            not isinstance(roots, list) or not roots or
            manifest.get("node_count") != len(nodes) or
            manifest.get("window_count") != len(roots)):
        raise ValueError("view tree node/window counts are invalid")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError("view tree contains invalid node structure")
        frame = node.get("frame")
        parent = node.get("parent")
        if (node.get("id") != index or not isinstance(node.get("class_name"), str) or
                (parent is not None and (type(parent) is not int or not 0 <= parent < index)) or
                not isinstance(frame, dict) or
                any(type(frame.get(key)) not in (int, float) or
                    not math.isfinite(frame[key]) for key in ("x", "y", "width", "height"))):
            raise ValueError("view tree contains invalid node structure")
    return {"manifest": manifest, "tree": tree,
            "files": sorted(names | {"manifest.json"})}


def _validate_flow_capture(path: Path, bundle: str, device_prefix: str,
                           binary_hashes=None) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("flow capture evidence hash mismatch")
    manifest = _read_json(path / "manifest.json")
    if (manifest.get("schema_version") != 1 or manifest.get("kind") != "ui_flow_capture" or
            manifest.get("status") != "complete" or
            manifest.get("bundle_id") != bundle or
            manifest.get("device_id_sha256_prefix") != device_prefix or
            manifest.get("ui_backend") not in ("ios-mcp", "ictrl")):
        raise ValueError("flow capture belongs to another app or device, or is incomplete")
    play = _validate_playbook(path / "playbook", bundle, device_prefix)
    views = _validate_view_tree(path / "view-tree", bundle, device_prefix)
    trace = None
    if manifest.get("trace_requested"):
        trace_dir = path / "trace"
        with redirect_stdout(io.StringIO()):
            if not verify_case(trace_dir):
                raise ValueError("flow trace evidence hash mismatch")
        trace = _read_json(trace_dir / "trace.json")
        trace_manifest = _read_json(trace_dir / "manifest.json")
        if (trace_manifest.get("kind") != "ui_flow_method_trace" or
                trace_manifest.get("status") != "complete" or
                manifest.get("trace_status") != "complete"):
            raise ValueError("flow trace status differs")
        validate_flow_trace_pair(play["manifest"], trace, bundle,
                                 device_prefix, binary_hashes)
        trace_names = {item.get("path") for item in trace_manifest.get("evidence", [])
                       if isinstance(item, dict)}
        if trace_names != {"hook.js", "trace.json"}:
            raise ValueError("flow trace lacks source or result evidence")
    network = None
    if manifest.get("network_requested"):
        network = validate_network_trace_files(path / "network", play["manifest"],
                                               bundle, device_prefix)
        if (manifest.get("network_status") != "complete" or
                manifest.get("network_event_count") != len(network["events"])):
            raise ValueError("flow network status or event count differs")
    validate_flow_pair(play["manifest"], views["manifest"], bundle,
                       device_prefix, manifest["ui_backend"])
    if (manifest.get("scenario_id") != play["manifest"].get("scenario_id") or
            manifest.get("source_script_sha256") != sha256_file(path / "playbook/playbook.json") or
            manifest.get("node_count") != views["manifest"].get("node_count") or
            manifest.get("window_count") != views["manifest"].get("window_count")):
        raise ValueError("flow capture child identity differs from parent")
    expected = {"playbook/" + item for item in play["files"]} | {
        "view-tree/" + item for item in views["files"]}
    if trace is not None:
        expected |= {"trace/manifest.json", "trace/hook.js", "trace/trace.json"}
    if network is not None:
        expected |= {"network/manifest.json", "network/hook.js", "network/network.json"}
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    if listed != expected:
        raise ValueError("flow capture evidence list is incomplete")
    return {"manifest": manifest, "playbook": play, "view_tree": views, "trace": trace,
            "network": network,
            "files": sorted(expected | {"manifest.json"})}


def _validate_rea_queue(path: Path, bundle: str, device_prefix: str,
                        binary_hashes: set) -> dict:
    path = path.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("REA queue evidence hash mismatch")
        if not verify_case(path / "sources" / "candidates"):
            raise ValueError("REA queue candidate source hash mismatch")
    manifest = _read_json(path / "manifest.json")
    record = _read_json(path / "queue.json")
    source = _read_json(path / "sources/candidates/candidates.json")
    digest = record.get("binary_sha256")
    selected = record.get("selected")
    results = record.get("results")
    if (manifest.get("kind") != "rea_candidate_queue" or
            manifest.get("status") != "complete" or record.get("status") != "complete" or
            digest not in binary_hashes or source.get("binary_sha256") != digest or
            source.get("bundle_id") != bundle or
            source.get("device_id_sha256_prefix") != device_prefix or
            record.get("candidate_case_sha256") !=
            sha256_file(path / "sources/candidates/candidates.json") or
            manifest.get("binary_sha256") != digest or
            manifest.get("provider") != record.get("provider") or
            not isinstance(selected, list) or not selected or
            not isinstance(results, list) or len(selected) != len(results)):
        raise ValueError("REA queue case, candidate or binary identity differs")
    candidate_addresses = {item.get("static_address") for item in source.get("candidates", [])
                           if isinstance(item, dict)}
    required = {"queue.json", "sources/candidates/candidates.json",
                "sources/candidates/manifest.json"}
    for selection, result in zip(selected, results):
        address = selection.get("address") if isinstance(selection, dict) else None
        if (address not in candidate_addresses or not isinstance(result, dict) or
                result.get("status") != "complete" or result.get("address") != address):
            raise ValueError("REA queue result differs from selected candidate")
        summary_name = result.get("summary")
        if not isinstance(summary_name, str):
            raise ValueError("REA queue result lacks a summary")
        summary_path = checked_path(path, summary_name)
        target = summary_path.parent
        summary = _validate_rea(target, binary_hashes)
        if (summary_path.name != "summary.json" or
                summary.get("provider", {}).get("id") != record.get("provider") or
                summary.get("resolved_procedure", {}).get("address", "").lower() !=
                address.lower() or summary.get("evidence_id") != result.get("evidence_id")):
            raise ValueError("REA queue function identity differs")
        required.update(str(target.relative_to(path) / name)
                        for name in ("summary.json", "evidence.json", "pseudocode.txt"))
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    if not required <= listed:
        raise ValueError("REA queue evidence list is incomplete")
    return {"manifest": manifest, "record": record,
            "files": sorted(listed | {"manifest.json"})}


def _validate_rea_bridge(path: Path, bundle: str, device_prefix: str,
                         binary_hashes: set) -> dict:
    path = path.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("REA bridge evidence hash mismatch")
    source = _validate_rea_queue(path / "sources/queue", bundle,
                                 device_prefix, binary_hashes)
    manifest = _read_json(path / "manifest.json")
    record = _read_json(path / "bridge-map.json")
    queue = source["record"]
    digest = queue["binary_sha256"]
    if (manifest.get("kind") != "rea_bridge_follow" or
            manifest.get("status") != "complete" or
            record.get("kind") != "rea_bridge_follow" or
            record.get("status") != "complete" or
            any(item.get("bundle_id") != bundle or
                item.get("device_id_sha256_prefix") != device_prefix or
                item.get("binary_sha256") != digest or
                item.get("provider") != queue["provider"]
                for item in (manifest, record)) or
            record.get("source_queue_sha256") !=
            sha256_file(path / "sources/queue/queue.json") or
            not isinstance(record.get("results"), list) or
            not isinstance(record.get("decisions"), list) or
            type(record.get("limit")) is not int or
            type(record.get("max_depth")) is not int):
        raise ValueError("REA bridge identity differs from source queue")
    frontier = []
    seen = set()
    for item in queue["results"]:
        address = item["address"].lower()
        seed = checked_path(path / "sources/queue", item["summary"])
        frontier.append((address, 0, _read_json(seed.parent / "evidence.json")))
        seen.add(address)
    followed = 0
    for decision in record["decisions"]:
        if not frontier or not isinstance(decision, dict):
            raise ValueError("REA bridge has an extra or invalid decision")
        address, depth, evidence = frontier.pop(0)
        eligible = [item for item in bridge_callees(evidence)
                    if item["address"] not in seen]
        if (decision.get("source_address") != address or
                decision.get("depth") != depth or
                decision.get("eligible_callees") != eligible):
            raise ValueError("REA bridge callee decision differs from source evidence")
        expected = ("depth_limit" if depth >= record["max_depth"] else
                    "ambiguous" if len(eligible) > 1 else
                    "none" if not eligible else
                    "function_limit" if followed >= record["limit"] else
                    "followed")
        if decision.get("status") != expected:
            raise ValueError("REA bridge decision status differs")
        if expected != "followed":
            continue
        if followed >= len(record["results"]):
            raise ValueError("REA bridge followed result is missing")
        item = record["results"][followed]
        child = eligible[0]["address"]
        summary_path = checked_path(path, item.get("summary", ""))
        if (item.get("source_address") != address or
                item.get("address") != child or item.get("depth") != depth + 1 or
                summary_path.name != "summary.json" or
                summary_path.parent.parent != path / "targets"):
            raise ValueError("REA bridge target differs from selected callee")
        summary = _validate_rea(summary_path.parent, binary_hashes)
        if (summary.get("provider", {}).get("id") != queue["provider"] or
                str(summary.get("resolved_procedure", {}).get("address", "")).lower()
                != child or summary.get("evidence_id") != item.get("evidence_id")):
            raise ValueError("REA bridge target identity differs")
        frontier.append((child, depth + 1,
                         _read_json(summary_path.parent / "evidence.json")))
        seen.add(child)
        followed += 1
    if frontier or followed != len(record["results"]):
        raise ValueError("REA bridge traversal is incomplete")
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    required = {"bridge-map.json", "sources/queue/queue.json",
                "sources/queue/manifest.json"}
    for item in record["results"]:
        base = str(Path(item["summary"]).parent)
        required |= {base + "/" + name for name in
                     ("summary.json", "evidence.json", "pseudocode.txt")}
    if not required <= listed:
        raise ValueError("REA bridge evidence list is incomplete")
    return {"manifest": manifest, "record": record,
            "files": sorted(listed | {"manifest.json"})}


def _validate_investigation(path: Path, bundle: str, device_prefix: str,
                            binary_hashes: set) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("investigation evidence hash mismatch")
    manifest = _read_json(path / "manifest.json")
    scout = _read_json(path / "method-scout.json")
    entry_status = manifest.get("entry_view_status")
    entry_path = path / "entry-view"
    entry = None
    if entry_status == "complete":
        entry = _validate_view_tree(entry_path, bundle, device_prefix)
        if (manifest.get("entry_view_manifest_sha256") !=
                sha256_file(entry_path / "manifest.json") or
                scout.get("runtime_view_sha256") !=
                sha256_file(entry_path / "view-tree.json")):
            raise ValueError("entry view selection differs from saved runtime tree")
    elif entry_status == "unavailable":
        with redirect_stdout(io.StringIO()):
            if not verify_case(entry_path):
                raise ValueError("failed entry view evidence hash mismatch")
        failed_entry = _read_json(entry_path / "manifest.json")
        if (failed_entry.get("status") != "failed" or
                failed_entry.get("bundle_id") != bundle or
                failed_entry.get("device_id_sha256_prefix") != device_prefix or
                manifest.get("entry_view_manifest_sha256") !=
                sha256_file(entry_path / "manifest.json") or
                scout.get("runtime_view_sha256") is not None):
            raise ValueError("failed entry view belongs to another app or device")
    elif entry_status is not None or entry_path.exists():
        raise ValueError("unexpected entry view evidence")
    has_candidates = manifest.get("candidate_status") in ("complete", "no_candidates")
    if has_candidates:
        with redirect_stdout(io.StringIO()):
            if not verify_case(path / "candidates"):
                raise ValueError("candidate evidence hash mismatch")
    candidates = _read_json(path / "candidates/candidates.json") if has_candidates else None
    flow = _validate_flow_capture(path / "flow", bundle, device_prefix, binary_hashes)
    provider = manifest.get("provider")
    queue = (_validate_rea_queue(path / "rea", bundle, device_prefix, binary_hashes)
             if provider in ("ghidra", "hopper") else None)
    direct_status = manifest.get("direct_ghidra_status")
    direct_path = path / "direct-ghidra"
    direct = (_validate_ghidra_direct_queue(direct_path, bundle, device_prefix,
                                            binary_hashes)
              if direct_status == "complete" else None)
    if (direct_status not in (None, "not_requested", "complete") or
            (direct is None and direct_path.exists()) or
            (provider == "ghidra-direct" and direct_status !=
             ("complete" if candidates and candidates.get("candidates") else "not_requested")) or
            (direct is not None and manifest.get("disabled_analyzer") !=
             direct["record"].get("disabled_analyzer")) or
            (provider != "ghidra-direct" and direct_status is not None)):
        raise ValueError("unexpected direct Ghidra investigation evidence")
    native_status = manifest.get("native_status")
    native_path = path / "native"
    native = None
    if native_status in ("complete", "partial", "unavailable"):
        if candidates is None or provider not in ("none", "ghidra-direct"):
            raise ValueError("native disassembly has no matching no-REA candidates")
        native = _validate_native_candidate_queue(native_path, candidates,
                                                  path / "candidates/candidates.json",
                                                  binary_hashes)
    elif native_status not in (None, "not_requested") or native_path.exists():
        raise ValueError("unexpected native disassembly evidence")
    methods = (flow.get("trace") or {}).get("requested_methods", [])
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "investigated_ui_flow" or
            manifest.get("status") != "complete" or
            manifest.get("bundle_id") != bundle or
            manifest.get("device_id_sha256_prefix") != device_prefix or
            manifest.get("binary_sha256") not in binary_hashes or
            (candidates is not None and manifest.get("binary_sha256") !=
             candidates.get("binary_sha256")) or
            (queue is not None and manifest.get("binary_sha256") !=
             queue["record"].get("binary_sha256")) or
            manifest.get("ui_backend") != flow["manifest"].get("ui_backend") or
            bool(manifest.get("network_requested")) !=
            bool(flow["manifest"].get("network_requested")) or
            provider not in ("none", "ghidra-direct", "ghidra", "hopper") or
            (queue is not None and provider != queue["record"].get("provider")) or
            manifest.get("flow_status") != "complete" or
            manifest.get("candidate_status") !=
            ("complete" if candidates and candidates.get("candidates") else
             "no_candidates" if candidates else "not_requested") or
            manifest.get("rea_status") != ("not_requested" if queue is None else "complete") or
            manifest.get("source_script_sha256") !=
            sha256_file(path / "flow/playbook/playbook.json") or
            manifest.get("selected_methods") != methods or
            scout.get("used_methods") != methods or
            scout.get("binary_sha256") != manifest.get("binary_sha256") or
            (manifest.get("method_selection") == "runtime_view_heuristic" and
             (entry is None or scout.get("selection_basis") !=
              "runtime_visible_class_unique_action" or
              scout.get("selected_methods") != methods or not methods)) or
            (manifest.get("method_selection") != "runtime_view_heuristic" and
             scout.get("selection_basis") == "runtime_visible_class_unique_action") or
            (candidates is not None and candidates.get("bundle_id") != bundle) or
            (candidates is not None and candidates.get("device_id_sha256_prefix") != device_prefix) or
            (queue is not None and candidates is not None and
             sha256_file(path / "candidates/candidates.json") !=
             queue["record"].get("candidate_case_sha256")) or
            (candidates is not None and sha256_file(path / "flow/manifest.json") !=
             sha256_file(path / "candidates/sources/flow-01/manifest.json")) or
            (candidates is None and (provider in ("ghidra", "hopper") or methods != [] or
             flow.get("trace") is not None)) or
            (native is not None and native_status != native["record"]["status"]) or
            (native_status == "not_requested" and provider in ("none", "ghidra-direct") and
             candidates is not None and candidates.get("candidates"))):
        raise ValueError("investigation stage identity or source chain differs")
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    required = {"method-scout.json", "review-brief.md", "flow/manifest.json"}
    if entry_status is not None:
        required.add("entry-view/manifest.json")
    if candidates is not None:
        required |= {"candidates/manifest.json", "candidates/candidates.json"}
    elif (path / "candidates").exists():
        raise ValueError("UI-only investigation contains unexpected candidates")
    if queue is not None:
        required |= {"rea/manifest.json", "rea/queue.json"}
    elif (path / "rea").exists():
        raise ValueError("no-REA investigation contains unexpected REA output")
    if native is not None:
        required |= {"native/manifest.json", "native/index.json"}
    if direct is not None:
        required |= {"direct-ghidra/manifest.json", "direct-ghidra/queue.json"}
    if not required <= listed:
        raise ValueError("investigation evidence list is incomplete")
    return {"manifest": manifest, "flow": flow, "queue": queue, "native": native,
            "direct_ghidra": direct,
            "files": sorted(listed | {"manifest.json"})}


def _validate_app_investigation(path: Path, bundle: str, device_prefix: str,
                                binary_hashes: set, analysis_index_sha256: str) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("app investigation evidence hash mismatch")
    manifest = _read_json(path / "manifest.json")
    scripts = manifest.get("scripts")
    flows = manifest.get("flows")
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "investigated_app" or
            manifest.get("status") != "complete" or
            manifest.get("bundle_id") != bundle or
            manifest.get("device_id_sha256_prefix") != device_prefix or
            manifest.get("analysis_index_sha256") != analysis_index_sha256 or
            manifest.get("ui_backend") not in ("ios-mcp", "ictrl") or
            manifest.get("provider") not in ("none", "ghidra-direct", "ghidra", "hopper") or
            not isinstance(scripts, list) or not 1 <= len(scripts) <= 12 or
            not isinstance(flows, list) or len(scripts) != len(flows)):
        raise ValueError("app investigation identity or flow list differs")
    listed = {item.get("path") for item in manifest.get("evidence", [])
              if isinstance(item, dict)}
    required = set()
    for index, (script, flow) in enumerate(zip(scripts, flows), 1):
        child_name = f"flows/flow-{index:02d}"
        child_path = path / child_name
        child_manifest = child_path / "manifest.json"
        if (not isinstance(script, dict) or not isinstance(flow, dict) or
                flow.get("index") != index or
                flow.get("status") != "complete" or
                flow.get("script_sha256") != script.get("sha256") or
                flow.get("manifest") != child_name + "/manifest.json" or
                flow.get("manifest_sha256") != sha256_file(child_manifest)):
            raise ValueError("app investigation child identity differs")
        child = _validate_investigation(child_path, bundle, device_prefix, binary_hashes)
        if (child["manifest"].get("source_script_sha256") != script["sha256"] or
                bool(child["manifest"].get("network_requested")) !=
                bool(manifest.get("network_requested")) or
                child["manifest"].get("selected_methods") != flow.get("selected_methods") or
                child["manifest"].get("ui_backend") != manifest["ui_backend"] or
                child["manifest"].get("provider") != manifest["provider"] or
                child["manifest"].get("disabled_analyzer") !=
                manifest.get("disabled_analyzer")):
            raise ValueError("app investigation child metadata differs")
        required |= {child_name + "/" + name for name in child["files"]}
    if not required <= listed:
        raise ValueError("app investigation evidence list is incomplete")
    return {"manifest": manifest, "files": sorted(listed | {"manifest.json"})}


def _validate_runtime_probe(path: Path, bundle: str, device_prefix: str,
                            binary_hashes: set) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("runtime probe evidence hash mismatch")
    record = _read_json(path / "probe.json")
    if (record.get("status") != "complete" or record.get("bundle_id") != bundle or
            not device_prefix or record.get("device_id_sha256_prefix") != device_prefix or
            record.get("binary_sha256") not in binary_hashes or
            record.get("frontmost_before") != bundle or
            record.get("frontmost_after") != bundle):
        raise ValueError("runtime probe belongs to another device, app or binary")
    for name in ("before.jpg", "after.jpg"):
        expected = record.get("screenshot_" + name.split(".")[0] + "_sha256")
        if not expected or sha256_file(path / name) != expected:
            raise ValueError(f"runtime probe screenshot hash mismatch: {name}")
    manifest = _read_json(path / "manifest.json")
    names = {item["path"] for item in manifest.get("evidence", [])}
    if not {"probe.json", "before.jpg", "after.jpg", "hook.js"} <= names:
        raise ValueError("runtime probe lacks source evidence")
    return {"record": record, "files": sorted(names | {"manifest.json"})}


def _validate_findings(findings: dict, bundle: str, evidence_ids: set) -> None:
    if findings.get("schema_version") != 1 or findings.get("target_bundle_id") != bundle:
        raise ValueError("findings target bundle or schema does not match case")
    sections = findings.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("findings must contain at least one section")
    found = 0
    for section in sections:
        if not isinstance(section, dict) or not section.get("title"):
            raise ValueError("finding section lacks a title")
        for finding in section.get("findings", []):
            if not isinstance(finding, dict) or not finding.get("claim"):
                raise ValueError("finding lacks a claim")
            confidence = finding.get("confidence")
            refs = finding.get("evidence")
            if confidence not in CONFIDENCE or not isinstance(refs, list):
                raise ValueError("finding confidence or evidence list is invalid")
            if confidence != "unknown" and not refs:
                raise ValueError("observed or inferred finding requires evidence")
            if any(ref not in evidence_ids for ref in refs):
                raise ValueError(f"finding references unknown evidence: {refs}")
            found += 1
    if not found:
        raise ValueError("findings contain no claims")


def _validate_sandbox_diff(path: Path, bundle: str, device_prefix: str) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("sandbox difference evidence hash mismatch")
    data = _read_json(path / "changes.json")
    before = _read_json(path / "before.json")
    after = _read_json(path / "after.json")
    for record in (data, before, after):
        if (record.get("bundle_id") != bundle or
                record.get("device_id_sha256_prefix") != device_prefix):
            raise ValueError("sandbox difference belongs to another device or app")
    if before.get("depth_limit") != after.get("depth_limit") or \
            data.get("depth_limit") != before.get("depth_limit"):
        raise ValueError("sandbox difference depth differs from source snapshots")
    if data.get("changes") != compute_sandbox_changes(before, after):
        raise ValueError("sandbox difference does not match source metadata")
    manifest = _read_json(path / "manifest.json")
    names = {item["path"] for item in manifest.get("evidence", [])}
    if not {"changes.json", "before.json", "after.json", "report.md"} <= names:
        raise ValueError("sandbox difference lacks source evidence")
    return {"summary": data, "files": sorted(names | {"manifest.json"})}


def _validate_data_source(source: Path, bundle: str, analysis_hash: str) -> None:
    if (source / "report-index.json").is_file():
        source_index = _read_json(source / "report-index.json")
        same_source = (source_index.get("target_bundle_id") == bundle and
                       source_index.get("source_case_index_sha256") == analysis_hash)
    elif (source / "capture.json").is_file():
        capture = _read_json(source / "capture.json")
        same_source = (capture.get("kind") == "sandbox_file_capture" and
                       capture.get("bundle_id") == bundle and
                       capture.get("source_analysis_index_sha256") == analysis_hash and
                       validate_sandbox_file_capture(source))
    else:
        raise ValueError("data structure source must be a verified report or sandbox capture")
    if not same_source:
        raise ValueError("data structure source belongs to another app or analysis")


def _validate_sqlite_schema(path: Path, bundle: str, analysis_hash: str) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("SQLite schema case failed verification")
    if not validate_sqlite_schema_case(path):
        raise ValueError("SQLite schema differs from captured database")
    data = _read_json(path / "schema.json")
    _validate_data_source(Path(data["source_case"]), bundle, analysis_hash)
    return {"record": data, "files": ["manifest.json", "schema.json", "report.md"]}


def _validate_plist_schema(path: Path, bundle: str, analysis_hash: str) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError("property-list schema case failed verification")
    if not validate_plist_schema_case(path):
        raise ValueError("property-list schema differs from captured file")
    data = _read_json(path / "profile.json")
    _validate_data_source(Path(data["source_case"]), bundle, analysis_hash)
    return {"record": data, "files": ["manifest.json", "profile.json", "report.md"]}


def compose_report(case: Path, findings_path: Path, evidence_args: List[str],
                   output: Path, feature_spec: Optional[Path] = None) -> Path:
    """Validate identities, retain selected evidence, and render an agent-authored report."""
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"report output is not empty: {output}")
    case = case.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        valid_case = (case / "analysis-index.json").is_file() and verify_case(case)
    if not valid_case:
        raise ValueError("base analysis case failed hash verification")
    survey = _read_json(case / "survey/manifest.json")
    bundle = survey.get("bundle_id")
    if not isinstance(bundle, str) or not bundle:
        raise ValueError("case has no target bundle ID")
    for relative in ("acquired/static/ipa-index.json", "decrypted/static/ipa-index.json",
                     "decrypted/decryption.json"):
        path = case / relative
        if path.is_file() and _read_json(path).get("bundle_id") != bundle:
            raise ValueError(f"case artifact belongs to another bundle: {relative}")
    binary_hashes = _main_and_embedded_hashes(case)
    supplied: List[Tuple[str, Path, str, dict]] = []
    used = set()
    for argument in evidence_args:
        key, separator, raw_path = argument.partition("=")
        if not separator or not EVIDENCE_ID.fullmatch(key) or key.startswith("case.") or key in used:
            raise ValueError(f"evidence must be a unique ID=PATH: {argument}")
        used.add(key)
        path = Path(raw_path).resolve(strict=True)
        if path.is_dir() and (path / "summary.json").is_file():
            summary_kind = _read_json(path / "summary.json").get("kind")
            if summary_kind == "native_disassembly":
                kind, data = "native_disassembly", _validate_native_disassembly(
                    path, binary_hashes)
            elif summary_kind == "ghidra_direct_decompilation":
                kind, data = "ghidra_direct", _validate_ghidra_direct(
                    path, binary_hashes)
            else:
                kind, data = "rea", _validate_rea(path, binary_hashes)
        elif path.is_dir() and (path / "experiment.json").is_file():
            kind, data = "experiment", _validate_experiment(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
        elif path.is_dir() and (path / "probe.json").is_file():
            kind, data = "runtime_probe", _validate_runtime_probe(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
        elif path.is_dir() and (path / "changes.json").is_file() and (path / "manifest.json").is_file():
            kind, data = "sandbox_diff", _validate_sandbox_diff(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""))
        elif path.is_dir() and (path / "schema.json").is_file() and (path / "manifest.json").is_file():
            kind, data = "sqlite_schema", _validate_sqlite_schema(
                path, bundle, sha256_file(case / "analysis-index.json"))
        elif path.is_dir() and (path / "profile.json").is_file() and (path / "manifest.json").is_file():
            kind, data = "plist_schema", _validate_plist_schema(
                path, bundle, sha256_file(case / "analysis-index.json"))
        elif path.is_dir() and (path / "manifest.json").is_file() and (path / "playbook.json").is_file():
            kind, data = "playbook", _validate_playbook(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""))
        elif path.is_dir() and (path / "manifest.json").is_file() and (path / "view-tree.json").is_file():
            kind, data = "view_tree", _validate_view_tree(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""))
        elif path.is_dir() and (path / "manifest.json").is_file() and \
                (path / "playbook").is_dir() and (path / "view-tree").is_dir():
            kind, data = "flow_capture", _validate_flow_capture(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
        elif path.is_dir() and (path / "manifest.json").is_file() and \
                (path / "playbook").is_dir() and (path / "network/network.json").is_file():
            kind, data = "network_flow", validate_network_flow(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""))
        elif path.is_dir() and (path / "queue.json").is_file() and \
                (path / "sources/candidates/candidates.json").is_file():
            queue_kind = _read_json(path / "queue.json").get("kind")
            if queue_kind == "ghidra_direct_candidate_queue":
                kind, data = "ghidra_direct_queue", _validate_ghidra_direct_queue(
                    path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
            else:
                kind, data = "rea_queue", _validate_rea_queue(
                    path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
        elif path.is_dir() and (path / "bridge-map.json").is_file() and \
                (path / "sources/queue/queue.json").is_file():
            kind, data = "rea_bridge", _validate_rea_bridge(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
        elif path.is_dir() and (path / "branch-map.json").is_file() and \
                (path / "manifest.json").is_file():
            kind, data = "branch_map", validate_branch_map(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
        elif path.is_dir() and (path / "method-scout.json").is_file() and \
                (path / "flow").is_dir() and (path / "manifest.json").is_file():
            kind, data = "investigation", _validate_investigation(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""), binary_hashes)
        elif path.is_dir() and (path / "flows").is_dir() and \
                (path / "manifest.json").is_file():
            kind, data = "app_investigation", _validate_app_investigation(
                path, bundle, str(survey.get("device_id_sha256_prefix") or ""),
                binary_hashes, sha256_file(case / "analysis-index.json"))
        elif path.is_dir() and (path / "ipa-index.json").is_file() and \
                (path / "manifest.json").is_file():
            kind, data = "ipa_static_index", _validate_ipa_static(path, bundle, case)
        elif path.is_file():
            kind, data = "file", {}
        else:
            raise ValueError(f"unsupported evidence input: {path}")
        supplied.append((key, path, kind, data))
    case_sources = {
        "case.survey": "survey/manifest.json", "case.ui": "survey/ui.json",
        "case.survey_report": "survey/report.md",
        "case.static": "acquired/static/ipa-index.json",
        "case.static_report": "acquired/static/ipa-report.md",
        "case.objc": "acquired/static/objc-index.json",
        "case.objc_report": "acquired/static/objc-report.md",
        "case.decrypted_static": "decrypted/static/ipa-index.json",
        "case.decrypted_static_report": "decrypted/static/ipa-report.md",
        "case.decrypted_objc": "decrypted/static/objc-index.json",
        "case.decrypted_objc_report": "decrypted/static/objc-report.md",
        "case.sandbox": "sandbox-index.json",
        "case.decryption": "decrypted/decryption.json",
    }
    for screenshot in ("survey/screenshot.jpg", "survey/screenshot.png"):
        if (case / screenshot).is_file():
            case_sources["case.screenshot"] = screenshot
            break
    case_sources = {key: relative for key, relative in case_sources.items()
                    if (case / relative).is_file()}
    # Saved OCR must point to an imported screenshot, not an unreviewed path
    # elsewhere on the host. Recompute the image and crop hashes before citing it.
    image_inputs = [case / relative for relative in case_sources.values()
                    if Path(relative).suffix.lower() in (".jpg", ".jpeg", ".png")]
    for _, path, kind, data in supplied:
        if kind == "file" and path.suffix.lower() in (".jpg", ".jpeg", ".png"):
            image_inputs.append(path)
        elif kind in ("playbook", "runtime_probe", "sandbox_diff", "view_tree", "flow_capture", "network_flow", "rea_queue", "ghidra_direct_queue", "rea_bridge", "investigation", "app_investigation"):
            image_inputs.extend(checked_path(path, name) for name in data["files"]
                                if Path(name).suffix.lower() in (".jpg", ".jpeg", ".png"))
        elif kind == "branch_map":
            image_inputs.extend(source for root in data["source_paths"]
                                for source in root.rglob("*")
                                if source.is_file() and source.suffix.lower() in (".jpg", ".jpeg", ".png"))
        elif kind == "experiment":
            image_inputs.extend(path / name for name in ("before.jpg", "after.jpg"))
    image_hashes = {sha256_file(path): path for path in image_inputs}
    for _, path, kind, data in supplied:
        if kind != "file" or path.suffix.lower() != ".json":
            continue
        content = _read_json(path)
        if content.get("kind") != "saved_screenshot_ocr":
            continue
        source = image_hashes.get(content.get("source_sha256"))
        if source is None or not verify_ocr_source(content, source):
            raise ValueError(f"saved OCR source screenshot or crop hash is not imported: {path}")
        data["source_verified"] = True
    findings = _read_json(findings_path)
    _validate_findings(findings, bundle, set(case_sources) | used)
    specification = _read_json(feature_spec) if feature_spec else None
    if specification is not None and specification.get("target_bundle_id") != bundle:
        raise ValueError("feature spec target bundle does not match case")
    if specification is not None:
        flows = specification.get("flows")
        available_evidence = set(case_sources) | used
        if (not isinstance(flows, list) or not flows or
                any(not isinstance(flow, dict) or not flow.get("id") or
                    not flow.get("entry") or not flow.get("expected") or
                    not flow.get("verification") or
                    not isinstance(flow.get("evidence"), list) or not flow["evidence"] or
                    any(not isinstance(ref, str) or ref not in available_evidence
                        for ref in flow["evidence"])
                    for flow in flows) or
                len({flow["id"] for flow in flows}) != len(flows)):
            raise ValueError("feature spec needs unique flows with entry, expected, verification and imported evidence")

    output.mkdir(parents=True, exist_ok=True)
    artifacts: Dict[str, dict] = {}
    evidence: Dict[str, dict] = {}
    for key, relative in case_sources.items():
        target = output / "evidence" / key / Path(relative).name
        _copy_file(case / relative, target, output, artifacts, key)
        evidence[key] = {"kind": "case", "path": artifacts[key]["path"],
                         "sha256": artifacts[key]["sha256"]}
    for key, path, kind, data in supplied:
        files = (["summary.json", "evidence.json", "pseudocode.txt"] if kind == "rea" else
                 data["files"] if kind == "native_disassembly" else
                 data["files"] if kind == "ghidra_direct" else
                 ["experiment.json", "before.jpg", "after.jpg"] if kind == "experiment" else
                 data["files"] if kind == "runtime_probe" else
                 data["files"] if kind == "sandbox_diff" else
                 data["files"] if kind == "sqlite_schema" else
                 data["files"] if kind == "plist_schema" else
                 data["files"] if kind == "playbook" else
                 data["files"] if kind == "ipa_static_index" else
                 data["files"] if kind == "view_tree" else
                 data["files"] if kind == "flow_capture" else
                 data["files"] if kind == "network_flow" else
                 data["files"] if kind == "rea_queue" else
                 data["files"] if kind == "ghidra_direct_queue" else
                 data["files"] if kind == "rea_bridge" else
                 data["files"] if kind == "branch_map" else
                 data["files"] if kind == "investigation" else
                 data["files"] if kind == "app_investigation" else
                 [path.name])
        for name in files:
            source = checked_path(path, name) if path.is_dir() else path
            target = output / "evidence" / key / name
            _copy_file(source, target, output, artifacts, key + "/" + name)
        if kind == "branch_map":
            binary = data["binary_path"]
            _copy_file(binary, output / "evidence" / key / "sources/binary",
                       output, artifacts, key + "/sources/binary")
            replay_sources = []
            for index, source_root in enumerate(data["source_paths"], 1):
                replay_sources.append({"path": f"sources/flow-{index:02d}",
                                       "manifest_sha256": sha256_file(source_root / "manifest.json")})
                flow_manifest = _read_json(source_root / "manifest.json")
                source_names = {"manifest.json"} | {
                    item["path"] for item in flow_manifest["evidence"]}
                for name in sorted(source_names):
                    source = checked_path(source_root, name)
                    relative = f"sources/flow-{index:02d}/" + name
                    _copy_file(source, output / "evidence" / key / relative,
                               output, artifacts, key + "/" + relative)
            replay = {"schema_version": 1, "kind": "branch_map_replay_sources",
                      "source_map_sha256": sha256_file(path / "branch-map.json"),
                      "binary": {"path": "sources/binary", "sha256": sha256_file(binary)},
                      "flows": replay_sources,
                      "note": "Paths are relative to this evidence directory; rerun branch-map with the copied binary and flows to reproduce observations."}
            replay_path = output / "evidence" / key / "replay-sources.json"
            replay_path.write_text(json.dumps(replay, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
            artifacts[key + "/replay-sources.json"] = {
                "path": str(replay_path.relative_to(output)),
                "sha256": sha256_file(replay_path)}
        primary = ("summary.json" if kind in ("rea", "native_disassembly", "ghidra_direct") else
                   "experiment.json" if kind == "experiment"
                   else "probe.json" if kind == "runtime_probe"
                   else "changes.json" if kind == "sandbox_diff"
                   else "schema.json" if kind == "sqlite_schema"
                   else "profile.json" if kind == "plist_schema"
                   else "ipa-index.json" if kind == "ipa_static_index"
                   else "manifest.json" if kind in ("playbook", "view_tree", "flow_capture", "network_flow", "rea_queue", "ghidra_direct_queue", "rea_bridge", "branch_map", "investigation", "app_investigation")
                   else path.name)
        evidence[key] = {"kind": kind, "path": artifacts[key + "/" + primary]["path"],
                         "sha256": artifacts[key + "/" + primary]["sha256"]}
        if kind == "file":
            evidence[key]["identity_verified"] = bool(data.get("source_verified"))
        if kind == "ipa_static_index":
            evidence[key].update({"bundle_id": data["index"]["bundle_id"],
                                  "ipa_sha256": data["index"]["ipa_sha256"],
                                  "catalog_count": len(data["index"]["asset_catalogs"])})
        if kind == "rea":
            evidence[key].update({"evidence_id": data["evidence_id"],
                                  "binary_sha256": data["binary_sha256"],
                                  "provider": data["provider"],
                                  "procedure": data["resolved_procedure"]})
        elif kind == "native_disassembly":
            evidence[key].update({"binary_sha256": data["summary"]["binary_sha256"],
                                  "address": data["summary"]["address"],
                                  "stop_address": data["summary"]["stop_address"],
                                  "truncated": data["summary"]["truncated"],
                                  "instruction_count": data["summary"]["instruction_count"]})
        elif kind == "ghidra_direct":
            evidence[key].update({"binary_sha256": data["summary"]["binary_sha256"],
                                  "address": data["summary"]["address"],
                                  "function_name": data["summary"]["function_name"],
                                  "script_sha256": data["summary"]["script_sha256"]})
        elif kind == "ghidra_direct_queue":
            evidence[key].update({"binary_sha256": data["record"]["binary_sha256"],
                                  "function_count": len(data["record"]["results"])})
        elif kind == "experiment":
            evidence[key].update({"bundle_id": data["bundle_id"],
                                  "requested_methods": data["requested_methods"],
                                  "call_counts": data["call_counts"],
                                  "frontmost_after": data.get("frontmost_after")})
        elif kind == "runtime_probe":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "binary_sha256": data["record"]["binary_sha256"],
                                  "frontmost_after": data["record"]["frontmost_after"]})
        elif kind == "sandbox_diff":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "counts": data["summary"].get("counts")})
        elif kind == "sqlite_schema":
            evidence[key].update({"bundle_id": bundle,
                                  "source_db_sha256": data["record"]["source_sha256"],
                                  "table_count": len(data["record"]["schema"]["tables"])})
        elif kind == "plist_schema":
            evidence[key].update({"bundle_id": bundle,
                                  "source_plist_sha256": data["record"]["source_sha256"],
                                  "field_count": len(data["record"]["structure"]["fields"])})
        elif kind == "playbook":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "scenario_id": data["manifest"]["scenario_id"],
                                  "ui_backend": data["manifest"]["ui_backend"]})
        elif kind == "view_tree":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "node_count": data["manifest"]["node_count"],
                                  "truncated": data["manifest"]["truncated"]})
        elif kind == "flow_capture":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "scenario_id": data["manifest"]["scenario_id"],
                                  "ui_backend": data["manifest"]["ui_backend"],
                                  "node_count": data["manifest"]["node_count"]})
            if data["network"] is not None:
                evidence[key]["network_event_count"] = len(data["network"]["events"])
        elif kind == "network_flow":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "ui_backend": data["manifest"]["ui_backend"],
                                  "event_count": len(data["trace"]["events"]),
                                  "dropped_events": data["trace"]["dropped_events"]})
        elif kind == "rea_queue":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "binary_sha256": data["record"]["binary_sha256"],
                                  "provider": data["record"]["provider"],
                                  "function_count": len(data["record"]["results"])})
        elif kind == "rea_bridge":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "binary_sha256": data["record"]["binary_sha256"],
                                  "provider": data["record"]["provider"],
                                  "followed_function_count": len(data["record"]["results"])})
        elif kind == "branch_map":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "binary_sha256": data["record"]["binary_sha256"],
                                  "method": data["record"]["method"],
                                  "source_flow_count": len(data["source_paths"]),
                                  "observed_tap_count": len(data["record"]["observations"])})
        elif kind == "investigation":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "binary_sha256": data["manifest"]["binary_sha256"],
                                  "provider": data["manifest"]["provider"],
                                  "selected_methods": data["manifest"]["selected_methods"],
                                  "function_count": (len(data["queue"]["record"]["results"])
                                                     if data["queue"] else
                                                     len(data["direct_ghidra"]["record"]["results"])
                                                     if data["direct_ghidra"] else 0),
                                  "native_function_count": (data["native"]["complete_count"]
                                                            if data["native"] else 0)})
        elif kind == "app_investigation":
            evidence[key].update({"bundle_id": bundle,
                                  "device_id_sha256_prefix": survey.get("device_id_sha256_prefix"),
                                  "provider": data["manifest"]["provider"],
                                  "flow_count": len(data["manifest"]["flows"])})
    _copy_file(findings_path, output / "findings.json", output, artifacts, "findings")
    if feature_spec:
        _copy_file(feature_spec, output / "feature-spec.json", output, artifacts, "feature_spec")

    app = _read_json(case / "survey/app.json")
    device = survey.get("device", {})
    lines = ["# " + str(findings.get("title") or bundle), "",
             f"- App：`{bundle}` / {app.get('CFBundleShortVersionString', '未知')}",
             f"- 设备：{device.get('ProductType', '未知')} / iOS {device.get('ProductVersion', '未知')}",
             f"- UI 归属：{survey.get('ui_attribution', {}).get('status', '未验证')}",
             "- 结论等级：直接观察 / 多证据推断 / 待验证", ""]
    if findings.get("review_status") == "needs_semantic_review":
        lines += ["> 事实草稿：尚需审阅关键函数、数据流和功能规格；不得作为完整逆向结论或直接复刻输入。", ""]
    for section in findings["sections"]:
        lines += ["## " + str(section["title"]), ""]
        for finding in section.get("findings", []):
            refs = finding["evidence"]
            links = ", ".join(f"[{ref}]({evidence[ref]['path']})" for ref in refs)
            lines += [f"### {finding['claim']}", "",
                      f"**判断：{CONFIDENCE[finding['confidence']]}。** " +
                      (f"证据：{links}。" if links else "当前缺少直接证据。"), ""]
            if finding.get("explanation"):
                lines += [str(finding["explanation"]), ""]
            if finding.get("limitation"):
                lines += ["边界：" + str(finding["limitation"]), ""]
    lines += ["## 函数与动态实验索引", ""]
    supplied_by_id = {key: (path, kind, data) for key, path, kind, data in supplied}
    for key, item in evidence.items():
        if item["kind"] == "rea":
            procedure = item["procedure"]
            stem = str(Path(item["path"]).parent)
            lines.append(f"- [{key}]({item['path']})：`{procedure.get('name')}` "
                         f"`{procedure.get('address')}`，{item['provider'].get('id')} "
                         f"{item['provider'].get('version')}，`{item['evidence_id']}`。"
                         f"[完整证据]({stem}/evidence.json) · [伪代码]({stem}/pseudocode.txt)")
        elif item["kind"] == "ghidra_direct":
            stem = str(Path(item["path"]).parent)
            facts_link = (f" · [函数关系]({stem}/function-facts.json)"
                          if (output / stem / "function-facts.json").is_file() else "")
            lines.append(f"- [{key}]({item['path']})：Copy APP 直连 Ghidra 函数 "
                         f"`{item['function_name']}` at `{item['address']}`；"
                         f"[伪代码]({stem}/pseudocode.txt){facts_link}。")
        elif item["kind"] == "ghidra_direct_queue":
            source_path, _, queue_data = supplied_by_id[key]
            stem = str(Path(item["path"]).parent)
            lines.append(f"- [{key}]({stem}/queue.json)：Copy APP 直连 Ghidra，"
                         f"{item['function_count']} 个函数。")
            for selected, result in zip(queue_data["record"]["selected"],
                                        queue_data["record"]["results"]):
                summary = _read_json(source_path / result["summary"])
                function_dir = str(Path(result["summary"]).parent)
                origin = (f"从 `{selected['source_address']}` 静态直接跟随；"
                          if selected.get("origin") == "native_direct_follow" else
                          f"第 {selected['flow_step']} 步在 `{selected['branch_site']}` "
                          f"观察到 `{selected['register']}` 指向该函数；"
                          if selected.get("origin") == "runtime_indirect_target" else
                          "运行时方法候选；")
                lines.append(f"  - `{result['address']}` `{summary['function_name']}`："
                             f"{origin}[伪代码]({stem}/{function_dir}/pseudocode.txt)"
                             + (f" · [函数关系]({stem}/{function_dir}/function-facts.json)"
                                if (source_path / function_dir / "function-facts.json").is_file()
                                else "") + "。")
        elif item["kind"] == "native_disassembly":
            stem = str(Path(item["path"]).parent)
            lines.append(f"- [{key}]({item['path']})：`{item['address']}` 的有界原生汇编；"
                         f"[指令]({stem}/assembly.txt)。")
        elif item["kind"] == "investigation":
            stem = str(Path(item["path"]).parent)
            lines.append(f"- [{key}]({item['path']})：一次原版流程，"
                         f"[逐步证据与函数来源]({stem}/review-brief.md)。")
        elif item["kind"] == "experiment":
            counts = ", ".join(f"`{method}` {count} 次" for method, count in
                               zip(item["requested_methods"], item["call_counts"]))
            lines.append(f"- [{key}]({item['path']})：{counts}；之后前台 "
                         f"`{item['frontmost_after']}`。")
        elif item["kind"] == "branch_map":
            stem = str(Path(item["path"]).parent)
            lines.append(f"- [{key}]({stem}/branch-map.json)："
                         f"{item['source_flow_count']} 条流程、{item['observed_tap_count']} 个点击窗口，"
                         f"方法 `{item['method']}`。[映射表]({stem}/report.md)；"
                         f"[重放来源]({stem}/replay-sources.json)保存报告内的流程与二进制副本路径。")
    lines += ["", "反编译伪代码是工具生成的解释材料，不是原作者源码；方法计数不包含参数与调用顺序。",
              "单独导入的截图或数据文件仅核对内容哈希；其设备、App 和采集时点需由采集记录或人工证据进一步确认。", ""]
    static_path = (case / "decrypted/static/ipa-index.json" if
                   (case / "decrypted/static/ipa-index.json").is_file() else
                   case / "acquired/static/ipa-index.json")
    if static_path.is_file():
        static = _read_json(static_path)
        binaries = static.get("binaries", [])
        main = next((item for item in binaries if item.get("path", "").endswith(
            "/" + str(static.get("executable", "")))), binaries[0] if binaries else {})
        lines += ["## 二进制与依赖附录", "",
                  "- 解析对象：" + ("解密后分析 IPA；原始采集索引也单独保留。" if
                                  "case.decrypted_static" in evidence else "安装包快照。"),
                  f"- 包内路径：{static.get('file_count', '未知')}；Mach-O：{len(binaries)}；"
                  f"嵌入 Framework：{len(static.get('frameworks', []))}；"
                  f"扩展：{len(static.get('extensions', []))}。",
                  f"- 主程序 SHA-256：`{main.get('sha256', '未知')}`；"
                  f"加密加载命令：`{main.get('encryption_status', '未知')}`。", ""]
        for library in main.get("linked_libraries", []):
            lines.append(f"- `{library}`")
        lines.append("")
    objc_path = (case / "decrypted/static/objc-index.json" if
                 (case / "decrypted/static/objc-index.json").is_file() else
                 case / "acquired/static/objc-index.json")
    if objc_path.is_file():
        objc = _read_json(objc_path)
        classes = objc.get("classes", [])
        objc_report = ("case.decrypted_objc_report" if "case.decrypted_objc_report" in evidence
                       else "case.objc_report" if "case.objc_report" in evidence else
                       "case.decrypted_objc" if "case.decrypted_objc" in evidence else "case.objc")
        lines += ["## 本地定义类附录", "",
                  f"共 {len(classes)} 类；方法签名、类型编码和地址见"
                  f" [Objective-C 索引]({evidence[objc_report]['path']})。", "",
                  "| 类 | 实例方法 | 类方法 |", "| --- | ---: | ---: |"]
        ranked = sorted(classes, key=lambda item: len(item.get("instance_methods", [])) +
                        len(item.get("class_methods", [])), reverse=True)
        for item in ranked[:60]:
            lines.append(f"| `{item['name']}` | {len(item.get('instance_methods', []))} | "
                         f"{len(item.get('class_methods', []))} |")
        if len(ranked) > 60:
            lines.append(f"\n此表按方法数量展示前 60 类；其余 {len(ranked)-60} 类见完整索引。")
        lines.append("")
    lines += [
              "## 附录与复刻规格", "", "- [基础采集报告](evidence/case.survey/manifest.json)",
              "- [静态索引](evidence/case.static/ipa-index.json)" if "case.static" in evidence else
              "- 静态索引：未采集", "- [Objective-C 索引](evidence/case.objc/objc-index.json)" if
              "case.objc" in evidence else "- Objective-C 索引：未采集"]
    if "case.decrypted_static" in evidence:
        lines.append("- [解密后静态索引](evidence/case.decrypted_static/ipa-index.json)")
    if "case.decrypted_objc" in evidence:
        lines.append("- [解密后 Objective-C 索引](evidence/case.decrypted_objc/objc-index.json)")
    if feature_spec:
        label = ("待审复刻规格" if specification.get("review_status") == "needs_semantic_review"
                 else "可执行复刻规格")
        lines.append(f"- [{label}](feature-spec.json)")
    lines += ["", "所有纳入的证据文件及 SHA-256 见 `report-index.json`。", ""]
    report = output / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    artifacts["report"] = {"path": "report.md", "sha256": sha256_file(report)}
    index = {"schema_version": 1, "target_bundle_id": bundle,
             "source_case": str(case),
             "source_case_index_sha256": sha256_file(case / "analysis-index.json"),
             "evidence": evidence, "artifacts": artifacts}
    (output / "report-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    return report
