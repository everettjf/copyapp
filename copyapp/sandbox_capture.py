"""Capture explicitly selected, indexed app-container files over pinned USB SSH."""

import hashlib
import io
import json
import re
import shlex
import subprocess
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import List

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.sandbox import CONTAINER_PATTERN
from copyapp.ssh_acquire import _ssh_argv
from copyapp.verify import checked_path, sha256_file, verify_case


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_PATHS = 4


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _relative(raw: str) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 1024 or any(
            ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError("sandbox path is invalid")
    parsed = PurePosixPath(raw)
    if (parsed.is_absolute() or ".." in parsed.parts or "." in parsed.parts or
            str(parsed) != raw or not parsed.parts):
        raise ValueError("sandbox path must be a normalized relative path")
    return raw


def _select(index: dict, paths: List[str]) -> list:
    if not 1 <= len(paths) <= MAX_PATHS or len(set(paths)) != len(paths):
        raise ValueError("choose one to four distinct sandbox paths")
    entries = index.get("entries")
    if not isinstance(entries, list):
        raise ValueError("sandbox index has no entries")
    by_path = {item.get("relative"): item for item in entries if isinstance(item, dict)}
    if len(by_path) != len(entries):
        raise ValueError("sandbox index contains duplicate paths")
    selected = []
    total = 0
    for raw in paths:
        relative = _relative(raw)
        item = by_path.get(relative)
        if not isinstance(item, dict) or item.get("kind") != "f" or \
                type(item.get("size")) is not int or not 0 <= item["size"] <= MAX_FILE_BYTES:
            raise ValueError(f"sandbox path is not an indexed bounded regular file: {relative}")
        parents = PurePosixPath(relative).parents
        for parent in parents:
            if str(parent) != "." and by_path.get(str(parent), {}).get("kind") != "d":
                raise ValueError(f"sandbox path has a non-directory ancestor: {relative}")
        total += item["size"]
        if total > MAX_TOTAL_BYTES:
            raise ValueError("selected sandbox files exceed total limit")
        selected.append(dict(item))
    return selected


def _source(analysis: Path, paths: List[str]) -> tuple[dict, dict, list]:
    analysis = analysis.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(analysis):
            raise ValueError("analysis case failed hash verification")
    if not (analysis / "analysis-index.json").is_file():
        raise ValueError("source must be a verified analysis case")
    survey = _read(analysis / "survey/manifest.json")
    index = _read(analysis / "sandbox-index.json")
    if (index.get("schema_version") != 1 or
            index.get("source") != "read-only SSH find metadata through USB tunnel" or
            index.get("bundle_id") != survey.get("bundle_id") or
            index.get("device_id_sha256_prefix") !=
            survey.get("device_id_sha256_prefix") or
            not re.fullmatch(r"[0-9a-f]{16}",
                             str(index.get("container_path_sha256_prefix", "")))):
        raise ValueError("sandbox index differs from analysis device or app")
    return survey, index, _select(index, paths)


def _stream_file(argv: list, container: str, relative: str, destination: Path,
                 expected_size: int) -> str:
    path = container + "/" + relative
    parts = PurePosixPath(relative).parts
    ancestors = [container + "/" + "/".join(parts[:count])
                 for count in range(1, len(parts))]
    checks = " && ".join("[ ! -L " + shlex.quote(item) + " ]" for item in ancestors)
    command = ((checks + " && ") if checks else "") + \
              "[ -f " + shlex.quote(path) + " ] && [ ! -L " + \
              shlex.quote(path) + " ] && cat " + shlex.quote(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    with destination.open("wb") as target:
        process = subprocess.Popen(argv + [command], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        try:
            assert process.stdout is not None
            while chunk := process.stdout.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_FILE_BYTES or total > expected_size:
                    raise ValueError("remote sandbox file exceeds its indexed size")
                digest.update(chunk)
                target.write(chunk)
            stderr = process.stderr.read(512) if process.stderr else b""
            if process.wait(timeout=30) != 0:
                raise RuntimeError("remote sandbox file read failed: " +
                                   stderr.decode(errors="replace")[:256])
        except Exception:
            process.kill()
            process.wait()
            raise
    if total != expected_size:
        raise ValueError("remote sandbox file size changed since index capture")
    return digest.hexdigest()


async def capture_sandbox_files(udid: str, analysis: Path, paths: List[str],
                                output: Path, port: int, identity: Path,
                                known_hosts: Path, user: str) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"sandbox capture output is not empty: {output}")
    survey, index, selected = _source(analysis, paths)
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    if prefix != survey.get("device_id_sha256_prefix"):
        raise ValueError("selected USB device differs from source analysis")
    argv = _ssh_argv(port, identity, known_hosts, user)
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any",
                                        bundle_identifiers=[index["bundle_id"]])
        app = apps.get(index["bundle_id"])
        if not isinstance(app, dict):
            raise ValueError("source app is no longer installed")
        container = str(app.get("Container") or "")
        if (not CONTAINER_PATTERN.fullmatch(container) or
                hashlib.sha256(container.encode()).hexdigest()[:16] !=
                index["container_path_sha256_prefix"] or
                app.get("CFBundleShortVersionString") != index.get("installed_version") or
                app.get("CFBundleVersion") != index.get("installed_build")):
            raise ValueError("installed app container or version differs from source index")
        output.mkdir(parents=True, exist_ok=True)
        records = []
        for item in selected:
            relative = item["relative"]
            destination = checked_path(output, "files/" + relative)
            digest = _stream_file(argv, container, relative, destination, item["size"])
            records.append({"relative": relative, "source_entry": item,
                            "path": "files/" + relative, "sha256": digest,
                            "size": item["size"]})
        record = {"schema_version": 1, "kind": "sandbox_file_capture",
                  "status": "complete", "captured_at": datetime.now(timezone.utc).isoformat(
                      timespec="seconds"),
                  "source_analysis": str(analysis.resolve()),
                  "source_analysis_index_sha256": sha256_file(analysis / "analysis-index.json"),
                  "source_sandbox_index_sha256": sha256_file(analysis / "sandbox-index.json"),
                  "device_id_sha256_prefix": prefix,
                  "bundle_id": index["bundle_id"],
                  "container_path_sha256_prefix": index["container_path_sha256_prefix"],
                  "files": records,
                  "limitation": "Read-only sequential copies; live file and WAL snapshots may not be atomic. Raw local files can contain private app data."}
        (output / "capture.json").write_text(json.dumps(record, ensure_ascii=False,
                                                        indent=2) + "\n", encoding="utf-8")
        (output / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "sandbox_file_capture", "status": "complete",
            "evidence": [{"path": item["path"], "sha256": item["sha256"]}
                         for item in records] + [{"path": "capture.json",
                                                  "sha256": sha256_file(output / "capture.json")}],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return output / "capture.json"
    finally:
        await device.close()


def validate_sandbox_file_capture(output: Path) -> bool:
    saved = _read(output / "capture.json")
    source = Path(saved["source_analysis"]).resolve(strict=True)
    if (source == output.resolve() or output.resolve() in source.parents or
            source in output.resolve().parents):
        return False
    survey, index, selected = _source(source, [item["relative"] for item in saved["files"]])
    manifest = _read(output / "manifest.json")
    if (saved.get("schema_version") != 1 or saved.get("kind") != "sandbox_file_capture" or
            saved.get("status") != "complete" or
            manifest.get("schema_version") != 1 or
            manifest.get("kind") != "sandbox_file_capture" or
            manifest.get("status") != "complete" or
            saved.get("source_analysis_index_sha256") !=
            sha256_file(source / "analysis-index.json") or
            saved.get("source_sandbox_index_sha256") !=
            sha256_file(source / "sandbox-index.json") or
            saved.get("bundle_id") != survey.get("bundle_id") or
            saved.get("device_id_sha256_prefix") !=
            survey.get("device_id_sha256_prefix") or
            saved.get("container_path_sha256_prefix") !=
            index.get("container_path_sha256_prefix") or
            len(saved["files"]) != len(selected)):
        return False
    expected = {"capture.json"}
    for record, item in zip(saved["files"], selected):
        relative = _relative(record["relative"])
        path = "files/" + relative
        file = checked_path(output, path)
        if (record.get("path") != path or record.get("source_entry") != item or
                record.get("size") != item["size"] or
                not file.is_file() or file.stat().st_size != item["size"] or
                record.get("sha256") != sha256_file(file)):
            return False
        expected.add(path)
    listed = [item.get("path") for item in manifest.get("evidence", [])]
    return len(listed) == len(expected) and set(listed) == expected
