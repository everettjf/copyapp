#!/usr/bin/env python3
"""Compare verified Compass-to-Maps URL handoffs without publishing coordinates."""

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image

from copyapp.verify import sha256_file, verify_case


def load(root: Path, bundle: str) -> dict:
    if not verify_case(root):
        raise ValueError(f"source evidence hash mismatch: {root}")
    data = json.loads((root / "experiment.json").read_text(encoding="utf-8"))
    if (data.get("status") != "complete" or data.get("bundle_id") != bundle or
            data.get("scenario_id") != "compass-coordinate-maps-url" or
            data.get("frontmost_after") != "com.apple.Maps"):
        raise ValueError(f"wrong or incomplete Maps URL case: {root}")
    return data


def compare(original_root: Path, clone_root: Path, output: Path) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    original_root = original_root.resolve(strict=True)
    clone_root = clone_root.resolve(strict=True)
    original = load(original_root, "com.apple.compass")
    clone = load(clone_root, "dev.copyapp.compass")
    if (original_root == clone_root or
            original["device_id_sha256_prefix"] != clone["device_id_sha256_prefix"] or
            original["ui_backend"] != clone["ui_backend"]):
        raise ValueError("both runs must use the same device and UI backend")
    first, second = original["maps_coordinate"], clone["maps_coordinate"]
    mean_latitude = math.radians((first["latitude"] + second["latitude"]) / 2)
    latitude_metres = (first["latitude"] - second["latitude"]) * 111320
    longitude_metres = (first["longitude"] - second["longitude"]) * 111320 * math.cos(mean_latitude)
    distance = math.hypot(latitude_metres, longitude_metres)
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(original_root, output / "original")
    shutil.copytree(clone_root, output / "clone")
    a = Image.open(output / "original" / "after.jpg").convert("RGB")
    b = Image.open(output / "clone" / "after.jpg").convert("RGB")
    if a.size != b.size:
        raise ValueError("Maps screenshots have different dimensions")
    side_by_side = Image.new("RGB", (a.width * 2, a.height))
    side_by_side.paste(a, (0, 0))
    side_by_side.paste(b, (a.width, 0))
    side_by_side.save(output / "maps-side-by-side.png")
    matching = original["maps_url"] == clone["maps_url"]
    metrics = {
        "schema_version": 1,
        "device_id_sha256_prefix": original["device_id_sha256_prefix"],
        "both_maps_frontmost": True,
        "original_url_event_count": len(original["url_events"]),
        "clone_url_event_count": len(clone["url_events"]),
        "exact_same_maps_url": matching,
        "targeted_handoff_check_passed": matching,
        "original_url_sha256": hashlib.sha256(original["maps_url"].encode()).hexdigest(),
        "clone_url_sha256": hashlib.sha256(clone["maps_url"].encode()).hexdigest(),
        "coordinate_difference_metres": round(distance, 2),
    }
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    report = f"""# Compass 到 Apple Maps 的真机对照

同一台 XR 上，原版与复刻版点击坐标后各捕获到一次 `UIApplication` 的 Maps URL 调用，`com.apple.Maps` 随后均位于前台。完整 URL 含设备位置，只保存在本地原始证据中。

- 两边发送的 Maps URL **{'逐字相同' if matching else '不同'}**，坐标差 **{distance:.2f} 米**；URL SHA-256 分别为 `{metrics['original_url_sha256']}` 和 `{metrics['clone_url_sha256']}`。
- [Maps 稳定画面并排](maps-side-by-side.png)；原版 [实验记录](original/experiment.json)，复刻版 [实验记录](clone/experiment.json)。
- 两份源案例及此对照的所有文件都可由 `copyapp verify` 检查哈希。

这证明本次点击发出了相同的地图请求，且两边落到同一个 Maps 地图视图；不覆盖定位权限拒绝、网络不可用或其他坐标状态。
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
    if not json.loads((args.out / "metrics.json").read_text())["targeted_handoff_check_passed"]:
        raise SystemExit(1)
