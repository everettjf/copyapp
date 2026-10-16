"""Hash-bound, bounded ARM64 disassembly using the local Xcode toolchain.

This is assembly evidence, not decompiled source or a semantic interpretation.
REA is never imported or invoked by this module.
"""

import json
import io
import re
import shutil
import struct
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional, Tuple

from copyapp.ipa import MAX_BINARY, inspect_macho
from copyapp.objc import MachOImage
from copyapp.verify import sha256_file, verify_case


LC_FUNCTION_STARTS = 0x26
MAX_FUNCTION_STARTS = 1_000_000
MAX_TOOL_OUTPUT = 512 * 1024
INSTRUCTION = re.compile(r"^([0-9a-fA-F]+):\s", re.MULTILINE)
DIRECT_CALL = re.compile(
    r"^([0-9a-fA-F]+):\s+[0-9a-fA-F]{8}\s+bl\s+0x([0-9a-fA-F]+)"
    r"(?:\s+<([^>\n]{1,300})>)?", re.MULTILINE)
DIRECT_BRANCH = re.compile(
    r"^([0-9a-fA-F]+):\s+[0-9a-fA-F]{8}\s+(b(?:\.[a-z]+)?)\s+"
    r"0x([0-9a-fA-F]+)", re.MULTILINE)
MAX_DIRECT_CALLS = 256


def is_arm64_blr(image: MachOImage, address: int, register: str) -> bool:
    """Check a disassembled BLR against the acquired Mach-O instruction bytes."""
    if (not re.fullmatch(r"x(?:[0-9]|[12][0-9]|30)", register) or
            address % 4):
        return False
    return image.unpack("<I", address)[0] == (0xd63f0000 | (int(register[1:]) << 5))


def direct_calls(assembly: str) -> tuple[list[dict], bool]:
    """Extract only literal ARM64 BL edges; dynamic dispatch remains unknown."""
    found = []
    truncated = False
    for match in DIRECT_CALL.finditer(assembly):
        if len(found) >= MAX_DIRECT_CALLS:
            truncated = True
            break
        symbol = match.group(3)
        selector = (symbol[len("_objc_msgSend$"):] if
                    symbol and symbol.startswith("_objc_msgSend$") and
                    "+0x" not in symbol else None)
        found.append({"site": f"0x{int(match.group(1), 16):x}",
                      "target": f"0x{int(match.group(2), 16):x}",
                      "symbol": symbol,
                      "objc_selector_stub": selector})
    return found, truncated


def direct_branches(assembly: str) -> list[dict]:
    """Extract literal B/B.cond edges, without guessing computed BR targets."""
    return [{"site": f"0x{int(match.group(1), 16):x}",
             "mnemonic": match.group(2),
             "target": f"0x{int(match.group(3), 16):x}"}
            for match in DIRECT_BRANCH.finditer(assembly)]


def rank_native_candidates(options: list, digest: str, limit: int) -> list[dict]:
    """Rank only hash-bound candidates with real nonzero runtime observations."""
    scored = []
    seen = set()
    for item in options:
        if not isinstance(item, dict):
            raise ValueError("candidate entry is invalid")
        address = item.get("static_address")
        observations = item.get("observations")
        if (not isinstance(address, str) or
                not re.fullmatch(r"0x[0-9a-fA-F]+", address) or
                int(address, 16) in seen or item.get("binary_sha256") != digest or
                not isinstance(observations, list) or not observations):
            raise ValueError("candidate address, binary or observations are invalid")
        seen.add(int(address, 16))
        current = direct = 0
        for hit in observations:
            if not isinstance(hit, dict):
                raise ValueError("candidate observation is invalid")
            calls = hit.get("calls")
            static_calls = (hit.get("static_entry") or {}).get("calls", 0)
            if (type(calls) is not int or calls < 0 or
                    type(static_calls) is not int or static_calls < 0):
                raise ValueError("candidate call count is invalid")
            current += calls
            direct += static_calls
        if not current and not direct:
            raise ValueError("candidate has no observed calls")
        scored.append(((-direct, -current, int(address, 16)), item))
    return [item for _, item in sorted(scored, key=lambda pair: pair[0])[:limit]]


def _function_starts(image: MachOImage) -> list[int]:
    """Decode LC_FUNCTION_STARTS as VM addresses relative to the image base."""
    blob = image.data
    ncmds = struct.unpack_from("<I", blob, 16)[0]
    cursor = 32
    for _ in range(ncmds):
        command, size = struct.unpack_from("<II", blob, cursor)
        if command == LC_FUNCTION_STARTS:
            if size < 16:
                raise ValueError("short LC_FUNCTION_STARTS command")
            offset, length = struct.unpack_from("<II", blob, cursor + 8)
            if offset + length > len(blob) or length > 8 * 1024 * 1024:
                raise ValueError("function starts exceed Mach-O bounds")
            starts = []
            delta = 0
            value = 0
            shift = 0
            for byte in blob[offset:offset + length]:
                value |= (byte & 0x7f) << shift
                if byte & 0x80:
                    shift += 7
                    if shift > 63:
                        raise ValueError("invalid function-start delta")
                    continue
                if value == 0:
                    break
                delta += value
                starts.append(image.base + delta)
                if len(starts) > MAX_FUNCTION_STARTS:
                    raise ValueError("too many function starts")
                value = shift = 0
            else:
                if shift:
                    raise ValueError("truncated function-start delta")
            return starts
        cursor += size
    return []


def _bounds(image: MachOImage, address: int, max_bytes: int) -> Tuple[int, str, bool]:
    sections = [(segment, base, base + length) for (segment, section),
                (base, length, _) in image.sections.items()
                if section == "__text" and segment in ("__TEXT", "__TEXT_EXEC")]
    containing = [(segment, start, end) for segment, start, end in sections
                  if start <= address < end]
    if len(containing) != 1 or address % 4:
        raise ValueError("address is not aligned inside a unique executable __text section")
    _, _, section_end = containing[0]
    starts = _function_starts(image)
    exact = address in starts
    next_start = next((item for item in starts if item > address), None)
    end = min(section_end, address + max_bytes,
              next_start if next_start is not None else section_end)
    if end <= address:
        raise ValueError("empty executable window")
    boundary = "next_function_start" if exact and next_start == end else "bounded_window"
    return end, boundary, boundary != "next_function_start"


def local_direct_targets(image: MachOImage, starts: set[int],
                         summary: dict, seen: set[int]) -> list[int]:
    """Return exact function starts reached by literal BL or B in local text."""
    text_ranges = [(base, base + length) for (segment, section),
                   (base, length, _) in image.sections.items()
                   if section == "__text" and segment in ("__TEXT", "__TEXT_EXEC")]
    targets = set()
    for edge in summary.get("direct_calls", []) + summary.get("direct_branches", []):
        target = int(edge["target"], 16)
        if (target in starts and target not in seen and
                any(start <= target < end for start, end in text_ranges)):
            targets.add(target)
    return sorted(targets)


def disassemble_native_function(binary: Path, digest: str, address: str,
                                output: Path, max_bytes: int = 1024,
                                tool: Optional[Path] = None,
                                timeout: int = 30) -> Path:
    """Save a bounded instruction window for an exact acquired Mach-O."""
    if not 16 <= max_bytes <= 4096 or max_bytes % 4:
        raise ValueError("max_bytes must be a multiple of four between 16 and 4096")
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("address must be hexadecimal")
    binary = binary.resolve(strict=True)
    if binary.stat().st_size > MAX_BINARY:
        raise ValueError("binary exceeds analysis size limit")
    if sha256_file(binary) != digest:
        raise ValueError("binary SHA-256 differs from requested digest")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    image = MachOImage(binary.read_bytes())
    if inspect_macho(image.data).get("encrypted_on_disk") is True:
        raise ValueError("selected Mach-O is still marked encrypted on disk")
    start = int(address, 16)
    end, boundary, truncated = _bounds(image, start, max_bytes)
    if tool is None:
        xcrun = shutil.which("xcrun")
        if not xcrun:
            raise FileNotFoundError("Xcode llvm-objdump is unavailable")
        found = subprocess.run([xcrun, "--find", "llvm-objdump"],
                               capture_output=True, text=True, timeout=timeout,
                               check=True).stdout.strip()
        tool = Path(found)
    tool = tool.resolve(strict=True)
    command = [str(tool), "--disassemble", f"--start-address=0x{start:x}",
               f"--stop-address=0x{end:x}", str(binary)]
    result = subprocess.run(command, capture_output=True, text=True,
                            timeout=timeout, check=True)
    assembly = result.stdout
    if len(assembly.encode("utf-8")) > MAX_TOOL_OUTPUT:
        raise ValueError("disassembler output exceeds bound")
    addresses = [int(match, 16) for match in INSTRUCTION.findall(assembly)]
    if (not addresses or addresses[0] != start or
            any(item < start or item >= end or item % 4 for item in addresses) or
            addresses != sorted(set(addresses))):
        raise ValueError("disassembler returned an unexpected instruction range")
    output.mkdir(parents=True, exist_ok=True)
    text_path = output / "assembly.txt"
    text_path.write_text(assembly, encoding="utf-8")
    calls, calls_truncated = direct_calls(assembly)
    branches = direct_branches(assembly)
    summary = {"schema_version": 1, "kind": "native_disassembly",
               "status": "complete", "binary_path": str(binary),
               "binary_sha256": digest, "address": f"0x{start:x}",
               "stop_address": f"0x{end:x}", "max_bytes": max_bytes,
               "boundary": boundary, "truncated": truncated,
               "instruction_count": len(addresses),
               "direct_calls": calls, "direct_calls_truncated": calls_truncated,
               "direct_branches": branches,
               "tool": str(tool), "tool_name": "llvm-objdump",
               "assembly_sha256": sha256_file(text_path),
               "limitation": "Assembly only; a bounded window may omit instructions and does not establish runtime execution or original source."}
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    manifest = {"schema_version": 1, "kind": "native_disassembly",
                "status": "complete", "evidence": [
                    {"path": "assembly.txt", "sha256": sha256_file(text_path)},
                    {"path": "summary.json", "sha256": sha256_file(summary_path)}]}
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary_path


def disassemble_native_candidates(candidates_dir: Path, output: Path,
                                  limit: int = 4, max_bytes: int = 1024,
                                  timeout: int = 30, follow_limit: int = 4,
                                  follow_depth: int = 2) -> Path:
    """Attempt bounded assembly for verified static candidates; retain failures."""
    if not 1 <= limit <= 32:
        raise ValueError("limit must be between 1 and 32")
    if not 0 <= follow_limit <= 16 or not 0 <= follow_depth <= 4:
        raise ValueError("follow_limit must be 0–16 and follow_depth must be 0–4")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    with redirect_stdout(io.StringIO()):
        if not verify_case(candidates_dir):
            raise ValueError("candidate evidence hash mismatch")
    source_path = candidates_dir / "candidates.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    digest = source.get("binary_sha256")
    binary = Path(source.get("binary_path", ""))
    if (source.get("kind") != "runtime_static_candidates" or
            not isinstance(digest, str) or
            not re.fullmatch(r"[a-f0-9]{64}", digest) or
            not binary.is_file() or binary.stat().st_size > MAX_BINARY or
            sha256_file(binary) != digest):
        raise ValueError("candidate case has no matching analysis binary")
    options = source.get("candidates")
    if not isinstance(options, list) or not options:
        raise ValueError("candidate case has no function addresses")

    selected = rank_native_candidates(options, digest, limit)
    image = MachOImage(binary.read_bytes())
    starts = set(_function_starts(image))
    output.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": 1, "kind": "native_candidate_queue",
              "candidate_case_sha256": sha256_file(source_path),
              "binary_sha256": digest, "limit": limit,
              "max_bytes": max_bytes, "follow_limit": follow_limit,
              "follow_depth": follow_depth, "results": [],
              "decisions": [], "followed": []}
    seen = {int(item["static_address"], 16) for item in selected}
    for index, item in enumerate(selected, 1):
        address = item.get("static_address")
        if (not isinstance(address, str) or
                item.get("binary_sha256") != digest or
                not re.fullmatch(r"0x[0-9a-fA-F]+", address)):
            raise ValueError("candidate address or binary identity is invalid")
        target = output / f"function-{index:02d}"
        result = {"index": index, "address": address,
                  "class": item.get("class"), "selector": item.get("selector")}
        try:
            summary = disassemble_native_function(binary, digest, address, target,
                                                  max_bytes, timeout=timeout)
            result.update(status="complete", summary=str(summary.relative_to(output)))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            result.update(status="unavailable", error={"type": type(exc).__name__,
                                                       "message": str(exc)[:300]})
        record["results"].append(result)
    for root in record["results"]:
        if root["status"] != "complete":
            continue
        source_address = root["address"]
        summary = json.loads((output / root["summary"]).read_text(encoding="utf-8"))
        depth = 0
        while True:
            eligible = local_direct_targets(image, starts, summary, seen)
            if summary.get("direct_calls_truncated"):
                status = "truncated_calls"
            elif depth >= follow_depth:
                status = "depth_limit"
            elif len(eligible) > 1:
                status = "ambiguous"
            elif not eligible:
                status = "none"
            elif len(record["followed"]) >= follow_limit:
                status = "function_limit"
            else:
                status = "followed"
            record["decisions"].append({"root_address": root["address"],
                                        "source_address": source_address,
                                        "depth": depth,
                                        "eligible_targets": [f"0x{item:x}" for item in eligible],
                                        "status": status})
            if status != "followed":
                break
            target_address = eligible[0]
            seen.add(target_address)
            target = output / f"followed-{len(record['followed']) + 1:02d}"
            followed = {"root_address": root["address"],
                        "source_address": source_address,
                        "address": f"0x{target_address:x}", "depth": depth + 1}
            try:
                path = disassemble_native_function(binary, digest,
                                                   followed["address"], target,
                                                   max_bytes, timeout=timeout)
                followed.update(status="complete", summary=str(path.relative_to(output)))
                summary = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                followed.update(status="unavailable", error={"type": type(exc).__name__,
                                                             "message": str(exc)[:300]})
            record["followed"].append(followed)
            if followed["status"] != "complete":
                break
            source_address = followed["address"]
            depth += 1
    successes = sum(item["status"] == "complete" for item in
                    record["results"] + record["followed"])
    total = len(record["results"]) + len(record["followed"])
    record["status"] = ("complete" if successes == total else
                        "partial" if successes else "unavailable")
    index_path = output / "index.json"
    index_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    evidence = [{"path": str(path.relative_to(output)), "sha256": sha256_file(path)}
                for path in sorted(output.rglob("*")) if path.is_file()]
    manifest = {"schema_version": 1, "kind": "native_candidate_queue",
                "status": record["status"], "evidence": evidence}
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return index_path
