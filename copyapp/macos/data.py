"""Explicit single-file App data capture; never a complete or atomic DB snapshot."""

import re
import shutil
from pathlib import Path, PurePosixPath

from copyapp.macos.case import Case, digest
from copyapp.macos.environment import environment_session
from copyapp.macos.observation import validate_reply
from copyapp.macos.playbook import output_bytes
from copyapp.macos.report import read


MAX_DATA = 64 << 20
ASSOCIATIONS = {"sandbox": "bundle_named_container_convention",
                "preferences": "bundle_named_preferences_convention",
                "support": "explicit_path_not_proof_of_app_ownership"}


def source_path(location: str, relative: str, bundle: str, library: str) -> str:
    if (not isinstance(bundle, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,255}", bundle) or bundle in {".", ".."} or
            location not in ASSOCIATIONS or not isinstance(relative, str) or not relative or relative == "." or
            len(relative.encode("utf-8")) > 4096 or "\0" in relative or "\\" in relative or
            PurePosixPath(relative).is_absolute() or str(PurePosixPath(relative)) != relative or
            any(part in {".", ".."} or len(part.encode("utf-8")) > 255 for part in PurePosixPath(relative).parts) or
            not isinstance(library, str) or not library.startswith("/") or "\0" in library or
            ".." in PurePosixPath(library).parts or str(PurePosixPath(library)) != library or
            PurePosixPath(library).name != "Library"):
        raise ValueError("expected a bounded App data location and canonical relative file path")
    if location == "preferences" and relative != bundle + ".plist":
        raise ValueError("preferences capture requires exactly the selected Bundle ID's plist")
    if location == "support" and len(PurePosixPath(relative).parts) < 2:
        raise ValueError("support capture requires an explicit folder and file")
    roots = {"sandbox": PurePosixPath(library) / "Containers" / bundle / "Data",
             "preferences": PurePosixPath(library) / "Preferences",
             "support": PurePosixPath(library) / "Application Support"}
    return str(roots[location] / relative)


def export_record(source: Path, health: dict, exported: dict) -> dict:
    target = read(source, "acquisition.json")
    package = read(source / "package", "app-index.json")
    environment = read(source / "environment", "environment.json")
    if (not validate_reply(health, environment, "health") or
            "data_file" not in health["response"]["result"].get("capabilities", []) or
            "data_file" not in read(source / "environment/collector-build", "collector-build.json")["self_test"]["methods"] or
            not validate_reply(exported, environment, "data_file", health["response"]["collector_instance"]) or
            exported["request"]["session_id"] != health["request"]["session_id"]):
        raise ValueError("data export has a different guest, collector or session")
    params, result = exported["request"]["params"], exported["response"]["result"]
    app = package["app"]
    facts = result["source_app"]
    expected = {"app_path": target["guest_app_path"], "bundle_id": target["bundle_id"],
                "binary_sha256": app["binary_sha256"], "location": result["location"],
                "relative_path": result["relative_source_path"]}
    if params != expected or any(facts[key] != app[key] for key in ("bundle_id", "binary_sha256", "version", "build")):
        raise ValueError("data export does not identify the acquired App build")
    info = next(row for row in package["entries"] if row["path"] == "Contents/Info.plist")
    expected_path = source_path(params["location"], params["relative_path"], app["bundle_id"], result["guest_library"])
    metadata = result["source_metadata"]
    if (facts["app_path"] != target["guest_app_path"] or facts["info_plist_sha256"] != info["sha256"] or
            result["guest_source_path"] != expected_path or result["association"] != ASSOCIATIONS[params["location"]] or
            result["relative_path"] != "data-files/" + exported["request"]["request_id"] + "/file.bin" or
            type(result["size"]) is not int or not 0 <= result["size"] <= MAX_DATA or
            not isinstance(result["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", result["sha256"]) or
            result.get("consistency") != "two_matching_reads_and_export" or result.get("atomic_database_snapshot") is not False or
            result.get("complete_app_data") is not False or not isinstance(metadata, dict) or
            set(metadata) != {"device", "inode", "size", "mtime_seconds", "mtime_nanoseconds", "ctime_seconds", "ctime_nanoseconds"} or
            any(type(value) is not int for value in metadata.values()) or metadata["size"] != result["size"] or
            min(metadata["device"], metadata["inode"]) < 0 or
            not all(0 <= metadata[key] < 1_000_000_000 for key in ("mtime_nanoseconds", "ctime_nanoseconds"))):
        raise ValueError("data source policy or snapshot consistency is invalid")
    return {"schema_version": 2, "platform": "macos", "scope": "selected_app_data_file",
            "source_manifest_sha256": digest(source / "manifest.json"), "bundle_id": app["bundle_id"],
            "package_sha256": package["package_sha256"], "environment_manifest_sha256": digest(source / "environment/manifest.json"),
            "guest_source_path": expected_path, "location": params["location"], "relative_path": params["relative_path"],
            "association": result["association"], "sha256": result["sha256"], "size": result["size"],
            "atomic_database_snapshot": False, "complete_app_data": False}


def data_file(acquisition: Path, location: str, relative: str, output: Path, timeout: float = 60) -> Path:
    from copyapp.verify import verify_case
    acquisition = acquisition.resolve(strict=True)
    if (not verify_case(acquisition) or read(acquisition, "manifest.json").get("kind") != "mac_app_acquisition" or
            output.resolve() == acquisition or acquisition in output.resolve().parents):
        raise ValueError("data capture needs a verified Mac acquisition and a separate new output case")
    target = read(acquisition, "acquisition.json")
    package = read(acquisition / "package", "app-index.json")
    source_path(location, relative, target["bundle_id"], "/placeholder/Library")
    case = Case(output, "mac_data_file")
    try:
        shutil.copytree(acquisition, case.root / "source", symlinks=True)
        case.record("source/manifest.json")
        with environment_session(acquisition / "environment", timeout) as (_, collector, _, health):
            case.add("session-health.json", health)
            if "data_file" not in health["response"]["result"].get("capabilities", []):
                raise ValueError("registered collector build does not support bounded data capture")
            exported = collector.call("data_file", {"app_path": target["guest_app_path"], "bundle_id": target["bundle_id"],
                                                    "binary_sha256": package["app"]["binary_sha256"],
                                                    "location": location, "relative_path": relative})
            case.add("export.json", exported)
            record = export_record(case.root / "source", health, exported)
            path = collector.responses / exported["response"]["result"]["relative_path"]
            if collector.responses.resolve() != collector.responses or (collector.root / "outbox").resolve() != collector.root / "outbox":
                raise ValueError("data export workspace is linked")
            data = output_bytes(path, collector.responses, MAX_DATA)
            case.add("data.bin", data, binary=True)
            if digest(case.root / "data.bin") != record["sha256"] or len(data) != record["size"]:
                raise ValueError("returned data differs from the collector's two-read snapshot")
            case.add("data-file.json", record)
        case.finish("complete", scope="selected_app_data_file", bundle_id=target["bundle_id"])
        if not verify_case(case.root):
            raise ValueError("copied data source changed during capture")
        return case.root
    except BaseException as exc:
        if isinstance(getattr(exc, "collector_evidence", None), dict):
            case.add("failed-collector-request.json", exc.collector_evidence)
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="selected_app_data_file")
        raise


def validate_data(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    if (manifest.get("status") != "complete" or manifest.get("scope") != "selected_app_data_file" or
            not {"source/manifest.json", "session-health.json", "export.json", "data.bin", "data-file.json"}.issubset(names) or
            not verify_case(root / "source") or read(root / "source", "manifest.json").get("kind") != "mac_app_acquisition"):
        return False
    record = export_record(root / "source", read(root, "session-health.json"), read(root, "export.json"))
    return (read(root, "data-file.json") == record and manifest.get("bundle_id") == record["bundle_id"] and
            (root / "data.bin").stat().st_size == record["size"] and digest(root / "data.bin") == record["sha256"])
