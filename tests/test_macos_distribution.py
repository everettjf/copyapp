import json
import os
import platform
import plistlib
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from copyapp.macos.case import canonical, digest
from copyapp.macos.distribution import attached, import_app, mount_image
from copyapp.verify import verify_case
from test_macos import make_app


def zip_tree(source, archive):
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source).as_posix()
            if path.is_symlink():
                info = zipfile.ZipInfo(relative)
                info.create_system = 3
                info.external_attr = path.lstat().st_mode << 16
                zipped.writestr(info, os.readlink(path).encode())
            else:
                zipped.write(path, relative + ("/" if path.is_dir() else ""))


class MacDistributionTests(unittest.TestCase):
    def test_unicode_names_and_internal_links_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input"
            app = make_app(source)
            app = app.rename(source / "Café.app")
            (app / "Contents/Resources").mkdir()
            (app / "Contents/Resources/résumé.txt").write_text("selected resource")
            (app / "Contents/resource-link").symlink_to("Resources/résumé.txt")
            archive = root / "input.zip"
            zip_tree(source, archive)
            case = import_app(archive, root / "imported")
            self.assertTrue(verify_case(case))
            self.assertEqual((case / "package/app/Café.app/Contents/Resources/résumé.txt").read_text(), "selected resource")

    def test_zip_selected_package_is_bound_to_archived_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input"
            app = make_app(source)
            (app / "Contents/alias").symlink_to("Info.plist")
            archive = root / "input.zip"
            zip_tree(source, archive)
            case = import_app(archive, root / "imported")
            self.assertTrue(verify_case(case))
            facts = json.loads((case / "import.json").read_text())
            self.assertFalse(facts["launched"])
            self.assertFalse(facts["installed"])
            archive.write_bytes(b"later upstream change")
            self.assertTrue(verify_case(case))
            # Refreshing both the artifact hash and the claimed archive hash
            # still cannot conceal an App that differs inside the ZIP.
            (app / "Contents/MacOS/Example").write_bytes(b"different executable")
            zip_tree(source, case / "source.zip")
            facts["source_sha256"] = digest(case / "source.zip")
            (case / "import.json").write_bytes(canonical(facts))
            manifest = json.loads((case / "manifest.json").read_text())
            for record in manifest["evidence"]:
                if record["path"] in {"source.zip", "import.json"}:
                    record["sha256"] = digest(case / record["path"])
            (case / "manifest.json").write_bytes(canonical(manifest))
            self.assertFalse(verify_case(case))

    def test_multiple_apps_require_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input"
            app = make_app(source)
            shutil.copytree(app, source / "Other.app")
            archive = root / "input.zip"
            zip_tree(source, archive)
            with self.assertRaisesRegex(ValueError, "app-relative"):
                import_app(archive, root / "ambiguous")
            self.assertFalse(verify_case(root / "ambiguous"))
            accepted = import_app(archive, root / "selected", "Other.app")
            self.assertTrue(verify_case(accepted))

    def test_zip_traversal_collisions_and_link_ancestors_are_rejected(self):
        variants = [
            [("../escape", None, b"bad")],
            [("/absolute", None, b"bad")],
            [("Example.app/file", None, b"a"), ("example.app/other", None, b"b")],
            [("Café.app/file", None, b"a"), ("Cafe\u0301.app/other", None, b"b")],
            [("duplicate", None, b"a"), ("duplicate", None, b"b")],
            [("link", stat.S_IFLNK | 0o777, b"/outside")],
            [("link", stat.S_IFLNK | 0o777, b"target"), ("link/file", None, b"bad")],
            [("special", stat.S_IFIFO | 0o600, b"")],
        ]
        for members in variants:
            with self.subTest(members=members), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = root / "input.zip"
                with zipfile.ZipFile(archive, "w") as zipped:
                    for name, mode, data in members:
                        info = zipfile.ZipInfo(name)
                        if mode is not None:
                            info.create_system = 3; info.external_attr = mode << 16
                        zipped.writestr(info, data)
                with self.assertRaises(ValueError):
                    import_app(archive, root / "rejected")
                self.assertFalse((root.parent / "escape").exists())

    def test_encryption_or_license_policy_refuses_before_attach(self):
        for properties in ({"Encrypted": True, "Software License Agreement": False},
                           {"Encrypted": False, "Software License Agreement": True}):
            with self.subTest(properties=properties), tempfile.TemporaryDirectory() as folder:
                logs = []
                with patch("copyapp.macos.distribution.platform.system", return_value="Darwin"), \
                     patch("copyapp.macos.distribution.platform.mac_ver", return_value=("27.0", (), "")), \
                     patch("copyapp.macos.distribution.attached", return_value=[]), \
                     patch("copyapp.macos.distribution.native", return_value=plistlib.dumps({"Properties": properties})) as command:
                    with self.assertRaises(ValueError):
                        with mount_image(Path(folder) / "input.dmg", Path(folder) / "mount", logs):
                            self.fail("must not attach a password/license-interactive image")
                    self.assertEqual(command.call_count, 1)


@unittest.skipUnless(platform.system() == "Darwin" and int((platform.mac_ver()[0] or "0").split(".")[0]) >= 27,
                     "real read-only DMG import currently uses the macOS 27 diskutil image interface")
class NativeDMGTests(unittest.TestCase):
    def test_real_readonly_import_reverification_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source = root / "input"
            make_app(source)
            (source / "Applications").symlink_to("/Applications")
            image = root / "input.dmg"
            subprocess.run(["/usr/sbin/diskutil", "image", "create", "from", "--format", "UDZO", "--volumeName",
                            "CopyAppTest", str(source), str(image)], capture_output=True, check=True, timeout=60)
            original_hash = digest(image)
            case = import_app(image, root / "imported")
            self.assertTrue(verify_case(case))
            self.assertEqual(original_hash, digest(image))
            self.assertFalse(attached(case / "source.dmg"))
            self.assertFalse(os.path.ismount(case / "mount"))
            logs = json.loads((case / "native-log.json").read_text())
            self.assertTrue(any("noexec" in row.get("mount_policy", "") for row in logs))
            (case / "package/app/Example.app/Contents/MacOS/Example").write_bytes(b"changed")
            self.assertFalse(verify_case(case))


if __name__ == "__main__":
    unittest.main()
