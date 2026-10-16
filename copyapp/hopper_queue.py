"""Analyze a bounded verified candidate queue with Copy APP's direct Hopper adapter."""

import io
import json
import re
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from copyapp.hopper_direct import decompile_hopper_function
from copyapp.ipa import MAX_BINARY
from copyapp.native_disasm import rank_native_candidates
from copyapp.verify import checked_path, sha256_file, verify_case


def _files(root: Path) -> list:
    return [{"path": str(path.relative_to(root)), "sha256": sha256_file(path)}
            for path in sorted(root.rglob("*"))
            if path.is_file() and path != root / "manifest.json"]


def decompile_hopper_queue(candidates_dir: Path, output: Path,
                            app: Optional[Path] = None, limit: int = 4,
                            timeout: int = 600) -> Tuple[Path, bool]:
    if not 1 <= limit <= 32:
        raise ValueError("limit must be between 1 and 32")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    candidates_dir = candidates_dir.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(candidates_dir):
            raise ValueError("candidate evidence hash mismatch")
    source = json.loads((candidates_dir / "candidates.json").read_text(encoding="utf-8"))
    source_manifest = json.loads((candidates_dir / "manifest.json").read_text(encoding="utf-8"))
    digest = source.get("binary_sha256")
    binary = Path(source.get("binary_path", ""))
    if (source.get("kind") != "runtime_static_candidates" or
            source_manifest.get("kind") != "runtime_static_candidates" or
            not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest) or
            not binary.is_file() or not 0 < binary.stat().st_size <= MAX_BINARY or
            sha256_file(binary) != digest or
            not isinstance(source.get("candidates"), list) or
            not source["candidates"]):
        raise ValueError("candidate case has no matching analysis binary")
    ranked = rank_native_candidates(source["candidates"], digest, limit)
    selected = [{"address": item["static_address"], "class": item.get("class"),
                 "selector": item.get("selector")} for item in ranked]
    output.mkdir(parents=True)
    copied = output / "sources/candidates"
    copied.mkdir(parents=True)
    shutil.copyfile(candidates_dir / "manifest.json", copied / "manifest.json")
    for item in source_manifest.get("evidence", []):
        relative = item["path"]
        target = copied / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checked_path(candidates_dir, relative), target)
    record = {"schema_version": 1, "kind": "hopper_direct_candidate_queue",
              "status": "failed", "binary_sha256": digest,
              "candidate_case_sha256": sha256_file(candidates_dir / "candidates.json"),
              "limit": limit, "selected": selected, "results": [],
              "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        for index, item in enumerate(selected, 1):
            address = item["address"]
            target = output / "targets" / f"{index:02d}-{int(address, 16):x}"
            try:
                summary = decompile_hopper_function(binary, digest, address,
                                                    target, app, timeout)
                record["results"].append({"address": address, "status": "complete",
                                          "summary": str(summary.relative_to(output))})
            except Exception as exc:
                record["results"].append({"address": address, "status": "failed",
                                          "error": str(exc)[:500]})
                raise
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
    record["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (output / "queue.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    manifest = {key: record[key] for key in
                ("schema_version", "kind", "status", "binary_sha256", "candidate_case_sha256")}
    manifest["evidence"] = _files(output)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
