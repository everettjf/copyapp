#!/usr/bin/env python3
"""Build an owned original sample. This is not a Copy APP rebuilt delivery."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    output = args.out.resolve()
    if output == source or source in output.parents:
        raise ValueError("build outside the source fixture")
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "source"
    shutil.copytree(source, snapshot, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    inputs = {str(path.relative_to(snapshot)): sha(path) for path in sorted(snapshot.rglob("*")) if path.is_file()}
    app = output / "BehaviorFixture.app"
    binary = app / "Contents/MacOS/BehaviorFixture"
    binary.parent.mkdir(parents=True)
    shutil.copyfile(snapshot / "Info.plist", app / "Contents/Info.plist")
    logs = []
    record = {"scope": "owned_original_fixture_build_only", "inputs": inputs, "launched": False}
    try:
        for argv in (["xcrun", "swiftc", "-swift-version", "5", "-target", "arm64-apple-macos14.0",
                      str(snapshot / "Sources/Main.swift"), "-o", str(binary)],
                     ["/usr/bin/codesign", "--sign", "-", "--identifier", "dev.copyapp.fixture.Behavior", str(app)],
                     ["/usr/bin/codesign", "--verify", "--strict", str(app)]):
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
            logs.append({"argv": argv, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                raise RuntimeError("fixture build failed; inspect build-log.json")
        if any(sha(source / name) != value or sha(snapshot / name) != value for name, value in inputs.items()):
            raise ValueError("fixture source changed during build")
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
