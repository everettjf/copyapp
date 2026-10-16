"""Inspect a verified captured SQLite file without exporting its rows."""

import io
import json
import shutil
import sqlite3
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.verify import checked_path, sha256_file, verify_case


MAX_DATABASE_BYTES = 64 * 1024 * 1024
MAX_SCHEMA_OBJECTS = 512
MAX_COLUMNS = 256


def _read(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _source_file(case: Path, relative: str) -> tuple[Path, str, str]:
    case = case.resolve(strict=True)
    if (case / "manifest.json").is_file() and _read(case / "manifest.json").get("kind") == "sqlite_schema":
        raise ValueError("SQLite schema cases cannot be used as their own source")
    with redirect_stdout(io.StringIO()):
        if not verify_case(case):
            raise ValueError("source case failed evidence verification")
    index_name = "report-index.json" if (case / "report-index.json").is_file() else "manifest.json"
    index = _read(case / index_name)
    records = (index.get("artifacts", {}).values() if index_name == "report-index.json"
               else index.get("evidence", []))
    matches = [item for item in records if isinstance(item, dict) and
               item.get("path") == relative]
    if len(matches) != 1:
        raise ValueError("selected SQLite file is not a unique recorded source artifact")
    path = checked_path(case, relative)
    if not path.is_file() or sha256_file(path) != matches[0].get("sha256"):
        raise ValueError("selected SQLite file hash differs from source case")
    return path, matches[0]["sha256"], sha256_file(case / index_name)


def _schema_from_file(path: Path, wal_path: Optional[Path]) -> dict:
    sizes = [path.stat().st_size] + ([wal_path.stat().st_size] if wal_path else [])
    if not 0 < sizes[0] <= MAX_DATABASE_BYTES or sum(sizes) > MAX_DATABASE_BYTES:
        raise ValueError("SQLite database and WAL exceed the bounded read limit")
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\0":
            raise ValueError("selected file has no SQLite 3 header")
    with tempfile.TemporaryDirectory(prefix="copyapp-sqlite-") as temporary:
        copied = Path(temporary) / "source.sqlite"
        shutil.copyfile(path, copied)
        if wal_path is not None:
            shutil.copyfile(wal_path, Path(str(copied) + "-wal"))
        # The source is a detached, verified snapshot. Immutable mode avoids
        # SQLite trying to create WAL sidecars while inspecting that copy.
        with sqlite3.connect(copied.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                "SELECT type, name, tbl_name FROM sqlite_master "
                "WHERE type IN ('table', 'view', 'index', 'trigger') "
                "ORDER BY type, name LIMIT ?", (MAX_SCHEMA_OBJECTS + 1,)).fetchall()
            if len(rows) > MAX_SCHEMA_OBJECTS:
                raise ValueError("SQLite schema has too many objects")
            objects = [{"type": kind, "name": name, "table": table}
                       for kind, name, table in rows]
            tables = []
            for item in objects:
                if item["type"] != "table":
                    continue
                quoted = '"' + item["name"].replace('"', '""') + '"'
                columns = db.execute(f"PRAGMA table_xinfo({quoted})").fetchall()
                if len(columns) > MAX_COLUMNS:
                    raise ValueError("SQLite table has too many columns")
                foreign_keys = db.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
                tables.append({
                    "name": item["name"],
                    "columns": [{"name": row[1], "type": row[2],
                                 "not_null": bool(row[3]), "primary_key_position": row[5],
                                 "hidden": row[6]} for row in columns],
                    "foreign_keys": [{"from": row[3], "to": row[4],
                                      "referenced_table": row[2]}
                                     for row in foreign_keys],
                })
            return {"user_version": db.execute("PRAGMA user_version").fetchone()[0],
                    "application_id": db.execute("PRAGMA application_id").fetchone()[0],
                    "objects": objects, "tables": tables}


def inspect_source(case: Path, relative: str) -> dict:
    """Recompute a metadata-only schema from one source-verified case artifact."""
    case = case.resolve(strict=True)
    source, digest, index_digest = _source_file(case, relative)
    wal_relative = relative + "-wal"
    wal_path = None
    wal_digest = None
    if (case / wal_relative).exists():
        wal_path, wal_digest, _ = _source_file(case, wal_relative)
    schema = _schema_from_file(source, wal_path)
    if sha256_file(source) != digest or (wal_path and sha256_file(wal_path) != wal_digest):
        raise ValueError("SQLite source changed while inspecting schema")
    return {"source_case": str(case), "source_index_sha256": index_digest,
            "source_relative_path": relative, "source_sha256": digest,
            "wal_sha256": wal_digest, "schema": schema,
            "scope": "SQLite schema metadata only. No table rows, SQL bodies, defaults or database bytes are exported. A copied WAL may be non-atomic if the source was changing."}


def create_sqlite_schema(case: Path, relative: str, output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    if output.resolve() == case.resolve():
        raise ValueError("schema output must differ from source case")
    result = inspect_source(case, relative)
    output.mkdir(parents=True, exist_ok=True)
    result.update({"schema_version": 1, "kind": "sqlite_schema",
                   "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    _write(output / "schema.json", result)
    schema = result["schema"]
    lines = ["# SQLite 数据结构", "",
             f"- 来源案例：`{result['source_case']}`；文件：`{relative}`。",
             f"- 文件 SHA-256：`{result['source_sha256']}`。",
             f"- 表 {len(schema['tables'])} 个；索引 {sum(o['type'] == 'index' for o in schema['objects'])} 个；"
             f"视图 {sum(o['type'] == 'view' for o in schema['objects'])} 个；"
             f"触发器 {sum(o['type'] == 'trigger' for o in schema['objects'])} 个。", "",
             "| 表名 | 列（名称 : 类型） | 外键 |", "| --- | --- | --- |"]
    for table in schema["tables"]:
        cell = lambda value: json.dumps(value, ensure_ascii=False).replace("|", "\\|")
        columns = ", ".join(f"{cell(col['name'])}: {cell(col['type'])}"
                            for col in table["columns"])
        foreign = ", ".join(f"{cell(key['from'])} → {cell(key['referenced_table'])}"
                            for key in table["foreign_keys"])
        lines.append(f"| {cell(table['name'])} | {columns or '—'} | {foreign or '—'} |")
    lines.extend(["", "只分析已保存文件的结构，不读取表记录；本次不说明 App 如何使用这些表。"
                  " 若数据库处于 WAL 写入状态，非原子复制可能不代表同一瞬间的完整状态。", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {"schema_version": 1, "kind": "sqlite_schema",
        "status": "complete", "source_index_sha256": result["source_index_sha256"],
        "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                     for name in ("schema.json", "report.md")]})
    return output / "report.md"


def validate_sqlite_schema_case(output: Path) -> bool:
    saved = _read(output / "schema.json")
    source = Path(saved["source_case"]).resolve(strict=True)
    if source == output.resolve():
        return False
    actual = inspect_source(source, saved["source_relative_path"])
    manifest = _read(output / "manifest.json")
    return (saved.get("schema_version") == 1 and saved.get("kind") == "sqlite_schema" and
            manifest.get("status") == "complete" and
            manifest.get("source_index_sha256") == actual["source_index_sha256"] and
            set(saved) == set(actual) | {"schema_version", "kind", "created_at"} and
            all(saved.get(key) == value for key, value in actual.items()))
