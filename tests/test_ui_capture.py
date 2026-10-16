import io
import unittest
from unittest.mock import patch

from PIL import Image

from copyapp.ui_capture import capture_stable


def png(color):
    image = Image.new("RGB", (40, 40), color)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class StableCaptureTest(unittest.TestCase):
    def test_minimum_samples_skips_static_intermediate_frame(self):
        frames = iter([png("white"), png("white"), png("white"),
                       png("black"), png("black")])
        with patch("copyapp.ui_capture.time.sleep"):
            result, info = capture_stable(lambda: next(frames), samples=5,
                                          interval=0.01, minimum_samples=5)
        self.assertEqual(result, png("black"))
        self.assertEqual(info["samples"], 5)

    def test_waits_until_transition_ends(self):
        frames = iter([png("white"), png("black"), png("black")])
        with patch("copyapp.ui_capture.time.sleep"):
            result, info = capture_stable(lambda: next(frames), interval=0.01)
        self.assertEqual(result, png("black"))
        self.assertTrue(info["stable"])
        self.assertEqual(info["samples"], 3)

    def test_reports_unsettled_window(self):
        frames = iter([png("white"), png("black"), png("white")])
        with patch("copyapp.ui_capture.time.sleep"):
            _result, info = capture_stable(lambda: next(frames), samples=3, interval=0.01)
        self.assertFalse(info["stable"])
        self.assertEqual(info["samples"], 3)
