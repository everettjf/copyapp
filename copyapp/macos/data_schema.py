"""Recomputed structure from one verified Mac data file, without scalar values/rows."""

import json
import plistlib
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from xml.parsers.expat import ExpatError

from copyapp.macos.case import Case, digest
from copyapp.macos.report import read
from copyapp.plist_schema import MAX_PLIST_BYTES, _structure


def sqlite_structure(path: Path) -> dict:
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\0":
            raise ValueError("selected file has no SQLite 3 header")
    with tempfile.TemporaryDirectory(prefix="copyapp-mac-sqlite-") as temporary:
        copied = Path(temporary) / "source.sqlite"
        shutil.copyfile(path, copied)
        db = sqlite3.connect(copied.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1)
        try:
            # Some macOS Python builds omit the extension-loading Python API.
            # Independently deny SQL function execution and database attachment.
            disable_extensions = getattr(db, "enable_load_extension", None)
            if disable_extensions is not None: disable_extensions(False)
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            trusted = db.execute("PRAGMA trusted_schema").fetchone()
            if trusted != (0,):
                raise ValueError("SQLite runtime does not support disabling trusted schema")
            db.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in {
                sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH} else sqlite3.SQLITE_OK)
            deadline, calls = time.monotonic() + 10, [0]

            def interrupt():
                calls[0] += 1
                return int(calls[0] > 2000 or time.monotonic() > deadline)

            db.set_progress_handler(interrupt, 1000)

            def rows(statement, limit):
                result = db.execute(statement).fetchmany(limit + 1)
                if len(result) > limit:
                    raise ValueError("SQLite structure exceeds its object/column/key bound")
                if any(isinstance(value, str) and len(value) > 4096 for row in result for value in row):
                    raise ValueError("SQLite structure contains an oversized name or type")
                return result

            objects = [{"type": kind, "name": name, "table": table} for kind, name, table in rows(
                "SELECT type, name, tbl_name FROM sqlite_master WHERE type IN ('table','view','index','trigger') ORDER BY type,name", 512)]
            tables = []
            for obj in objects:
                if obj["type"] != "table": continue
                quoted = '"' + obj["name"].replace('"', '""') + '"'
                columns = rows("PRAGMA table_xinfo(" + quoted + ")", 256)
                foreign = rows("PRAGMA foreign_key_list(" + quoted + ")", 512)
                tables.append({"name": obj["name"], "columns": [
                    {"name": row[1], "type": row[2], "not_null": bool(row[3]),
                     "primary_key_position": row[5], "hidden": row[6]} for row in columns],
                    "foreign_keys": [{"from": row[3], "to": row[4], "referenced_table": row[2]} for row in foreign]})
            return {"user_version": db.execute("PRAGMA user_version").fetchone()[0],
                    "application_id": db.execute("PRAGMA application_id").fetchone()[0],
                    "objects": objects, "tables": tables}
        finally:
            db.close()


def structure(path: Path, kind: str) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 64 << 20:
        raise ValueError("structure needs a bounded nonempty regular file")
    try:
        if kind == "plist":
            if path.stat().st_size > MAX_PLIST_BYTES:
                raise ValueError("property list exceeds the 4 MiB bound")
            return _structure(plistlib.loads(path.read_bytes()))
        if kind == "sqlite":
            return sqlite_structure(path)
        raise ValueError("choose plist or sqlite structure explicitly")
    except (sqlite3.Error, plistlib.InvalidFileException, ExpatError, RecursionError, OverflowError) as exc:
        raise ValueError("selected file could not be parsed within the structure limits") from exc


def schema_record(source: Path, kind: str) -> dict:
    from copyapp.verify import verify_case
    if not verify_case(source) or read(source, "manifest.json").get("kind") != "mac_data_file":
        raise ValueError("a verified single-file Mac data acquisition is required")
    data = read(source, "data-file.json")
    if kind not in {"plist", "sqlite"}:
        raise ValueError("choose plist or sqlite structure explicitly")
    return {"schema_version": 2, "platform": "macos", "scope": "data_structure_only", "format": kind,
            "source_manifest_sha256": digest(source / "manifest.json"), "source_data_sha256": data["sha256"],
            "bundle_id": data["bundle_id"], "package_sha256": data["package_sha256"],
            "environment_manifest_sha256": data["environment_manifest_sha256"],
            "guest_app_path": read(source / "source", "acquisition.json")["guest_app_path"],
            "guest_source_path": data["guest_source_path"], "association": data["association"],
            "atomic_database_snapshot": False, "complete_app_data": False,
            "scalar_values_exported": False, "rows_exported": False, "sql_bodies_exported": False,
            "wal_included": False, "function_analysis": "not_performed"}


def schema_markdown(record: dict, value: dict) -> str:
    return ("# Mac data structure\n\nFormat: " + record["format"] + ".\n\n"
            "Source association: `" + record["association"] + "`. This does not prove App ownership.\n\n"
            "Only key paths/types or SQLite schema metadata are described. Scalar values,\n"
            "table rows, SQL bodies and defaults are omitted. Names themselves may be private.\n"
            "SQLite inspection uses the saved main file alone; no WAL or SHM is merged.\n"
            "This is neither an atomic database snapshot nor complete App data or function analysis.\n\n"
            "[Source identity](data-schema.json) · [Structure](structure.json)\n\n```json\n" +
            json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n")


def data_schema(source: Path, kind: str, output: Path) -> Path:
    source = source.resolve(strict=True)
    if output.resolve() == source or source in output.resolve().parents:
        raise ValueError("structure case must be outside its source data case")
    schema_record(source, kind)
    case = Case(output, "mac_data_schema")
    try:
        shutil.copytree(source, case.root / "source", symlinks=True)
        case.record("source/manifest.json")
        record = schema_record(case.root / "source", kind)
        value = structure(case.root / "source/data.bin", kind)
        if digest(case.root / "source/data.bin") != record["source_data_sha256"]:
            raise ValueError("data changed during structure extraction")
        case.add("data-schema.json", record)
        case.add("structure.json", value)
        case.add("schema.md", schema_markdown(record, value).encode("utf-8"), binary=True)
        case.finish("complete", scope="data_structure_only", format=kind)
        from copyapp.verify import verify_case
        if not verify_case(case.root):
            raise ValueError("structure source revalidation failed")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="data_structure_only", format=kind)
        raise


def validate_schema(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "data_structure_only" or
            not {"source/manifest.json", "data-schema.json", "structure.json", "schema.md"}.issubset(names)):
        return False
    record = schema_record(root / "source", manifest["format"])
    value = structure(root / "source/data.bin", record["format"])
    return (read(root, "data-schema.json") == record and read(root, "structure.json") == value and
            (root / "schema.md").read_text() == schema_markdown(record, value))


def report_data_source(root: Path, source_id: str) -> dict:
    from copyapp.verify import verify_case
    if not verify_case(root) or read(root, "manifest.json").get("kind") != "mac_data_schema":
        raise ValueError("report data citations require a verified Mac structure case")
    record = read(root, "data-schema.json")
    return {"id": source_id, "manifest_sha256": digest(root / "manifest.json"),
            "structure_sha256": digest(root / "structure.json"), **record}
