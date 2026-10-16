"""Source-bound Hopper function decompilation without an REA runtime dependency."""

import json
import hashlib
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.ipa import MAX_BINARY, _slice_macho, inspect_macho
from copyapp.verify import sha256_file

SCRIPT = Path(__file__).with_name("hopper_script.py")
DEFAULT_APP = Path("/Applications/Hopper Disassembler.app")
MAX_PSEUDOCODE = 2 * 1024 * 1024
MAX_LOG = 8 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_direct_hopper(app: Optional[Path] = None) -> dict:
    """Check only stable local prerequisites; a GUI analysis still needs a live run."""
    app = (app or Path(os.environ.get("HOPPER_APP", DEFAULT_APP))).resolve(strict=True)
    launcher = app / "Contents/MacOS/hopper"
    if not launcher.is_file() or not os.access(launcher, os.X_OK) or not SCRIPT.is_file():
        raise FileNotFoundError("Hopper launcher or Copy APP script is unavailable")
    info_path = app / "Contents/Info.plist"
    info = plistlib.loads(info_path.read_bytes()) if info_path.is_file() else {}
    return {"healthy": True, "provider": "hopper-direct", "app": str(app),
            "launcher": str(launcher), "version": str(info.get("CFBundleShortVersionString", "unknown")),
            "script_sha256": sha256_file(SCRIPT)}


def _files(output: Path) -> list:
    return [{"path": item.name, "sha256": sha256_file(item)}
            for item in sorted(output.iterdir())
            if item.is_file() and item.name != "manifest.json"]


def decompile_hopper_function(binary: Path, expected_sha256: str, address: str,
                              output: Path, app: Optional[Path] = None,
                              timeout: int = 600) -> Path:
    """Launch Hopper on a private thin copy and retain a verifiable function case."""
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("expected SHA-256 must be lowercase hexadecimal")
    if not re.fullmatch(r"0x[0-9a-fA-F]+", address):
        raise ValueError("function address must be hexadecimal")
    if not 60 <= timeout <= 1800:
        raise ValueError("timeout must be between 60 and 1800 seconds")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    binary = binary.resolve(strict=True)
    if not 0 < binary.stat().st_size <= MAX_BINARY or sha256_file(binary) != expected_sha256:
        raise ValueError("binary is too large or its SHA-256 differs from selected evidence")
    body = _slice_macho(binary.read_bytes())
    details = inspect_macho(body)
    if details["encryption_status"] == "encrypted":
        raise ValueError("Hopper requires the recovered analysis binary")
    doctor = check_direct_hopper(app)
    output.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": 1, "kind": "hopper_direct_decompilation",
              "status": "failed", "binary": str(binary),
              "binary_sha256": expected_sha256,
              "slice_sha256": hashlib.sha256(body).hexdigest(),
              "address": f"0x{int(address, 16):x}",
              "provider": "hopper-direct", "hopper_version": doctor["version"],
              "script_sha256": doctor["script_sha256"], "started_at": _now()}
    shutil.copyfile(SCRIPT, output / "CopyAppHopper.py")
    try:
        with tempfile.TemporaryDirectory(prefix="copyapp-hopper-") as temporary:
            target = Path(temporary) / "target.macho"
            target.write_bytes(body)
            config = {"target": str(target.resolve()), "address": record["address"],
                      "slice_sha256": record["slice_sha256"],
                      "result": str((output / "result.json").resolve()),
                      "pseudocode": str((output / "pseudocode.txt").resolve())}
            script = Path(temporary) / "run.py"
            script.write_text("CONFIG = " + repr(config) + "\n" + SCRIPT.read_text(encoding="utf-8"),
                              encoding="utf-8")
            command = [doctor["launcher"], "--loader", "Mach-O", "--aarch64",
                       "--analysis", "-Y", str(script),
                       "--executable", str(target)]
            deadline = time.monotonic() + timeout
            with (output / "launcher.log").open("wb") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                try:
                    while not (output / "result.json").is_file():
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Hopper did not return function evidence before timeout")
                        exit_code = process.poll()
                        if exit_code is not None and exit_code != 0:
                            raise RuntimeError(f"Hopper launcher exited with status {exit_code}")
                        time.sleep(0.25)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=3)
        if (output / "launcher.log").stat().st_size > MAX_LOG:
            raise ValueError("Hopper launcher log exceeded limit")
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        if result.get("status") != "complete":
            raise RuntimeError("Hopper script failed: " + str(result.get("error", "unknown")))
        if (result.get("address") != record["address"] or
                result.get("binary_path") != config["target"] or
                result.get("slice_sha256") != record["slice_sha256"] or
                not isinstance(result.get("name"), str) or
                not 0 < len(result["name"]) <= 512 or
                not isinstance(result.get("signature"), str) or
                len(result["signature"]) > 2048):
            raise ValueError("Hopper function identity differs from requested binary or address")
        pseudo = output / "pseudocode.txt"
        if not pseudo.is_file() or not 0 < pseudo.stat().st_size <= MAX_PSEUDOCODE:
            raise ValueError("Hopper pseudocode is missing or oversized")
        record.update(status="complete", function_name=result["name"],
                      signature=result["signature"],
                      pseudocode_sha256=sha256_file(pseudo),
                      limitation="Hopper pseudocode is an interpretation, not original source.")
        (output / "report.md").write_text(
            f"# Hopper function {record['address']}\n\n"
            f"- Binary SHA-256: `{expected_sha256}`\n"
            f"- Function: `{result['name']}`\n"
            f"- Signature: `{result['signature']}`\n"
            "- Pseudocode is decompiler output; runtime execution requires separate evidence.\n",
            encoding="utf-8")
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
    record["finished_at"] = _now()
    (output / "summary.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    manifest = {key: record[key] for key in
                ("schema_version", "kind", "status", "binary_sha256", "address")}
    manifest["evidence"] = _files(output)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    if record["status"] != "complete":
        raise RuntimeError(f"Hopper analysis failed; inspect {output / 'summary.json'}")
    return output / "summary.json"
