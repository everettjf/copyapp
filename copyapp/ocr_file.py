"""Hash-pinned macOS Vision OCR for a saved screenshot or a selected region."""

import io
import hashlib
import json
from pathlib import Path
from typing import List, Optional

from PIL import Image

from copyapp.host_ocr import recognize_screenshot
from copyapp.verify import sha256_file


def ocr_file(source: Path, output: Path, roi: Optional[List[int]] = None) -> Path:
    source = source.resolve(strict=True)
    if output.exists():
        raise FileExistsError(output)
    if source.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("screenshot exceeds 20 MiB")
    data = source.read_bytes()
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if roi is not None:
        if (len(roi) != 4 or any(type(value) is not int for value in roi) or
                not 0 <= roi[0] < roi[2] <= width or
                not 0 <= roi[1] < roi[3] <= height):
            raise ValueError("ROI must fit screenshot pixel bounds")
        image = image.crop(tuple(roi))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        ocr_input = stream.getvalue()
    else:
        ocr_input = data
    result = recognize_screenshot(ocr_input)
    record = {"schema_version": 1, "kind": "saved_screenshot_ocr",
              "source_path": str(source), "source_sha256": sha256_file(source),
              "source_width": width, "source_height": height,
              "roi": roi, "ocr_input_sha256": hashlib.sha256(ocr_input).hexdigest(),
              "result": result}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def verify_ocr_source(record: dict, source: Path) -> bool:
    if (record.get("schema_version") != 1 or record.get("kind") != "saved_screenshot_ocr" or
            record.get("source_sha256") != sha256_file(source) or
            not isinstance(record.get("result"), dict) or
            record["result"].get("engine") != "macos-vision" or
            not isinstance(record["result"].get("texts"), list)):
        return False
    data = source.read_bytes()
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if (record.get("source_width"), record.get("source_height")) != (width, height):
        return False
    roi = record.get("roi")
    if roi is not None:
        if (not isinstance(roi, list) or len(roi) != 4 or
                any(type(value) is not int for value in roi) or
                not 0 <= roi[0] < roi[2] <= width or
                not 0 <= roi[1] < roi[3] <= height):
            return False
        image = image.crop(tuple(roi))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        data = stream.getvalue()
    return record.get("ocr_input_sha256") == hashlib.sha256(data).hexdigest()
