#!/usr/bin/env python3
"""Re-point an undefined symbol's two-level-namespace source library.

Mach-O binaries built with the TWOLEVEL namespace record, per undefined symbol,
WHICH library it must come from (the "library ordinal", in the high byte of
nlist.n_desc). dyld looks only in that library — so merely loading another dylib
that defines the symbol does NOT satisfy the bind.

We need that for back-compat: Xcode's prebuilt XCTRunner stub hard-references
`_OBJC_CLASS_$_XCTCommandLineToolHelper` *from XCTest*, but older iOS Developer
disk images ship an XCTest without that class, so dyld aborts at launch. We ship
a shim dylib defining the class and use this tool to point the symbol at the
shim's ordinal instead of XCTest's.

Handles both thin binaries and (1-or-more-slice) fat containers.

Usage:
  retarget-undef-symbol.py <macho> <symbol> <new-dylib-name-substring>
    e.g. ... runner '_OBJC_CLASS_$_XCTCommandLineToolHelper' libXCTCompatShim
"""
import struct
import sys

FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA
MH_MAGIC_64 = 0xFEEDFACF
LC_SYMTAB = 0x02
LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
N_STAB = 0xE0
N_TYPE = 0x0E
N_UNDF = 0x00

DYLIB_CMDS = (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB)


def cstr(buf, at):
    return buf[at:buf.index(b"\x00", at)].decode("utf-8", "replace")


def patch_slice(buf, base, want_sym, want_lib):
    """Retarget `want_sym` to the dylib whose name contains `want_lib`, in the
    Mach-O slice starting at `base`. Returns how many symbols were changed."""
    ncmds = struct.unpack_from("<I", buf, base + 16)[0]
    off = base + 32
    symoff = nsyms = stroff = None
    ordinal = 0                  # LC_LOAD* commands are numbered from 1, in order
    target_ordinal = None

    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", buf, off)
        if cmd in DYLIB_CMDS:
            ordinal += 1
            name = cstr(buf, off + struct.unpack_from("<I", buf, off + 8)[0])
            if want_lib in name:
                target_ordinal = ordinal
                print(f"   target library ordinal {ordinal}: {name}")
        elif cmd == LC_SYMTAB:
            symoff, nsyms, stroff, _ = struct.unpack_from("<IIII", buf, off + 8)
            # Offsets in the load command are relative to the slice, not the file.
            symoff += base
            stroff += base
        off += cmdsize

    if target_ordinal is None or symoff is None:
        return 0

    changed = 0
    for i in range(nsyms):
        e = symoff + i * 16      # nlist_64: n_strx(4) n_type(1) n_sect(1) n_desc(2) n_value(8)
        n_strx, n_type, _n_sect, n_desc = struct.unpack_from("<IBBH", buf, e)
        if (n_type & N_STAB) or (n_type & N_TYPE) != N_UNDF:
            continue
        if cstr(buf, stroff + n_strx) != want_sym:
            continue
        old = (n_desc >> 8) & 0xFF
        struct.pack_into("<H", buf, e + 6, (n_desc & 0x00FF) | (target_ordinal << 8))
        print(f"   {want_sym}: library ordinal {old} -> {target_ordinal}")
        changed += 1
    return changed


def main():
    if len(sys.argv) != 4:
        print("usage: retarget-undef-symbol.py <macho> <symbol> <dylib-substr>", file=sys.stderr)
        return 2
    path, want_sym, want_lib = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(path, "rb") as fh:
        buf = bytearray(fh.read())

    # A thin binary is often still wrapped in a 1-slice fat container.
    if struct.unpack_from(">I", buf, 0)[0] in (FAT_MAGIC, FAT_CIGAM):
        nfat = struct.unpack_from(">I", buf, 4)[0]
        bases = [struct.unpack_from(">I", buf, 8 + i * 20 + 8)[0] for i in range(nfat)]
    else:
        bases = [0]

    total = 0
    for base in bases:
        if struct.unpack_from("<I", buf, base)[0] == MH_MAGIC_64:
            total += patch_slice(buf, base, want_sym, want_lib)

    if not total:
        print(f"🔴 '{want_sym}' not found as an undefined symbol, or no dylib matching "
              f"'{want_lib}' is loaded", file=sys.stderr)
        return 1

    with open(path, "wb") as fh:
        fh.write(buf)
    print(f"   ✅ retargeted {total} symbol(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
