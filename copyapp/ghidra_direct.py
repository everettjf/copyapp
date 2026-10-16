"""Decompile one pinned Mach-O function with Ghidra directly, without REA."""

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.ipa import MAX_BINARY
from copyapp.verify import sha256_file


MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_PSEUDOCODE_BYTES = 2 * 1024 * 1024
MAX_FACTS_BYTES = 512 * 1024
SCRIPT = Path(__file__).parent / "ghidra_scripts/CopyAppDecompile.java"
OPTIONS_SCRIPT = Path(__file__).parent / "ghidra_scripts/CopyAppAnalysisOptions.java"
REA_LICENSE = Path(__file__).parent / "ghidra_scripts/REA-LICENSE.txt"


def validate_function_facts(path: Path, address: str, name: str) -> dict:
    """Check bounded Ghidra call relationships before admitting them as evidence."""
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_FACTS_BYTES:
        raise ValueError("Ghidra did not return bounded function facts")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or
            value["schema_version"] not in (1, 2) or value.get("address") != address or
            value.get("name") != name or
            not isinstance(value.get("signature"), str) or
            not 0 < len(value["signature"]) <= 2048 or
            type(value.get("is_thunk")) is not bool or
            type(value.get("is_external")) is not bool or
            not isinstance(value.get("limitation"), str) or
            "static" not in value["limitation"].lower()):
        raise ValueError("Ghidra function facts identity or metadata differs")
    for key in ("callers", "callees"):
        entries = value.get(key)
        if (not isinstance(entries, list) or len(entries) > 256 or
                type(value.get(key + "_truncated")) is not bool):
            raise ValueError("Ghidra function relationships are unbounded")
        addresses = []
        for item in entries:
            if (not isinstance(item, dict) or
                    not isinstance(item.get("address"), str) or
                    not re.fullmatch(r"0x[0-9a-f]+", item["address"]) or
                    not isinstance(item.get("name"), str) or
                    not 0 < len(item["name"]) <= 512):
                raise ValueError("Ghidra related function is invalid")
            addresses.append(int(item["address"], 16))
        if addresses != sorted(set(addresses)):
            raise ValueError("Ghidra related functions are not unique and ordered")
    if value["schema_version"] == 2:
        blocks = value.get("basic_blocks")
        references = value.get("instruction_references")
        if (not isinstance(blocks, list) or len(blocks) > 256 or
                type(value.get("basic_blocks_truncated")) is not bool or
                not isinstance(references, list) or len(references) > 256 or
                type(value.get("instruction_references_truncated")) is not bool or
                type(value.get("instructions_scanned")) is not int or
                not 0 <= value["instructions_scanned"] <= 20000):
            raise ValueError("Ghidra function topology or references are unbounded")
        block_starts = []
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError("Ghidra basic block is invalid")
            start, end, edges = (block.get("start"), block.get("end_inclusive"),
                                 block.get("successors"))
            if (not isinstance(start, str) or not re.fullmatch(r"0x[0-9a-f]+", start) or
                    not isinstance(end, str) or not re.fullmatch(r"0x[0-9a-f]+", end) or
                    int(end, 16) < int(start, 16) or
                    not isinstance(edges, list) or len(edges) > 256 or
                    any(not isinstance(edge, str) or
                        not re.fullmatch(r"0x[0-9a-f]+", edge) for edge in edges) or
                    edges != sorted(set(edges), key=lambda edge: int(edge, 16))):
                raise ValueError("Ghidra basic block is invalid")
            block_starts.append(int(start, 16))
        if block_starts != sorted(set(block_starts)):
            raise ValueError("Ghidra basic blocks are not ordered")
        reference_keys = []
        for item in references:
            if not isinstance(item, dict):
                raise ValueError("Ghidra instruction reference is invalid")
            source, target, kind = item.get("from"), item.get("to"), item.get("type")
            preview = item.get("string_preview")
            if (not isinstance(source, str) or not re.fullmatch(r"0x[0-9a-f]+", source) or
                    not isinstance(target, str) or not re.fullmatch(r"0x[0-9a-f]+", target) or
                    not isinstance(kind, str) or not 0 < len(kind) <= 128 or
                    (preview is not None and
                     (not isinstance(preview, str) or len(preview) > 256))):
                raise ValueError("Ghidra instruction reference is invalid")
            reference_keys.append((source, target, kind))
        if reference_keys != sorted(set(reference_keys)):
            raise ValueError("Ghidra instruction references are not unique and ordered")
    return value


def check_direct_ghidra(ghidra_dir: Path, java_home: Path,
                        disabled_analyzer: Optional[str] = None) -> dict:
    """Check a direct Ghidra/JDK installation before touching a device."""
    launcher = ghidra_dir.resolve(strict=True) / "support/analyzeHeadless"
    if (not launcher.is_file() or not os.access(launcher, os.X_OK) or
            not SCRIPT.is_file() or not REA_LICENSE.is_file()):
        raise FileNotFoundError("direct Ghidra launcher or Copy APP script is unavailable")
    if disabled_analyzer is not None and (not isinstance(disabled_analyzer, str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+/-]{0,127}", disabled_analyzer) or
            not OPTIONS_SCRIPT.is_file()):
        raise ValueError("disabled analyzer must be one installed Ghidra analyzer name")
    java_binary = java_home.resolve(strict=True) / "bin/java"
    if not java_binary.is_file() or not os.access(java_binary, os.X_OK):
        raise FileNotFoundError("selected JDK has no executable bin/java")
    version = subprocess.run([str(java_binary), "-version"], capture_output=True, timeout=10)
    if version.returncode != 0 or len(version.stderr) + len(version.stdout) > 16384:
        raise RuntimeError("selected JDK did not pass java -version")
    version_lines = (version.stderr or version.stdout).decode(
        "utf-8", errors="replace").splitlines()
    result = {"healthy": True, "provider": "ghidra-direct",
            "ghidra_launcher": str(launcher),
            "java_home": str(java_home.resolve()),
            "java_version": version_lines[0][:160] if version_lines else "available",
            "script_sha256": sha256_file(SCRIPT)}
    if disabled_analyzer is not None:
        result["disabled_analyzer"] = disabled_analyzer
        result["options_script_sha256"] = sha256_file(OPTIONS_SCRIPT)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _files(output: Path) -> list:
    return [{"path": path.name, "sha256": sha256_file(path)}
            for path in sorted(output.iterdir())
            if path.is_file() and path.name != "manifest.json"]


def _stop_process(process: subprocess.Popen) -> None:
    for number in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, number)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            continue


def decompile_ghidra_function(binary: Path, expected_sha256: str, address: str,
                              output: Path, ghidra_dir: Path,
                              java_home: Optional[Path] = None,
                              timeout: int = 600,
                              disabled_analyzer: Optional[str] = None) -> Path:
    """Run an isolated Ghidra headless import and save a source-bound function case."""
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("expected SHA-256 must be lowercase hexadecimal")
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("function address must be hexadecimal")
    if not 60 <= timeout <= 1800:
        raise ValueError("timeout must be between 60 and 1800 seconds")
    if disabled_analyzer is not None and (not isinstance(disabled_analyzer, str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+/-]{0,127}", disabled_analyzer) or
            not OPTIONS_SCRIPT.is_file()):
        raise ValueError("disabled analyzer must be one installed Ghidra analyzer name")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    binary = binary.resolve(strict=True)
    if not 0 < binary.stat().st_size <= MAX_BINARY or sha256_file(binary) != expected_sha256:
        raise ValueError("binary is too large or its SHA-256 differs from selected evidence")
    ghidra_dir = ghidra_dir.resolve(strict=True)
    launcher = ghidra_dir / "support/analyzeHeadless"
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise FileNotFoundError("Ghidra support/analyzeHeadless is unavailable")
    if not SCRIPT.is_file() or not REA_LICENSE.is_file():
        raise FileNotFoundError("Copy APP's packaged Ghidra post-script is unavailable")
    environment = os.environ.copy()
    if java_home is not None:
        home = java_home.resolve(strict=True)
        if not (home / "bin/java").is_file():
            raise FileNotFoundError("selected Java home has no bin/java")
        environment["JAVA_HOME"] = str(home)
    output.mkdir(parents=True, exist_ok=True)
    script_copy = output / SCRIPT.name
    shutil.copyfile(SCRIPT, script_copy)
    shutil.copyfile(REA_LICENSE, output / REA_LICENSE.name)
    if disabled_analyzer is not None:
        shutil.copyfile(OPTIONS_SCRIPT, output / OPTIONS_SCRIPT.name)
    record = {"schema_version": 1, "kind": "ghidra_direct_decompilation",
              "status": "failed", "binary_sha256": expected_sha256,
              "address": f"0x{int(address, 16):x}",
              "script_sha256": sha256_file(script_copy), "facts_schema_version": 2,
              "rea_license_sha256": sha256_file(output / REA_LICENSE.name),
              "started_at": _now()}
    if disabled_analyzer is not None:
        record["disabled_analyzer"] = disabled_analyzer
        record["options_script_sha256"] = sha256_file(output / OPTIONS_SCRIPT.name)
    try:
        with tempfile.TemporaryDirectory(prefix="copyapp-ghidra-") as temporary:
            argv = [str(launcher), temporary, "CopyApp", "-import", str(binary),
                    "-scriptPath", str(output.resolve())]
            if disabled_analyzer is not None:
                argv += ["-preScript", OPTIONS_SCRIPT.name,
                         disabled_analyzer, str(output.resolve())]
            argv += ["-postScript", SCRIPT.name,
                    record["address"], str(output.resolve()), "-max-cpu", "2",
                    "-analysisTimeoutPerFile", str(max(30, timeout - 60)),
                    "-deleteProject", "-log", str(output.resolve() / "ghidra.log")]
            with (output / "launcher.log").open("wb") as log:
                process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                           env=environment, start_new_session=True)
                try:
                    exit_code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired as exc:
                    _stop_process(process)
                    raise TimeoutError("Ghidra headless decompilation timed out") from exc
        if exit_code != 0:
            raise RuntimeError(f"Ghidra headless exited with status {exit_code}")
        if (output / "launcher.log").stat().st_size > MAX_LOG_BYTES:
            raise ValueError("Ghidra launcher log exceeded limit")
        if (output / "ghidra.log").is_file() and \
                (output / "ghidra.log").stat().st_size > MAX_LOG_BYTES:
            raise ValueError("Ghidra application log exceeded limit")
        logs = (output / "launcher.log").read_bytes() + (
            (output / "ghidra.log").read_bytes() if (output / "ghidra.log").is_file() else b"")
        if (b"Analysis timed out at" in logs or
                b"Processing not completed for file" in logs):
            raise TimeoutError("Ghidra automatic analysis timed out before decompilation")
        pseudocode = output / "pseudocode.txt"
        if not pseudocode.is_file() or not 0 < pseudocode.stat().st_size <= MAX_PSEUDOCODE_BYTES:
            raise ValueError("Ghidra did not return bounded pseudocode")
        result_address = (output / "address.txt").read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[0-9a-fA-F]+", result_address) or \
                int(result_address, 16) != int(address, 16):
            raise ValueError("Ghidra resolved a different function address")
        function_name = (output / "name.txt").read_text(encoding="utf-8").strip()
        language = (output / "language.txt").read_text(encoding="utf-8").strip()
        if not function_name or len(function_name) > 512 or not language or len(language) > 128:
            raise ValueError("Ghidra function metadata is missing or oversized")
        facts = validate_function_facts(output / "function-facts.json",
                                        record["address"], function_name)
        if facts["schema_version"] != record["facts_schema_version"]:
            raise ValueError("Ghidra function facts schema differs from the packaged script")
        if disabled_analyzer is not None and (
                (output / "analysis-options.txt").read_text(encoding="utf-8") !=
                disabled_analyzer + "=false\n"):
            raise ValueError("Ghidra did not confirm the requested disabled analyzer")
        summary = {**record, "status": "complete", "binary": str(binary),
                   "function_name": function_name, "language": language,
                   "pseudocode_sha256": sha256_file(pseudocode),
                   "facts_sha256": sha256_file(output / "function-facts.json"),
                   "ghidra_launcher": str(launcher),
                   "limitation": "Decompiler output is an interpretation of the selected binary, not original source or runtime proof."}
        (output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "report.md").write_text(
            "# Ghidra 直接反编译\n\n"
            f"- 函数：`{function_name}` at `{record['address']}`。\n"
            f"- 二进制 SHA-256：`{expected_sha256}`。\n"
            f"- 语言：`{language}`。\n"
            "- [伪代码](pseudocode.txt) · [函数关系](function-facts.json) · [完整元数据](summary.json)。\n\n"
            "伪代码不是原作者源码；静态结果不证明该函数在测试流程中运行。\n",
            encoding="utf-8")
        record["status"] = "complete"
    except Exception as exc:
        (output / "failure.json").write_text(json.dumps({
            "status": "failed", "type": type(exc).__name__,
            "message": str(exc)[:400], "binary_sha256": expected_sha256,
            "address": record["address"]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    finally:
        record["finished_at"] = _now()
        record["evidence"] = _files(output)
        (output / "manifest.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if record["status"] != "complete":
        raise RuntimeError("direct Ghidra decompilation failed; inspect failure.json and logs")
    return output / "summary.json"


def decompile_ghidra_batch(binary: Path, expected_sha256: str, addresses: list,
                           output: Path, ghidra_dir: Path,
                           java_home: Optional[Path] = None,
                           timeout: int = 600,
                           disabled_analyzer: Optional[str] = None) -> list:
    """Import one binary once and decompile 2-32 pinned functions in that project."""
    if (not isinstance(addresses, list) or not 2 <= len(addresses) <= 32 or
            any(not isinstance(address, str) or
                not re.fullmatch(r"0x[0-9a-fA-F]+", address) for address in addresses) or
            len({int(address, 16) for address in addresses}) != len(addresses)):
        raise ValueError("batch requires 2-32 distinct hexadecimal addresses")
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("expected SHA-256 must be lowercase hexadecimal")
    if not 60 <= timeout <= 1800:
        raise ValueError("timeout must be between 60 and 1800 seconds")
    if disabled_analyzer is not None and (not isinstance(disabled_analyzer, str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._+/-]{0,127}", disabled_analyzer) or
            not OPTIONS_SCRIPT.is_file()):
        raise ValueError("disabled analyzer must be one installed Ghidra analyzer name")
    if output.exists() and any(path.name != "sources" for path in output.iterdir()):
        raise FileExistsError(f"batch output already contains results: {output}")
    binary = binary.resolve(strict=True)
    if not 0 < binary.stat().st_size <= MAX_BINARY or sha256_file(binary) != expected_sha256:
        raise ValueError("binary is too large or its SHA-256 differs from selected evidence")
    launcher = ghidra_dir.resolve(strict=True) / "support/analyzeHeadless"
    if (not launcher.is_file() or not os.access(launcher, os.X_OK) or
            not SCRIPT.is_file() or not REA_LICENSE.is_file()):
        raise FileNotFoundError("direct Ghidra launcher or Copy APP script is unavailable")
    environment = os.environ.copy()
    if java_home is not None:
        home = java_home.resolve(strict=True)
        if not (home / "bin/java").is_file():
            raise FileNotFoundError("selected Java home has no bin/java")
        environment["JAVA_HOME"] = str(home)
    targets = [output / "targets" / f"function-{index:02d}"
               for index in range(1, len(addresses) + 1)]
    started = _now()
    records = []
    output.mkdir(parents=True, exist_ok=True)
    for address, target in zip(addresses, targets):
        target.mkdir(parents=True)
        shutil.copyfile(SCRIPT, target / SCRIPT.name)
        shutil.copyfile(REA_LICENSE, target / REA_LICENSE.name)
        record = {"schema_version": 1, "kind": "ghidra_direct_decompilation",
                  "status": "failed", "binary_sha256": expected_sha256,
                  "address": f"0x{int(address, 16):x}",
                  "script_sha256": sha256_file(target / SCRIPT.name),
                  "facts_schema_version": 2,
                  "rea_license_sha256": sha256_file(target / REA_LICENSE.name),
                  "batch_size": len(addresses), "batch_index": len(records) + 1,
                  "started_at": started}
        if disabled_analyzer is not None:
            shutil.copyfile(OPTIONS_SCRIPT, target / OPTIONS_SCRIPT.name)
            record["disabled_analyzer"] = disabled_analyzer
            record["options_script_sha256"] = sha256_file(target / OPTIONS_SCRIPT.name)
        records.append(record)
    try:
        with tempfile.TemporaryDirectory(prefix="copyapp-ghidra-") as temporary:
            argv = [str(launcher), temporary, "CopyApp", "-import", str(binary),
                    "-scriptPath", str(targets[0].resolve())]
            if disabled_analyzer is not None:
                argv += ["-preScript", OPTIONS_SCRIPT.name,
                         disabled_analyzer, str(targets[0].resolve())]
            argv += ["-postScript", SCRIPT.name]
            for record, target in zip(records, targets):
                argv += [record["address"], str(target.resolve())]
            argv += ["-max-cpu", "2", "-analysisTimeoutPerFile",
                     str(max(30, timeout - 60)), "-deleteProject",
                     "-log", str((output / "ghidra.log").resolve())]
            with (output / "launcher.log").open("wb") as log:
                process = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                           env=environment, start_new_session=True)
                try:
                    exit_code = process.wait(timeout=timeout + 125 * (len(addresses) - 1))
                except subprocess.TimeoutExpired as exc:
                    _stop_process(process)
                    raise TimeoutError("Ghidra batch decompilation timed out") from exc
        if exit_code != 0:
            raise RuntimeError(f"Ghidra headless exited with status {exit_code}")
        if (output / "launcher.log").stat().st_size > MAX_LOG_BYTES or (
                (output / "ghidra.log").is_file() and
                (output / "ghidra.log").stat().st_size > MAX_LOG_BYTES):
            raise ValueError("Ghidra batch log exceeded limit")
        logs = (output / "launcher.log").read_bytes() + (
            (output / "ghidra.log").read_bytes()
            if (output / "ghidra.log").is_file() else b"")
        if (b"Analysis timed out at" in logs or
                b"Processing not completed for file" in logs):
            raise TimeoutError("Ghidra automatic analysis timed out before decompilation")
        if f"COPYAPP_BATCH_COMPLETE {len(addresses)}".encode() not in logs or any(
                f"COPYAPP_DECOMPILE_COMPLETE {int(address, 16):x}".encode() not in logs
                for address in addresses):
            raise ValueError("Ghidra did not confirm every batch function completed")
        if disabled_analyzer is not None:
            profile = targets[0] / "analysis-options.txt"
            if (not profile.is_file() or profile.read_text(encoding="utf-8") !=
                    disabled_analyzer + "=false\n"):
                raise ValueError("Ghidra did not confirm the requested disabled analyzer")
        for record, target in zip(records, targets):
            pseudocode = target / "pseudocode.txt"
            if not pseudocode.is_file() or not 0 < pseudocode.stat().st_size <= MAX_PSEUDOCODE_BYTES:
                raise ValueError(f"Ghidra did not return bounded pseudocode for {record['address']}")
            returned = (target / "address.txt").read_text(encoding="utf-8").strip()
            if not re.fullmatch(r"[0-9a-fA-F]+", returned) or \
                    int(returned, 16) != int(record["address"], 16):
                raise ValueError(f"Ghidra resolved a different function for {record['address']}")
            name = (target / "name.txt").read_text(encoding="utf-8").strip()
            language = (target / "language.txt").read_text(encoding="utf-8").strip()
            if not name or len(name) > 512 or not language or len(language) > 128:
                raise ValueError("Ghidra function metadata is missing or oversized")
            facts = validate_function_facts(target / "function-facts.json",
                                            record["address"], name)
            if facts["schema_version"] != record["facts_schema_version"]:
                raise ValueError("Ghidra function facts schema differs from the packaged script")
        for record, target in zip(records, targets):
            if disabled_analyzer is not None and target != targets[0]:
                shutil.copyfile(targets[0] / "analysis-options.txt",
                                target / "analysis-options.txt")
            summary = {**record, "status": "complete", "binary": str(binary),
                       "function_name": (target / "name.txt").read_text(encoding="utf-8").strip(),
                       "language": (target / "language.txt").read_text(encoding="utf-8").strip(),
                       "pseudocode_sha256": sha256_file(target / "pseudocode.txt"),
                       "facts_sha256": sha256_file(target / "function-facts.json"),
                       "ghidra_launcher": str(launcher),
                       "limitation": "Decompiler output is an interpretation of the selected binary, not original source or runtime proof."}
            (target / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (target / "report.md").write_text(
                "# Ghidra 直接反编译\n\n"
                f"- 函数：`{summary['function_name']}` at `{record['address']}`。\n"
                f"- 二进制 SHA-256：`{expected_sha256}`。\n"
                f"- 语言：`{summary['language']}`。\n"
                "- [伪代码](pseudocode.txt) · [函数关系](function-facts.json) · [完整元数据](summary.json)。\n\n"
                "伪代码不是原作者源码；静态结果不证明该函数在测试流程中运行。\n",
                encoding="utf-8")
            record["status"] = "complete"
    except Exception as exc:
        for record, target in zip(records, targets):
            record["status"] = "failed"
            for partial in ("summary.json", "report.md"):
                (target / partial).unlink(missing_ok=True)
            (target / "failure.json").write_text(json.dumps({
                "status": "failed", "type": type(exc).__name__,
                "message": str(exc)[:400], "binary_sha256": expected_sha256,
                "address": record["address"]}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        raise RuntimeError("direct Ghidra batch failed; inspect target failures and logs") from exc
    finally:
        for record, target in zip(records, targets):
            if (output / "launcher.log").is_file():
                shutil.copyfile(output / "launcher.log", target / "launcher.log")
            if (output / "ghidra.log").is_file():
                shutil.copyfile(output / "ghidra.log", target / "ghidra.log")
            record["finished_at"] = _now()
            record["evidence"] = _files(target)
            (target / "manifest.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return [target / "summary.json" for target in targets]
