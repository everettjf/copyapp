import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from copyapp.verify import verify_case


def digest(data):
    return hashlib.sha256(data).hexdigest()


class VerifyCaseTest(unittest.TestCase):
    def test_acquisition_detects_changed_bundle_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "bundle" / "Example.app"
            app.mkdir(parents=True)
            (app / "binary").write_bytes(b"original")
            (root / "bundle-snapshot.ipa").write_bytes(b"snapshot")
            (root / "acquisition.json").write_text(json.dumps({
                "remote_bundle_path": "/Applications/Example.app",
                "files": [{"relative": "binary", "sha256": digest(b"original")}],
                "snapshot_sha256": digest(b"snapshot"),
            }))
            self.assertTrue(verify_case(root))
            (app / "binary").write_bytes(b"changed")
            self.assertFalse(verify_case(root))

    def test_acquisition_refuses_evidence_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bundle-snapshot.ipa").write_bytes(b"snapshot")
            (root / "acquisition.json").write_text(json.dumps({
                "remote_bundle_path": "/Applications/Example.app",
                "files": [{"relative": "../../outside", "sha256": digest(b"x")}],
                "snapshot_sha256": digest(b"snapshot"),
            }))
            self.assertFalse(verify_case(root))


if __name__ == "__main__":
    unittest.main()
