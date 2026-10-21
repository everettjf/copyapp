"""Explicit review of every full Mac screenshot pair and each starting state."""

import json
import shutil
from pathlib import Path
from urllib.parse import quote

from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.report import read, text


def template(comparison: dict) -> dict:
    return {"schema_version": 2, "platform": "macos", "reviewer": "",
            "judgments": [{"id": pair["id"], "verdict": None, "notes": "", "reviewed_full_screens": False}
                          for pair in comparison["screenshot_pairs"]],
            "starting_states": [{"round": row["round"], "flow_id": row["flow_id"], "judgment": "unknown", "notes": ""}
                                for row in comparison["flows"]]}


def review_task(comparison: dict) -> str:
    lines = ["# Review Mac paired runs", "",
             "Open both full, unmasked screenshots for every pair below. Review the actual App",
             "content, controls, window placement, menus/dialogs and visible differences. Metrics",
             "and predeclared masks are measurements; they cannot substitute for this review.", "",
             "Compare each initial launch and starting-state assertion too. Judge whether the",
             "declared starting states are equivalent. Mark uncertainty instead of assuming it.", "",
             "Copy visual-judgments-template.json to an ignored case workspace and fill every",
             "entry. Use equivalent, minor_difference or major_difference for screenshot pairs;",
             "use equivalent, different or unknown for starting states. Retain specific differences.", "",
             "Run copyapp mac visual-review --check <THIS_CASE> --judgments <JSON> --out <NEW_CASE>.", "",
             "The reviewer label is self-declared. Verification checks image identity and coverage,",
             "not the truth of a subjective judgment or the completeness of the App inventory.", ""]
    for pair in comparison["screenshot_pairs"]:
        lines.extend(["- " + pair["id"] + ": [original](" + quote(pair["original"]["path"]) +
                      ") · [rebuilt](" + quote(pair["rebuilt"]["path"]) + ")"])
    return "\n".join(lines) + "\n"


def reviewed(check: Path, judgments: dict) -> dict:
    from copyapp.macos.checks import require
    require(check, "mac_rebuild_check")
    data = read(check, "comparison.json")
    if (not isinstance(judgments, dict) or set(judgments) != {"schema_version", "platform", "reviewer", "judgments", "starting_states"} or
            type(judgments.get("schema_version")) is not int or judgments["schema_version"] != 2 or judgments.get("platform") != "macos"):
        raise ValueError("invalid Mac visual review")
    text(judgments["reviewer"])
    entries, states = judgments["judgments"], judgments["starting_states"]
    if (not isinstance(entries, list) or [row["id"] for row in entries] != [pair["id"] for pair in data["screenshot_pairs"]] or
            not isinstance(states, list) or [(row["round"], row["flow_id"]) for row in states] !=
            [(row["round"], row["flow_id"]) for row in data["flows"]]):
        raise ValueError("review must cover every screenshot pair and starting state exactly once in template order")
    results = []
    for entry, pair in zip(entries, data["screenshot_pairs"]):
        if (set(entry) != {"id", "verdict", "notes", "reviewed_full_screens"} or
                entry["verdict"] not in {"equivalent", "minor_difference", "major_difference"} or
                entry["reviewed_full_screens"] is not True):
            raise ValueError("each pair needs an explicit full-screen review and verdict")
        text(entry["notes"])
        results.append({**entry, "original_sha256": pair["original"]["sha256"], "rebuilt_sha256": pair["rebuilt"]["sha256"]})
    for entry in states:
        if (set(entry) != {"round", "flow_id", "judgment", "notes"} or
                type(entry["round"]) is not int or entry["judgment"] not in {"equivalent", "different", "unknown"}):
            raise ValueError("each starting state needs an explicit judgment")
        text(entry["notes"])
    return {"schema_version": 2, "platform": "macos", "scope": "full_screenshot_review",
            "check_manifest_sha256": digest(check / "manifest.json"), "reviewer": judgments["reviewer"],
            "judgments": results, "starting_states": states, "complete": True,
            "major_differences": sum(row["verdict"] == "major_difference" for row in entries),
            "minor_differences": sum(row["verdict"] == "minor_difference" for row in entries),
            "starting_state_issues": sum(row["judgment"] != "equivalent" for row in states),
            "dimension_mismatches": sum(not row["metrics"]["dimensions_match"] for row in data["screenshot_pairs"])}


def markdown(data: dict) -> str:
    lines = ["# Mac screenshot review", "", "Reviewer (self-declared): " + data["reviewer"], "",
             "All required full screenshot pairs have explicit judgments. This verifies coverage",
             "and image identity; it does not certify the truth of the judgments.", "",
             "Major differences: " + str(data["major_differences"]) + "; minor differences: " + str(data["minor_differences"]) +
             "; starting-state issues: " + str(data["starting_state_issues"]) + ".", ""]
    for row in data["judgments"]:
        lines.append("- " + row["id"] + ": " + row["verdict"] + ". " + row["notes"])
    lines.extend(["", "## Starting states", ""])
    for row in data["starting_states"]:
        lines.append("- Round " + str(row["round"]) + " / " + row["flow_id"] + ": " + row["judgment"] + ". " + row["notes"])
    return "\n".join(lines) + "\n"


def visual_review(check: Path, judgments_path: Path, output: Path) -> Path:
    check = check.resolve(strict=True)
    if output.resolve() == check or check in output.resolve().parents:
        raise ValueError("visual review must be outside its check case")
    judgments = json.loads(judgments_path.read_text())
    reviewed(check, judgments)
    case = Case(output, "mac_visual_review")
    try:
        shutil.copytree(check, case.root / "check", symlinks=True)
        case.record("check/manifest.json")
        data = reviewed(case.root / "check", judgments)
        case.add("review-input.json", judgments)
        case.add("visual-review.json", data)
        case.add("review.md", markdown(data).encode("utf-8"), binary=True)
        case.finish("complete", scope="full_screenshot_review")
        from copyapp.macos.checks import require
        require(case.root, "mac_visual_review")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="full_screenshot_review")
        raise


def validate_visual(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "full_screenshot_review" or
            not {"check/manifest.json", "review-input.json", "visual-review.json", "review.md"}.issubset(names)):
        return False
    data = reviewed(root / "check", read(root, "review-input.json"))
    return canonical(data) == canonical(read(root, "visual-review.json")) and (root / "review.md").read_text() == markdown(data)
