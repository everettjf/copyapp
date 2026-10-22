#!/usr/bin/env python3
"""Build and install the release wheel outside the source checkout."""

import hashlib
import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path


SOURCE = Path(__file__).resolve().parent.parent
REQUIRED_DATA = {
    "copyapp/macos/collector/Collector.swift",
    "copyapp/fidelity.py",
    "copyapp/ictrl_runner_stop.py",
    "copyapp/ghidra_scripts/CopyAppAnalysisOptions.java",
    "copyapp/ghidra_scripts/CopyAppDecompile.java",
    "copyapp/ghidra_scripts/REA-LICENSE.txt",
}


def run(argv, *, cwd, env=None):
    return subprocess.run(argv, cwd=cwd, env=env, check=True, text=True,
                          capture_output=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="copyapp-wheel-check-") as directory:
        root = Path(directory)
        dist = root / "dist"
        dist.mkdir()
        run([sys.executable, "-m", "pip", "wheel", "--no-deps",
             "--no-build-isolation", "--wheel-dir", str(dist), str(SOURCE)], cwd=root)
        wheels = list(dist.glob("copyapp-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one Copy APP wheel; found {len(wheels)}")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
        missing = REQUIRED_DATA - names
        if missing:
            raise RuntimeError("wheel lacks required runtime files: " +
                               ", ".join(sorted(missing)))
        invalid = sorted(name for name in names
                         if not (name.startswith("copyapp/") or
                                 (name.startswith("copyapp-") and
                                  ".dist-info/" in name)) or
                         any(part in {"cases", "toolchains", "rebuild", ".ssh", "__pycache__"}
                             for part in Path(name).parts) or
                         name.endswith((".pyc", ".mobileprovision", ".pem")))
        if invalid:
            raise RuntimeError("wheel contains unexpected files: " + ", ".join(invalid[:10]))

        isolated = root / "venv"
        venv.EnvBuilder(with_pip=True).create(isolated)
        python = isolated / "bin" / "python"
        cli = isolated / "bin" / "copyapp"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("COPYAPP_SOURCE_ROOT", None)
        run([str(python), "-m", "pip", "install", str(wheel)], cwd=root, env=env)
        help_text = run([str(cli), "--help"], cwd=root, env=env).stdout
        if not all(command in help_text for command in ("onboard", "analyze", "copy", "mac",
                                                       "fidelity-plan", "fidelity-template", "fidelity-check")):
            raise RuntimeError("installed wheel CLI lacks expected commands")
        fidelity_help = run([str(cli), "fidelity-plan", "--help"], cwd=root, env=env).stdout
        if "--fidelity" not in fidelity_help or "--max-iterations" not in fidelity_help:
            raise RuntimeError("installed wheel lacks bounded fidelity options")
        mac_help = run([str(cli), "mac", "--help"], cwd=root, env=env).stdout
        if not all(command in mac_help for command in ("doctor", "inspect", "build-collector", "acquire",
                                                       "playbook", "report", "rebuild-plan", "build-app", "install",
                                                       "check-plan", "rebuild-check", "visual-review", "delivery",
                                                       "share-probe", "share-probe-check", "import-app", "discover-check", "data-file", "data-schema",
                                                       "snapshot-inspect", "snapshot-take", "snapshot-restore", "probe-collector")):
            raise RuntimeError("installed wheel lacks Mac entry points")
        probe = ("import copyapp, pathlib, sys; "
                 "root=pathlib.Path(copyapp.__file__).resolve().parent; "
                 "assert root.is_relative_to(pathlib.Path(sys.argv[1]).resolve()); "
                 "assert (root/'ghidra_scripts'/'CopyAppDecompile.java').is_file()")
        run([str(python), "-c", probe, str(isolated)], cwd=root, env=env)
        print(f"wheel OK: {wheel.name} SHA-256 {hashlib.sha256(wheel.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
