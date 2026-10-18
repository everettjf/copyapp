"""Select a settled UI screenshot before OCR or visual interpretation."""

import io
import time
from typing import Callable, Dict, Tuple

from PIL import Image, ImageChops, ImageStat


def _thumbnail(image: bytes) -> Image.Image:
    with Image.open(io.BytesIO(image)) as source:
        return source.convert("L").resize((48, 48), Image.Resampling.BILINEAR)


def frame_health(image: bytes) -> Dict:
    """Flag an almost uniform black app area, excluding system chrome.

    This is deliberately narrow: dark themed screens with text and controls
    retain enough variance to pass. A flagged frame is diagnostic evidence,
    never a successful screenshot for a UI playbook.
    """
    with Image.open(io.BytesIO(image)) as source:
        gray = source.convert("L")
        width, height = gray.size
        if width < 20 or height < 20:
            raise ValueError("screenshot is too small to assess")
        app_area = gray.crop((int(width * .2), int(height * .2),
                              max(int(width * .9), 1), max(int(height * .9), 1)))
        stats = ImageStat.Stat(app_area)
    mean = round(stats.mean[0], 2)
    deviation = round(stats.stddev[0], 2)
    return {"mean_luma": mean, "stddev_luma": deviation,
            "near_uniform_black": mean <= 4 and deviation <= 3,
            "region": "central_70_percent"}


def capture_stable(capture: Callable[[], bytes], samples: int = 5,
                   interval: float = 0.35, threshold: float = 0.02,
                   minimum_samples: int = 2) -> Tuple[bytes, Dict]:
    """Return the newest frame once two successive downscaled frames are similar.

    Dynamic areas may remain in the image. The stability flag describes only
    visual change during this short window, not whether the app is ready.
    """
    if samples < 2 or not 2 <= minimum_samples <= samples or interval < 0 or not 0 <= threshold <= 1:
        raise ValueError("invalid capture stability settings")
    previous = capture()
    previous_thumb = _thumbnail(previous)
    distance = None
    for attempt in range(2, samples + 1):
        time.sleep(interval)
        current = capture()
        current_thumb = _thumbnail(current)
        distance = ImageStat.Stat(ImageChops.difference(previous_thumb, current_thumb)).mean[0] / 255
        if attempt >= minimum_samples and distance <= threshold:
            return current, {"stable": True, "samples": attempt,
                             "mean_pixel_change": round(distance, 5), "threshold": threshold}
        previous, previous_thumb = current, current_thumb
    return previous, {"stable": False, "samples": samples,
                      "mean_pixel_change": round(distance, 5), "threshold": threshold}
