import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from copyapp.ssh_acquire import _write_snapshot


class SnapshotTest(unittest.TestCase):
    def test_snapshot_hash_ignores_local_file_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "Example.app"
            bundle.mkdir()
            source = bundle / "sample.bin"
            source.write_bytes(b"unchanged app content")
            files = [{"relative": "sample.bin"}]
            first, second = root / "one.ipa", root / "two.ipa"
            os.utime(source, (1000000000, 1000000000))
            _write_snapshot(bundle, "Example.app", files, first)
            os.utime(source, (1500000000, 1500000000))
            _write_snapshot(bundle, "Example.app", files, second)
            self.assertEqual(hashlib.sha256(first.read_bytes()).hexdigest(),
                             hashlib.sha256(second.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
