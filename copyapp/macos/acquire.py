"""Acquire a stable guest .app snapshot through the bounded collector."""

import json
import shutil
from pathlib import Path, PurePosixPath

from copyapp.macos.case import Case, digest
from copyapp.macos.environment import environment_session
from copyapp.macos.observation import validate_reply
from copyapp.macos.package import index_app


def acquire_app(environment: Path, app_path: str, bundle_id: str, output: Path,
                timeout: float = 60) -> Path:
    from copyapp.verify import verify_case
    environment = environment.resolve(strict=True)
    if output.resolve() == environment or environment in output.resolve().parents:
        raise ValueError("acquisition must be outside its source environment")
    if not verify_case(environment):
        raise ValueError("source environment is not verified")
    case = Case(output, "mac_app_acquisition")
    try:
        shutil.copytree(environment, case.root / "environment", symlinks=True)
        case.record("environment/manifest.json")
        with environment_session(environment, timeout) as (computer, collector, registered, health):
            case.add("session-health.json", health)
            identity = collector.call("app_identity", {"app_path": app_path, "bundle_id": bundle_id})
            case.add("identity.json", identity)
            facts = identity["response"]["result"]
            exported = collector.call("export_app", {"app_path": facts["app_path"], "bundle_id": bundle_id,
                                                      "binary_sha256": facts["binary_sha256"]})
            case.add("export.json", exported)
            result = exported["response"]["result"]
            relative = result["relative_path"]
            parts = PurePosixPath(relative).parts
            if (len(parts) != 3 or parts[0] != "exports" or
                    parts[1] != exported["request"]["request_id"] or
                    not parts[2].endswith(".app") or str(PurePosixPath(relative)) != relative):
                raise ValueError("invalid guest package export path")
            source = collector.responses.joinpath(*parts)
            base = collector.root / "outbox"
            if (base.resolve() != base or base not in source.resolve(strict=True).parents or
                    any(path.is_symlink() for path in [source, *source.parents]
                        if path == base or base in path.parents)):
                raise ValueError("guest package export escapes its outbox")
            package = index_app(source, case.root / "package")
            case.record("package/manifest.json")
            index = json.loads((package / "app-index.json").read_text())
            if result["package_sha256"] != index["package_sha256"]:
                raise ValueError("exported package differs from the observed guest bundle")
            case.add("acquisition.json", {"schema_version": 2, "platform": "macos", "bundle_id": bundle_id,
                                          "scope": "guest_package_snapshot", "guest_app_path": facts["app_path"],
                                          "environment_manifest_sha256": digest(environment / "manifest.json"),
                                          "package_manifest_sha256": digest(package / "manifest.json")})
        case.finish("complete", scope="guest_package_snapshot", bundle_id=bundle_id)
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="guest_package_snapshot", bundle_id=bundle_id)
        raise


def validate_acquisition(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    required = {"environment/manifest.json", "package/manifest.json", "session-health.json",
                "identity.json", "export.json", "acquisition.json"}
    if (manifest.get("status") != "complete" or manifest.get("scope") != "guest_package_snapshot" or
            not required.issubset(names)):
        return False
    if not verify_case(root / "environment") or not verify_case(root / "package"):
        return False
    environment = json.loads((root / "environment/environment.json").read_text())
    package = json.loads((root / "package/app-index.json").read_text())
    health = json.loads((root / "session-health.json").read_text())
    identity = json.loads((root / "identity.json").read_text())
    exported = json.loads((root / "export.json").read_text())
    record = json.loads((root / "acquisition.json").read_text())
    if not validate_reply(health, environment, "health"):
        return False
    instance = health["response"]["collector_instance"]
    if not validate_reply(identity, environment, "app_identity", instance) or not validate_reply(exported, environment, "export_app", instance):
        return False
    if any(item["request"]["session_id"] != health["request"]["session_id"] for item in (identity, exported)):
        return False
    result = exported["response"]["result"]
    facts = identity["response"]["result"]
    guest = result["source_app"]
    params = exported["request"]["params"]
    common = ("bundle_id", "app_path", "executable_path", "binary_sha256", "info_plist_sha256", "version", "build")
    if any(facts.get(key) != guest.get(key) for key in common):
        return False
    app = package["app"]
    if any(app.get(key) != facts.get(key) for key in ("bundle_id", "binary_sha256", "version", "build")):
        return False
    info = next((row for row in package["entries"] if row["path"] == "Contents/Info.plist"), {})
    return (record.get("schema_version") == 2 and record.get("platform") == "macos" and
            record.get("scope") == "guest_package_snapshot" and
            record.get("bundle_id") == manifest.get("bundle_id") == facts["bundle_id"] and
            record.get("guest_app_path") == facts["app_path"] and
            record.get("environment_manifest_sha256") == digest(root / "environment/manifest.json") and
            record.get("package_manifest_sha256") == digest(root / "package/manifest.json") and
            params.get("binary_sha256") == facts["binary_sha256"] and
            params.get("app_path") == facts["app_path"] and params.get("bundle_id") == facts["bundle_id"] and
            info.get("sha256") == facts.get("info_plist_sha256") and
            result.get("package_sha256") == package.get("package_sha256") and
            result.get("entry_count") == len(package["entries"]) and
            result.get("consistency") == "matching_source_copy_source_inventories")
