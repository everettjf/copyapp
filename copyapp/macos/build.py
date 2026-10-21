"""Build independent Mac source pinned to a reviewed plan, without launching it."""

import hashlib
import os
import platform
import plistlib
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from copyapp.macos.case import Case, canonical, digest, now
from copyapp.macos.package import app_facts, index_app, inventory, snapshot_bundle
from copyapp.macos.report import read, text


IGNORED = (".git", ".build", "DerivedData", "__pycache__", ".DS_Store")
MAX_LOG = 16 << 20


def generated_directories(before: list, after: list, recipe: dict) -> list:
    """Permit only Xcode's newly created empty workspace metadata directories."""
    originals = {row["path"]: row for row in before}
    observed = {row["path"]: row for row in after}
    if any(observed.get(name) != row for name, row in originals.items()):
        raise ValueError("build changed captured source inputs")
    added = [row for row in after if row["path"] not in originals]
    prefix = (recipe.get("xcode_project") or "") + "/project.xcworkspace"
    if added and (recipe["mode"] != "xcode" or len(added) > 128 or
                  any(row["kind"] != "directory" or
                      not (row["path"] == prefix or row["path"].startswith(prefix + "/")) for row in added)):
        raise ValueError("build wrote unexpected files into captured source; inspect before a new attempt")
    return added


def relative(value: str) -> str:
    if (not isinstance(value, str) or not value or "\0" in value or
            PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts or
            str(PurePosixPath(value)) != value or PurePosixPath(value).parts[0] in IGNORED):
        raise ValueError("build input must be a canonical project-relative path")
    return value


def recipe_for(*, swift_sources=(), info_plist=None, resources=None, xcode_project=None,
               scheme=None, configuration="Debug", signing_identity="-", deployment_target="14.0") -> dict:
    sources = list(swift_sources)
    if bool(sources) == bool(xcode_project):
        raise ValueError("choose Swift source files or an Xcode project")
    text(signing_identity)
    if len(signing_identity) > 256 or "\0" in signing_identity:
        raise ValueError("invalid signing identity")
    if xcode_project:
        if sources or info_plist is not None or resources is not None:
            raise ValueError("Swift bundle inputs cannot be mixed with an Xcode build")
        relative(xcode_project); text(scheme); text(configuration)
        if not xcode_project.endswith(".xcodeproj") or any("\0" in value for value in (scheme, configuration)):
            raise ValueError("invalid Xcode project, scheme or configuration")
        if deployment_target not in {None, "14.0"}:
            raise ValueError("set the Xcode deployment target in the project settings")
    else:
        if (not 1 <= len(sources) <= 256 or len(set(sources)) != len(sources) or scheme is not None or
                configuration not in {"Debug", "Release"} or
                not re.fullmatch(r"[1-9][0-9]?\.[0-9]{1,2}(?:\.[0-9]{1,2})?", deployment_target)):
            raise ValueError("invalid Swift source list or deployment target")
        for source in sources:
            if not relative(source).endswith(".swift"):
                raise ValueError("Swift inputs must have a .swift extension")
        relative(info_plist)
        if resources is not None:
            relative(resources)
    return {"mode": "xcode" if xcode_project else "swift", "swift_sources": sources,
            "info_plist": info_plist, "resources": resources, "xcode_project": xcode_project,
            "scheme": scheme, "configuration": configuration, "signing_identity": signing_identity,
            "deployment_target": None if xcode_project else deployment_target}


def run_command(argv: list, cwd: Path, logs: list, timeout: float, *, sdk_root=None):
    """Retain bounded output and stop only this owned build's process group."""
    log = {"argv": argv, "cwd": str(cwd), "started_at": now(), "timed_out": False}
    environment = None
    if sdk_root is not None:
        environment = dict(os.environ, SDKROOT=sdk_root)
        log["environment"] = {"SDKROOT": sdk_root}
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True,
                                   env=environment)
        try:
            process.wait(timeout=timeout)
        except BaseException as exc:
            log["timed_out"] = isinstance(exc, subprocess.TimeoutExpired)
            log["interrupted"] = not log["timed_out"]
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            except ProcessLookupError:
                pass
            raise
        finally:
            stdout.seek(0); stderr.seek(0)
            out, err = stdout.read(MAX_LOG + 1), stderr.read(MAX_LOG + 1)
            log.update(returncode=process.returncode, finished_at=now(),
                       stdout=out[:MAX_LOG].decode("utf-8", errors="replace"),
                       stderr=err[:MAX_LOG].decode("utf-8", errors="replace"),
                       output_truncated=len(out) > MAX_LOG or len(err) > MAX_LOG)
            logs.append(log)
    if process.returncode or log["output_truncated"]:
        raise RuntimeError("Mac build command failed or exceeded output bound: " + Path(argv[0]).name +
                           "; inspect build-log.json\n" + log["stderr"][-1200:])


def tool(path: str) -> dict:
    # swiftc dispatches by argv[0]; executing its swift-frontend symlink target
    # changes driver behavior. Hash the resolved bytes, execute the driver path.
    driver = Path(path).absolute()
    resolved = driver.resolve(strict=True)
    return {"path": str(driver), "resolved_path": str(resolved), "sha256": digest(resolved)}


def commands(workspace: Path, target: dict, recipe: dict, tools: dict, executable: str) -> list:
    source = workspace / "source"
    app = workspace / "products" / PurePosixPath(target["app_path"]).name
    compiler, signer = tools["compiler"]["path"], tools["codesign"]["path"]
    if recipe["mode"] == "swift":
        build = [compiler, "-sdk", tools["sdk"]["path"], "-parse-as-library", "-swift-version", "5", "-target", "arm64-apple-macos" + recipe["deployment_target"],
                 "-O" if recipe["configuration"] == "Release" else "-Onone",
                 *[str(source / name) for name in recipe["swift_sources"]],
                 "-o", str(app / "Contents/MacOS" / executable)]
    else:
        build = [compiler, "-project", str(source / recipe["xcode_project"]), "-scheme", recipe["scheme"],
                 "-configuration", recipe["configuration"], "-sdk", tools["sdk"]["path"],
                 "-destination", "generic/platform=macOS", "-derivedDataPath", str(workspace / "derived"),
                 "CONFIGURATION_BUILD_DIR=" + str(workspace / "products"), "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES",
                 "CODE_SIGN_IDENTITY=" + recipe["signing_identity"], "CODE_SIGN_STYLE=Manual", "build"]
    result = [[compiler, "--version" if recipe["mode"] == "swift" else "-version"], build]
    if recipe["mode"] == "swift":
        result.append([signer, "--force", "--sign", recipe["signing_identity"], "--identifier", target["bundle_id"], str(app)])
    # Xcode signs its products using the project's entitlements. Do not replace
    # that signature with an ad-hoc main-bundle signature after the build.
    return result + [[signer, "--verify", "--deep", "--strict", str(app)],
                     [signer, "--display", "--verbose=4", str(app)]]


def build_app(plan: Path, output: Path, recipe: dict, timeout: float = 1200) -> Path:
    from copyapp.verify import verify_case
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("initial Mac build support requires an Apple Silicon macOS host")
    if type(timeout) not in {int, float} or not 0 < timeout <= 1800:
        raise ValueError("build timeout must be bounded to thirty minutes")
    plan = plan.resolve(strict=True)
    if not verify_case(plan) or read(plan, "manifest.json").get("kind") != "mac_rebuild_plan":
        raise ValueError("a verified Mac rebuild plan is required")
    frozen = read(plan, "rebuild-plan.json")
    target = frozen["target"]
    project = Path(target["project"]).resolve(strict=True)
    destination = output.resolve()
    if any(destination == parent or parent in destination.parents for parent in (project, plan)):
        raise ValueError("build case must be outside its source project and plan")
    if plan == project or plan in project.parents:
        raise ValueError("independent source must be outside report/plan evidence")
    expected = recipe_for(**{key: value for key, value in recipe.items() if key != "mode"})
    if recipe != expected:
        raise ValueError("invalid Mac build recipe")
    before = inventory(project, exclude=IGNORED)
    case = Case(output, "mac_build")
    logs = []
    try:
        shutil.copytree(plan, case.root / "plan", symlinks=True)
        case.record("plan/manifest.json")
        snapshot_bundle(project, case.root / "source", before)
        if inventory(case.root / "source") != before or inventory(project, exclude=IGNORED) != before:
            raise ValueError("source changed during snapshot")
        case.add("source-index.json", {"entries": before, "ignored_top_level": list(IGNORED),
                                       "sha256": hashlib.sha256(canonical(before)).hexdigest()})
        case.add("recipe.json", recipe)
        if recipe["mode"] == "swift":
            if (case.root / "source" / recipe["info_plist"]).stat().st_size > 1 << 20:
                raise ValueError("oversized bundle Info.plist")
            info = plistlib.loads((case.root / "source" / recipe["info_plist"]).read_bytes())
            executable = info.get("CFBundleExecutable")
            if (info.get("CFBundleIdentifier") != target["bundle_id"] or info.get("CFBundlePackageType") != "APPL" or
                    not isinstance(executable, str) or Path(executable).name != executable or executable in {"", ".", ".."}):
                raise ValueError("source Info.plist does not match the independent target")
            product = case.root / "products" / PurePosixPath(target["app_path"]).name
            (product / "Contents/MacOS").mkdir(parents=True)
            shutil.copyfile(case.root / "source" / recipe["info_plist"], product / "Contents/Info.plist")
            if recipe["resources"]:
                resource_root = case.root / "source" / recipe["resources"]
                snapshot_bundle(resource_root, product / "Contents/Resources", inventory(resource_root))
            located = subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True, text=True, check=True, timeout=30)
            compiler = located.stdout.strip()
        else:
            executable = ""  # Xcode chooses the product executable from its project.
            product = case.root / "products" / PurePosixPath(target["app_path"]).name
            project_path = case.root / "source" / recipe["xcode_project"]
            if not project_path.is_dir():
                raise ValueError("Xcode project is missing from source snapshot")
            located = subprocess.run(["xcrun", "--find", "xcodebuild"], capture_output=True, text=True, check=True, timeout=30)
            compiler = located.stdout.strip()
        sdk_probe = subprocess.run(["xcrun", "--sdk", "macosx", "--show-sdk-path"], capture_output=True, text=True, check=True, timeout=30)
        # Swift derives the SDK name/version from this versioned spelling.
        # Keep xcrun's versioned spelling for Swift's SDK-name inference.
        # Direct swiftc also needs SDKROOT for its clang linker invocation;
        # without it this toolchain stamps minos as the linked SDK version.
        sdk = Path(sdk_probe.stdout.strip()).absolute()
        sdk_settings = sdk / "SDKSettings.json"
        if sdk_settings.stat().st_size > 1 << 20:
            raise ValueError("oversized SDK metadata")
        case.add("sdk-settings.json", sdk_settings.read_bytes(), binary=True)
        tools = {"compiler": tool(compiler), "codesign": tool(shutil.which("codesign") or "/usr/bin/codesign"),
                 "sdk": {"path": str(sdk), "settings_sha256": digest(case.root / "sdk-settings.json"),
                         "export_root": True}}
        case.add("tools.json", tools)
        for argv in commands(case.root, target, recipe, tools, executable):
            run_command(argv, case.root / "source", logs, timeout, sdk_root=str(sdk))
        facts = app_facts(product)
        if facts["bundle_id"] != target["bundle_id"]:
            raise ValueError("built product has another Bundle ID")
        generated = generated_directories(before, inventory(case.root / "source"), recipe)
        if inventory(project, exclude=IGNORED) != before:
            raise ValueError("host project changed during build; inspect before a new attempt")
        package = index_app(product, case.root / "package")
        case.record("package/manifest.json")
        case.add("build-log.json", logs)
        case.add("build.json", {"schema_version": 2, "platform": "macos", "scope": "build_only",
                                "workspace": str(case.root), "project": str(project), "executable": executable,
                                "host": {"system": platform.system(), "version": platform.mac_ver()[0], "architecture": platform.machine()},
                                "plan_manifest_sha256": digest(case.root / "plan/manifest.json"),
                                "source_sha256": hashlib.sha256(canonical(before)).hexdigest(),
                                "generated_source_directories": generated,
                                "package_manifest_sha256": digest(package / "manifest.json"), "app": facts,
                                "installed": False, "behavior_checked": False})
        case.finish("complete", scope="build_only")
        if not verify_case(case.root):
            raise ValueError("built case failed source validation")
        return case.root
    except BaseException as exc:
        if not (case.root / "build-log.json").exists():
            case.add("build-log.json", logs)
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="build_only")
        raise


def validate_build(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    required = {"build.json", "build-log.json", "plan/manifest.json", "source-index.json", "recipe.json", "tools.json", "sdk-settings.json", "package/manifest.json"}
    if (manifest.get("status") != "complete" or manifest.get("scope") != "build_only" or
            not required.issubset(names) or not verify_case(root / "plan") or not verify_case(root / "package") or
            read(root / "plan", "manifest.json").get("kind") != "mac_rebuild_plan" or
            read(root / "package", "manifest.json").get("kind") != "mac_app_index"):
        return False
    saved = read(root, "build.json")
    source = read(root, "source-index.json")
    recipe = read(root, "recipe.json")
    tools = read(root, "tools.json")
    target = read(root / "plan", "rebuild-plan.json")["target"]
    entries = source["entries"]
    generated = generated_directories(entries, inventory(root / "source"), recipe)
    if (recipe != recipe_for(**{key: value for key, value in recipe.items() if key != "mode"}) or
            source != {"entries": entries, "ignored_top_level": list(IGNORED), "sha256": hashlib.sha256(canonical(entries)).hexdigest()} or
            set(tools) != {"compiler", "codesign", "sdk"} or
            set(tools["sdk"]) not in ({"path", "settings_sha256"}, {"path", "settings_sha256", "export_root"}) or
            ("export_root" in tools["sdk"] and tools["sdk"]["export_root"] is not True) or
            not Path(tools["sdk"]["path"]).is_absolute() or
            tools["sdk"]["settings_sha256"] != digest(root / "sdk-settings.json")):
        return False
    for value in (tools["compiler"], tools["codesign"]):
        if (set(value) != {"path", "resolved_path", "sha256"} or not Path(value["path"]).is_absolute() or
                not Path(value["resolved_path"]).is_absolute() or
                not re.fullmatch("[a-f0-9]{64}", value["sha256"])):
            return False
    package = read(root / "package", "app-index.json")
    app = package["app"]
    expected_argv = commands(Path(saved["workspace"]), target, recipe, tools, saved["executable"])
    logs = read(root, "build-log.json")
    # Historical cases omit export_root and retain their original log shape.
    expected_environment = {"SDKROOT": tools["sdk"]["path"]} if tools["sdk"].get("export_root") else None
    if (not isinstance(logs, list) or len(logs) != len(expected_argv) or
            any(log.get("argv") != argv or type(log.get("returncode")) is not int or log["returncode"] != 0 or
                log.get("environment") != expected_environment or
                log.get("cwd") != str(Path(saved["workspace"]) / "source") or
                log.get("timed_out") is not False or log.get("output_truncated") is not False
                for log, argv in zip(logs, expected_argv))):
        return False
    if recipe["mode"] == "swift":
        info = plistlib.loads((root / "source" / recipe["info_plist"]).read_bytes())
        if (info.get("CFBundleIdentifier") != target["bundle_id"] or
                info.get("CFBundleExecutable") != saved["executable"] or
                info.get("CFBundlePackageType") != "APPL"):
            return False
    return (type(saved.get("schema_version")) is int and saved["schema_version"] == 2 and
            saved.get("platform") == "macos" and saved.get("scope") == "build_only" and
            saved.get("project") == target["project"] and Path(saved["workspace"]).is_absolute() and
            saved.get("host", {}).get("system") == "Darwin" and saved["host"].get("architecture") == "arm64" and
            saved.get("source_sha256") == source["sha256"] and saved.get("app") == app and
            saved.get("generated_source_directories") == generated and
            app["bundle_id"] == target["bundle_id"] and
            PurePosixPath(package["snapshot_path"]).name == PurePosixPath(target["app_path"]).name and
            saved.get("plan_manifest_sha256") == digest(root / "plan/manifest.json") and
            saved.get("package_manifest_sha256") == digest(root / "package/manifest.json") and
            saved.get("installed") is False and saved.get("behavior_checked") is False)
