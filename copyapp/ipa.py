"""Bounded, read-only index of an IPA and its Mach-O load commands."""

import hashlib
import json
import plistlib
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from zipfile import ZipFile


MAX_BINARY = 250 * 1024 * 1024
MAX_ASSET_CATALOG = 64 * 1024 * 1024
MAX_ASSET_METADATA = 16 * 1024 * 1024
MAX_CATALOGS = 24
MACHO64_LE = b"\xcf\xfa\xed\xfe"
FAT32_BE = b"\xca\xfe\xba\xbe"
FAT64_BE = b"\xca\xfe\xba\xbf"
MACHO_MAGICS = {MACHO64_LE, FAT32_BE, FAT64_BE}
ARM64_CPU = 0x0100000C
DYLIB_COMMANDS = {0xC, 0x18, 0x1F, 0x20, 0x23}


def _slice_macho(data: bytes) -> bytes:
    if data[:4] == MACHO64_LE:
        return data
    if data[:4] not in (FAT32_BE, FAT64_BE):
        raise ValueError("not a supported arm64 Mach-O")
    fat64 = data[:4] == FAT64_BE
    if len(data) < 8:
        raise ValueError("short fat header")
    count = struct.unpack_from(">I", data, 4)[0]
    if count > 64:
        raise ValueError("too many fat architectures")
    step = 32 if fat64 else 20
    candidates = []
    for index in range(count):
        pos = 8 + index * step
        if pos + step > len(data):
            raise ValueError("truncated fat architecture table")
        cpu = struct.unpack_from(">I", data, pos)[0]
        offset, size = struct.unpack_from(">QQ" if fat64 else ">II", data, pos + 8)
        if offset + size > len(data):
            raise ValueError("fat slice outside file")
        candidates.append((cpu, offset, size))
    match = next((item for item in candidates if item[0] == ARM64_CPU), None)
    if match is None:
        raise ValueError("fat binary has no arm64 slice")
    _, offset, size = match
    return data[offset:offset + size]


def inspect_macho(data: bytes) -> Dict[str, Any]:
    body = _slice_macho(data)
    if len(body) < 32 or body[:4] != MACHO64_LE:
        raise ValueError("not a supported 64-bit little-endian Mach-O")
    cpu, subtype, _file_type, ncmds, sizeofcmds = struct.unpack_from("<IIIII", body, 4)
    if ncmds > 10000 or 32 + sizeofcmds > len(body):
        raise ValueError("invalid load-command bounds")
    cursor = 32
    dylibs: List[str] = []
    encryption: Optional[Dict[str, int]] = None
    uuid = None
    for _ in range(ncmds):
        if cursor + 8 > 32 + sizeofcmds:
            raise ValueError("truncated load command")
        cmd, size = struct.unpack_from("<II", body, cursor)
        if size < 8 or cursor + size > 32 + sizeofcmds:
            raise ValueError("invalid load-command size")
        base_cmd = cmd & 0x7FFFFFFF
        if base_cmd in DYLIB_COMMANDS and size >= 24:
            name_pos = struct.unpack_from("<I", body, cursor + 8)[0]
            if 24 <= name_pos < size:
                raw = body[cursor + name_pos:cursor + size].split(b"\0", 1)[0]
                dylibs.append(raw.decode("utf-8", "replace"))
        elif base_cmd == 0x2C and size >= 24:  # LC_ENCRYPTION_INFO_64
            cryptoff, cryptsize, cryptid = struct.unpack_from("<III", body, cursor + 8)
            encryption = {"cryptoff": cryptoff, "cryptsize": cryptsize, "cryptid": cryptid}
        elif base_cmd == 0x1B and size >= 24:  # LC_UUID
            uuid = body[cursor + 8:cursor + 24].hex()
        cursor += size
    return {
        "cpu_type": cpu, "cpu_subtype": subtype, "uuid": uuid,
        "linked_libraries": sorted(set(dylibs)),
        "encryption_info": encryption,
        "encryption_status": (
            "command_absent" if encryption is None else
            "cryptid_zero" if encryption["cryptid"] == 0 else "cryptid_nonzero"
        ),
        "encrypted_on_disk": encryption is not None and encryption["cryptid"] != 0,
    }


def _catalog_assets(metadata: Any) -> List[Dict[str, Any]]:
    if not isinstance(metadata, list):
        raise ValueError("assetutil metadata is not a list")
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in metadata:
        if not isinstance(row, dict):
            raise ValueError("assetutil metadata contains a non-object row")
        name = row.get("Name")
        if not isinstance(name, str) or not name:
            continue  # The catalog header has no asset name.
        entry = grouped.setdefault(name, {"name": name, "types": set(), "renditions": set(),
                                          "idioms": set(), "scales": set(), "pixel_sizes": set(),
                                          "variant_count": 0})
        entry["variant_count"] += 1
        for source, target in (("AssetType", "types"), ("RenditionName", "renditions"),
                               ("Idiom", "idioms")):
            value = row.get(source)
            if isinstance(value, str) and value:
                entry[target].add(value)
        scale = row.get("Scale")
        if isinstance(scale, (int, float)) and not isinstance(scale, bool) and scale > 0:
            entry["scales"].add(scale)
        width, height = row.get("PixelWidth"), row.get("PixelHeight")
        if (isinstance(width, int) and isinstance(height, int) and
                not isinstance(width, bool) and not isinstance(height, bool) and
                0 < width <= 32768 and 0 < height <= 32768):
            entry["pixel_sizes"].add((width, height))
    return [{"name": name, "types": sorted(item["types"]),
             "renditions": sorted(item["renditions"]), "idioms": sorted(item["idioms"]),
             "scales": sorted(item["scales"]),
             "pixel_sizes": [list(size) for size in sorted(item["pixel_sizes"])],
             "variant_count": item["variant_count"]}
            for name, item in sorted(grouped.items())]


def _inspect_asset_catalogs(archive: ZipFile, infos: list, prefix: str) -> List[Dict[str, Any]]:
    candidates = sorted((item for item in infos if item.filename.startswith(prefix)
                         and item.filename.endswith(".car") and not item.is_dir()),
                        key=lambda item: item.filename)
    available = shutil.which("xcrun") is not None
    results: List[Dict[str, Any]] = []
    for item in candidates[:MAX_CATALOGS]:
        result: Dict[str, Any] = {"path": item.filename, "size": item.file_size}
        if item.file_size > MAX_ASSET_CATALOG:
            result["status"] = "skipped: catalog exceeds size limit"
            results.append(result)
            continue
        blob = archive.read(item)
        result["sha256"] = hashlib.sha256(blob).hexdigest()
        if not available:
            result["status"] = "assetutil unavailable"
            results.append(result)
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="copyapp-assets-") as temporary:
                car = Path(temporary) / "Assets.car"
                metadata_path = Path(temporary) / "metadata.json"
                car.write_bytes(blob)
                with metadata_path.open("wb") as destination:
                    completed = subprocess.run(["xcrun", "assetutil", "--info", str(car)],
                                               stdout=destination, stderr=subprocess.PIPE,
                                               timeout=45, check=False)
                if completed.returncode:
                    raise ValueError(f"assetutil exit code {completed.returncode}")
                if metadata_path.stat().st_size > MAX_ASSET_METADATA:
                    raise ValueError("assetutil metadata exceeds size limit")
                result["assets"] = _catalog_assets(json.loads(metadata_path.read_text("utf-8")))
                result["asset_count"] = len(result["assets"])
                result["status"] = "indexed"
        except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
            result["status"] = f"assetutil failed: {type(exc).__name__}: {exc}"[:240]
        results.append(result)
    if len(candidates) > MAX_CATALOGS:
        results.append({"status": "skipped: catalog count exceeds limit",
                        "remaining_count": len(candidates) - MAX_CATALOGS})
    return results


def analyze_ipa(path: Path) -> Dict[str, Any]:
    path = path.resolve(strict=True)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    ipa_digest = digest.hexdigest()
    with ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("IPA contains duplicate ZIP paths")
        info_path = next((i.filename for i in infos if i.filename.startswith("Payload/")
                          and i.filename.endswith(".app/Info.plist")
                          and i.filename.count("/") == 2), None)
        if info_path is None:
            raise ValueError("IPA has no Payload/*.app/Info.plist")
        if archive.getinfo(info_path).file_size > 4 * 1024 * 1024:
            raise ValueError("Info.plist exceeds size limit")
        plist = plistlib.loads(archive.read(info_path))
        prefix = info_path[:-len("Info.plist")]
        executable = plist.get("CFBundleExecutable")
        if not executable:
            raise ValueError("Info.plist has no CFBundleExecutable")
        candidates = {prefix + executable}
        for info in infos:
            name = info.filename
            if not name.startswith(prefix) or info.is_dir():
                continue
            if name.endswith(".dylib"):
                candidates.add(name)
            # Embedded executables need not match their framework/extension folder.
            # Inspect a bounded magic prefix so every Mach-O is included, even
            # when a nested Info.plist uses a different executable name.
            if info.file_size >= 4:
                with archive.open(info) as stream:
                    if stream.read(4) in MACHO_MAGICS:
                        candidates.add(name)
        names = set(names)
        binaries = []
        for name in sorted(candidates & names):
            size = archive.getinfo(name).file_size
            if size > MAX_BINARY:
                binaries.append({"path": name, "status": "skipped: binary exceeds size limit"})
                continue
            blob = archive.read(name)
            try:
                analysis = inspect_macho(blob)
                binaries.append({"path": name, "size": size,
                                 "sha256": hashlib.sha256(blob).hexdigest(), **analysis})
            except ValueError as exc:
                binaries.append({"path": name, "size": size, "status": str(exc)})
        paths = [item.filename for item in infos if item.filename.startswith(prefix)]
        asset_catalogs = _inspect_asset_catalogs(archive, infos, prefix)
        return {
            "schema_version": 1, "source": str(path), "ipa_sha256": ipa_digest,
            "bundle_id": plist.get("CFBundleIdentifier"),
            "version": plist.get("CFBundleShortVersionString"),
            "build": plist.get("CFBundleVersion"),
            "executable": executable, "file_count": len(paths),
            "frameworks": sorted({p.split(".framework/")[0].rsplit("/", 1)[-1] + ".framework"
                                   for p in paths if ".framework/" in p}),
            "extensions": sorted({p.split(".appex/")[0].rsplit("/", 1)[-1] + ".appex"
                                   for p in paths if ".appex/" in p}),
            "binaries": binaries, "asset_catalogs": asset_catalogs,
        }


def write_ipa_report(result: Dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "ipa-index.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = [
        f"# IPA 静态索引：{result['bundle_id']}", "",
        f"- 版本：{result['version']}（构建 {result['build']}）",
        f"- IPA SHA-256：`{result['ipa_sha256']}`",
        f"- 包内文件：{result['file_count']}",
        f"- Framework：{', '.join(result['frameworks']) or '未发现'}",
        f"- 扩展：{', '.join(result['extensions']) or '未发现'}", "",
        "## Mach-O 二进制", "",
    ]
    for binary in result["binaries"]:
        lines.extend([f"### `{binary['path']}`", ""])
        if "status" in binary:
            lines.extend([f"- 状态：{binary['status']}", ""])
            continue
        encryption_status = binary.get("encryption_status")
        if encryption_status == "command_absent":
            state = "未发现 LC_ENCRYPTION_INFO；本工具未执行脱壳"
        elif encryption_status == "cryptid_zero":
            state = "存在 LC_ENCRYPTION_INFO，cryptid=0；本工具未执行脱壳"
        elif encryption_status == "cryptid_nonzero":
            state = "存在 LC_ENCRYPTION_INFO，cryptid 非零；磁盘文件仍标记为加密"
        else:
            state = "未知"
        lines.extend([
            f"- 文件 SHA-256：`{binary['sha256']}`",
            f"- Mach-O UUID：`{binary['uuid']}`",
            f"- 加密命令状态：{state}",
            f"- 链接库：{', '.join(binary['linked_libraries']) or '无可见 LC_LOAD_DYLIB'}", "",
        ])
    lines.extend(["## 资源目录", ""])
    catalogs = result.get("asset_catalogs", [])
    if not catalogs:
        lines.extend(["未发现 Assets.car 资源目录。", ""])
    for catalog in catalogs:
        lines.append(f"### `{catalog.get('path', '额外资源目录')}`")
        lines.append("")
        lines.append(f"- 状态：{catalog['status']}")
        if catalog.get("sha256"):
            lines.append(f"- 文件 SHA-256：`{catalog['sha256']}`")
        if catalog.get("status") == "indexed":
            assets = catalog["assets"]
            lines.append(f"- 命名资源：{len(assets)}；完整目录见 `ipa-index.json` 的 `asset_catalogs`。")
            interesting = [item for item in assets if any(word in item["name"].lower()
                           for word in ("login", "auth", "logo", "whale", "icon"))][:80]
            if interesting:
                lines.extend(["", "| 资源名 | 类型 | 变体 |", "| --- | --- | ---: |"])
                for item in interesting:
                    lines.append(f"| `{item['name'].replace('|', '&#124;')}` | "
                                 f"{', '.join(item['types'])} | {item['variant_count']} |")
        lines.append("")
    lines.extend(["## 边界", "", "该索引解析包结构、Mach-O 加载命令及可用时的 Assets.car 命名资源元数据；它不导出图像像素，不证明哪个资源出现在特定界面，也不包含方法体或运行行为。", ""])
    (output / "ipa-report.md").write_text("\n".join(lines), encoding="utf-8")
    evidence = []
    for name in ("ipa-index.json", "ipa-report.md"):
        data = (output / name).read_bytes()
        evidence.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "kind": "ipa_static_index",
        "source_ipa": str(Path(result["source"]).resolve()),
        "ipa_sha256": result["ipa_sha256"], "evidence": evidence,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
