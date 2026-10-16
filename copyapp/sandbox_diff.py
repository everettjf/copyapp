"""Compare two metadata-only snapshots of the same app data container."""

import json
import shutil
import io
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path, PurePosixPath

from copyapp.verify import sha256_file, verify_case


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError(f"invalid sandbox index: {path}")
    entries = {}
    for entry in data["entries"]:
        name = entry.get("relative")
        if (not isinstance(name, str) or not name or
                PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or
                name in entries):
            raise ValueError(f"unsafe or repeated sandbox path: {name!r}")
        if (entry.get("kind") not in tuple("bcdflps") or
                not isinstance(entry.get("size"), int) or entry["size"] < 0 or
                not isinstance(entry.get("modified_epoch"), (int, float))):
            raise ValueError(f"invalid sandbox metadata: {name}")
        entries[name] = entry
    return data


def compute_sandbox_changes(before: dict, after: dict) -> list:
    """Return path and metadata differences; no file contents are inspected."""
    first = {item["relative"]: item for item in before["entries"]}
    second = {item["relative"]: item for item in after["entries"]}
    changes = []
    for name in sorted(first.keys() | second.keys()):
        old, new = first.get(name), second.get(name)
        if old is None:
            change = "added"
            fields = []
        elif new is None:
            change = "removed"
            fields = []
        else:
            fields = [key for key in ("kind", "size", "modified_epoch")
                      if old[key] != new[key]]
            if not fields:
                continue
            change = "metadata_changed"
        changes.append({"relative": name, "change": change,
                        "changed_fields": fields, "before": old, "after": new})
    return changes


def compare_sandbox(before_path: Path, after_path: Path, output: Path,
                    action_path: Path = None) -> Path:
    """Retain source snapshots and return a hash-verifiable difference report."""
    if before_path.resolve() == after_path.resolve():
        raise ValueError("before and after must be different snapshots")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    before, after = _load(before_path), _load(after_path)
    for key in ("device_id_sha256_prefix", "bundle_id", "depth_limit"):
        if not before.get(key) or before.get(key) != after.get(key):
            raise ValueError(f"sandbox snapshot identity differs: {key}")
    for key in ("installed_version", "installed_build"):
        if before.get(key) != after.get(key):
            raise ValueError(f"sandbox snapshot identity differs: {key}")
    container_before = before.get("container_path_sha256_prefix")
    container_after = after.get("container_path_sha256_prefix")
    if container_before and container_after and container_before != container_after:
        raise ValueError("sandbox container changed between snapshots")
    action = None
    if action_path is not None:
        with redirect_stdout(io.StringIO()):
            if not verify_case(action_path):
                raise ValueError("action playbook evidence hash mismatch")
        action = json.loads((action_path / "manifest.json").read_text(encoding="utf-8"))
        if (action.get("status") != "complete" or action.get("bundle_id") != before["bundle_id"] or
                action.get("device_id_sha256_prefix") != before["device_id_sha256_prefix"]):
            raise ValueError("action playbook identity or status differs from sandbox snapshots")
        try:
            before_at = datetime.fromisoformat(before["captured_at"])
            after_at = datetime.fromisoformat(after["captured_at"])
            started_at = datetime.fromisoformat(action["started_at"])
            finished_at = datetime.fromisoformat(action["finished_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("action comparison requires four valid timestamps") from exc
        if not before_at <= started_at <= finished_at <= after_at:
            raise ValueError("action playbook is outside the before/after capture interval")
    changes = compute_sandbox_changes(before, after)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(before_path, output / "before.json")
    shutil.copyfile(after_path, output / "after.json")
    if action_path is not None:
        shutil.copytree(action_path, output / "action")
    counts = {kind: sum(item["change"] == kind for item in changes)
              for kind in ("added", "removed", "metadata_changed")}
    result = {"schema_version": 1, "bundle_id": before["bundle_id"],
              "device_id_sha256_prefix": before["device_id_sha256_prefix"],
              "depth_limit": before["depth_limit"],
              "before_captured_at": before.get("captured_at"),
              "after_captured_at": after.get("captured_at"),
              "action_scenario_id": (action.get("scenario_id") or "playbook") if action else None,
              "counts": counts, "changes": changes,
              "scope": "path, kind, size and modification time only; no file bytes were read"}
    (output / "changes.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    rows = [f"| `{item['relative']}` | {item['change']} | "
            f"{', '.join(item['changed_fields']) or '—'} |" for item in changes]
    report = ["# App 沙盒元数据前后差异", "",
              f"- Bundle ID：`{before['bundle_id']}`",
              f"- 新增 {counts['added']}，删除 {counts['removed']}，元数据变化 {counts['metadata_changed']}。",
              f"- 深度上限：{before['depth_limit']}；两份原始索引见 [before.json](before.json) 与 [after.json](after.json)。",
              *([f"- 操作案例：[{action.get('scenario_id') or 'playbook'}](action/manifest.json)，已验证同一设备、App、完整状态及采集时间顺序。"]
                if action else []),
              "", "| 相对路径 | 变化 | 字段 |", "| --- | --- | --- |",
              *(rows or ["| 无可见变化 | — | — |"]), "",
              "此对照只读取路径、类型、大小和修改时间。文件元数据变化不证明内容变化，"
              "没有变化也不证明文件内容不变；超过深度上限的路径不可见。目录修改时间可能仅由子项变化导致。", ""]
    (output / "report.md").write_text("\n".join(report), encoding="utf-8")
    files = sorted(path for path in output.rglob("*") if path.is_file())
    (output / "manifest.json").write_text(json.dumps({"schema_version": 1,
        "evidence": [{"path": str(path.relative_to(output)), "sha256": sha256_file(path)}
                     for path in files]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output / "report.md"
