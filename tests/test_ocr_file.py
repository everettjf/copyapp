import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.ocr_file import ocr_file, verify_ocr_source
from copyapp.verify import sha256_file


class SavedOCRTest(unittest.TestCase):
    def test_cropped_result_pins_original_image_and_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "screen.jpg"
            Image.new("RGB", (40, 60), "black").save(screenshot)
            destination = root / "ocr.json"
            with patch("copyapp.ocr_file.recognize_screenshot",
                       return_value={"engine": "macos-vision", "texts": [{"text": "15"}]}) as recognize:
                ocr_file(screenshot, destination, [5, 10, 30, 40])
            record = json.loads(destination.read_text())
            self.assertEqual(record["source_sha256"], sha256_file(screenshot))
            self.assertEqual(record["result"]["texts"][0]["text"], "15")
            self.assertEqual(record["roi"], [5, 10, 30, 40])
            self.assertTrue(recognize.call_args.args[0].startswith(b"\x89PNG"))
            self.assertTrue(verify_ocr_source(record, screenshot))
            record["ocr_input_sha256"] = "0" * 64
            self.assertFalse(verify_ocr_source(record, screenshot))
            with self.assertRaises(FileExistsError):
                ocr_file(screenshot, destination)

    def test_rejects_roi_outside_image_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "screen.jpg"
            Image.new("RGB", (40, 60), "black").save(screenshot)
            destination = root / "ocr.json"
            with self.assertRaisesRegex(ValueError, "ROI"):
                ocr_file(screenshot, destination, [0, 0, 41, 20])
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
