"""Build an inspectable, same-device comparison of two UI playbook runs."""

import io
import json
import math
import shutil
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageChops, ImageStat

from copyapp.ocr_file import verify_ocr_source
from copyapp.playbook import _exact_labels
from copyapp.verify import checked_path, sha256_file, verify_case


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_run(root: Path, require_comparable: bool = True) -> Tuple[dict, dict]:
    with redirect_stdout(io.StringIO()):
        if not verify_case(root):
            raise ValueError(f"playbook evidence failed SHA-256 verification: {root}")
    manifest = _read_json(root / "manifest.json")
    plan = _read_json(root / "playbook.json")
    if (manifest.get("schema_version") != 1 or plan.get("schema_version") != 1 or
            manifest.get("status") != "complete" or
            manifest.get("bundle_id") != plan.get("bundle_id") or
            not manifest.get("device_id_sha256_prefix") or
            not manifest.get("ui_backend") or
            (require_comparable and not plan.get("scenario_id")) or
            manifest.get("scenario_id") != plan.get("scenario_id")):
        raise ValueError(f"playbook run identity or completion is invalid: {root}")
    steps = manifest.get("steps")
    planned = plan.get("steps")
    if (not isinstance(steps, list) or not isinstance(planned, list) or
            len(steps) != len(planned) or not steps):
        raise ValueError(f"playbook steps are incomplete: {root}")
    for index, (observed, requested) in enumerate(zip(steps, planned), 1):
        expected_frontmost = (requested.get("bundle_id") if
                              requested.get("action") == "expect_foreground" else
                              manifest["bundle_id"])
        if (observed.get("index") != index or
                observed.get("action") != requested.get("action") or
                observed.get("frontmost") != expected_frontmost or
                (requested.get("action") == "expect_foreground" and
                 observed.get("expected_frontmost") != expected_frontmost)):
            raise ValueError(f"playbook step identity mismatch at {index}: {root}")
        region = requested.get("region_points") if requested.get("action") == "tap_label" else None
        if region is not None:
            match = (observed.get("result") or {}).get("match")
            if (not isinstance(region, list) or len(region) != 4 or
                    any(type(value) not in (int, float) or not math.isfinite(value)
                        for value in region) or
                    not isinstance(match, dict) or
                    type(match.get("x")) not in (int, float) or
                    type(match.get("y")) not in (int, float) or
                    not math.isfinite(match["x"]) or not math.isfinite(match["y"]) or
                    not region[0] <= match["x"] <= region[2] or
                    not region[1] <= match["y"] <= region[3]):
                raise ValueError(f"bounded label tap does not match saved region at {index}: {root}")
        if observed["action"] == "observe" and observed.get("observation_source") == "screenshot_ocr":
            image_relative = observed.get("observation_image_path")
            ocr_relative = observed.get("observation_ocr_path")
            if not isinstance(image_relative, str) or not isinstance(ocr_relative, str):
                raise ValueError(f"observation OCR evidence is missing at {index}: {root}")
            image_path = checked_path(root, image_relative)
            ocr_path = checked_path(root, ocr_relative)
            listed = {entry.get("path") for entry in manifest.get("evidence", [])}
            if (sha256_file(image_path) != observed.get("observation_image_sha256") or
                    sha256_file(ocr_path) != observed.get("observation_ocr_sha256") or
                    not {image_relative, ocr_relative} <= listed):
                raise ValueError(f"observation OCR evidence mismatch at {index}: {root}")
            ocr_record = _read_json(ocr_path)
            if not verify_ocr_source(ocr_record, image_path):
                raise ValueError(f"observation OCR source mismatch at {index}: {root}")
            ocr_text = "\n".join(str(entry.get("text") or "") for entry in
                                 ocr_record["result"]["texts"] if isinstance(entry, dict))
            expected = requested.get("contains", [])
            if isinstance(expected, str):
                expected = [expected]
            if (not isinstance(expected, list) or
                    any(not isinstance(value, str) or value not in ocr_text for value in expected)):
                raise ValueError(f"observation OCR content mismatch at {index}: {root}")
        if observed["action"] == "observe" and requested.get("exact_labels"):
            labels = requested["exact_labels"]
            if isinstance(labels, str):
                labels = [labels]
            relative = observed.get("evidence_path")
            listed = {entry.get("path") for entry in manifest.get("evidence", [])}
            if (not isinstance(labels, list) or any(not isinstance(label, str) or not label
                    for label in labels) or not isinstance(relative, str) or relative not in listed or
                    observed.get("exact_label_source") != "accessibility" or
                    observed.get("missing_exact_labels") != []):
                raise ValueError(f"exact observation evidence is incomplete at {index}: {root}")
            observation = _read_json(checked_path(root, relative))
            if any(label not in _exact_labels(observation, manifest["ui_backend"])
                   for label in labels):
                raise ValueError(f"exact observation labels do not match evidence at {index}: {root}")
        if observed["action"] == "screenshot":
            stability = observed.get("stability")
            ready = requested.get("ready_contains")
            if (require_comparable and
                (requested.get("stable") is not True or
                 not isinstance(ready, str) or not ready)) or \
                    (requested.get("stable") is True and
                     (not isinstance(stability, dict) or stability.get("stable") is not True)) or \
                    (ready is not None and
                     (not isinstance(ready, str) or not ready or
                      observed.get("ready_contains") != ready or
                      observed.get("ready_found") is not True)):
                raise ValueError(f"screenshot readiness was not verified at {index}: {root}")
            relative = observed.get("evidence_path")
            if (not isinstance(relative, str) or
                    not relative.endswith(".jpg") or
                    sha256_file(checked_path(root, relative)) != observed.get("sha256")):
                raise ValueError(f"screenshot identity mismatch at {index}: {root}")
            if observed.get("ready_source") == "screenshot_ocr":
                ocr_relative = observed.get("ready_ocr_path")
                if not isinstance(ocr_relative, str):
                    raise ValueError(f"screenshot OCR evidence is missing at {index}: {root}")
                ocr_path = checked_path(root, ocr_relative)
                if (sha256_file(ocr_path) != observed.get("ready_ocr_sha256") or
                        ocr_relative not in {entry.get("path") for entry in manifest.get("evidence", [])}):
                    raise ValueError(f"screenshot OCR evidence mismatch at {index}: {root}")
                ocr_record = _read_json(ocr_path)
                if not verify_ocr_source(ocr_record, checked_path(root, relative)):
                    raise ValueError(f"screenshot OCR source mismatch at {index}: {root}")
                ocr_text = "\n".join(str(entry.get("text") or "") for entry in
                                     ocr_record["result"]["texts"] if isinstance(entry, dict))
                if ready not in ocr_text:
                    raise ValueError(f"screenshot OCR content mismatch at {index}: {root}")
    return manifest, plan


def _image_pair(first: Path, second: Path, output: Path, stem: str,
                artifacts: Dict[str, dict]) -> dict:
    with Image.open(first) as opened_first, Image.open(second) as opened_second:
        original = opened_first.convert("RGB")
        rebuilt = opened_second.convert("RGB")
    if (original.size != rebuilt.size or original.width * original.height > 5_000_000):
        raise ValueError(f"screenshots differ in size or exceed image limit: {stem}")
    side = Image.new("RGB", (original.width * 2, original.height))
    side.paste(original, (0, 0))
    side.paste(rebuilt, (original.width, 0))
    difference = ImageChops.difference(original, rebuilt)
    mean = sum(ImageStat.Stat(difference).mean) / 3 / 255
    comparison = output / "comparison"
    comparison.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, image in (("side_by_side", side), ("pixel_difference", difference)):
        path = comparison / f"{stem}-{name}.png"
        image.save(path)
        key = str(path.relative_to(output))
        artifacts[key] = {"path": key, "sha256": sha256_file(path)}
        paths[name] = key
    return {"width": original.width, "height": original.height,
            "mean_absolute_rgb": round(mean, 5), **paths}


def _pulse_check(check: dict, screenshots: Dict[int, Path]) -> dict:
    roi = check.get("roi")
    steps = check.get("steps")
    channel = check.get("channel")
    minimum = check.get("minimum_channel")
    ratio = check.get("dominance_ratio")
    rise = check.get("min_rise")
    return_delta = check.get("max_return_delta")
    if (check.get("kind") != "color_pulse" or
            not isinstance(check.get("id"), str) or not check["id"] or
            not isinstance(roi, list) or len(roi) != 4 or
            any(type(value) is not int or value < 0 for value in roi) or
            roi[0] >= roi[2] or roi[1] >= roi[3] or
            not isinstance(steps, list) or len(steps) != 3 or
            any(type(value) is not int or value not in screenshots for value in steps) or
            steps != sorted(set(steps)) or channel not in ("red", "green", "blue") or
            type(minimum) is not int or not 0 <= minimum <= 255 or
            type(ratio) not in (int, float) or not 1 <= ratio <= 10 or
            type(rise) is not int or rise < 1 or
            type(return_delta) is not int or return_delta < 0):
        raise ValueError(f"invalid color pulse check: {check.get('id')}")
    selected = {"red": 0, "green": 1, "blue": 2}[channel]
    counts = []
    for step in steps:
        with Image.open(screenshots[step]) as opened:
            image = opened.convert("RGB")
        if roi[2] > image.width or roi[3] > image.height:
            raise ValueError(f"color pulse ROI exceeds screenshot at step {step}")
        pixels = image.crop(tuple(roi)).getdata()
        count = sum(1 for pixel in pixels if pixel[selected] >= minimum and
                    all(pixel[selected] >= pixel[other] * ratio
                        for other in range(3) if other != selected))
        counts.append(count)
    passed = (counts[1] - counts[0] >= rise and
              abs(counts[2] - counts[0]) <= return_delta)
    return {"id": check["id"], "steps": steps, "counts": counts,
            "min_rise": rise, "max_return_delta": return_delta, "passed": passed}


def _color_match_check(check: dict, originals: Dict[int, Path],
                       rebuilt: Dict[int, Path]) -> dict:
    roi = check.get("roi")
    steps = check.get("steps")
    channel = check.get("channel")
    minimum = check.get("minimum_channel")
    ratio = check.get("dominance_ratio")
    tolerance = check.get("max_count_delta")
    if (check.get("kind") != "color_match" or
            not isinstance(check.get("id"), str) or not check["id"] or
            not isinstance(roi, list) or len(roi) != 4 or
            any(type(value) is not int or value < 0 for value in roi) or
            roi[0] >= roi[2] or roi[1] >= roi[3] or
            not isinstance(steps, list) or not 1 <= len(steps) <= 64 or
            any(type(value) is not int or value not in originals or value not in rebuilt
                for value in steps) or steps != sorted(set(steps)) or
            channel not in ("red", "green", "blue") or
            type(minimum) is not int or not 0 <= minimum <= 255 or
            type(ratio) not in (int, float) or not 1 <= ratio <= 10 or
            type(tolerance) is not int or tolerance < 0):
        raise ValueError(f"invalid color match check: {check.get('id')}")
    selected = {"red": 0, "green": 1, "blue": 2}[channel]
    counts = []
    for images in (originals, rebuilt):
        side_counts = []
        for step in steps:
            with Image.open(images[step]) as opened:
                image = opened.convert("RGB")
            if roi[2] > image.width or roi[3] > image.height:
                raise ValueError(f"color match ROI exceeds screenshot at step {step}")
            count = sum(1 for pixel in image.crop(tuple(roi)).getdata()
                        if pixel[selected] >= minimum and
                        all(pixel[selected] >= pixel[other] * ratio
                            for other in range(3) if other != selected))
            side_counts.append(count)
        counts.append(side_counts)
    passed = all(abs(first - second) <= tolerance
                 for first, second in zip(counts[0], counts[1]))
    return {"id": check["id"], "kind": "color_match", "steps": steps,
            "max_count_delta": tolerance,
            "original": {"counts": counts[0], "passed": passed},
            "rebuilt": {"counts": counts[1], "passed": passed}}


def compare_playbooks(original_root: Path, rebuilt_root: Path, output: Path) -> Path:
    """Pair completed runs; retain images and observations without auto-grading fidelity."""
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"comparison output is not empty: {output}")
    original_root = original_root.resolve(strict=True)
    rebuilt_root = rebuilt_root.resolve(strict=True)
    original, original_plan = _load_run(original_root)
    rebuilt, rebuilt_plan = _load_run(rebuilt_root)
    if (original_root == rebuilt_root or
            original["bundle_id"] == rebuilt["bundle_id"] or
            original["device_id_sha256_prefix"] != rebuilt["device_id_sha256_prefix"] or
            original["ui_backend"] != rebuilt["ui_backend"] or
            original["scenario_id"] != rebuilt["scenario_id"] or
            original.get("screen") != rebuilt.get("screen")):
        raise ValueError("playbook runs must be different apps in the same scenario, device and backend")
    first_steps, second_steps = original_plan["steps"], rebuilt_plan["steps"]
    if ([step["action"] for step in first_steps] !=
            [step["action"] for step in second_steps]):
        raise ValueError("playbook action sequence differs")
    checks = original_plan.get("visual_checks", [])
    if (checks != rebuilt_plan.get("visual_checks", []) or
            not isinstance(checks, list)):
        raise ValueError("playbook visual checks differ")
    for index, (first, second) in enumerate(zip(first_steps, second_steps), 1):
        if first["action"] == "tap_label" and (
                first.get("label"), first.get("region_points")) != (
                second.get("label"), second.get("region_points")):
            raise ValueError(f"tap labels or regions differ at step {index}")
        if first["action"] == "tap" and (first.get("x"), first.get("y")) != (
                second.get("x"), second.get("y")):
            raise ValueError(f"tap coordinates differ at step {index}")
        if (first["action"] == "expect_foreground" and
                first.get("bundle_id") != second.get("bundle_id")):
            raise ValueError(f"expected handoff app differs at step {index}")
        if first["action"] == "observe" and (
                first.get("contains", []), first.get("exact_labels", [])) != (
                second.get("contains", []), second.get("exact_labels", [])):
            raise ValueError(f"observation conditions differ at step {index}")
    output.mkdir(parents=True, exist_ok=True)
    artifacts: Dict[str, dict] = {}
    for label, root, manifest in (("original", original_root, original),
                                  ("rebuilt", rebuilt_root, rebuilt)):
        target = output / label
        target.mkdir()
        for relative in {"manifest.json", "playbook.json"} | {
                item["path"] for item in manifest.get("evidence", [])}:
            source_path = checked_path(root, relative)
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
            key = str(destination.relative_to(output))
            artifacts[key] = {"path": key, "sha256": sha256_file(destination)}
    screenshot_pairs = []
    for first, second in zip(original["steps"], rebuilt["steps"]):
        if first["action"] != "screenshot":
            continue
        index = first["index"]
        first_path = output / "original" / first["evidence_path"]
        second_path = output / "rebuilt" / second["evidence_path"]
        visual = _image_pair(first_path, second_path, output,
                             f"step-{index:02d}", artifacts)
        screenshot_pairs.append({"step": index, "visual": visual})
    if not screenshot_pairs:
        raise ValueError("paired playbooks have no screenshots to compare")
    visual_results = []
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("invalid visual check")
        original_images = {step["index"]: output / "original" / step["evidence_path"]
                           for step in original["steps"] if step["action"] == "screenshot"}
        rebuilt_images = {step["index"]: output / "rebuilt" / step["evidence_path"]
                          for step in rebuilt["steps"] if step["action"] == "screenshot"}
        if check.get("kind") == "color_match":
            visual_results.append(_color_match_check(check, original_images, rebuilt_images))
        else:
            visual_results.append({"id": check.get("id"), "kind": "color_pulse",
                                   "original": _pulse_check(check, original_images),
                                   "rebuilt": _pulse_check(check, rebuilt_images)})
    checks_status = ("unreviewed" if not visual_results else
                     "passed" if all(item["original"]["passed"] and
                                     item["rebuilt"]["passed"] for item in visual_results)
                     else "failed")
    lines = [f"# UI 对照：{original['scenario_id']}", "",
             f"- 设备 ID 哈希前缀：`{original['device_id_sha256_prefix']}`",
             f"- 界面后端：`{original['ui_backend']}`",
             f"- 原版：`{original['bundle_id']}`",
             f"- 复刻版：`{rebuilt['bundle_id']}`",
             "- 两次脚本状态：均完成；动作类型顺序及坐标点击位置已核对。", "",
             "## 步骤结果", "",
             "| 步骤 | 动作 | 原版前台 | 复刻版前台 | 原版耗时 ms | 复刻版耗时 ms |",
             "| ---: | --- | --- | --- | ---: | ---: |"]
    for first, second in zip(original["steps"], rebuilt["steps"]):
        lines.append(f"| {first['index']} | {first['action']} | "
                     f"{first['frontmost']} | {second['frontmost']} | "
                     f"{first.get('duration_ms', '?')} | {second.get('duration_ms', '?')} |")
    lines += ["", "## 画面对照", ""]
    for pair in screenshot_pairs:
        visual = pair["visual"]
        lines += [f"### 步骤 {pair['step']}", "",
                  f"- [左右并排]({visual['side_by_side']}) · "
                  f"[像素差图]({visual['pixel_difference']})",
                  f"- 同尺寸 {visual['width']}×{visual['height']}；"
                  f"平均 RGB 绝对差（0–1）：{visual['mean_absolute_rgb']}", ""]
    if visual_results:
        lines += ["## 指定视觉状态检查", "",
                  "| 信号 | 原版指定步骤计数 | 复刻版指定步骤计数 | 结果 |",
                  "| --- | --- | --- | --- |"]
        for item in visual_results:
            passed = item["original"]["passed"] and item["rebuilt"]["passed"]
            lines.append(f"| {item['id']} | {item['original']['counts']} | "
                         f"{item['rebuilt']['counts']} | {'通过' if passed else '未通过'} |")
        lines += ["", "颜色检查仅比较指定区域的像素计数或脉冲变化；"
                  "仍需人工检查标记形状、动画和交互含义。", ""]
    lines += ["原版和复刻版的原始截图、观察结果与脚本见各自目录。"
              "动态方位、位置、状态栏和拍摄时间会影响像素差；该数值不代表功能通过。"
              "行为、状态与视觉差异仍需结合图片及设备输出审阅。", ""]
    report = output / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    artifacts["report.md"] = {"path": "report.md", "sha256": sha256_file(report)}
    index = {"schema_version": 1, "scenario_id": original["scenario_id"],
             "original_bundle_id": original["bundle_id"],
             "rebuilt_bundle_id": rebuilt["bundle_id"],
             "device_id_sha256_prefix": original["device_id_sha256_prefix"],
             "ui_backend": original["ui_backend"], "screenshots": screenshot_pairs,
             "visual_checks": visual_results, "checks_status": checks_status,
             "artifacts": artifacts}
    (output / "report-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
