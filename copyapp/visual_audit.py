"""Measure saved screenshot pairs in a declared content region."""

import io
import json
import math
import os
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from copyapp.verify import checked_path, sha256_file, verify_case


def _read(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"expected JSON object: {path}")
    return result


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _measure(original: Path, rebuilt: Path, roi: list, threshold: int) -> dict:
    with Image.open(original) as first, Image.open(rebuilt) as second:
        if first.size != second.size or first.width * first.height > 5_000_000:
            raise ValueError("screenshots differ in size or exceed image limit")
        width, height = first.size
        x1, y1, x2, y2 = roi
        if (x2 > width or y2 > height or
                (x2 - x1) * (y2 - y1) < width * height * 0.5):
            raise ValueError("audit region must cover at least half of the screen")
        diff = ImageChops.difference(first.convert("RGB").crop(tuple(roi)),
                                     second.convert("RGB").crop(tuple(roi)))
    mean = sum(ImageStat.Stat(diff).mean) / (3 * 255)
    changed = sum(max(pixel) > threshold for pixel in diff.getdata())
    return {"width": width, "height": height,
            "normalized_mean_absolute_rgb": round(mean, 7),
            "changed_pixel_fraction": round(changed / ((x2 - x1) * (y2 - y1)), 7)}


def compute_visual_audit(check_case: Path, roi: list, max_mean: float,
                         max_changed: float, difference_threshold: int = 24) -> dict:
    """Recompute metrics for every pair in one verified multi-flow device check."""
    check_case = check_case.resolve(strict=True)
    if (not isinstance(roi, list) or len(roi) != 4 or
            any(type(value) is not int or value < 0 for value in roi) or
            roi[0] >= roi[2] or roi[1] >= roi[3] or
            type(difference_threshold) is not int or
            not 0 <= difference_threshold <= 255 or
            type(max_mean) not in (int, float) or not math.isfinite(max_mean) or
            not 0 < max_mean <= 1 or
            type(max_changed) not in (int, float) or not math.isfinite(max_changed) or
            not 0 < max_changed <= 1):
        raise ValueError("invalid visual audit region or thresholds")
    with redirect_stdout(io.StringIO()):
        if not verify_case(check_case):
            raise ValueError("rebuild check failed hash verification")
    source = _read(check_case / "manifest.json")
    flows = source.get("flows")
    if (source.get("kind") != "rebuild_check" or source.get("status") != "complete" or
            not isinstance(flows, list) or not 1 <= len(flows) <= 32):
        raise ValueError("visual audit requires a complete bounded rebuild check")
    pairs_out = []
    seen = set()
    for flow in flows:
        if not isinstance(flow, dict):
            raise ValueError("invalid rebuild flow")
        flow_id = flow.get("flow_id")
        if (not isinstance(flow_id, str) or not flow_id or flow_id in seen or
                not isinstance(flow.get("comparison_index"), str)):
            raise ValueError("invalid or duplicate rebuild flow")
        seen.add(flow_id)
        index_path = checked_path(check_case, flow["comparison_index"])
        comparison = _read(index_path)
        pairs = comparison.get("screenshots")
        artifacts = comparison.get("artifacts")
        if (not isinstance(pairs, list) or not pairs or len(pairs) > 64 or
                len(pairs) != flow.get("screenshot_pairs") or
                not isinstance(artifacts, dict)):
            raise ValueError(f"missing screenshot pairs: {flow_id}")
        seen_steps = set()
        for pair in pairs:
            if not isinstance(pair, dict):
                raise ValueError("invalid screenshot pair")
            step = pair.get("step")
            if type(step) is not int or step < 1 or step in seen_steps:
                raise ValueError("invalid screenshot step")
            seen_steps.add(step)
            names = [f"original/step-{step:02d}-screenshot.jpg",
                     f"rebuilt/step-{step:02d}-screenshot.jpg"]
            paths = [checked_path(index_path.parent, name) for name in names]
            hashes = []
            for name, path in zip(names, paths):
                actual = sha256_file(path)
                if actual != artifacts.get(name, {}).get("sha256"):
                    raise ValueError(f"comparison screenshot changed: {name}")
                hashes.append(actual)
            measured = _measure(paths[0], paths[1], roi, difference_threshold)
            if (measured["width"] != pair.get("visual", {}).get("width") or
                    measured["height"] != pair.get("visual", {}).get("height")):
                raise ValueError("comparison dimensions changed")
            passed = (measured["normalized_mean_absolute_rgb"] <= max_mean and
                      measured["changed_pixel_fraction"] <= max_changed)
            pairs_out.append({"flow_id": flow_id, "step": step,
                              "original_path": str(paths[0]), "original_sha256": hashes[0],
                              "rebuilt_path": str(paths[1]), "rebuilt_sha256": hashes[1],
                              **measured, "within_declared_threshold": passed})
    status = ("metric_within_threshold" if all(pair["within_declared_threshold"]
                                               for pair in pairs_out) else "metric_exceeded")
    return {"schema_version": 1, "kind": "visual_audit", "status": status,
            "rebuild_check_case": str(check_case),
            "rebuild_check_manifest_sha256": sha256_file(check_case / "manifest.json"),
            "device_id_sha256_prefix": source.get("device_id_sha256_prefix"),
            "roi_pixels": roi, "max_normalized_mean_absolute_rgb": max_mean,
            "max_changed_pixel_fraction": max_changed,
            "difference_threshold": difference_threshold, "pairs": pairs_out,
            "scope_limit": "Pixel metrics cover only saved screenshots and the declared region; dynamic states, semantics and whole-app visual parity remain unverified."}


def create_visual_audit(check_case: Path, output: Path, roi: list,
                        max_mean: float, max_changed: float,
                        difference_threshold: int = 24) -> Path:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"visual audit output is not empty: {output}")
    result = compute_visual_audit(check_case, roi, max_mean, max_changed,
                                  difference_threshold)
    result["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "audit.json", result)
    def link(path: Path, label: str) -> str:
        return f"[{label}]({os.path.relpath(path, output)})"
    lines = ["# 成对截图区域审计", "",
             f"- 来源：{link(Path(result['rebuild_check_case']) / 'report.md', '真机对照')}；"
             f"设备 ID 哈希前缀：`{result['device_id_sha256_prefix']}`。",
             f"- 区域 `{roi}`；平均 RGB 差上限 `{max_mean}`（归一化）；"
             f"单像素最大通道差大于 `{difference_threshold}` 的比例上限 `{max_changed}`。",
             f"- 指标结果：`{result['status']}`；{len(result['pairs'])} 张成对截图。", "",
             "| 流程 | 步骤 | 平均 RGB 差 | 差异像素比例 | 结果 |",
             "| --- | ---: | ---: | ---: | --- |"]
    for pair in result["pairs"]:
        lines.append(f"| `{pair['flow_id']}` | {pair['step']} | "
                     f"{pair['normalized_mean_absolute_rgb']:.5f} | "
                     f"{pair['changed_pixel_fraction']:.3%} | "
                     f"{'阈值内' if pair['within_declared_threshold'] else '超过阈值'} |")
    lines.extend(["", "阈值若在查看截图后设定，属于事后诊断，不是预先声明的视觉验收。"
                  "人工审阅仍需记录具体界面差异。", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {
        "schema_version": 1, "kind": "visual_audit", "status": result["status"],
        "rebuild_check_manifest_sha256": result["rebuild_check_manifest_sha256"],
        "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                     for name in ("audit.json", "report.md")],
    })
    return output / "report.md"
