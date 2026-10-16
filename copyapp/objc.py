"""Bounded Objective-C metadata index for an on-disk arm64 Mach-O image.

This extracts names, type encodings and implementation addresses.  It does
not disassemble implementations or claim to recover original source code.
"""

import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from copyapp.ipa import MAX_BINARY, _slice_macho


LC_SEGMENT_64 = 0x19
MAX_CLASSES = 10000
MAX_METHODS = 200000
MAX_STRING = 4096


class ObjCIndexError(ValueError):
    pass


class MachOImage:
    def __init__(self, blob: bytes):
        self.data = _slice_macho(blob)
        if len(self.data) < 32 or self.data[:4] != b"\xcf\xfa\xed\xfe":
            raise ObjCIndexError("expected little-endian 64-bit Mach-O")
        self.sections: Dict[Tuple[str, str], Tuple[int, int, int]] = {}
        self.ranges: List[Tuple[int, int, int]] = []
        self.base: Optional[int] = None
        ncmds, sizeofcmds = struct.unpack_from("<II", self.data, 16)
        if ncmds > 10000 or 32 + sizeofcmds > len(self.data):
            raise ObjCIndexError("invalid load-command bounds")
        cursor = 32
        for _ in range(ncmds):
            if cursor + 8 > 32 + sizeofcmds:
                raise ObjCIndexError("truncated load command")
            command, size = struct.unpack_from("<II", self.data, cursor)
            if size < 8 or cursor + size > 32 + sizeofcmds:
                raise ObjCIndexError("invalid load-command size")
            if command == LC_SEGMENT_64:
                if size < 72:
                    raise ObjCIndexError("short segment command")
                vmaddr, _vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", self.data, cursor + 24)
                if fileoff + filesize > len(self.data):
                    raise ObjCIndexError("segment outside image")
                if fileoff == 0 and filesize and (self.base is None or vmaddr < self.base):
                    self.base = vmaddr
                nsects = struct.unpack_from("<I", self.data, cursor + 64)[0]
                if nsects > 10000 or 72 + nsects * 80 > size:
                    raise ObjCIndexError("invalid section count")
                for index in range(nsects):
                    pos = cursor + 72 + index * 80
                    section = self._fixed_name(self.data[pos:pos + 16])
                    segment = self._fixed_name(self.data[pos + 16:pos + 32])
                    address, length, offset = struct.unpack_from("<QQI", self.data, pos + 32)
                    flags = struct.unpack_from("<I", self.data, pos + 64)[0]
                    # S_ZEROFILL, S_GB_ZEROFILL, S_THREAD_LOCAL_ZEROFILL.
                    if flags & 0xFF in (1, 12, 18):
                        continue
                    if offset + length > len(self.data):
                        raise ObjCIndexError("section outside image")
                    self.sections[(segment, section)] = (address, length, offset)
                    self.ranges.append((address, address + length, offset))
            cursor += size
        if self.base is None:
            raise ObjCIndexError("image base not found")

    @staticmethod
    def _fixed_name(raw: bytes) -> str:
        return raw.split(b"\0", 1)[0].decode("ascii", "replace")

    def offset(self, address: int, length: int = 1) -> int:
        if length < 0:
            raise ObjCIndexError("negative read length")
        for start, end, fileoff in self.ranges:
            if start <= address and address + length <= end:
                return fileoff + address - start
        raise ObjCIndexError(f"address outside file-backed sections: 0x{address:x}")

    def unpack(self, fmt: str, address: int):
        size = struct.calcsize(fmt)
        return struct.unpack_from(fmt, self.data, self.offset(address, size))

    def pointer(self, raw: int) -> int:
        """Resolve plain or arm64e authenticated/rebased pointers within this image."""
        if not raw:
            return 0
        candidates = (raw, self.base + (raw & 0xFFFFFFFF), raw & 0x0000FFFFFFFFFFFF)
        for candidate in candidates:
            try:
                self.offset(candidate)
                return candidate
            except ObjCIndexError:
                pass
        raise ObjCIndexError(f"unresolved image pointer: 0x{raw:x}")

    def read_pointer(self, address: int) -> int:
        return self.pointer(self.unpack("<Q", address)[0])

    def string(self, address: int) -> str:
        start = self.offset(address)
        end = min(start + MAX_STRING, len(self.data))
        stop = self.data.find(b"\0", start, end)
        if stop < 0:
            raise ObjCIndexError("unterminated Objective-C string")
        return self.data[start:stop].decode("utf-8", "replace")

    def method_list(self, address: int) -> List[Dict[str, Any]]:
        if not address:
            return []
        flags, count = self.unpack("<II", address)
        relative = bool(flags & 0x80000000)
        direct_selector = bool(flags & 0x40000000)
        entry_size = flags & 0xFFFF
        expected = 12 if relative else 24
        if entry_size < expected or count > MAX_METHODS:
            raise ObjCIndexError("invalid Objective-C method list")
        self.offset(address + 8, count * entry_size)
        methods = []
        for index in range(count):
            entry = address + 8 + index * entry_size
            if relative:
                name_rel, type_rel, imp_rel = self.unpack("<iii", entry)
                selector_target = entry + name_rel
                selector = selector_target if direct_selector else self.read_pointer(selector_target)
                types = entry + 4 + type_rel
                implementation = entry + 8 + imp_rel
            else:
                name_raw, type_raw, imp_raw = self.unpack("<QQQ", entry)
                selector = self.pointer(name_raw)
                types = self.pointer(type_raw)
                implementation = self.pointer(imp_raw)
            methods.append({
                "selector": self.string(selector),
                "types": self.string(types),
                "imp": f"0x{implementation:x}",
            })
        return methods

    def class_record(self, address: int) -> Dict[str, Any]:
        isa_raw, superclass_raw = self.unpack("<QQ", address)
        data_raw = self.unpack("<Q", address + 32)[0]
        ro = self.pointer(data_raw & ~7)
        name = self.string(self.read_pointer(ro + 24))
        methods = self.method_list(self.read_pointer(ro + 32)) if self.unpack("<Q", ro + 32)[0] else []
        result = {"name": name, "address": f"0x{address:x}", "instance_methods": methods}
        try:
            superclass = self.pointer(superclass_raw)
            result["superclass_address"] = f"0x{superclass:x}"
        except ObjCIndexError:
            # External classes are typically fixups/imports, not local pointers.
            result["superclass_address"] = None
        if isa_raw:
            try:
                meta = self.pointer(isa_raw)
                meta_ro = self.pointer(self.unpack("<Q", meta + 32)[0] & ~7)
                meta_methods_raw = self.unpack("<Q", meta_ro + 32)[0]
                result["class_methods"] = self.method_list(self.pointer(meta_methods_raw)) if meta_methods_raw else []
            except ObjCIndexError:
                result["class_methods"] = []
        else:
            result["class_methods"] = []
        return result


def index_objc(path: Path) -> Dict[str, Any]:
    if path.stat().st_size > MAX_BINARY:
        raise ObjCIndexError("binary exceeds size limit")
    blob = path.read_bytes()
    image = MachOImage(blob)
    sections = [value for (segment, section), value in image.sections.items()
                if section == "__objc_classlist"]
    classes = []
    for address, length, _offset in sections:
        if length % 8 or length // 8 > MAX_CLASSES:
            raise ObjCIndexError("invalid Objective-C class list")
        for index in range(length // 8):
            classes.append(image.class_record(image.read_pointer(address + index * 8)))
    if len(classes) > MAX_CLASSES or sum(len(item["instance_methods"]) + len(item["class_methods"])
                                      for item in classes) > MAX_METHODS:
        raise ObjCIndexError("Objective-C metadata exceeds limits")
    return {"schema_version": 1, "binary_sha256": hashlib.sha256(blob).hexdigest(),
            "image_base": f"0x{image.base:x}",
            "class_count": len(classes), "classes": classes,
            "scope": "locally defined Objective-C classes in __objc_classlist; no decompilation"}


def write_objc_report(result: Dict[str, Any], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    (output / "objc-index.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Objective-C 类与方法索引", "",
             f"- 二进制 SHA-256：`{result['binary_sha256']}`",
             f"- 本地定义类：{result['class_count']}", "",
             "方法地址是静态 Mach-O 虚拟地址，不是运行时地址；本索引没有反编译函数体。", ""]
    for item in result["classes"]:
        lines.extend([f"## {item['name']}", ""])
        for kind, marker in (("instance_methods", "-"), ("class_methods", "+")):
            for method in item[kind]:
                lines.append(f"- `{marker}[{item['name']} {method['selector']}]` · "
                             f"`{method['imp']}` · `{method['types']}`")
        lines.append("")
    path = output / "objc-report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
