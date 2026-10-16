"""Assemble verified recovered binaries into a non-installable analysis IPA."""

import hashlib
import json
import shutil
from copy import copy
from pathlib import Path, PurePosixPath
from typing import Dict, List
from zipfile import ZipFile

from copyapp.decrypt import _cryptid_offset
from copyapp.decrypt_verify import inspect_decrypted_ipa, write_decryption_check
from copyapp.ipa import analyze_ipa, inspect_macho


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validated_case(case: Path) -> tuple:
    record = json.loads((case / "decryption.json").read_text())
    extension = "relative_path" in record
    prefix = "extension" if extension else "main"
    original = (case / f"encrypted-{prefix}.bin").read_bytes()
    recovered = (case / f"decrypted-{prefix}.bin").read_bytes()
    if len(original) != len(recovered):
        raise ValueError("recovered executable changed file length")
    if _sha256(original) != record["encrypted_file_sha256"]:
        raise ValueError("encrypted hash differs from decryption record")
    if _sha256(recovered) != record["decrypted_file_sha256"]:
        raise ValueError("recovered hash differs from decryption record")
    before, after = inspect_macho(original), inspect_macho(recovered)
    crypt = before["encryption_info"]
    start, size = record["cryptoff"], record["cryptsize"]
    if not crypt or crypt["cryptoff"] != start or crypt["cryptsize"] != size:
        raise ValueError("encrypted range disagrees with Mach-O")
    patch_offset = _cryptid_offset(original)
    expected = bytearray(original)
    expected[start:start + size] = recovered[start:start + size]
    expected[patch_offset:patch_offset + 4] = recovered[patch_offset:patch_offset + 4]
    if expected != recovered or original == recovered:
        raise ValueError("recovered binary contains changes outside cryptid and encrypted range")
    if after["encryption_status"] != "cryptid_zero" or before["uuid"] != after["uuid"]:
        raise ValueError("recovered Mach-O identity or cryptid invalid")
    return record, recovered


def assemble_analysis_ipa(snapshot: Path, recovered_cases: List[Path], output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    if not recovered_cases:
        raise ValueError("at least one recovered binary is required")
    index = analyze_ipa(snapshot)
    binary_index = {item["path"]: item for item in index["binaries"]}
    main = next((item for item in index["binaries"]
                 if item["path"].startswith("Payload/")
                 and item["path"].count("/") == 2
                 and item["path"].endswith("/" + index["executable"])), None)
    if main is None:
        raise ValueError("snapshot main executable missing")
    app_root = main["path"].rsplit("/", 1)[0]
    replacements: Dict[str, bytes] = {}
    recovered_records = []
    for case in recovered_cases:
        record, recovered = _validated_case(case)
        if index["bundle_id"] != record["bundle_id"]:
            raise ValueError("snapshot bundle ID differs from decryption record")
        if index["version"] != record["installed_version"]:
            raise ValueError("snapshot app version differs from recovered source")
        if "relative_path" in record:
            relative = PurePosixPath(record["relative_path"])
            if (relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 3
                    or relative.parts[0] != "PlugIns" or not relative.parts[1].endswith(".appex")
                    or relative.parts[2] != record["executable"]):
                raise ValueError("invalid extension relative path")
            path = app_root + "/" + relative.as_posix()
        else:
            if record["executable"] != index["executable"]:
                raise ValueError("main executable differs from snapshot")
            path = main["path"]
        if path in replacements:
            raise ValueError("duplicate recovered binary path")
        if path not in binary_index or binary_index[path].get("sha256") != record["encrypted_file_sha256"]:
            raise ValueError("snapshot binary differs from recovered source")
        replacements[path] = recovered
        recovered_records.append({"path": path, "sha256": record["decrypted_file_sha256"]})

    output.mkdir(parents=True, exist_ok=True)
    result = output / "analysis-snapshot.ipa"
    with ZipFile(snapshot) as source, ZipFile(result, "w") as target:
        for info in source.infolist():
            if info.is_dir():
                target.writestr(copy(info), b"")
                continue
            with target.open(copy(info), "w") as sink:
                if info.filename in replacements:
                    sink.write(replacements[info.filename])
                else:
                    with source.open(info) as content:
                        shutil.copyfileobj(content, sink, length=1024 * 1024)
    check = inspect_decrypted_ipa(result, index["bundle_id"])
    write_decryption_check(check, output)
    manifest = {
        "schema_version": 2,
        "source_snapshot_sha256": index["ipa_sha256"],
        "recovered_binaries": recovered_records,
        "analysis_ipa_sha256": check["ipa_sha256"],
        "bundle_id": index["bundle_id"],
        "main_path": main["path"],
        "all_macho_headers_decrypted": check["header_check_passed"],
        "remaining_failures": check["failures"],
        "note": "Analysis snapshot only; modified code signatures are invalid and installability is not asserted.",
    }
    path = output / "assembly.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return path


def assemble_main_ipa(snapshot: Path, recovered_case: Path, output: Path) -> Path:
    """Compatibility entry point for callers with only a recovered main binary."""
    return assemble_analysis_ipa(snapshot, [recovered_case], output)
