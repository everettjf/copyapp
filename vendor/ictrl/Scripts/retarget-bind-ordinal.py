#!/usr/bin/env python3
"""Re-point a symbol's bind record to a different library, in the LC_DYLD_INFO
bind opcode stream (the one dyld actually executes).

Why this is separate from the symbol table: binaries with LC_DYLD_INFO_ONLY keep
their binding instructions in a bytecode stream, NOT derived from LC_SYMTAB.
Patching the nlist library ordinal changes what `nm`/`dyld_info -imports` print
but does nothing at runtime — dyld executes the opcodes. Both must agree.

The stream is a sequence of opcodes; the ones we care about:
  BIND_OPCODE_SET_DYLIB_ORDINAL_IMM  (0x10 | ordinal)   ordinal in the low nibble
  BIND_OPCODE_SET_DYLIB_ORDINAL_ULEB (0x20)             ordinal as a ULEB128
  BIND_OPCODE_SET_SYMBOL_TRAILING_FLAGS_IMM (0x40)      NUL-terminated name follows
"Current ordinal" is stateful: it applies to every subsequent bind until changed.
So to retarget one symbol we rewrite the ordinal that is in effect when its name
appears — and, because the old ordinal must stay in effect for the OTHER symbols,
we re-emit it right after. That only works when both fit in the IMM form, which
holds here (small ordinals); we bail out loudly otherwise.

Newer linkers (the runner stub from Xcode 27 on) emit LC_DYLD_CHAINED_FIXUPS
instead of a bind stream. There the library ordinal lives in the fixups'
IMPORTS table, one entry per imported symbol, so retargeting is a direct field
write — handled by patch_chained_imports below. Each binary uses one form or the
other; both are tried.

Usage: retarget-bind-ordinal.py <macho> <symbol> <new-ordinal>
"""
import struct
import sys

FAT_MAGIC = 0xCAFEBABE
FAT_CIGAM = 0xBEBAFECA
MH_MAGIC_64 = 0xFEEDFACF
LC_DYLD_INFO = 0x22
LC_DYLD_INFO_ONLY = 0x80000022
LC_DYLD_CHAINED_FIXUPS = 0x80000034

BIND_OPCODE_MASK = 0xF0
BIND_IMMEDIATE_MASK = 0x0F
BIND_OPCODE_DONE = 0x00
BIND_OPCODE_SET_DYLIB_ORDINAL_IMM = 0x10
BIND_OPCODE_SET_DYLIB_ORDINAL_ULEB = 0x20
BIND_OPCODE_SET_DYLIB_SPECIAL_IMM = 0x30
BIND_OPCODE_SET_SYMBOL_TRAILING_FLAGS_IMM = 0x40


def read_uleb(buf, i):
    result = shift = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7


def patch_stream(buf, start, size, want_sym, new_ord):
    """Walk the bind opcodes; when `want_sym` is bound under an ordinal that is
    not new_ord, rewrite that SET_DYLIB_ORDINAL_IMM byte. Returns #patched."""
    i = start
    end = start + size
    cur_ord_pos = None      # file offset of the byte holding the current ordinal
    cur_ord = None
    patched = 0

    while i < end:
        op = buf[i]
        opcode = op & BIND_OPCODE_MASK
        imm = op & BIND_IMMEDIATE_MASK
        here = i
        i += 1

        if opcode == BIND_OPCODE_DONE:
            continue
        if opcode == BIND_OPCODE_SET_DYLIB_ORDINAL_IMM:
            cur_ord_pos, cur_ord = here, imm
        elif opcode == BIND_OPCODE_SET_DYLIB_ORDINAL_ULEB:
            cur_ord, i = read_uleb(buf, i)
            cur_ord_pos = None          # can't rewrite in place safely
        elif opcode == BIND_OPCODE_SET_DYLIB_SPECIAL_IMM:
            cur_ord_pos, cur_ord = None, -imm
        elif opcode == BIND_OPCODE_SET_SYMBOL_TRAILING_FLAGS_IMM:
            j = buf.index(b"\x00", i)
            name = buf[i:j].decode("utf-8", "replace")
            i = j + 1
            if name == want_sym and cur_ord != new_ord:
                if cur_ord_pos is None:
                    print(f"🔴 '{name}' bound via a non-IMM ordinal ({cur_ord}); "
                          f"in-place patch unsupported", file=sys.stderr)
                    return -1
                if not (0 <= new_ord <= 0x0F):
                    print(f"🔴 new ordinal {new_ord} doesn't fit the IMM form", file=sys.stderr)
                    return -1
                # The ordinal is STATEFUL — it stays in effect for every later
                # bind in the stream. Flipping it in place would silently
                # re-point the symbols that follow (here: XCTestDriver,
                # XCTestObservationCenter), which must keep coming from XCTest.
                # So: flip it for our symbol, then splice in a second
                # SET_DYLIB_ORDINAL_IMM restoring the old value right after this
                # symbol's DO_BIND. The extra byte is paid for out of the run of
                # redundant trailing DONE opcodes.
                old_ord = cur_ord
                bind_end = i
                while bind_end < end and (buf[bind_end] & BIND_OPCODE_MASK) != 0x90:
                    op2 = buf[bind_end] & BIND_OPCODE_MASK
                    bind_end += 1
                    if op2 in (0x60, 0x70, 0x80, 0xA0):
                        _, bind_end = read_uleb(buf, bind_end)
                    elif op2 == 0xC0:
                        _, bind_end = read_uleb(buf, bind_end)
                        _, bind_end = read_uleb(buf, bind_end)
                if bind_end >= end:
                    print(f"🔴 no DO_BIND found after '{name}'", file=sys.stderr)
                    return -1
                bind_end += 1                      # just past this symbol's DO_BIND
                if buf[end - 1] != BIND_OPCODE_DONE:
                    print("🔴 no trailing DONE padding to reclaim", file=sys.stderr)
                    return -1
                buf[cur_ord_pos] = BIND_OPCODE_SET_DYLIB_ORDINAL_IMM | new_ord
                # shift [bind_end, end-1) right by one, dropping one trailing DONE
                buf[bind_end + 1:end] = buf[bind_end:end - 1]
                buf[bind_end] = BIND_OPCODE_SET_DYLIB_ORDINAL_IMM | old_ord
                print(f"   bind '{name}': dylib ordinal {old_ord} -> {new_ord} "
                      f"(restored {old_ord} for following symbols)")
                patched += 1
                cur_ord = old_ord
                i = bind_end + 1
        elif opcode in (0x50, 0x90):        # SET_TYPE_IMM / DO_BIND: no operand
            pass
        elif opcode in (0x60, 0x70, 0xA0, 0xB0):  # SET_ADDEND/SEGMENT/ADD_ADDR/DO_BIND_ADD
            _, i = read_uleb(buf, i)
            if opcode == 0x70:              # SET_SEGMENT_AND_OFFSET_ULEB: 1 more uleb
                pass
        elif opcode == 0xC0:                # DO_BIND_ULEB_TIMES_SKIPPING
            _, i = read_uleb(buf, i)
            _, i = read_uleb(buf, i)
    return patched


def patch_chained_imports(buf, hdr, want_sym, new_ord):
    """Point every chained-fixups import of `want_sym` at library `new_ord`.

    dyld_chained_fixups_header: version, starts_offset, imports_offset,
    symbols_offset, imports_count, imports_format, symbols_format (all u32).
    Import formats (lib_ordinal is the low bits of the first word):
      1 DYLD_CHAINED_IMPORT           u32: ordinal:8  weak:1 name_offset:23
      2 DYLD_CHAINED_IMPORT_ADDEND    the same u32 + i32 addend
      3 DYLD_CHAINED_IMPORT_ADDEND64  u64: ordinal:16 weak:1 reserved:15 name_offset:32, + u64 addend
    """
    _ver, _starts, imports_off, symbols_off, count, fmt, sym_fmt = struct.unpack_from("<7I", buf, hdr)
    if sym_fmt != 0:
        print(f"🔴 compressed chained-fixups symbol table (format {sym_fmt}) is not supported", file=sys.stderr)
        return -1
    stride, ord_bits = {1: (4, 8), 2: (8, 8), 3: (16, 16)}.get(fmt, (0, 0))
    if not stride:
        print(f"🔴 unknown chained-fixups imports format {fmt}", file=sys.stderr)
        return -1
    if new_ord >= (1 << ord_bits) - 16:   # the top values are special ordinals
        print(f"🔴 ordinal {new_ord} doesn't fit import format {fmt}", file=sys.stderr)
        return -1

    want = want_sym.encode()
    patched = 0
    for i in range(count):
        at = hdr + imports_off + i * stride
        if fmt == 3:
            word = struct.unpack_from("<Q", buf, at)[0]
            name_off = word >> 32
        else:
            word = struct.unpack_from("<I", buf, at)[0]
            name_off = word >> 9
        name_at = hdr + symbols_off + name_off
        end = buf.index(b"\0", name_at)
        if bytes(buf[name_at:end]) != want:
            continue
        mask = (1 << ord_bits) - 1
        old = word & mask
        if old == new_ord:
            continue
        word = (word & ~mask) | new_ord
        struct.pack_into("<Q" if fmt == 3 else "<I", buf, at, word)
        print(f"   ↪ chained import '{want_sym}': library ordinal {old} → {new_ord}")
        patched += 1
    return patched


def main():
    if len(sys.argv) != 4:
        print("usage: retarget-bind-ordinal.py <macho> <symbol> <new-ordinal>", file=sys.stderr)
        return 2
    path, want_sym, new_ord = sys.argv[1], sys.argv[2], int(sys.argv[3])

    with open(path, "rb") as fh:
        buf = bytearray(fh.read())

    if struct.unpack_from(">I", buf, 0)[0] in (FAT_MAGIC, FAT_CIGAM):
        nfat = struct.unpack_from(">I", buf, 4)[0]
        bases = [struct.unpack_from(">I", buf, 8 + i * 20 + 8)[0] for i in range(nfat)]
    else:
        bases = [0]

    total = 0
    for base in bases:
        if struct.unpack_from("<I", buf, base)[0] != MH_MAGIC_64:
            continue
        ncmds = struct.unpack_from("<I", buf, base + 16)[0]
        off = base + 32
        for _ in range(ncmds):
            cmd, cmdsize = struct.unpack_from("<II", buf, off)
            if cmd == LC_DYLD_CHAINED_FIXUPS:
                dataoff = struct.unpack_from("<I", buf, off + 8)[0]
                n = patch_chained_imports(buf, base + dataoff, want_sym, new_ord)
                if n < 0:
                    return 1
                total += n
            if cmd in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
                bind_off, bind_size = struct.unpack_from("<II", buf, off + 16)
                lazy_off, lazy_size = struct.unpack_from("<II", buf, off + 32)
                for so, sz in ((bind_off, bind_size), (lazy_off, lazy_size)):
                    if not sz:
                        continue
                    n = patch_stream(buf, base + so, sz, want_sym, new_ord)
                    if n < 0:
                        return 1
                    total += n
            off += cmdsize

    if not total:
        print(f"🔴 no bind record for '{want_sym}' needed changing", file=sys.stderr)
        return 1

    with open(path, "wb") as fh:
        fh.write(buf)
    print(f"   ✅ patched {total} bind record(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
