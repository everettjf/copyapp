import struct
import tempfile
import unittest
from pathlib import Path

from copyapp.objc import index_objc


BASE = 0x100000000


def authenticated(offset):
    return 0x8000000000000000 | offset


def fixture_image():
    blob = bytearray(0x500)
    command_size = 72 + 2 * 80
    struct.pack_into("<IiiIIIII", blob, 0, 0xFEEDFACF, 0x0100000C, 0, 2, 1,
                     command_size, 0, 0)
    struct.pack_into("<II16sQQQQiiII", blob, 32, 0x19, command_size, b"__DATA",
                     BASE, len(blob), 0, len(blob), 3, 3, 2, 0)
    struct.pack_into("<16s16sQQIIIIIIII", blob, 32 + 72,
                     b"__objc_classlist", b"__DATA", BASE + 0x200, 8, 0x200,
                     3, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<16s16sQQIIIIIIII", blob, 32 + 72 + 80,
                     b"__objc_data", b"__DATA", BASE + 0x208, 0x200, 0x208,
                     3, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<Q", blob, 0x200, authenticated(0x220))
    struct.pack_into("<Q", blob, 0x220 + 32, authenticated(0x280))
    struct.pack_into("<Q", blob, 0x280 + 24, authenticated(0x3A0))
    struct.pack_into("<Q", blob, 0x280 + 32, authenticated(0x340))
    struct.pack_into("<IIiii", blob, 0x340, 0x8000000C, 1,
                     0x380 - 0x348, 0x3C0 - 0x34C, 0x420 - 0x350)
    struct.pack_into("<Q", blob, 0x380, authenticated(0x3B0))
    blob[0x3A0:0x3A7] = b"Sample\0"
    blob[0x3B0:0x3B6] = b"tick:\0"
    blob[0x3C0:0x3C8] = b"v16@0:8\0"
    return bytes(blob)


class ObjCIndexTest(unittest.TestCase):
    def test_authenticated_class_pointer_and_relative_method(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture"
            path.write_bytes(fixture_image())
            index = index_objc(path)
        self.assertEqual(index["class_count"], 1)
        item = index["classes"][0]
        self.assertEqual(item["name"], "Sample")
        self.assertEqual(item["instance_methods"], [{
            "selector": "tick:", "types": "v16@0:8", "imp": "0x100000420",
        }])


if __name__ == "__main__":
    unittest.main()
