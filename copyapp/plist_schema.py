"""Describe a captured property list's structure without exporting values."""

import json
import plistlib
from datetime import datetime, timezone
from pathlib import Path

from copyapp.sqlite_schema import _source_file
from copyapp.verify import sha256_file


MAX_PLIST_BYTES = 4 * 1024 * 1024
MAX_NODES = 2048
MAX_FIELDS = 1024
MAX_DEPTH = 12


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _type(value) -> str:
    if isinstance(value, dict):
        return "dictionary"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "real"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bytes):
        return "data"
    if isinstance(value, datetime):
        return "date"
    if isinstance(value, plistlib.UID):
        return "uid"
    raise ValueError("property list contains an unsupported value type")


def _structure(value) -> dict:
    observed = set()
    fields = []
    scanned = 0
    truncated = False

    def walk(current, path: str, depth: int) -> None:
        nonlocal scanned, truncated
        if scanned >= MAX_NODES:
            truncated = True
            return
        scanned += 1
        kind = _type(current)
        key = (path, kind)
        if key not in observed:
            if len(fields) >= MAX_FIELDS:
                truncated = True
                return
            observed.add(key)
            fields.append({"path": path, "type": kind})
        if depth >= MAX_DEPTH:
            if isinstance(current, (dict, list)) and current:
                truncated = True
            return
        if isinstance(current, dict):
            for name in sorted(current):
                if not isinstance(name, str) or len(name) > 256 or any(
                        ord(char) < 32 or ord(char) == 127 for char in name):
                    truncated = True
                    continue
                escaped = name.replace("~", "~0").replace("/", "~1")
                child = path + "/" + escaped
                if len(child) > 1024:
                    truncated = True
                    continue
                walk(current[name], child, depth + 1)
        elif isinstance(current, list):
            for child in current:
                walk(child, path + "/*", depth + 1)

    walk(value, "", 0)
    fields.sort(key=lambda item: (item["path"], item["type"]))
    return {"root_type": _type(value), "fields": fields,
            "nodes_scanned": scanned, "truncated": truncated}


def inspect_plist_source(case: Path, relative: str) -> dict:
    source, digest, index_digest = _source_file(case, relative)
    if not 0 < source.stat().st_size <= MAX_PLIST_BYTES:
        raise ValueError("property list exceeds bounded size")
    raw = source.read_bytes()
    try:
        value = plistlib.loads(raw)
    except (ValueError, TypeError, OSError) as exc:
        raise ValueError("selected file is not a valid property list") from exc
    structure = _structure(value)
    if sha256_file(source) != digest:
        raise ValueError("property list changed during structure inspection")
    return {"source_case": str(case.resolve()),
            "source_index_sha256": index_digest,
            "source_relative_path": relative, "source_sha256": digest,
            "structure": structure,
            "scope": "Property-list key paths and value types only. Values, array lengths and data bytes are omitted; repeated array element shapes are merged."}


def create_plist_schema(case: Path, relative: str, output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"property-list output is not empty: {output}")
    if output.resolve() == case.resolve():
        raise ValueError("property-list output must differ from source case")
    result = inspect_plist_source(case, relative)
    output.mkdir(parents=True, exist_ok=True)
    result.update({"schema_version": 1, "kind": "plist_schema",
                   "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _write(output / "profile.json", result)
    structure = result["structure"]
    lines = ["# Property List 数据结构", "",
             f"- 来源：`{result['source_case']}` / `{relative}`。",
             f"- 文件 SHA-256：`{result['source_sha256']}`。",
             f"- 键路径与类型：{len(structure['fields'])} 项；"
             f"扫描对象：{structure['nodes_scanned']}；"
             f"截断：{'是' if structure['truncated'] else '否'}。", "",
             "| 键路径 | 类型 |", "| --- | --- |"]
    for item in structure["fields"]:
        label = json.dumps(item["path"] or "/", ensure_ascii=False).replace("|", "\\|")
        lines.append(f"| {label} | {item['type']} |")
    lines.extend(["", "只记录键路径与类型；值、数组长度和二进制正文未导出。"
                  "结构不能单独证明 App 的读写时机或业务语义。", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {"schema_version": 1, "kind": "plist_schema",
        "status": "complete", "source_index_sha256": result["source_index_sha256"],
        "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                     for name in ("profile.json", "report.md")]})
    return output / "report.md"


def validate_plist_schema_case(output: Path) -> bool:
    saved = _read(output / "profile.json")
    source = Path(saved["source_case"]).resolve(strict=True)
    if source == output.resolve() or source in output.resolve().parents:
        return False
    actual = inspect_plist_source(source, saved["source_relative_path"])
    manifest = _read(output / "manifest.json")
    return (saved.get("schema_version") == 1 and saved.get("kind") == "plist_schema" and
            manifest.get("schema_version") == 1 and manifest.get("kind") == "plist_schema" and
            manifest.get("status") == "complete" and
            manifest.get("source_index_sha256") == actual["source_index_sha256"] and
            set(saved) == set(actual) | {"schema_version", "kind", "created_at"} and
            all(saved.get(key) == value for key, value in actual.items()))
