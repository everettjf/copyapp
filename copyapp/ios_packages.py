"""Host-side package inputs, independently attributed from phone observations."""

import io
import plistlib
import re
import shutil
import subprocess
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zipfile import BadZipFile, ZipFile

from copyapp.ipa import analyze_ipa
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.verify import sha256_file, verify_case

IPATOOL_VERSION = "2.7.0"

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def package_index(ipa: Path) -> dict:
    result = analyze_ipa(ipa)
    # A package case remains verifiable after being copied into a report.
    result["source"] = "input.ipa"
    with ZipFile(ipa) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("package has duplicate archive members")
        infos = [name for name in names if re.fullmatch(r"Payload/[^/]+\.app/Info.plist", name)]
        if len(infos) != 1:
            raise ValueError("package must contain exactly one primary iOS App")
        info = plistlib.loads(archive.read(infos[0]))
        platforms = info.get("CFBundleSupportedPlatforms")
        if platforms is not None and (not isinstance(platforms, list) or "iPhoneOS" not in platforms):
            raise ValueError("package does not declare iOS support; Mac packages use copyapp mac")
        result["declared_platforms"] = platforms
        if "iTunesMetadata.plist" in names:
            metadata = plistlib.loads(archive.read("iTunesMetadata.plist"))
            value = metadata.get("softwareVersionExternalIdentifier")
            if type(value) in (str, int) and re.fullmatch(r"[0-9]+", str(value)):
                result["external_version_id"] = str(value)
    return result


def _finish_package(output: Path, record: dict) -> Path:
    if record["status"] == "complete":
        index = package_index(output / "input.ipa")
        requested = record.get("requested_bundle_id")
        if requested is not None and index["bundle_id"] != requested:
            raise ValueError("downloaded package Bundle ID differs from requested App")
        if record["source_type"] == "user_import" and record["original_sha256"] != index["ipa_sha256"]:
            raise ValueError("input IPA changed during import")
        if record["source_type"] == "appstore_download":
            requested_version = record["requested_external_version_id"]
            actual_version = index.get("external_version_id")
            if requested_version is not None and actual_version is not None and requested_version != actual_version:
                raise ValueError("downloaded external version differs from the requested version")
            record["external_version_check"] = ("not_requested" if requested_version is None else
                                                 "matched" if actual_version == requested_version else "unverified")
        record["bundle_id"] = index["bundle_id"]
        record["ipa_sha256"] = index["ipa_sha256"]
        write_json(output / "package-index.json", index)
    write_json(output / "package.json", record)
    lines = ["# iOS package input", "", f"Status: `{record['status']}`.",
             f"Source: `{record['source_type']}`.", "",
             "This is host-side package evidence. It does not establish the identity of an installed "
             "phone binary, runtime behavior, correct decrypted code, or installability.", ""]
    if record["status"] == "complete":
        lines += [f"Bundle ID: `{record['bundle_id']}`. SHA-256: `{record['ipa_sha256']}`.", "",
                  "[Static index](package-index.json). Encrypted functions remain unavailable until "
                  "separately recovered and checked. Account-specific license files stay in this ignored case.", ""]
    else:
        lines += ["Download did not complete. Raw account/session output is deliberately not retained. "
                  "Check authentication and App ownership interactively with ipatool, then use a new case.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return seal_case(output, "ios_package", status=record["status"],
                     bundle_id=record.get("bundle_id"), source_type=record["source_type"])


def import_package(ipa: Path, output: Path, bundle: Optional[str] = None) -> Path:
    if output.exists():
        raise FileExistsError(output)
    if not ipa.is_file() or ipa.is_symlink():
        raise ValueError("input IPA must be a regular file")
    index = package_index(ipa)
    if bundle is not None and bundle != index["bundle_id"]:
        raise ValueError("input IPA Bundle ID differs from requested App")
    output.mkdir(parents=True)
    shutil.copyfile(ipa, output / "input.ipa")
    return _finish_package(output, {"status": "complete", "source_type": "user_import",
                                    "created_at": _now(), "requested_bundle_id": bundle,
                                    "original_sha256": index["ipa_sha256"]})


def download_package(bundle: str, output: Path, tool: Optional[Path] = None,
                       external_version: Optional[str] = None,
                       acquire_license: bool = False, timeout: int = 600) -> tuple[Path, bool]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid Bundle ID")
    if external_version is not None and not re.fullmatch(r"[0-9]+", external_version):
        raise ValueError("external version must be the numeric App Store version identifier")
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("download timeout must be 1–3600 seconds")
    if output.exists():
        raise FileExistsError(output)
    local_tool = Path("toolchains/bin/ipatool")
    executable = tool or (local_tool if local_tool.is_file() else
                          Path(shutil.which("ipatool")) if shutil.which("ipatool") else None)
    if executable is None or not executable.is_file():
        raise FileNotFoundError("ipatool is not installed; install and authenticate it interactively first")
    executable = executable.resolve(strict=True)
    tool_hash = sha256_file(executable)
    version = subprocess.run([str(executable), "--version"], capture_output=True, timeout=10, check=False)
    match = re.search(rb"\b[0-9]+\.[0-9]+\.[0-9]+\b", version.stdout + version.stderr)
    if version.returncode or match is None:
        raise ValueError("ipatool did not return a recognizable version")
    if match.group().decode() != IPATOOL_VERSION:
        raise ValueError(f"ipatool version differs from the reviewed {IPATOOL_VERSION}; run the pinned host-tool setup")
    output.mkdir(parents=True)
    command = [str(executable), "--non-interactive", "--format", "json", "download",
               "--bundle-identifier", bundle, "--platform", "iphone", "--output",
               str((output / "input.ipa").resolve())]
    if external_version:
        command += ["--external-version-id", external_version]
    if acquire_license:
        command.append("--purchase")
    record = {"status": "failed", "source_type": "appstore_download", "created_at": _now(),
              "requested_bundle_id": bundle, "requested_external_version_id": external_version,
              "requested_platform": "iphone", "storefront": "account_selected_not_independently_verified",
              "license_acquisition_requested": acquire_license,
              "tool": {"name": "ipatool", "version": match.group().decode(), "sha256": tool_hash},
              "exit_code": None, "error": "download_failed"}
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
        record["exit_code"] = result.returncode
        # stdout/stderr may contain account data, signed URLs and session tokens.
        # Retain only outcome metadata; never serialize their raw values.
        if sha256_file(executable) != tool_hash:
            record["error"] = "tool_changed_during_download"
        elif result.returncode == 0 and (output / "input.ipa").is_file():
            package_index(output / "input.ipa")
            record["status"] = "complete"
            record.pop("error")
    except subprocess.TimeoutExpired:
        record["error"] = "download_timeout"
    except (OSError, ValueError, BadZipFile):
        record["error"] = "invalid_download_or_package"
    try:
        path = _finish_package(output, record)
    except (ValueError, OSError, BadZipFile):
        record.update(status="failed", error="package_identity_or_structure_mismatch")
        path = _finish_package(output, record)
    return path, record["status"] == "complete"


def validate_package(root: Path, manifest: dict) -> bool:
    record = read_json(root / "package.json")
    if (record.get("status") != manifest.get("status") or
            record.get("source_type") != manifest.get("source_type") or
            record.get("source_type") not in ("user_import", "appstore_download")):
        return False
    if record["status"] == "failed":
        return (record["source_type"] == "appstore_download" and
                record.get("error") in {"download_failed", "download_timeout", "invalid_download_or_package",
                                        "package_identity_or_structure_mismatch", "tool_changed_during_download"})
    if record["status"] != "complete":
        return False
    index = package_index(root / "input.ipa")
    if (read_json(root / "package-index.json") != index or
            manifest.get("bundle_id") != record.get("bundle_id") or
            record.get("ipa_sha256") != index["ipa_sha256"] or
            record["bundle_id"] != index["bundle_id"] or
            record.get("requested_bundle_id") not in (None, index["bundle_id"])):
        return False
    if record["source_type"] == "user_import":
        return record.get("original_sha256") == index["ipa_sha256"]
    requested = record.get("requested_external_version_id")
    actual = index.get("external_version_id")
    if requested is not None and actual is not None and requested != actual:
        return False
    expected_check = "not_requested" if requested is None else "matched" if requested == actual else "unverified"
    return (record.get("external_version_check") == expected_check and
            record.get("exit_code") == 0 and record.get("requested_platform") == "iphone" and
            isinstance(record.get("tool"), dict) and
            record["tool"].get("name") == "ipatool" and record["tool"].get("version") == IPATOOL_VERSION and
            re.fullmatch(r"[0-9a-f]{64}", record["tool"].get("sha256", "")) is not None)


def verified_package(root: Path) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(root):
            raise ValueError("package input failed case verification")
    manifest = read_json(root / "manifest.json")
    if manifest.get("kind") != "ios_package" or manifest.get("status") != "complete":
        raise ValueError("expected a complete iOS package input")
    return read_json(root / "package-index.json")
