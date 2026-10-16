"""Resume a multi-flow investigation and prepare its coding-agent review task."""

import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.draft_analysis import draft_analysis
from copyapp.investigate_app import investigate_app
from copyapp.verify import sha256_file, verify_case


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verified(path: Path) -> bool:
    with redirect_stdout(io.StringIO()):
        return verify_case(path)


def _save(output: Path, record: dict) -> Path:
    record["updated_at"] = _now()
    record["evidence"] = [
        {"path": name, "sha256": sha256_file(output / name)}
        for name in ("toolchain-doctor.json", "draft/manifest.json")
        if (output / name).is_file()]
    path = output / "manifest.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _ghidra_ready(output: Path, ghidra_dir: Optional[Path],
                  java_home: Optional[Path],
                  disabled_analyzer: Optional[str] = None) -> None:
    """Check the selected decompiler before any phone touch is attempted."""
    from copyapp.ghidra_direct import check_direct_ghidra
    if ghidra_dir is None:
        raise FileNotFoundError("direct Ghidra requires --ghidra-dir or GHIDRA_INSTALL_DIR")
    selected_java = java_home or (Path(os.environ["JAVA_HOME"])
                                  if os.environ.get("JAVA_HOME") else None)
    if selected_java is None:
        raise FileNotFoundError("direct Ghidra requires a JDK via --java-home or JAVA_HOME")
    result = check_direct_ghidra(ghidra_dir, selected_java, disabled_analyzer)
    (output / "toolchain-doctor.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hopper_ready(output: Path, hopper_app: Optional[Path]) -> None:
    from copyapp.hopper_direct import check_direct_hopper
    result = check_direct_hopper(hopper_app)
    (output / "toolchain-doctor.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_analysis(udid: str, analysis: Path, scripts: list[Path], output: Path,
                     backend: str = "ios-mcp", provider: str = "none",
                     rea_limit: int = 4, rea_script: Optional[Path] = None,
                     ghidra_dir: Optional[Path] = None,
                     java_home: Optional[Path] = None, timeout: int = 240,
                     rebuilt_bundle_id: str = "", resume: bool = False,
                     investigation: Optional[Path] = None,
                     disabled_analyzer: Optional[str] = None,
                     network: bool = False,
                     hopper_app: Optional[Path] = None) -> tuple[Path, bool]:
    """Prepare a verified review task; completion still needs semantic agent work."""
    if not 1 <= len(scripts) <= 12:
        raise ValueError("provide 1–12 playbooks for one app")
    if disabled_analyzer is not None and provider != "ghidra-direct":
        raise ValueError("disabled analyzer requires ghidra-direct provider")
    if provider not in ("none", "ghidra-direct", "hopper-direct") or rea_script is not None:
        raise ValueError("unsupported analysis provider or removed REA script option")
    if ghidra_dir is None and os.environ.get("GHIDRA_INSTALL_DIR"):
        ghidra_dir = Path(os.environ["GHIDRA_INSTALL_DIR"])
    if java_home is None and os.environ.get("JAVA_HOME"):
        java_home = Path(os.environ["JAVA_HOME"])
    analysis = analysis.resolve(strict=True)
    if not _verified(analysis):
        raise ValueError("analysis case evidence hash mismatch")
    survey = _read(analysis / "survey/manifest.json")
    bundle = survey.get("bundle_id")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    if not isinstance(bundle, str) or survey.get("device_id_sha256_prefix") != prefix:
        raise ValueError("analysis case belongs to another device")
    script_records = []
    for script in scripts:
        script = script.resolve(strict=True)
        if _read(script).get("bundle_id") != bundle:
            raise ValueError(f"playbook belongs to another app: {script}")
        script_records.append({"path": str(script), "sha256": sha256_file(script)})
    if len({item["sha256"] for item in script_records}) != len(script_records):
        raise ValueError("duplicate playbooks are not allowed")
    investigation = investigation.resolve(strict=True) if investigation else output / "investigation"
    resolved_output = output.resolve()
    internal_investigation = (resolved_output / "investigation").resolve()
    if (analysis == investigation or
            (resolved_output == analysis or resolved_output in analysis.parents) or
            (investigation != internal_investigation and
             (investigation == resolved_output or resolved_output in investigation.parents))):
        raise ValueError("source cases must be distinct and outside the preparation output")
    source = {"analysis_case": str(analysis),
              "analysis_index_sha256": sha256_file(analysis / "analysis-index.json"),
              "investigation_case": str(investigation.resolve()),
              "external_investigation": investigation.resolve() != internal_investigation,
              "device_id_sha256_prefix": prefix, "bundle_id": bundle,
              "scripts": script_records, "ui_backend": backend, "provider": provider,
              "rebuilt_bundle_id": rebuilt_bundle_id}
    if disabled_analyzer is not None:
        source["disabled_analyzer"] = disabled_analyzer
    if network:
        source["network_requested"] = True
    parent = output / "manifest.json"
    if resume:
        if not parent.is_file():
            raise ValueError("resume requires an existing preparation manifest")
        record = _read(parent)
        if (record.get("kind") != "analysis_preparation" or
                record.get("disabled_analyzer") != disabled_analyzer or
                bool(record.get("network_requested")) != network or
                any(record.get(key) != value for key, value in source.items())):
            raise ValueError("resume target, scripts or settings differ")
    else:
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"output directory is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        record = {"schema_version": 1, "kind": "analysis_preparation", **source,
                  "created_at": _now(), "status": "running"}
        _save(output, record)
    try:
        child_manifest = investigation / "manifest.json"
        if child_manifest.is_file() and _read(child_manifest).get("status") == "complete":
            if not _verified(investigation):
                raise ValueError("completed investigation failed source verification")
            if bool(_read(child_manifest).get("network_requested")) != network:
                raise ValueError("completed investigation network setting differs")
        elif source["external_investigation"]:
            raise ValueError("external investigation is not complete")
        else:
            if provider == "ghidra-direct":
                _ghidra_ready(output, ghidra_dir, java_home, disabled_analyzer)
            elif provider == "hopper-direct":
                _hopper_ready(output, hopper_app)
            _save(output, record)
            _, complete = investigate_app(
                udid, analysis, [Path(item["path"]) for item in script_records], investigation,
                backend, provider, rea_limit, rea_script, ghidra_dir, java_home,
                timeout, resume and child_manifest.is_file(),
                **({"hopper_app": hopper_app} if provider == "hopper-direct" else {}),
                **({"network": True} if network else {}),
                **({"disabled_analyzer": disabled_analyzer}
                   if disabled_analyzer is not None else {}))
            if not complete:
                record["status"] = "investigation_incomplete"
                record["investigation_status"] = _read(child_manifest).get("status")
                record["investigation_manifest_sha256"] = sha256_file(child_manifest)
                return _save(output, record), False
            if not _verified(investigation):
                raise ValueError("new investigation failed source verification")
        investigated = _read(child_manifest)
        if (investigated.get("bundle_id") != bundle or
                investigated.get("device_id_sha256_prefix") != prefix or
                investigated.get("analysis_index_sha256") != source["analysis_index_sha256"] or
                investigated.get("scripts") != script_records or
                investigated.get("ui_backend") != backend or
                investigated.get("provider") != provider or
                investigated.get("disabled_analyzer") != disabled_analyzer):
            raise ValueError("investigation identity differs from preparation input")
        record["investigation_manifest_sha256"] = sha256_file(child_manifest)
        _save(output, record)
        draft = output / "draft"
        if (draft / "manifest.json").is_file() and _read(draft / "manifest.json").get("status") == "complete":
            if not _verified(draft):
                raise ValueError("completed review task failed source verification")
        else:
            if draft.exists():
                archive = output / "attempts" / (
                    "draft-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
                archive.parent.mkdir(exist_ok=True)
                shutil.move(str(draft), str(archive))
            _, complete = draft_analysis(analysis, investigation, draft, rebuilt_bundle_id)
            if not complete:
                record["status"] = "draft_incomplete"
                return _save(output, record), False
            if not _verified(draft):
                raise ValueError("new review task failed source verification")
        task = _read(draft / "task.json")
        if (task.get("kind") != "agent_semantic_review_task" or
                task.get("analysis_index_sha256") != source["analysis_index_sha256"] or
                task.get("app_investigation_sha256") != record["investigation_manifest_sha256"] or
                task.get("target_bundle_id") != bundle or
                task.get("device_id_sha256_prefix") != prefix):
            raise ValueError("review task identity differs from preparation input")
        record["status"] = "needs_semantic_review"
        record.pop("error", None)
        return _save(output, record), True
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
        _save(output, record)
        return parent, False
