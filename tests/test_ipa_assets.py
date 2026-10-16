import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from copyapp.ipa import analyze_ipa, write_ipa_report
from copyapp.verify import verify_case


class IPAAssetCatalogTest(unittest.TestCase):
    def test_catalog_names_bind_to_source_ipa_and_variants(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ipa = root / "Target.ipa"
            with ZipFile(ipa, "w") as archive:
                archive.writestr("Payload/Target.app/Info.plist", plistlib.dumps({
                    "CFBundleIdentifier": "example.target", "CFBundleExecutable": "Target",
                }))
                archive.writestr("Payload/Target.app/Target", b"ordinary-file")
                archive.writestr("Payload/Target.app/Assets.car", b"catalog-bytes")

            rows = [{"SchemaVersion": 2},
                    {"Name": "Login/lock", "AssetType": "Image", "Scale": 1,
                     "PixelWidth": 28, "PixelHeight": 28},
                    {"Name": "Login/lock", "AssetType": "Vector", "Scale": 2,
                     "PixelWidth": 56, "PixelHeight": 56},
                    {"Name": "Auth/google", "AssetType": "Image", "RenditionName": "google.svg"}]

            def fake_assetutil(command, *, stdout, stderr, timeout, check):
                self.assertEqual(command[:3], ["xcrun", "assetutil", "--info"])
                self.assertEqual(timeout, 45)
                stdout.write(json.dumps(rows).encode())
                return SimpleNamespace(returncode=0)

            with patch("copyapp.ipa.shutil.which", return_value="/usr/bin/xcrun"), \
                    patch("copyapp.ipa.subprocess.run", side_effect=fake_assetutil):
                index = analyze_ipa(ipa)
            catalog = index["asset_catalogs"][0]
            self.assertEqual(catalog["status"], "indexed")
            self.assertEqual(catalog["asset_count"], 2)
            self.assertEqual(catalog["assets"][1]["name"], "Login/lock")
            self.assertEqual(catalog["assets"][1]["pixel_sizes"], [[28, 28], [56, 56]])
            self.assertEqual(catalog["assets"][1]["variant_count"], 2)

            output = root / "index"
            write_ipa_report(index, output)
            self.assertTrue(verify_case(output))
            ipa.write_bytes(ipa.read_bytes() + b"changed")
            self.assertFalse(verify_case(output))


if __name__ == "__main__":
    unittest.main()
