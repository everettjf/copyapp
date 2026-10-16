"""Try a second UI backend only when the first failed before any touch."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from copyapp.gestures import GESTURE_ACTIONS
from copyapp.ictrl import DEFAULT_CLIENT
from copyapp.playbook import run_playbook
from copyapp.verify import sha256_file, verify_case


def run_playbook_auto(udid: str, primary: str, fallback: str, script: Path,
                      output: Path, ictrl_client: Path = DEFAULT_CLIENT) -> tuple:
    if {primary, fallback} != {"ios-mcp", "ictrl"}:
        raise ValueError("playbook-auto requires one ios-mcp and one ictrl backend")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    plan = json.loads(script.read_text(encoding="utf-8"))
    script_sha256 = sha256_file(script)
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    output.mkdir(parents=True, exist_ok=True)
    attempts = []
    evidence = []
    final_backend = None
    status = "failed"
    for index, backend in enumerate((primary, fallback), 1):
        root = output / ("primary" if index == 1 else "fallback")
        manifest, complete = run_playbook(udid, backend, script, root,
                                          ictrl_client=ictrl_client)
        if not verify_case(root):
            raise ValueError(f"{backend} playbook evidence hash mismatch")
        record = json.loads(manifest.read_text(encoding="utf-8"))
        if (sha256_file(root / "playbook.json") != script_sha256 or
                record.get("bundle_id") != plan.get("bundle_id") or
                record.get("device_id_sha256_prefix") != prefix or
                record.get("ui_backend") != backend or
                record.get("status") != ("complete" if complete else "failed")):
            raise ValueError("playbook attempt identity or script changed")
        touched = any(step.get("action") in ("tap", "tap_label", *GESTURE_ACTIONS)
                      for step in record["steps"])
        attempts.append({"backend": backend, "status": record["status"],
                         "touch_attempted": touched,
                         "manifest": str(manifest.relative_to(output)),
                         "error": record.get("error")})
        for path in sorted(root.rglob("*")):
            if path.is_file():
                evidence.append({"path": str(path.relative_to(output)), "sha256": sha256_file(path)})
        if complete:
            status = "complete"
            final_backend = backend
            break
        if touched:
            break
    result = {"schema_version": 1, "status": status,
              "bundle_id": plan.get("bundle_id"), "scenario_id": plan.get("scenario_id"),
              "script_sha256": script_sha256,
              "device_id_sha256_prefix": prefix,
              "primary_backend": primary, "fallback_backend": fallback,
              "selected_backend": final_backend,
              "fallback_skipped_after_touch": bool(attempts[-1]["touch_attempted"] and status != "complete"),
              "attempts": attempts, "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "evidence": evidence}
    target = output / "manifest.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target, status == "complete"
