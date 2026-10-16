#!/usr/bin/env python3
"""Compare the verified 45-degree Compass bearing-sector experiments."""

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image

from copyapp.verify import sha256_file, verify_case


ROI = (110, 190, 210, 270)


def red_mask(image: Image.Image) -> set:
    pixels = image.convert("RGB")
    return {(x, y) for y in range(ROI[1], ROI[3]) for x in range(ROI[0], ROI[2])
            if (lambda color: color[0] > 150 and color[0] > color[1] * 1.5
                and color[0] > color[2] * 1.5)(pixels.getpixel((x, y)))}


def dominant_red(image: Image.Image, mask: set) -> tuple:
    pixels = image.convert("RGB")
    counts = Counter(tuple(value // 10 * 10 for value in pixels.getpixel(point)) for point in mask)
    return counts.most_common(1)[0][0]


def load_case(root: Path, bundle: str) -> dict:
    if not verify_case(root):
        raise ValueError(f"source evidence hash mismatch: {root}")
    data = json.loads((root / "experiment.json").read_text(encoding="utf-8"))
    if (data.get("status") != "complete" or data.get("bundle_id") != bundle or
            data.get("scenario_id") != "compass-locked-bearing-motion-offset"):
        raise ValueError(f"wrong or incomplete Compass offset case: {root}")
    stages = {item["label"]: item for item in data["stages"]}
    if not all(label in stages for label in ("locked", "offset", "restored")):
        raise ValueError(f"missing required stages: {root}")
    return data


def compare(original_root: Path, clone_root: Path, output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    original_root = original_root.resolve(strict=True)
    clone_root = clone_root.resolve(strict=True)
    original = load_case(original_root, "com.apple.compass")
    clone = load_case(clone_root, "dev.copyapp.compass")
    if (original_root == clone_root or
            original["device_id_sha256_prefix"] != clone["device_id_sha256_prefix"] or
            original["offset_degrees"] != clone["offset_degrees"] or
            original["ui_backend"] != clone["ui_backend"]):
        raise ValueError("experiments must use different apps, the same device, offset and UI backend")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(original_root, output / "original")
    shutil.copytree(clone_root, output / "clone")
    a = Image.open(output / "original" / "offset.jpg").convert("RGB")
    b = Image.open(output / "clone" / "offset.jpg").convert("RGB")
    if a.size != (414, 896) or b.size != a.size:
        raise ValueError("unexpected or mismatched screen dimensions")
    mask_a, mask_b = red_mask(a), red_mask(b)
    intersection = len(mask_a & mask_b)
    union = len(mask_a | mask_b)
    iou = intersection / union if union else 0.0
    color_a = dominant_red(a, mask_a)
    color_b = dominant_red(b, mask_b)
    targeted_passed = iou >= 0.90 and color_a == color_b

    side_by_side = Image.new("RGB", (a.width * 2, a.height))
    side_by_side.paste(a, (0, 0))
    side_by_side.paste(b, (a.width, 0))
    side_by_side.save(output / "offset-side-by-side.png")
    mask_image = Image.new("RGB", (ROI[2] - ROI[0], ROI[3] - ROI[1]), "black")
    for x, y in mask_a | mask_b:
        color = (0, 190, 0) if (x, y) in mask_a & mask_b else (
            (255, 80, 0) if (x, y) in mask_a else (60, 90, 255))
        mask_image.putpixel((x - ROI[0], y - ROI[1]), color)
    mask_image.resize((600, 480), Image.Resampling.NEAREST).save(output / "sector-mask-overlay.png")
    values = {
        "schema_version": 1,
        "device_id_sha256_prefix": original["device_id_sha256_prefix"],
        "angle_degrees": original["offset_degrees"],
        "roi": ROI,
        "original_red_pixels": len(mask_a),
        "clone_red_pixels": len(mask_b),
        "overlap_pixels": intersection,
        "union_pixels": union,
        "mask_iou": round(iou, 5),
        "original_dominant_red_rgb_bin": color_a,
        "clone_dominant_red_rgb_bin": color_b,
        "targeted_sector_check_passed": targeted_passed,
        "original_hook_mode": original["hook_mode"],
        "clone_hook_mode": clone["hook_mode"],
    }
    (output / "metrics.json").write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    report = f"""# Compass 锁定方位偏差扇区真机对照

同一台 iPhone XR、同一 iOS MCP 后端，各施加 {values['angle_degrees']:g}° 可撤销偏移；两份源案例均完成并通过哈希校验。原版在 `CompassBearingView` 的 `_angle` 上改变视图状态并执行 `updateLayer`，复刻版在 `CMDeviceMotion.heading` 读取处改变返回值。两处注入点不同，因此整屏方位数字和刻度旋转不应直接比较。

- [整屏并排](offset-side-by-side.png)；[扇区掩码叠图](sector-mask-overlay.png)：绿色为重叠，橙色仅原版，蓝色仅复刻版。
- 扇区 ROI `{ROI}`：原版红色像素 {len(mask_a)}，复刻版 {len(mask_b)}；交并比 **{iou:.3f}**。
- 量化后的主导红色 RGB 桶：原版 `{color_a}`，复刻版 `{color_b}`。
- 原版与复刻版的锁定、偏移、恢复截图及运行时探针，分别保存于 [original](original/experiment.json) 和 [clone](clone/experiment.json)。

这个对照只验证 XR 上一次 45° 偏差时的扇区区域和颜色。它不证明真实转动时的动画、所有角度、其他机型或整屏复刻一致。
"""
    (output / "report.md").write_text(report, encoding="utf-8")
    files = sorted(path for path in output.rglob("*")
                   if path.is_file() and path != output / "manifest.json")
    manifest = {"schema_version": 1,
                "evidence": [{"path": str(path.relative_to(output)), "sha256": sha256_file(path)}
                             for path in files]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    return output / "report.md"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--clone", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = compare(args.original, args.clone, args.out)
    print(result)
    if not json.loads((args.out / "metrics.json").read_text())["targeted_sector_check_passed"]:
        raise SystemExit(1)
