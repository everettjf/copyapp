"""Analyze a bounded, verified runtime-to-static candidate queue with REA."""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from copyapp.rea_function import analyze_rea_function
from copyapp.verify import checked_path, sha256_file, verify_case


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _files(root: Path) -> list:
    return [{"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
            for path in sorted(root.rglob("*"))
            if path.is_file() and path != root / "manifest.json"]


def analyze_candidate_queue(candidates_dir: Path, provider: str, output: Path,
                            limit: int = 8, rea_script: Optional[Path] = None,
                            ghidra_dir: Optional[Path] = None,
                            java_home: Optional[Path] = None,
                            timeout: int = 240) -> Tuple[Path, bool]:
    if provider not in ("ghidra", "hopper"):
        raise ValueError("provider must be ghidra or hopper")
    if not 1 <= limit <= 32:
        raise ValueError("limit must be between 1 and 32")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    if not verify_case(candidates_dir):
        raise ValueError("candidate evidence hash mismatch")
    source = json.loads((candidates_dir / "candidates.json").read_text(encoding="utf-8"))
    candidate_manifest = json.loads((candidates_dir / "manifest.json").read_text(encoding="utf-8"))
    binary = Path(source.get("binary_path", ""))
    digest = source.get("binary_sha256")
    if (candidate_manifest.get("kind") != "runtime_static_candidates" or
            source.get("schema_version") != 1 or
            not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest) or
            not binary.is_file() or sha256_file(binary) != digest):
        raise ValueError("candidate case or exact binary identity is invalid")
    options = source.get("candidates")
    if not isinstance(options, list) or not options:
        raise ValueError("candidate case has no methods to analyze")
    seen = set()
    queue = []
    for item in options:
        if not isinstance(item, dict):
            raise ValueError("invalid candidate entry")
        address = item.get("static_address")
        if (not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", address) or
                int(address, 16) in seen or item.get("binary_sha256") != digest or
                not isinstance(item.get("observations"), list) or not item["observations"]):
            raise ValueError("candidate address, binary or observations are invalid")
        seen.add(int(address, 16))
        counts = [(observation.get("calls"),
                   (observation.get("static_entry") or {}).get("calls", 0))
                  for observation in item["observations"] if isinstance(observation, dict)]
        if (len(counts) != len(item["observations"]) or
                any(type(current) is not int or type(direct) is not int or
                    current < 0 or direct < 0 for current, direct in counts)):
            raise ValueError("candidate call counts are invalid")
        current = sum(count[0] for count in counts)
        direct = sum(count[1] for count in counts)
        if direct + current == 0:
            raise ValueError("candidate has no observed calls")
        queue.append({"class": item.get("class"), "selector": item.get("selector"),
                      "address": address, "static_calls": direct,
                      "current_calls": current})
    queue.sort(key=lambda item: (-item["static_calls"], -item["current_calls"],
                                 int(item["address"], 16)))
    selected = queue[:limit]
    output.mkdir(parents=True, exist_ok=True)
    source_dir = output / "sources" / "candidates"
    source_dir.mkdir(parents=True)
    shutil.copyfile(candidates_dir / "manifest.json", source_dir / "manifest.json")
    for item in candidate_manifest.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("candidate evidence list is invalid")
        source_file = checked_path(candidates_dir, item["path"])
        target = source_dir / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, target)
    record = {"schema_version": 1, "kind": "rea_candidate_queue",
              "status": "failed", "provider": provider,
              "candidate_case_sha256": sha256_file(candidates_dir / "candidates.json"),
              "binary_sha256": digest, "binary_path": str(binary.resolve()),
              "started_at": _now(), "selected": selected,
              "results": [], "note": "Candidates are ordered by observed static-entry and current-IMP counts. REA pseudocode is not original source."}
    manifest_path = output / "manifest.json"
    try:
        for index, item in enumerate(selected, 1):
            target = output / "targets" / f"{index:02d}-{int(item['address'], 16):x}"
            try:
                summary = analyze_rea_function(binary, digest, item["address"], provider,
                                               target, rea_script, ghidra_dir,
                                               java_home, timeout)
                result = json.loads(summary.read_text(encoding="utf-8"))
                if (result.get("binary_sha256") != digest or
                        result.get("provider", {}).get("id") != provider or
                        result.get("resolved_procedure", {}).get("address", "").lower() !=
                        item["address"].lower()):
                    raise ValueError("REA result does not resolve the requested candidate")
                record["results"].append({"index": index, "address": item["address"],
                                          "status": "complete",
                                          "summary": str(summary.relative_to(output)),
                                          "evidence_id": result["evidence_id"]})
            except Exception as exc:
                record["results"].append({"index": index, "address": item["address"],
                                          "status": "failed", "error": {
                                              "type": type(exc).__name__,
                                              "message": str(exc)[:400]}})
                break
        else:
            record["status"] = "complete"
    finally:
        record["finished_at"] = _now()
        record_path = output / "queue.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        manifest_path.write_text(json.dumps({"schema_version": 1,
            "kind": "rea_candidate_queue", "status": record["status"],
            "binary_sha256": digest, "provider": provider,
            "evidence": _files(output)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return manifest_path, record["status"] == "complete"
