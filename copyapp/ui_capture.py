"""Select a settled UI screenshot before OCR or visual interpretation."""

import io
import time
from typing import Callable, Dict, Tuple

from PIL import Image, ImageChops, ImageStat


def _thumbnail(image: bytes) -> Image.Image:
    with Image.open(io.BytesIO(image)) as source:
        return source.convert("L").resize((48, 48), Image.Resampling.BILINEAR)


def capture_stable(capture: Callable[[], bytes], samples: int = 5,
                   interval: float = 0.35, threshold: float = 0.02) -> Tuple[bytes, Dict]:
    """Return the newest frame once two successive downscaled frames are similar.

    Dynamic areas may remain in the image. The stability flag describes only
    visual change during this short window, not whether the app is ready.
    """
    if samples < 2 or interval < 0 or not 0 <= threshold <= 1:
        raise ValueError("invalid capture stability settings")
    previous = capture()
    previous_thumb = _thumbnail(previous)
    distance = None
    for attempt in range(2, samples + 1):
        time.sleep(interval)
        current = capture()
        current_thumb = _thumbnail(current)
        distance = ImageStat.Stat(ImageChops.difference(previous_thumb, current_thumb)).mean[0] / 255
        if distance <= threshold:
            return current, {"stable": True, "samples": attempt,
                             "mean_pixel_change": round(distance, 5), "threshold": threshold}
        previous, previous_thumb = current, current_thumb
    return previous, {"stable": False, "samples": samples,
                      "mean_pixel_change": round(distance, 5), "threshold": threshold}
