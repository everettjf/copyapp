"""Explicit dispatch for new iOS cases without changing historical v1 rules."""

import json
from pathlib import Path
from zipfile import BadZipFile

from copyapp.verify import checked_path, compare, sha256_file


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_separate_trees(source: Path, output: Path) -> None:
    """Reject self-copy and aliases before creating any evidence directories."""
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("source and output must be separate directory trees; overlap is not allowed")


def seal_case(root: Path, kind: str, **fields) -> Path:
    records = []
    for path in sorted(root.rglob("*")):
        if path == root / "manifest.json":
            continue
        if path.is_symlink():
            raise ValueError("iOS cases cannot contain symbolic links")
        if path.is_file():
            records.append({"path": str(path.relative_to(root)), "sha256": sha256_file(path)})
    write_json(root / "manifest.json", {
        **fields, "schema_version": 2, "platform": "ios", "kind": kind,
        "evidence": records,
    })
    return root / "manifest.json"


def verify_ios_case(root: Path) -> bool:
    try:
        root = root.resolve(strict=True)
        manifest = read_json(root / "manifest.json")
        if manifest.get("schema_version") != 2 or manifest.get("platform") != "ios":
            return False
        records = manifest.get("evidence")
        if not isinstance(records, list) or not records:
            return False
        names = [item["path"] for item in records]
        actual = {str(path.relative_to(root)) for path in root.rglob("*")
                  if path.is_file() and path != root / "manifest.json"}
        if (len(names) != len(set(names)) or set(names) != actual or
                any(path.is_symlink() for path in root.rglob("*")) or
                not compare(root, records)):
            return False
        for name in names:
            checked_path(root, name)
        if manifest.get("kind") == "ios_capabilities":
            from copyapp.ios_capabilities import validate_capabilities
            return validate_capabilities(root, manifest)
        if manifest.get("kind") == "ios_analysis":
            from copyapp.ios_analysis import validate_ios_analysis
            return validate_ios_analysis(root, manifest)
        if manifest.get("kind") == "ios_behavior_report":
            from copyapp.ios_report import validate_behavior_report
            return validate_behavior_report(root, manifest)
        if manifest.get("kind") == "ios_behavior_delivery":
            from copyapp.ios_delivery import validate_behavior_delivery
            return validate_behavior_delivery(root, manifest)
        if manifest.get("kind") == "ios_copy_workflow":
            from copyapp.ios_workflow import validate_ios_workflow
            return validate_ios_workflow(root, manifest)
        if manifest.get("kind") == "ios_package":
            from copyapp.ios_packages import validate_package
            return validate_package(root, manifest)
        if manifest.get("kind") == "ios_offline_package":
            from copyapp.ios_offline import validate_offline
            return validate_offline(root, manifest)
        if manifest.get("kind") == "ios_fairplay_credential":
            from copyapp.ios_credentials import validate_credential_case
            return validate_credential_case(root, manifest)
        if manifest.get("kind") == "ios_package_cross_check":
            from copyapp.ios_cross_check import validate_cross_check
            return validate_cross_check(root, manifest)
        # Unknown new formats never fall back to a legacy filename validator.
        return False
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError, BadZipFile):
        return False
