"""Recognize an iOS MCP screenshot in a short-lived macOS Vision process."""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict


OCR_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ocr-image.swift"


def recognize_screenshot(image: bytes) -> Dict[str, Any]:
    if not image:
        raise ValueError("empty screenshot")
    with tempfile.TemporaryDirectory(prefix="copyapp-host-ocr-") as directory:
        path = Path(directory) / "screen.jpg"
        path.write_bytes(image)
        try:
            result = subprocess.run(
                ["xcrun", "swift", str(OCR_SCRIPT), str(path)],
                capture_output=True, timeout=90, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("macOS Vision OCR timed out") from exc
    if result.returncode:
        raise RuntimeError("macOS Vision OCR failed: " + result.stderr[:600].decode(errors="replace"))
    if len(result.stdout) > 2 * 1024 * 1024:
        raise RuntimeError("macOS Vision OCR result exceeds 2 MiB")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("engine") != "macos-vision" or not isinstance(value.get("texts"), list):
        raise RuntimeError("macOS Vision OCR returned an unexpected result")
    return value
