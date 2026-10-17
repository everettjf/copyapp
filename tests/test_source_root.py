import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.source_root import source_root


class SourceRootTest(unittest.TestCase):
    def test_explicit_checkout_for_wheel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts/bootstrap-macos.sh").write_text("#!/bin/sh\n")
            (root / "pyproject.toml").write_text("[project]\nname = 'copyapp'\n")
            with patch.dict(os.environ, {"COPYAPP_SOURCE_ROOT": str(root)}):
                self.assertEqual(source_root(), root.resolve())

    def test_invalid_explicit_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"COPYAPP_SOURCE_ROOT": directory}):
                with self.assertRaisesRegex(ValueError, "source checkout"):
                    source_root()

    def test_editable_install_uses_package_parent(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(source_root(), Path(__file__).resolve().parents[1])
