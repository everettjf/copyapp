"""Follow uniquely resolved, unnamed local callees from a verified REA queue."""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from copyapp.rea_function import analyze_rea_function
from copyapp.verify import checked_path, sha256_file


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


def bridge_callees(evidence: dict) -> list:
    """Return resolved local FUN_ targets; these are leads, not proven semantics."""
    result = evidence.get("normalized_result") or {}
    candidates = []
    seen = set()
    for item in result.get("callees", []):
        if not isinstance(item, dict):
            continue
        address = item.get("address")
        classification = item.get("classification") or {}
        body = item.get("body") or {}
        if (not isinstance(address, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", address) or
                not re.fullmatch(r"FUN_[0-9a-fA-F]+", str(item.get("name", ""))) or
                classification.get("external") is not False or
                classification.get("thunk") is not False or
                body.get("available") is not True or
                address.lower() in seen):
            continue
        seen.add(address.lower())
        candidates.append({"address": address.lower(), "name": item["name"]})
    return sorted(candidates, key=lambda item: int(item["address"], 16))


def follow_rea_bridges(queue_dir: Path, output: Path, limit: int = 4,
                       max_depth: int = 2, rea_script: Optional[Path] = None,
                       ghidra_dir: Optional[Path] = None,
                       java_home: Optional[Path] = None,
                       timeout: int = 240) -> Tuple[Path, bool]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    if not 1 <= limit <= 16 or not 1 <= max_depth <= 4:
        raise ValueError("bridge limit or depth is out of range")
    queue_dir = queue_dir.resolve(strict=True)
    if output.resolve() == queue_dir or queue_dir in output.resolve().parents:
        raise ValueError("bridge output must be outside its source queue")
    source = _read(queue_dir / "sources/candidates/candidates.json")
    queue = _read(queue_dir / "queue.json")
    digest = queue.get("binary_sha256")
    bundle = source.get("bundle_id")
    prefix = source.get("device_id_sha256_prefix")
    if not all(isinstance(value, str) and value for value in
               (digest, bundle, prefix)):
        raise ValueError("REA queue lacks source identity")
    # This checks the nested candidate case and every seed function dossier.
    from copyapp.report import _validate_rea_queue
    _validate_rea_queue(queue_dir, bundle, prefix, {digest})
    binary = Path(queue.get("binary_path", ""))
    if not binary.is_file() or sha256_file(binary) != digest:
        raise ValueError("REA queue exact binary is unavailable or changed")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(queue_dir, output / "sources" / "queue")
    record = {"schema_version": 1, "kind": "rea_bridge_follow",
              "status": "failed", "bundle_id": bundle,
              "device_id_sha256_prefix": prefix,
              "provider": queue["provider"], "binary_sha256": digest,
              "source_queue_sha256": sha256_file(queue_dir / "queue.json"),
              "limit": limit, "max_depth": max_depth,
              "started_at": _now(), "decisions": [], "results": [],
              "limitation": "Only a unique resolved, unnamed local FUN_ callee is followed at each node. This is a static call graph lead, not proof that a UI action executed the callee."}
    seeds = []
    for item in queue["results"]:
        path = checked_path(queue_dir, item["summary"])
        seeds.append({"address": item["address"].lower(), "depth": 0,
                      "evidence": _read(path.parent / "evidence.json")})
    frontier = seeds
    seen = {item["address"] for item in seeds}
    try:
        while frontier:
            node = frontier.pop(0)
            callees = [item for item in bridge_callees(node["evidence"])
                       if item["address"] not in seen]
            decision = {"source_address": node["address"], "depth": node["depth"],
                        "eligible_callees": callees}
            if node["depth"] >= max_depth:
                decision["status"] = "depth_limit"
            elif len(callees) != 1:
                decision["status"] = "ambiguous" if callees else "none"
            elif len(record["results"]) >= limit:
                decision["status"] = "function_limit"
            else:
                callee = callees[0]
                address = callee["address"]
                target = output / "targets" / f"{len(record['results'])+1:02d}-{int(address,16):x}"
                summary_path = analyze_rea_function(binary, digest, address,
                                                    queue["provider"], target,
                                                    rea_script, ghidra_dir,
                                                    java_home, timeout)
                summary = _read(summary_path)
                if (summary.get("binary_sha256") != digest or
                        summary.get("provider", {}).get("id") != queue["provider"] or
                        str(summary.get("resolved_procedure", {}).get("address", "")).lower()
                        != address):
                    raise ValueError("followed function identity differs")
                record["results"].append({"source_address": node["address"],
                                          "address": address, "depth": node["depth"] + 1,
                                          "summary": str(summary_path.relative_to(output)),
                                          "evidence_id": summary["evidence_id"]})
                seen.add(address)
                frontier.append({"address": address, "depth": node["depth"] + 1,
                                 "evidence": _read(target / "evidence.json")})
                decision["status"] = "followed"
            record["decisions"].append(decision)
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
    finally:
        record["finished_at"] = _now()
        (output / "bridge-map.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "rea_bridge_follow",
            "status": record["status"], "bundle_id": bundle,
            "device_id_sha256_prefix": prefix, "binary_sha256": digest,
            "provider": queue["provider"], "evidence": _files(output),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
