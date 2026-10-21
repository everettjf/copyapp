"""Build the guest helper as a separate app; do not grant host permissions."""

import json
import plistlib
import subprocess
from pathlib import Path

from copyapp.macos.case import Case, digest
from copyapp.macos.package import app_facts, inventory


APP = "CopyAppMacCollector.app"


def build_collector(output: Path, signing_identity: str = "-") -> Path:
    case = Case(output, "mac_collector_build")
    output = case.root
    source = Path(__file__).parent / "collector/Collector.swift"
    case.add("Collector.swift", source.read_bytes(), binary=True)
    saved = output / "Collector.swift"
    app = output / APP
    executable = app / "Contents/MacOS/CopyAppMacCollector"
    executable.parent.mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "dev.copyapp.MacCollector",
        "CFBundleName": "Copy APP Mac Collector", "CFBundleExecutable": executable.name,
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "0.1.2",
        "CFBundleVersion": "1", "LSUIElement": True, "LSMinimumSystemVersion": "14.0"}))
    commands = [["xcrun", "swiftc", "-swift-version", "5", "-target", "arm64-apple-macos14.0",
                 str(saved), "-o", str(executable)],
                ["codesign", "--force", "--sign", signing_identity,
                 "--identifier", "dev.copyapp.MacCollector", str(app)],
                ["codesign", "--verify", "--strict", str(app)],
                [str(executable), "--self-test"]]
    logs = []
    try:
        for argv in commands:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
            logs.append({"argv": argv, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                raise RuntimeError("Collector build failed; inspect " + str(output / "build-log.json"))
        case.add("build-log.json", logs)
        case.add("collector-build.json", {
            "schema_version": 2, "platform": "macos", "protocol_version": 2,
            "source_sha256": digest(saved), "executable_sha256": digest(executable),
            "bundle_id": "dev.copyapp.MacCollector", "signing_identity": signing_identity,
            "app_path": APP, "app": app_facts(app), "entries": inventory(app),
            "self_test": json.loads(logs[-1]["stdout"])})
        case.finish("complete", scope="collector_build_only")
        return app
    except BaseException as exc:
        if not (output / "build-log.json").exists():
            case.add("build-log.json", logs)
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="collector_build_only")
        raise


def validate_build(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "collector_build_only" or
            not {"Collector.swift", "build-log.json", "collector-build.json"}.issubset(names)):
        return False
    record = json.loads((root / "collector-build.json").read_text())
    logs = json.loads((root / "build-log.json").read_text())
    app = root / APP
    if app.is_symlink():
        return False
    facts = app_facts(app)
    self_test = record.get("self_test", {})
    methods = self_test.get("methods")
    from copyapp.macos.bridge import METHODS
    if (self_test.get("protocol_version") != 2 or not isinstance(methods, list) or
            any(not isinstance(method, str) for method in methods) or len(methods) != len(set(methods)) or
            not {"health", "app_identity", "observe"}.issubset(methods) or
            not set(methods).issubset(METHODS)):
        return False
    return (record.get("platform") == "macos" and record.get("schema_version") == 2 and
            record.get("protocol_version") == 2 and record.get("app_path") == APP and
            record.get("bundle_id") == "dev.copyapp.MacCollector" and
            record.get("source_sha256") == digest(root / "Collector.swift") and
            record.get("executable_sha256") == facts["binary_sha256"] and
            record.get("app") == facts and record.get("entries") == inventory(app) and
            isinstance(logs, list) and len(logs) == 4 and
            all(type(log.get("returncode")) is int and log["returncode"] == 0 for log in logs) and
            json.loads(logs[-1]["stdout"]) == record["self_test"])
