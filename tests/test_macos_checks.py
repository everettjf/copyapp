import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from copyapp.macos.checks import captures, has_start_assertion, measure
from copyapp.macos.ui import check_ui, check_window
from macos_fakes import UI, WINDOW


class MacComparisonTests(unittest.TestCase):
    def test_metrics_count_only_predeclared_unmasked_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, rebuilt = root / "original.png", root / "rebuilt.png"
            Image.new("RGB", (4, 4), "black").save(original)
            image = Image.new("RGB", (4, 4), "black")
            image.putpixel((0, 0), (255, 0, 0)); image.save(rebuilt)
            result = measure(original, rebuilt, [])
            self.assertEqual(result["unmasked_pixels"], 16)
            self.assertEqual(result["changed_pixel_fraction"], 0.0625)
            self.assertAlmostEqual(result["mean_absolute_error"], 1 / 48, places=7)
            masked = measure(original, rebuilt, [[0, 0, 1, 1]])
            self.assertEqual(masked["unmasked_pixels"], 15)
            self.assertEqual(masked["mean_absolute_error"], 0)
            self.assertEqual(masked["changed_pixel_fraction"], 0)
            with self.assertRaises(ValueError):
                measure(original, rebuilt, [[0, 0, 4, 4]])
            with self.assertRaises(ValueError):
                measure(original, rebuilt, [[3, 3, 2, 2]])
            Image.new("RGB", (3, 3), "black").save(rebuilt)
            mismatch = measure(original, rebuilt, [])
            self.assertFalse(mismatch["dimensions_match"])
            self.assertIsNone(mismatch["mean_absolute_error"])

    def test_initial_state_guard_and_capture_inventory(self):
        launch, edit = {"action": "launch"}, {"action": "type", "text": "hello"}
        assertion = {"action": "expect_text", "text": ""}
        script = {"steps": [launch, assertion, edit, {"action": "expect_file"}, {"action": "quit"}, {"action": "expect_stopped"}]}
        self.assertTrue(has_start_assertion(script))
        self.assertFalse(has_start_assertion({"steps": [launch, edit, assertion]}))
        self.assertFalse(has_start_assertion({"steps": [launch, dict(assertion, match="contains"), edit]}))
        self.assertEqual(captures(script), ["steps/01/after", "steps/02/before", "steps/03/before", "steps/03/after", "steps/05/before"])

    def test_ui_settings_and_initial_window_are_measured_guards(self):
        check_ui(UI, {"response": {"result": {"ui_environment": UI}}})
        changed = copy.deepcopy(UI)
        changed["appearance"] = "dark"
        with self.assertRaises(ValueError):
            check_ui(UI, {"response": {"result": {"ui_environment": changed}}})
        tree = {"source_channel": "ax", "truncated": False, "focused_window_node": 0,
                "nodes": [{"role": "AXWindow", "frame": WINDOW}]}
        check_window(tree, WINDOW)
        with self.assertRaises(ValueError):
            check_window(tree, dict(WINDOW, x=2))
        with self.assertRaises(ValueError):
            check_window(dict(tree, truncated=True), WINDOW)


if __name__ == "__main__":
    unittest.main()
