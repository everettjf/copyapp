"""Bind an explicit image-by-image review to saved device screenshots."""

import io
import json
import os
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from copyapp.verify import checked_path, sha256_file, verify_case


VERDICTS = {"match", "minor_difference", "major_difference"}


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def screenshot_pairs(check_case: Path) -> list[dict]:
    """Collect the exact screenshots and display composites in a verified check."""
    check_case = check_case.resolve(strict=True)
    with redirect_stdout(io.StringIO()):
        if not verify_case(check_case):
            raise ValueError("rebuild check failed verification")
    source = _read(check_case / "manifest.json")
    flows = source.get("flows")
    if (source.get("kind") != "rebuild_check" or source.get("status") != "complete" or
            not isinstance(flows, list) or not 1 <= len(flows) <= 32):
        raise ValueError("visual review requires a complete rebuild check")
    result = []
    seen = set()
    for flow in flows:
        if not isinstance(flow, dict) or not isinstance(flow.get("flow_id"), str):
            raise ValueError("invalid flow in rebuild check")
        flow_id = flow["flow_id"]
        if not flow_id or flow_id in seen:
            raise ValueError("duplicate flow in rebuild check")
        seen.add(flow_id)
        index_path = checked_path(check_case, flow["comparison_index"])
        comparison = _read(index_path)
        screenshots = comparison.get("screenshots")
        artifacts = comparison.get("artifacts")
        if (not isinstance(screenshots, list) or not screenshots or len(screenshots) > 64 or
                len(screenshots) != flow.get("screenshot_pairs") or
                not isinstance(artifacts, dict)):
            raise ValueError(f"invalid screenshots for {flow_id}")
        steps = set()
        for item in screenshots:
            step = item.get("step") if isinstance(item, dict) else None
            if type(step) is not int or step < 1 or step in steps:
                raise ValueError(f"invalid screenshot step for {flow_id}")
            steps.add(step)
            paths = {}
            for role, name in (
                ("original", f"original/step-{step:02d}-screenshot.jpg"),
                ("rebuilt", f"rebuilt/step-{step:02d}-screenshot.jpg"),
                ("side_by_side", f"comparison/step-{step:02d}-side_by_side.png"),
            ):
                path = checked_path(index_path.parent, name)
                actual = sha256_file(path)
                if actual != artifacts.get(name, {}).get("sha256"):
                    raise ValueError(f"comparison image changed: {flow_id} {name}")
                paths[role + "_path"] = str(path.relative_to(check_case))
                paths[role + "_sha256"] = actual
            result.append({"flow_id": flow_id, "step": step, **paths})
    return result


def validate_review(review: dict, check_case: Path) -> bool:
    """Rebind recorded judgments to every unchanged source image."""
    check_case = check_case.resolve(strict=True)
    expected = screenshot_pairs(check_case)
    rows = review.get("pairs")
    if (review.get("schema_version") != 1 or review.get("kind") != "visual_review" or
            Path(review.get("rebuild_check_case", "")).resolve() != check_case or
            review.get("rebuild_check_manifest_sha256") !=
            sha256_file(check_case / "manifest.json") or
            not isinstance(review.get("reviewer"), str) or
            not review["reviewer"].strip() or
            not isinstance(rows, list) or len(rows) != len(expected)):
        return False
    for actual, source in zip(rows, expected):
        if (not isinstance(actual, dict) or
                any(actual.get(key) != value for key, value in source.items()) or
                actual.get("verdict") not in VERDICTS or
                not isinstance(actual.get("note"), str) or
                len(actual["note"].strip()) < 12):
            return False
    return review.get("status") == (
        "reviewed_with_major_differences" if any(item["verdict"] == "major_difference" for item in rows)
        else "reviewed_with_minor_differences" if any(item["verdict"] == "minor_difference" for item in rows)
        else "reviewed_matching")


def create_visual_review(check_case: Path, judgments_path: Path,
                         output: Path, reviewer: str) -> Path:
    """Save subjective judgments, while mechanically verifying image coverage and identity."""
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"visual review output is not empty: {output}")
    check_case = check_case.resolve(strict=True)
    judgments = _read(judgments_path.resolve(strict=True))
    supplied = judgments.get("pairs")
    if not isinstance(supplied, list):
        raise ValueError("judgments must contain a pairs list")
    keyed = {}
    for row in supplied:
        if not isinstance(row, dict) or type(row.get("step")) is not int:
            raise ValueError("invalid judgment pair")
        key = (row.get("flow_id"), row["step"])
        if key in keyed or not isinstance(key[0], str):
            raise ValueError("duplicate or invalid judgment pair")
        keyed[key] = row
    expected = screenshot_pairs(check_case)
    if len(keyed) != len(expected) or set(keyed) != {
            (item["flow_id"], item["step"]) for item in expected}:
        raise ValueError("judgments must cover every saved screenshot pair exactly once")
    rows = []
    for source in expected:
        judgment = keyed[(source["flow_id"], source["step"])]
        verdict = judgment.get("verdict")
        note = judgment.get("note")
        if (verdict not in VERDICTS or not isinstance(note, str) or
                len(note.strip()) < 12):
            raise ValueError("each pair needs a verdict and a concrete note")
        rows.append(dict(source, verdict=verdict, note=note.strip()))
    status = ("reviewed_with_major_differences" if any(
        row["verdict"] == "major_difference" for row in rows) else
        "reviewed_with_minor_differences" if any(
            row["verdict"] == "minor_difference" for row in rows) else
        "reviewed_matching")
    review = {"schema_version": 1, "kind": "visual_review", "status": status,
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "reviewer": reviewer, "rebuild_check_case": str(check_case),
              "rebuild_check_manifest_sha256": sha256_file(check_case / "manifest.json"),
              "pairs": rows,
              "scope_limit": "Judgments cover saved screenshots only; reviewer notes are subjective, and animations, unseen states and whole-app parity remain unverified."}
    if not validate_review(review, check_case):
        raise ValueError("review failed source validation")
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "review.json", review)
    lines = ["# 成对截图逐张审阅", "",
             f"- 来源：[真机对照]({os.path.relpath(check_case / 'report.md', output)})。",
             f"- 审阅者：`{reviewer}`；结果：`{status}`；{len(rows)} 对截图。",
             "- 结论是审阅者对保存画面的判断；哈希验证只能证明图片和判断没有被替换。", "",
             "| 流程 | 步骤 | 判断 | 可见差异 | 图片 |",
             "| --- | ---: | --- | --- | --- |"]
    for row in rows:
        side = check_case / row["side_by_side_path"]
        lines.append(f"| `{row['flow_id']}` | {row['step']} | `{row['verdict']}` | "
                     f"{row['note'].replace('|', '/')} | "
                     f"[并排图]({os.path.relpath(side, output)}) |")
    lines += ["", "未出现的页面、动画和其他设备未纳入本次视觉审阅。", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {
        "schema_version": 1, "kind": "visual_review", "status": status,
        "rebuild_check_manifest_sha256": review["rebuild_check_manifest_sha256"],
        "evidence": [{"path": name, "sha256": sha256_file(output / name)}
                     for name in ("review.json", "report.md")],
    })
    return output / "report.md"
