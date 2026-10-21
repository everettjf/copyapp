"""Non-overwriting guest installation of a source-linked independent Mac build."""

import json
import shutil
from pathlib import Path, PurePosixPath
from uuid import UUID, uuid4

from copyapp.macos.case import Case, digest
from copyapp.macos.chatcomputer import UnknownCompletion
from copyapp.macos.environment import environment_session
from copyapp.macos.observation import validate_reply
from copyapp.macos.package import inventory, snapshot_bundle
from copyapp.macos.playbook import same_build
from copyapp.macos.report import read


def environment_for(build: Path) -> Path:
    frozen = read(build / "plan", "rebuild-plan.json")
    return build / "plan/report/evidence" / frozen["selected_flow_ids"][0] / "source/environment"


def install_params(target: dict, package: dict, original_bundle: str, relative: str) -> dict:
    return {"app_path": target["app_path"], "bundle_id": target["bundle_id"],
            "binary_sha256": package["app"]["binary_sha256"], "package_sha256": package["package_sha256"],
            "source_relative_path": relative, "original_bundle_id": original_bundle}


def install_app(build: Path, output: Path, timeout: float = 60) -> Path:
    from copyapp.verify import verify_case
    build = build.resolve(strict=True)
    if not verify_case(build) or read(build, "manifest.json").get("kind") != "mac_build":
        raise ValueError("a verified source-linked Mac build is required")
    if output.resolve() == build or build in output.resolve().parents:
        raise ValueError("installation case must be outside its build")
    frozen = read(build / "plan", "rebuild-plan.json")
    target = frozen["target"]
    environment = environment_for(build)
    registered = read(environment, "environment.json")
    install_root = registered.get("install_root")
    if not install_root or str(PurePosixPath(target["app_path"]).parent) != install_root:
        raise ValueError("rebuild target must be directly inside the registered guest install_root; prepare a new plan")
    package = read(build / "package", "app-index.json")
    original = read(build / "plan/report", "feature-spec.json")["app"]["bundle_id"]
    case = Case(output, "mac_install")
    phase = "preflight"
    try:
        shutil.copytree(build, case.root / "build", symlinks=True)
        case.record("build/manifest.json")
        with environment_session(environment, timeout) as (_, collector, active, health):
            case.add("session-health.json", health)
            result = health["response"]["result"]
            if ("install_app" not in result.get("capabilities", []) or result.get("install_root") != install_root or
                    active != registered):
                raise ValueError("collector lacks the registered bounded installation capability")
            relative = "packages/" + str(uuid4()) + "/" + PurePosixPath(target["app_path"]).name
            staged = collector.requests / relative
            if (collector.requests.resolve() != collector.requests or
                    collector.requests not in staged.resolve().parents or staged.exists()):
                raise ValueError("package staging must stay inside the new session inbox")
            source = build / "package" / package["snapshot_path"]
            snapshot_bundle(source, staged, package["entries"])
            if inventory(staged) != package["entries"] or inventory(source) != package["entries"]:
                raise ValueError("build package changed during staging")
            params = install_params(target, package, original, relative)
            case.add("install-request.json", params)
            phase = "install_requested"
            installed = collector.call("install_app", params)
            phase = "install_completed"
            case.add("install-result.json", installed)
            if installed["response"]["result"]["package_sha256"] != package["package_sha256"]:
                raise ValueError("installed package differs from build")
            checked = collector.call("package_identity", {key: params[key] for key in ("app_path", "bundle_id", "binary_sha256")})
            case.add("package-check.json", checked)
            if checked["response"]["result"]["package_sha256"] != package["package_sha256"]:
                raise ValueError("installed package changed after installation")
            case.add("install.json", {"schema_version": 2, "platform": "macos", "scope": "installed_package_only",
                                      "build_manifest_sha256": digest(case.root / "build/manifest.json"),
                                      "environment_manifest_sha256": digest(environment / "manifest.json"),
                                      "target": target, "package_sha256": package["package_sha256"],
                                      "launch_verified": False, "behavior_checked": False})
        case.finish("complete", scope="installed_package_only")
        if not verify_case(case.root):
            raise ValueError("installation receipt failed source validation")
        return case.root
    except BaseException as exc:
        if isinstance(getattr(exc, "collector_evidence", None), dict):
            case.add("failed-collector-request.json", exc.collector_evidence)
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc), "phase": phase,
                                  "completion_unknown": isinstance(exc, UnknownCompletion)})
        case.finish("failed", scope="installed_package_only", phase=phase)
        raise


def validate_install(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    required = {"build/manifest.json", "session-health.json", "install-request.json", "install-result.json",
                "package-check.json", "install.json"}
    if (manifest.get("status") != "complete" or manifest.get("scope") != "installed_package_only" or
            not required.issubset(names) or not verify_case(root / "build") or
            read(root / "build", "manifest.json").get("kind") != "mac_build"):
        return False
    build = root / "build"
    environment = environment_for(build)
    registered = read(environment, "environment.json")
    target = read(build / "plan", "rebuild-plan.json")["target"]
    package = read(build / "package", "app-index.json")
    original = read(build / "plan/report", "feature-spec.json")["app"]["bundle_id"]
    health, installed, checked = [read(root, name) for name in ("session-health.json", "install-result.json", "package-check.json")]
    if not validate_reply(health, registered, "health") or health["request"].get("params") != {}:
        return False
    health_result = health["response"]["result"]
    install_root = registered.get("install_root")
    if (not install_root or health_result.get("install_root") != install_root or
            "install_app" not in health_result.get("capabilities", []) or
            str(PurePosixPath(target["app_path"]).parent) != install_root):
        return False
    instance = health["response"]["collector_instance"]
    session = health["request"]["session_id"]
    requests = {health["request"]["request_id"]}
    for value, method in ((installed, "install_app"), (checked, "package_identity")):
        if (not validate_reply(value, registered, method, instance) or
                value["request"].get("session_id") != session or value["request"]["request_id"] in requests):
            return False
        requests.add(value["request"]["request_id"])
    params = read(root, "install-request.json")
    relative = params["source_relative_path"]
    parts = PurePosixPath(relative).parts
    if (len(parts) != 3 or parts[0] != "packages" or str(PurePosixPath(relative)) != relative or
            parts[2] != PurePosixPath(target["app_path"]).name):
        return False
    UUID(parts[1])
    expected = install_params(target, package, original, relative)
    if params != expected or installed["request"].get("params") != expected:
        return False
    identity_params = {key: params[key] for key in ("app_path", "bundle_id", "binary_sha256")}
    if checked["request"].get("params") != identity_params:
        return False
    result, check = installed["response"]["result"], checked["response"]["result"]
    for facts in (result["app"], check["app"]):
        same_build(facts, package)
        if facts.get("app_path") != target["app_path"]:
            return False
    signature = result.get("signature", {})
    stage = install_root + "/.copyapp-install-" + installed["request"]["request_id"] + ".app"
    if (signature.get("executable") != "/usr/bin/codesign" or signature.get("arguments") != ["--verify", "--deep", "--strict", stage] or
            type(signature.get("returncode")) is not int or signature["returncode"] != 0):
        return False
    if (result.get("source_relative_path") != relative or result.get("install_root") != install_root or
            result.get("package_sha256") != package["package_sha256"] or result.get("entry_count") != len(package["entries"]) or
            result.get("consistency") != "matching_staged_source_copy_installed_inventories" or result.get("launched") is not False or
            check.get("package_sha256") != package["package_sha256"] or check.get("entry_count") != len(package["entries"]) or
            check.get("consistency") != "two_matching_inventories"):
        return False
    record = read(root, "install.json")
    return (type(record.get("schema_version")) is int and record["schema_version"] == 2 and
            record.get("platform") == "macos" and record.get("scope") == "installed_package_only" and
            record.get("build_manifest_sha256") == digest(build / "manifest.json") and
            record.get("environment_manifest_sha256") == digest(environment / "manifest.json") and
            record.get("target") == target and record.get("package_sha256") == package["package_sha256"] and
            record.get("launch_verified") is False and record.get("behavior_checked") is False)
