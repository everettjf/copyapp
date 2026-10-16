#!/usr/bin/env python3
"""Add an LC_LOAD_DYLIB load command to a Mach-O binary, in place.

What `optool install -c load` did for the runner's compat shim, without the
dependency: optool isn't in Homebrew, and the binary floating around is x86_64,
which doesn't run on an Apple Silicon Mac without Rosetta. A fresh clone has to
build with nothing but Xcode, so this ships with the repo.

The new command goes into the padding between the existing load commands and
the first section's data — the space the linker leaves for exactly this
(-headerpad). If that space is too small, nothing is written and the script
fails. The code signature is left stale on purpose: the build re-signs every
binary afterwards.

Handles thin 64-bit binaries and fat containers of them.

Usage:
  insert-dylib.py <macho> <install-name>
    e.g. ... runner @rpath/libXCTCompatShim.dylib
"""
import struct
import sys

FAT_MAGIC = 0xCAFEBABE
MH_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
LC_LOAD_DYLIB = 0x0C
DYLIB_CMDS = {0x0C, 0x0D, 0x80000018, 0x8000001F, 0x80000023}  # load/id/weak/reexport/upward
S_ZEROFILL_TYPES = {0x1, 0xC, 0x12}  # zerofill, gb_zerofill, thread_local_zerofill
HEADER_64 = 32


def dylib_name(buf, off):
    name_off = struct.unpack_from('<I', buf, off + 8)[0]
    end = buf.index(b'\0', off + name_off)
    return bytes(buf[off + name_off:end]).decode()


def insert(buf, base, install_name):
    magic, _cpu, _sub, _ft, ncmds, sizeofcmds, _flags, _res = struct.unpack_from('<IiiIIIII', buf, base)
    if magic != MH_MAGIC_64:
        sys.exit(f"not a 64-bit Mach-O slice at offset {base:#x}")

    # Walk the commands: refuse a duplicate, and find where section data begins.
    first_data = None
    off = base + HEADER_64
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', buf, off)
        if cmd in DYLIB_CMDS and dylib_name(buf, off) == install_name:
            sys.exit(f"{install_name} is already loaded — nothing to do")
        if cmd == LC_SEGMENT_64:
            nsects = struct.unpack_from('<I', buf, off + 64)[0]
            for i in range(nsects):
                s = off + 72 + i * 80
                sec_size = struct.unpack_from('<Q', buf, s + 40)[0]
                sec_off, = struct.unpack_from('<I', buf, s + 48)
                sec_flags, = struct.unpack_from('<I', buf, s + 64)
                if sec_off and sec_size and (sec_flags & 0xFF) not in S_ZEROFILL_TYPES:
                    first_data = sec_off if first_data is None else min(first_data, sec_off)
        off += size

    name = install_name.encode() + b'\0'
    cmdsize = (24 + len(name) + 7) & ~7  # dylib_command + name, 8-byte aligned
    end_of_cmds = base + HEADER_64 + sizeofcmds
    limit = base + (first_data if first_data is not None else len(buf) - base)
    if end_of_cmds + cmdsize > limit:
        sys.exit(f"not enough header padding: need {cmdsize} bytes, have {limit - end_of_cmds}")
    if any(buf[end_of_cmds:end_of_cmds + cmdsize]):
        sys.exit("header padding is not empty — refusing to overwrite it")

    # dylib_command: cmd, cmdsize, name offset, timestamp, current, compatibility
    cmd_bytes = struct.pack('<IIIIII', LC_LOAD_DYLIB, cmdsize, 24, 2, 0x10000, 0x10000) + name
    buf[end_of_cmds:end_of_cmds + cmdsize] = cmd_bytes.ljust(cmdsize, b'\0')
    struct.pack_into('<II', buf, base + 16, ncmds + 1, sizeofcmds + cmdsize)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    path, install_name = sys.argv[1], sys.argv[2]
    with open(path, 'rb') as f:
        buf = bytearray(f.read())

    if struct.unpack_from('>I', buf, 0)[0] == FAT_MAGIC:
        nfat = struct.unpack_from('>I', buf, 4)[0]
        for i in range(nfat):
            slice_off = struct.unpack_from('>I', buf, 8 + i * 20 + 8)[0]
            insert(buf, slice_off, install_name)
    else:
        insert(buf, 0, install_name)

    with open(path, 'wb') as f:
        f.write(buf)


if __name__ == '__main__':
    main()
