import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from copyapp.macos.build import generated_directories, recipe_for, run_command


class MacBuildInputTests(unittest.TestCase):
    def test_xcode_metadata_does_not_allow_source_rewrites_or_new_inputs(self):
        recipe = recipe_for(xcode_project="Editor.xcodeproj", scheme="Editor")
        before = [{"path": "Main.swift", "kind": "file", "mode": 420, "sha256": "a" * 64, "size": 1}]
        directory = {"path": "Editor.xcodeproj/project.xcworkspace", "kind": "directory", "mode": 493}
        self.assertEqual(generated_directories(before, before + [directory], recipe), [directory])
        for added in ({"path": "New.swift", "kind": "file"}, {"path": "arbitrary", "kind": "directory"}):
            with self.assertRaises(ValueError):
                generated_directories(before, before + [added], recipe)
        with self.assertRaises(ValueError):
            generated_directories(before, [dict(before[0], sha256="b" * 64)], recipe)

    def test_recipe_separates_xcode_and_swift_inputs(self):
        swift = recipe_for(swift_sources=["Main.swift"], info_plist="Info.plist")
        self.assertEqual(swift["mode"], "swift")
        self.assertEqual(recipe_for(xcode_project="Editor.xcodeproj", scheme="Editor")["mode"], "xcode")
        invalid = [
            {}, {"swift_sources": ["../Main.swift"], "info_plist": "Info.plist"},
            {"swift_sources": ["Main.swift", "Main.swift"], "info_plist": "Info.plist"},
            {"swift_sources": ["Main.swift"], "info_plist": "Info.plist", "deployment_target": "14;anything"},
            {"swift_sources": ["Main.swift"], "info_plist": "Info.plist", "xcode_project": "Editor.xcodeproj", "scheme": "Editor"},
            {"xcode_project": "Editor.xcodeproj"},
            {"xcode_project": "../Editor.xcodeproj", "scheme": "Editor"},
            {"xcode_project": "Editor.xcodeproj", "scheme": "Editor", "resources": "Resources"},
            {"xcode_project": "Editor.xcodeproj", "scheme": "Editor", "deployment_target": "15.0"},
            {"swift_sources": ["Main.swift"], "info_plist": "Info.plist", "configuration": "UnimplementedConfiguration"},
        ]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                recipe_for(**args)

    def test_failed_build_keeps_output_and_return_code(self):
        with tempfile.TemporaryDirectory() as folder:
            logs = []
            with self.assertRaises(RuntimeError):
                run_command([sys.executable, "-c", "import sys; print('compiler diagnostic', file=sys.stderr); sys.exit(7)"],
                            Path(folder), logs, 5)
            self.assertEqual(logs[0]["returncode"], 7)
            self.assertIn("compiler diagnostic", logs[0]["stderr"])

    @unittest.skipUnless(os.name == "posix", "owned process-group cleanup uses POSIX signals")
    def test_build_timeout_keeps_a_terminal_failure_log(self):
        with tempfile.TemporaryDirectory() as folder:
            logs = []
            with self.assertRaises(subprocess.TimeoutExpired):
                run_command([sys.executable, "-c", "import time; time.sleep(30)"], Path(folder), logs, 0.1)
            self.assertIs(logs[0]["timed_out"], True)
            self.assertIsNotNone(logs[0]["returncode"])


if __name__ == "__main__":
    unittest.main()
