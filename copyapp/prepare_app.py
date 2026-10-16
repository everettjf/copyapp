"""Join installed-app collection and selected-flow analysis preparation."""

import asyncio
import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from copyapp.analyze import analyze_case
from copyapp.prepare_analysis import _rea_ready, prepare_analysis
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
        for name in ("toolchain-doctor.json", "analysis/analysis-index.json",
                     "preparation/manifest.json")
        if (output / name).is_file()
    ]
    path = output / "manifest.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


async def prepare_app(udid: str, bundle: str, scripts: list[Path], output: Path,
                      survey: Callable[..., Awaitable[int]], *,
                      launch: bool = True, ui_backend: str = "ios-mcp",
                      backend: str = "ios-mcp", decrypt: bool = False,
                      decrypt_helper: Path = Path("../toolchains/ipadecrypt-helper-arm64"),
                      ssh_port: int = 22222, ssh_user: str = "mobile",
                      ssh_identity: Path = Path("cases/ssh/id_ed25519"),
                      ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
                      provider: str = "none", rea_limit: int = 4,
                      rea_script: Optional[Path] = None,
                      ghidra_dir: Optional[Path] = None,
                      java_home: Optional[Path] = None, timeout: int = 240,
                      rebuilt_bundle_id: str = "", resume: bool = False,
                      disabled_analyzer: Optional[str] = None,
                      network: bool = False) -> tuple[Path, bool]:
    """Produce a source-bound semantic-review task from one connected App."""
    if not 1 <= len(scripts) <= 12:
        raise ValueError("provide 1–12 playbooks for one app")
    if disabled_analyzer is not None and provider != "ghidra-direct":
        raise ValueError("disabled analyzer requires ghidra-direct provider")
    if not bundle or not udid or ui_backend not in ("usb", "ios-mcp") or \
            backend not in ("ios-mcp", "ictrl") or provider not in ("none", "ghidra-direct", "ghidra", "hopper"):
        raise ValueError("invalid device, bundle, UI backend or analysis provider")
    if not 1 <= ssh_port <= 65535 or ssh_user not in ("root", "mobile"):
        raise ValueError("invalid SSH transport")
    if provider == "none":
        rea_script = ghidra_dir = java_home = None
    else:
        if provider in ("ghidra", "hopper") and rea_script is None and os.environ.get("COPYAPP_REA_SCRIPT"):
            rea_script = Path(os.environ["COPYAPP_REA_SCRIPT"])
        if provider == "ghidra-direct":
            rea_script = None
        if ghidra_dir is None and os.environ.get("GHIDRA_INSTALL_DIR"):
            ghidra_dir = Path(os.environ["GHIDRA_INSTALL_DIR"])
        if java_home is None and os.environ.get("JAVA_HOME"):
            java_home = Path(os.environ["JAVA_HOME"])
    script_records = []
    for script in scripts:
        script = script.resolve(strict=True)
        if _read(script).get("bundle_id") != bundle:
            raise ValueError(f"playbook belongs to another app: {script}")
        script_records.append({"path": str(script), "sha256": sha256_file(script)})
    if len({item["sha256"] for item in script_records}) != len(script_records):
        raise ValueError("duplicate playbooks are not allowed")
    output = output.resolve()
    if any(output == Path(item["path"]) or output in Path(item["path"]).parents
           for item in script_records):
        raise ValueError("playbooks must be outside the preparation output")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    source = {
        "schema_version": 1, "kind": "app_preparation",
        "bundle_id": bundle, "device_id_sha256_prefix": prefix,
        "scripts": script_records, "launch": launch, "ui_backend": ui_backend,
        "investigation_backend": backend, "decrypt": decrypt,
        "decrypt_helper": str(decrypt_helper.resolve()),
        "ssh_port": ssh_port, "ssh_user": ssh_user,
        "ssh_identity": str(ssh_identity.resolve()),
        "ssh_known_hosts": str(ssh_known_hosts.resolve()),
        "provider": provider, "rea_limit": rea_limit,
        "rea_script": str(rea_script.resolve()) if rea_script else None,
        "ghidra_dir": str(ghidra_dir.resolve()) if ghidra_dir else None,
        "java_home": str(java_home.resolve()) if java_home else None,
        "timeout": timeout, "rebuilt_bundle_id": rebuilt_bundle_id,
    }
    if disabled_analyzer is not None:
        source["disabled_analyzer"] = disabled_analyzer
    if network:
        source["network_requested"] = True
    parent = output / "manifest.json"
    if resume:
        if not parent.is_file():
            raise ValueError("resume requires an existing app preparation manifest")
        record = _read(parent)
        if (record.get("disabled_analyzer") != disabled_analyzer or
                bool(record.get("network_requested")) != network or
                any(record.get(key) != value for key, value in source.items())):
            raise ValueError("resume target, playbooks or settings differ")
    else:
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"output directory is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        record = dict(source, created_at=_now(), status="preparing")
        _save(output, record)
    analysis = output / "analysis"
    preparation = output / "preparation"
    try:
        analysis_index = analysis / "analysis-index.json"
        expected_stages = {"survey", "bundle", "sandbox"}
        if decrypt:
            expected_stages.add("decryption")
        analysis_ok = (
            analysis_index.is_file() and
            record.get("analysis_index_sha256") == sha256_file(analysis_index) and
            set(_read(analysis_index).get("steps", {})) == expected_stages and
            all(item.get("ok") is True for item in _read(analysis_index).get("steps", {}).values()) and
            _read(analysis / "run-state.json").get("bundle_id") == bundle and
            _read(analysis / "run-state.json").get("device_id_sha256_prefix") == prefix and
            _read(analysis / "run-state.json").get("decrypt_requested") == decrypt and
            _verified(analysis)
        )
        if not analysis_ok:
            # Explicit decompilation needs a toolchain preflight before device work.
            if provider != "none":
                _rea_ready(output, provider, rea_script, ghidra_dir, java_home,
                           disabled_analyzer)
            _save(output, record)
            completed = await analyze_case(
                udid, bundle, analysis, launch, ssh_port, ssh_user,
                ssh_identity, ssh_known_hosts, survey, decrypt,
                decrypt_helper, (analysis / "run-state.json").is_file())
            if not completed:
                record["status"] = "analysis_incomplete"
                record["analysis_index_sha256"] = (
                    sha256_file(analysis_index) if analysis_index.is_file() else None)
                return _save(output, record), False
            if not _verified(analysis):
                raise ValueError("new analysis failed source verification")
        record["analysis_index_sha256"] = sha256_file(analysis_index)
        record["status"] = "analysis_ready"
        _save(output, record)
        preparation_manifest = preparation / "manifest.json"
        if (preparation_manifest.is_file() and
                record.get("preparation_manifest_sha256") == sha256_file(preparation_manifest) and
                _read(preparation_manifest).get("status") == "needs_semantic_review" and
                _verified(preparation)):
            record["preparation_status"] = "needs_semantic_review"
            record["status"] = "needs_semantic_review"
            record.pop("error", None)
            return _save(output, record), True
        prepared, complete = await asyncio.to_thread(
            prepare_analysis, udid, analysis,
            [Path(item["path"]) for item in script_records],
            preparation, backend, provider, rea_limit, rea_script,
            ghidra_dir, java_home, timeout, rebuilt_bundle_id,
            (preparation / "manifest.json").is_file(),
            **({"network": True} if network else {}),
            **({"disabled_analyzer": disabled_analyzer}
               if disabled_analyzer is not None else {}))
        record["preparation_manifest_sha256"] = sha256_file(prepared)
        record["preparation_status"] = _read(prepared).get("status")
        record["status"] = "needs_semantic_review" if complete else "preparation_incomplete"
        record.pop("error", None)
        return _save(output, record), complete
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
        return _save(output, record), False
