import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.verify import sha256_file, verify_case


class InstallationVerificationTest(unittest.TestCase):
    def test_rechecks_ipa_bytes_and_recorded_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ipa = root / "app.ipa"
            ipa.write_bytes(b"saved package")
            digest = sha256_file(ipa)
            case = root / "install"
            case.mkdir()
            record = {"schema_version": 1, "status": "installed",
                      "device_id": "00008020-000D650434B8003A",
                      "ipa": str(ipa), "ipa_sha256": digest,
                      "staged_sha256": digest, "helper_exit_code": 0,
                      "bundle_id": "com.copyapp.example", "version": "1.0", "build": "1"}
            (case / "install.json").write_text(json.dumps(record))
            package = {"bundle_id": "com.copyapp.example", "version": "1.0",
                       "build": "1"}
            with patch("copyapp.ipa.analyze_ipa", return_value=package):
                self.assertTrue(verify_case(case))
                ipa.write_bytes(b"changed package")
                self.assertFalse(verify_case(case))


if __name__ == "__main__":
    unittest.main()
