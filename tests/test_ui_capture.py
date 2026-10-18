import io
import unittest
from unittest.mock import patch

from PIL import Image

from copyapp.ui_capture import capture_stable, frame_health


def png(color):
    image = Image.new("RGB", (40, 40), color)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class StableCaptureTest(unittest.TestCase):
    def test_frame_health_rejects_black_app_area_but_accepts_dark_ui(self):
        self.assertTrue(frame_health(png("black"))["near_uniform_black"])
        self.assertFalse(frame_health(png("#303030"))["near_uniform_black"])
        image = Image.new("RGB", (100, 100), "black")
        for x in range(25, 75):
            for y in range(25, 75):
                image.putpixel((x, y), (255, 255, 255))
        out = io.BytesIO()
        image.save(out, format="JPEG")
        self.assertFalse(frame_health(out.getvalue())["near_uniform_black"])
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
