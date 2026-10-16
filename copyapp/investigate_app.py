"""Run and resume several bounded UI investigations for one installed app."""

import hashlib
import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from copyapp.investigate_flow import _files, investigate_flow
from copyapp.verify import checked_path, sha256_file, verify_case


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verified_resume_evidence(output: Path, previous: dict, bundle: str,
                              prefix: str, analysis: Path,
                              script_records: list[dict]) -> bool:
    """Admit a separately completed child without accepting unrelated edits."""
    with redirect_stdout(io.StringIO()):
        if verify_case(output):
            return True
    flows = previous.get("flows")
    evidence = previous.get("evidence")
    if not isinstance(flows, list) or not isinstance(evidence, list):
        return False
    from copyapp.report import _main_and_embedded_hashes, _validate_investigation
    binary_hashes = _main_and_embedded_hashes(analysis)
    promoted = []
    for item in flows:
        if not isinstance(item, dict) or item.get("status") == "complete":
            continue
        index = item.get("index")
        if type(index) is not int or not 1 <= index <= len(script_records):
            return False
        child = output / "flows" / f"flow-{index:02d}"
        if item.get("manifest") != str((child / "manifest.json").relative_to(output)):
            return False
        manifest = child / "manifest.json"
        if not manifest.is_file() or _read(manifest).get("status") != "complete":
            continue
        if (_read(manifest).get("source_script_sha256") !=
                script_records[index - 1]["sha256"]):
            return False
        try:
            _validate_investigation(child, bundle, prefix, binary_hashes)
        except (OSError, ValueError, KeyError, TypeError):
            return False
        promoted.append(f"flows/flow-{index:02d}/")
    if not promoted:
        return False
    expected_paths = set()
    for item in evidence:
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str) or
                not isinstance(item.get("sha256"), str)):
            return False
        relative = item["path"]
        if relative in expected_paths:
            return False
        expected_paths.add(relative)
        try:
            path = checked_path(output, relative)
            if not any(relative.startswith(scope) for scope in promoted) and (
                    not path.is_file() or sha256_file(path) != item["sha256"]):
                return False
        except (OSError, ValueError):
            return False
    actual_paths = {str(path.relative_to(output)) for path in output.rglob("*")
                    if path.is_file() and path != output / "manifest.json"}
    return all(path in expected_paths or any(path.startswith(scope) for scope in promoted)
               for path in actual_paths)


def investigate_app(udid: str, analysis: Path, scripts: List[Path], output: Path,
                    backend: str = "ios-mcp", provider: str = "none",
                    rea_limit: int = 4, rea_script: Optional[Path] = None,
                    ghidra_dir: Optional[Path] = None,
                    java_home: Optional[Path] = None,
                    timeout: int = 240, resume: bool = False,
                    disabled_analyzer: Optional[str] = None,
                    network: bool = False) -> Tuple[Path, bool]:
    if not 1 <= len(scripts) <= 12:
        raise ValueError("provide 1–12 playbooks for one app")
    if disabled_analyzer is not None and provider != "ghidra-direct":
        raise ValueError("disabled analyzer requires ghidra-direct provider")
    if output.exists() and any(output.iterdir()) and not resume:
        raise FileExistsError(f"output directory is not empty: {output}")
    with redirect_stdout(io.StringIO()):
        if not verify_case(analysis):
            raise ValueError("analysis case evidence hash mismatch")
    survey = _read(analysis / "survey/manifest.json")
    bundle = survey.get("bundle_id")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    if not isinstance(bundle, str) or survey.get("device_id_sha256_prefix") != prefix:
        raise ValueError("analysis case belongs to another device")
    script_records = []
    for script in scripts:
        plan = _read(script)
        if plan.get("bundle_id") != bundle:
            raise ValueError(f"playbook belongs to another app: {script}")
        script_records.append({"path": str(script.resolve(strict=True)),
                               "sha256": sha256_file(script)})
    if len({item["sha256"] for item in script_records}) != len(script_records):
        raise ValueError("duplicate playbooks are not allowed")
    analysis_hash = sha256_file(analysis / "analysis-index.json")
    previous = None
    if resume:
        parent = output / "manifest.json"
        if not parent.is_file():
            raise ValueError("resume requires an existing app investigation")
        previous = _read(parent)
        if (previous.get("status") == "complete" or
                previous.get("kind") != "investigated_app" or
                previous.get("bundle_id") != bundle or
                previous.get("device_id_sha256_prefix") != prefix or
                previous.get("analysis_index_sha256") != analysis_hash or
                previous.get("scripts") != script_records or
                previous.get("ui_backend") != backend or
                previous.get("provider") != provider or
                bool(previous.get("network_requested")) != network or
                previous.get("disabled_analyzer") != disabled_analyzer):
            raise ValueError("resume app, script, device or provider identity differs")
        if not _verified_resume_evidence(output, previous, bundle, prefix,
                                         analysis, script_records):
            raise ValueError("existing app investigation evidence hash mismatch")
    output.mkdir(parents=True, exist_ok=True)
    record = dict(previous) if previous else {"schema_version": 1,
        "kind": "investigated_app", "bundle_id": bundle,
        "device_id_sha256_prefix": prefix,
        "analysis_index_sha256": analysis_hash,
        "ui_backend": backend, "provider": provider,
        "scripts": script_records, "started_at": _now()}
    if disabled_analyzer is not None:
        record["disabled_analyzer"] = disabled_analyzer
    if network:
        record["network_requested"] = True
    if previous:
        record.setdefault("history", []).append({"at": _now(),
                                                   "previous_status": previous["status"]})
    record["status"] = "failed"
    record["flows"] = []
    record.pop("error", None)
    try:
        for index, script in enumerate(scripts, 1):
            child = output / "flows" / f"flow-{index:02d}"
            child_manifest = child / "manifest.json"
            if resume and child_manifest.is_file() and \
                    _read(child_manifest).get("status") == "complete":
                from copyapp.report import _main_and_embedded_hashes, _validate_investigation
                _validate_investigation(child, bundle, prefix,
                                        _main_and_embedded_hashes(analysis))
                complete = True
            else:
                _, complete = investigate_flow(udid, analysis, script, child,
                                               backend=backend, provider=provider,
                                               rea_limit=rea_limit,
                                               rea_script=rea_script,
                                               ghidra_dir=ghidra_dir,
                                               java_home=java_home,
                                               timeout=timeout,
                                               resume=resume and child_manifest.is_file(),
                                               **({"network": True} if network else {}),
                                               **({"disabled_analyzer": disabled_analyzer}
                                                  if disabled_analyzer is not None else {}))
            child_record = _read(child_manifest)
            if (child_record.get("bundle_id") != bundle or
                    child_record.get("device_id_sha256_prefix") != prefix or
                    child_record.get("source_script_sha256") != script_records[index-1]["sha256"]):
                raise ValueError("child investigation identity differs")
            record["flows"].append({"index": index,
                                    "script_sha256": script_records[index-1]["sha256"],
                                    "manifest": str(child_manifest.relative_to(output)),
                                    "manifest_sha256": sha256_file(child_manifest),
                                    "status": child_record["status"],
                                    "selected_methods": child_record.get("selected_methods", [])})
            if not complete:
                record["status"] = child_record["status"]
                break
        else:
            record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
    finally:
        record["finished_at"] = _now()
        record["evidence"] = _files(output)
        (output / "manifest.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
