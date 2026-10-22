#!/usr/bin/env python3
"""Build the independent offline demo; this is not an accepted Copy APP delivery."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    output = parser.parse_args().out.resolve()
    source = Path(__file__).resolve().parent
    if output == source or source in output.parents:
        raise ValueError("build outside the source directory")
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "source"
    shutil.copytree(source, snapshot, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    inputs = {str(p.relative_to(snapshot)): sha(p) for p in sorted(snapshot.rglob("*")) if p.is_file()}
    app = output / "CopyAppStocks.app"
    binary = app / "Contents/MacOS/CopyAppStocks"
    binary.parent.mkdir(parents=True)
    shutil.copyfile(snapshot / "Info.plist", app / "Contents/Info.plist")
    logs = []
    record = {"scope": "independent_offline_demo_build_only", "inputs": inputs, "launched": False}
    try:
        sdk_result = subprocess.run(["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                    check=True, timeout=30)
        sdk = str(Path(sdk_result.stdout.strip()).resolve(strict=True))
        record["sdkroot"] = sdk
        build_env = dict(os.environ, SDKROOT=sdk)
        commands = [
            ["xcrun", "swiftc", "-parse-as-library", "-swift-version", "5", "-target", "arm64-apple-macos14.0",
             "-sdk", sdk, str(snapshot / "Sources/Main.swift"), "-o", str(binary)],
            ["/usr/bin/codesign", "--sign", "-", "--identifier", "dev.copyapp.examples.Stocks", str(app)],
            ["/usr/bin/codesign", "--verify", "--strict", str(app)],
        ]
        for argv in commands:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                    env=build_env, timeout=180)
            logs.append({"argv": argv, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                raise RuntimeError("demo build failed; inspect build-log.json")
        if any(sha(source / name) != value or sha(snapshot / name) != value for name, value in inputs.items()):
            raise ValueError("demo source changed during build")
        record.update(status="built", executable_sha256=sha(binary))
    except BaseException as exc:
        record.update(status="failed", error=type(exc).__name__, message=str(exc))
        raise
    finally:
        (output / "build-log.json").write_text(json.dumps(logs, indent=2) + "\n")
        (output / "build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(app)


if __name__ == "__main__":
    main()
