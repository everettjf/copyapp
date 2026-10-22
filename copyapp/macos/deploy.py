"""Prepare only the collector's own files for a read-only guest share."""

import json
import shutil
from pathlib import Path

from copyapp.macos.case import Case, digest


def collector_launcher(binary_hash: str, request_accessibility: bool) -> str:
    # Only a verifier-produced digest and an explicit boolean become code.
    if type(request_accessibility) is not bool or len(binary_hash) != 64 or any(c not in "0123456789abcdef" for c in binary_hash):
        raise ValueError("invalid collector launcher identity or permission request")
    return '''#!/bin/zsh
set -eu
[[ -d "/Volumes/My Shared Files/inbox" ]] || { print -u2 "Run this launcher inside the ChatComputer guest"; exit 1; }
[[ "$(/usr/sbin/sysctl -n kern.hv_vmm_present 2>/dev/null || print 0)" == "1" ]] || { print -u2 "This launcher is for a virtual Mac"; exit 1; }
copyapp_source="${0:A:h}/source-build/CopyAppMacCollector.app"
copyapp_install="$HOME/Applications/CopyAppTools/HASH"
if [[ ! -d "$copyapp_install/CopyAppMacCollector.app" ]]; then
    /bin/mkdir -p "$copyapp_install"
    /usr/bin/ditto "$copyapp_source" "$copyapp_install/CopyAppMacCollector.app"
fi
/usr/bin/codesign --verify --strict "$copyapp_install/CopyAppMacCollector.app"
copyapp_actual=$(/usr/bin/shasum -a 256 "$copyapp_install/CopyAppMacCollector.app/Contents/MacOS/CopyAppMacCollector" | /usr/bin/awk '{print $1}')
[[ "$copyapp_actual" == "HASH" ]] || { print -u2 "Collector hash mismatch"; exit 1; }
/usr/bin/open "$copyapp_install/CopyAppMacCollector.app" --args --shared-root "/Volumes/My Shared Files"ACCESSIBILITY
'''.replace("HASH", binary_hash).replace("ACCESSIBILITY", " --request-accessibility" if request_accessibility else "")


def prepare_collector(build: Path, output: Path, request_accessibility: bool = False) -> Path:
    from copyapp.verify import verify_case
    build = build.resolve(strict=True)
    if output.resolve() == build or build in output.resolve().parents:
        raise ValueError("deployment must be outside the build case")
    if not verify_case(build):
        raise ValueError("collector build case is not verified")
    manifest = json.loads((build / "manifest.json").read_text())
    if manifest.get("kind") != "mac_collector_build" or manifest.get("status") != "complete":
        raise ValueError("a complete collector build is required")
    metadata = json.loads((build / "collector-build.json").read_text())
    case = Case(output, "mac_collector_deployment")
    source = case.root / "payload/source-build"
    shutil.copytree(build, source, symlinks=True)
    case.record("payload/source-build/manifest.json")
    binary_hash = metadata["executable_sha256"]
    script = collector_launcher(binary_hash, request_accessibility)
    case.add("payload/Start Collector.command", script.encode(), binary=True)
    (case.root / "payload/Start Collector.command").chmod(0o755)
    case.add("deployment.json", {"schema_version": 2, "platform": "macos",
                                "build_manifest_sha256": digest(source / "manifest.json"),
                                "collector_sha256": binary_hash,
                                "share_path": "payload", "launcher": "payload/Start Collector.command",
                                "guest_shared_root": "/Volumes/My Shared Files",
                                "request_accessibility": request_accessibility,
                                "status": "prepared_not_installed"})
    case.finish("complete", scope="collector_deployment_preparation")
    return case.root


def validate_deployment(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    if (manifest.get("status") != "complete" or
            manifest.get("scope") != "collector_deployment_preparation" or
            not {"deployment.json", "payload/Start Collector.command",
                 "payload/source-build/manifest.json"}.issubset(names)):
        return False
    record = json.loads((root / "deployment.json").read_text())
    build = root / "payload/source-build"
    source_manifest = json.loads((build / "manifest.json").read_text())
    metadata = json.loads((build / "collector-build.json").read_text())
    return (record.get("schema_version") == 2 and record.get("platform") == "macos" and
            record.get("status") == "prepared_not_installed" and
            record.get("share_path") == "payload" and
            record.get("launcher") == "payload/Start Collector.command" and
            record.get("guest_shared_root") == "/Volumes/My Shared Files" and
            record.get("build_manifest_sha256") == digest(build / "manifest.json") and
            record.get("collector_sha256") == metadata["executable_sha256"] and
            type(record.get("request_accessibility")) is bool and
            (root / record["launcher"]).read_text() == collector_launcher(metadata["executable_sha256"], record["request_accessibility"]) and
            (root / record["launcher"]).stat().st_mode & 0o777 == 0o755 and
            source_manifest.get("kind") == "mac_collector_build" and verify_case(build))
