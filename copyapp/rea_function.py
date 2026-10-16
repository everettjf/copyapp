"""Run one REA native-function query with a pinned input hash and retained evidence."""

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Optional


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_bounded(argv: list[str], timeout: int, env: dict) -> subprocess.CompletedProcess:
    """Keep REA's provider children in one process group for timeout cleanup."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # subprocess.run only kills its immediate child on timeout. Ghidra is
        # launched below Node and can otherwise survive with the analysis lock.
        for signal_number in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, signal_number)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=3)
                break
            except subprocess.TimeoutExpired:
                continue
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def analyze_rea_function(binary: Path, expected_sha256: str, procedure: str,
                         provider: str, output: Path, rea_script: Optional[Path],
                         ghidra_dir: Optional[Path], java_home: Optional[Path],
                         timeout: int = 240) -> Path:
    if provider not in ("ghidra", "hopper"):
        raise ValueError("provider must be ghidra or hopper")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("expected SHA-256 must be lowercase hexadecimal")
    if not procedure or len(procedure) > 512 or "\0" in procedure:
        raise ValueError("invalid procedure selector")
    if not 10 <= timeout <= 600:
        raise ValueError("timeout must be between 10 and 600 seconds")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    binary = binary.resolve(strict=True)
    actual_sha256 = _sha256(binary)
    if actual_sha256 != expected_sha256:
        raise ValueError("binary SHA-256 does not match selected case evidence")
    if rea_script is None:
        executable = shutil.which("rea")
        if executable is None:
            raise FileNotFoundError("REA CLI not found; pass --rea-script or install rea")
        argv = [executable]
    else:
        node = shutil.which("node")
        if node is None:
            raise FileNotFoundError("Node.js not found")
        argv = [node, str(rea_script.resolve(strict=True))]
    argv += ["function", str(binary), "--procedure=" + procedure,
             "--provider", provider, "--json"]
    env = os.environ.copy()
    # REA has its own provider startup deadline. Keep it inside the outer
    # subprocess deadline so a caller's --timeout actually controls large
    # imports and REA has time to report/clean up before Python terminates it.
    startup_setting = ("REA_GHIDRA_STARTUP_TIMEOUT_MS" if provider == "ghidra"
                       else "REA_HOPPER_STARTUP_TIMEOUT_MS")
    if not env.get(startup_setting):
        env[startup_setting] = str(max(1000, timeout * 1000 - 15000))
    if ghidra_dir is not None:
        env["GHIDRA_INSTALL_DIR"] = str(ghidra_dir.resolve(strict=True))
    if java_home is not None:
        env["JAVA_HOME"] = str(java_home.resolve(strict=True))
    output.mkdir(parents=True, exist_ok=True)
    try:
        run = _run_bounded(argv, timeout, env)
    except subprocess.TimeoutExpired as exc:
        (output / "failure.json").write_text(json.dumps({
            "status": "timeout", "provider": provider, "procedure": procedure,
            "binary_sha256": actual_sha256, "timeout_seconds": timeout,
        }, indent=2) + "\n")
        raise RuntimeError("REA function query timed out; inspect failure.json") from exc
    if run.returncode != 0 or len(run.stdout) > 20 * 1024 * 1024:
        (output / "failure.json").write_text(json.dumps({
            "status": "failed", "provider": provider, "procedure": procedure,
            "binary_sha256": actual_sha256, "exit_code": run.returncode,
            "stdout_excerpt": run.stdout[:4096].decode(errors="replace"),
            "stderr_excerpt": run.stderr[:4096].decode(errors="replace"),
        }, ensure_ascii=False, indent=2) + "\n")
        raise RuntimeError("REA function query failed; inspect failure.json")
    try:
        evidence = json.loads(run.stdout)
    except json.JSONDecodeError as exc:
        (output / "failure.json").write_text(json.dumps({
            "status": "invalid_json", "provider": provider,
            "procedure": procedure, "binary_sha256": actual_sha256,
        }, indent=2) + "\n")
        raise RuntimeError("REA returned invalid JSON") from exc
    if not isinstance(evidence, dict):
        raise RuntimeError("REA evidence must be a JSON object")
    subject = evidence.get("subject", {})
    result = evidence.get("normalized_result", {})
    if (subject.get("digest", {}).get("sha256") != actual_sha256 or
            evidence.get("provider", {}).get("id") != provider or
            not evidence.get("evidence_id") or
            not result.get("procedure")):
        (output / "failure.json").write_text(json.dumps({
            "status": "identity_mismatch", "provider": provider,
            "procedure": procedure, "binary_sha256": actual_sha256,
        }, indent=2) + "\n")
        raise RuntimeError("REA evidence identity does not match requested binary/provider")
    (output / "evidence.json").write_bytes(run.stdout)
    summary = {
        "schema_version": 1,
        "binary": str(binary), "binary_sha256": actual_sha256,
        "provider": evidence["provider"],
        "analysis_profile_digest": evidence.get("analysis_profile", {}).get("digest"),
        "requested_procedure": procedure,
        "resolved_procedure": result["procedure"],
        "evidence_id": evidence["evidence_id"],
        "limitations": evidence.get("limitations", []),
        "pseudocode_is_original_source": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (output / "pseudocode.txt").write_text(result.get("pseudocode", ""), encoding="utf-8")
    report = ["# REA 函数证据", "",
              f"- 二进制 SHA-256：`{actual_sha256}`",
              f"- Provider：`{provider}` / {evidence['provider'].get('version')}",
              f"- 函数：`{result['procedure'].get('name')}` at `{result['procedure'].get('address')}`",
              f"- Evidence ID：`{evidence['evidence_id']}`", "",
              "[完整证据](evidence.json) · [伪代码](pseudocode.txt)", "",
              "伪代码由反编译器生成，不是原作者源码。", ""]
    (output / "report.md").write_text("\n".join(report), encoding="utf-8")
    return output / "summary.json"
