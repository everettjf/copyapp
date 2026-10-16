#!/usr/bin/env python3
"""Record the XR Compass no-location visual comparison with hashed inputs."""

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

from copyapp.verify import sha256_file


def disk_rows(image: Image.Image) -> tuple:
    pixels = image.convert("RGB")
    rows = [y for y in range(290, 420)
            if (lambda color: max(color) - min(color) < 8 and
                23 <= sum(color) / 3 <= 58)(pixels.getpixel((185, y)))]
    return min(rows), max(rows)


def heading_rows(image: Image.Image) -> tuple:
    pixels = image.convert("RGB")
    rows = [y for y in range(600, 780)
            if sum(1 for x in range(65, 345) if min(pixels.getpixel((x, y))) > 155) > 10]
    return min(rows), max(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = args.out
    if output.exists() and any(output.iterdir()):
        parser.error("output directory is not empty")
    sources = {
        "original-denied.jpg": "compass-original-location-denied-unlocked-20261015.jpg",
        "clone-before.jpg": "compass-clone-location-denied-20261015.jpg",
        "clone-after.jpg": "compass-clone-location-denied-layout-fixed-20261015.jpg",
        "original-never.jpg": "settings-original-compass-permission-never-20261015.jpg",
        "original-restored.jpg": "settings-original-compass-permission-restored-20261015.jpg",
        "clone-never.jpg": "settings-copy-compass-layout-permission-never-20261015.jpg",
        "clone-restored.jpg": "settings-copy-compass-layout-permission-restored-20261015.jpg",
    }
    output.mkdir(parents=True, exist_ok=True)
    for destination, source in sources.items():
        shutil.copyfile(Path("cases") / source, output / destination)
    images = {name: Image.open(output / name).convert("RGB")
              for name in ("original-denied.jpg", "clone-before.jpg", "clone-after.jpg")}
    if any(image.size != (414, 896) for image in images.values()):
        raise ValueError("unexpected screenshot dimensions")
    metrics = {name: {"disk_rows": disk_rows(image), "heading_rows": heading_rows(image)}
               for name, image in images.items()}
    target = metrics["original-denied.jpg"]
    after = metrics["clone-after.jpg"]
    metrics["targeted_vertical_check_passed"] = (
        abs(target["disk_rows"][0] - after["disk_rows"][0]) <= 2 and
        abs(target["heading_rows"][0] - after["heading_rows"][0]) <= 2
    )
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    side = Image.new("RGB", (414 * 3, 896))
    for index, image in enumerate(images.values()):
        side.paste(image, (414 * index, 0))
    side.save(output / "side-by-side.png")
    (output / "report.md").write_text(
        "# Compass 拒绝定位状态的 XR 对照\n\n"
        "同一台 XR 上，临时将两款 App 的定位权限分别设为 Never，采集界面，然后均恢复为 While Using the App。"
        "设置前后的截图保存在本案例；两款 App 的原有精确定位开关保持开启。\n\n"
        "[原版、修复前复刻版、修复后复刻版并排截图](side-by-side.png)。"
        "原版与修复版均隐藏了坐标、地名和海拔。图像上灰色中心盘的纵向像素范围"
        f"为 {target['disk_rows']} 与 {after['disk_rows']}，方位大字为"
        f" {target['heading_rows']} 与 {after['heading_rows']}；"
        f"纵向位置检查：**{'通过' if metrics['targeted_vertical_check_passed'] else '未通过'}**。"
        "修复前的对应数值见 [metrics.json](metrics.json)。\n\n"
        "像素测量只比较 XR 当前尺寸的纵向布局；字体形状、刻度细节和动态过渡仍有差异。"
        "截图与 Settings 状态按操作顺序采集，但截图本身没有独立的 Bundle ID 身份字段。\n",
        encoding="utf-8",
    )
    files = sorted(path for path in output.iterdir() if path.is_file())
    (output / "manifest.json").write_text(json.dumps({"schema_version": 1,
        "evidence": [{"path": path.name, "sha256": sha256_file(path)} for path in files]},
        indent=2) + "\n", encoding="utf-8")
    print(output / "report.md")
    if not metrics["targeted_vertical_check_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
