#!/usr/bin/env python3
"""Print the two-level-namespace library ordinal of a loaded dylib.

Bind records address their source library by ordinal (its position among the
LC_LOAD*_DYLIB commands, counting from 1), so retargeting a symbol needs the
number, not the name. Inserting a dylib shifts nothing before it, but the value
still depends on how many load commands precede it — so compute it, never
hardcode.

Usage: dylib-ordinal.py <macho> <dylib-name-substring>
"""
import struct
import sys

FAT_MAGIC, FAT_CIGAM = 0xCAFEBABE, 0xBEBAFECA
MH_MAGIC_64 = 0xFEEDFACF
DYLIB_CMDS = (0x0C, 0x80000018, 0x8000001F)  # LOAD, LOAD_WEAK, REEXPORT


def main():
    if len(sys.argv) != 3:
        print("usage: dylib-ordinal.py <macho> <dylib-substr>", file=sys.stderr)
        return 2
    path, want = sys.argv[1], sys.argv[2]
    buf = open(path, "rb").read()

    base = 0
    if struct.unpack_from(">I", buf, 0)[0] in (FAT_MAGIC, FAT_CIGAM):
        base = struct.unpack_from(">I", buf, 8 + 8)[0]   # first slice
    if struct.unpack_from("<I", buf, base)[0] != MH_MAGIC_64:
        print("not a 64-bit Mach-O", file=sys.stderr)
        return 1

    ncmds = struct.unpack_from("<I", buf, base + 16)[0]
    off, ordinal = base + 32, 0
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", buf, off)
        if cmd in DYLIB_CMDS:
            ordinal += 1
            start = off + struct.unpack_from("<I", buf, off + 8)[0]
            name = buf[start:buf.index(b"\x00", start)].decode("utf-8", "replace")
            if want in name:
                print(ordinal)
                return 0
        off += cmdsize
    print(f"no loaded dylib matching '{want}'", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
