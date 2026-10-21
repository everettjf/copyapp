"""Source-linked selected Mac delivery with explicit known-capability decisions."""

import hashlib
import json
import shutil
from pathlib import Path

from copyapp.macos.build import IGNORED
from copyapp.macos.case import Case, canonical, digest, now
from copyapp.macos.checks import require, timestamp
from copyapp.macos.package import inventory
from copyapp.macos.report import read, text


def delivery_record(visual: Path, coverage: dict, source_review: dict) -> dict:
    require(visual, "mac_visual_review")
    review = read(visual, "visual-review.json")
    if any(review[key] for key in ("major_differences", "starting_state_issues", "dimension_mismatches")):
        raise ValueError("delivery requires no major visual difference, equivalent starting states and matching image dimensions")
    check = visual / "check"
    comparison = read(check, "comparison.json")
    install = check / "plan/install"
    build = install / "build"
    frozen = read(build / "plan", "rebuild-plan.json")
    spec = read(build / "plan/report", "feature-spec.json")
    if (not isinstance(coverage, dict) or set(coverage) != {"schema_version", "platform", "reviewer", "capabilities"} or
            type(coverage.get("schema_version")) is not int or coverage["schema_version"] != 2 or coverage.get("platform") != "macos"):
        raise ValueError("invalid Mac capability review")
    text(coverage["reviewer"])
    decisions = coverage["capabilities"]
    capabilities = spec["capabilities"]
    if not isinstance(decisions, list) or [row["id"] for row in decisions] != [row["id"] for row in capabilities]:
        raise ValueError("review each frozen known capability exactly once in inventory order")
    verified, selected, target = [], set(frozen["selected_flow_ids"]), set(frozen["target_capability_ids"])
    for decision, capability in zip(decisions, capabilities):
        if (set(decision) != {"id", "decision", "evidence_flow_ids", "reason"} or
                decision["decision"] not in {"verified", "deferred", "blocked"} or
                not isinstance(decision["evidence_flow_ids"], list)):
            raise ValueError("invalid known-capability decision")
        text(decision["reason"])
        if decision["decision"] == "verified":
            if (decision["id"] not in target or capability["disposition"] != "available" or
                    not capability["flow_ids"] or not set(capability["flow_ids"]).issubset(selected) or
                    decision["evidence_flow_ids"] != sorted(capability["flow_ids"])):
                raise ValueError("verified capabilities need all their selected flow gates and an explicit planned target")
            verified.append(decision["id"])
        elif decision["evidence_flow_ids"]:
            raise ValueError("unverified capabilities must not claim accepted flow evidence")
    if set(verified) != target:
        raise ValueError("the frozen target has not received a verified decision for every selected capability")
    source = read(build, "source-index.json")
    if (set(source_review) != {"project", "source_sha256", "entries", "reviewed_at"} or
            source_review.get("project") != frozen["target"]["project"] or
            source_review.get("source_sha256") != source["sha256"] or
            type(source_review.get("entries")) is not int or source_review["entries"] != len(source["entries"])):
        raise ValueError("current project review differs from built source")
    timestamp(source_review["reviewed_at"])
    return {"schema_version": 2, "platform": "macos", "scope": "selected_behavior_delivery",
            "visual_review_manifest_sha256": digest(visual / "manifest.json"),
            "install_manifest_sha256": digest(install / "manifest.json"),
            "build_manifest_sha256": digest(build / "manifest.json"), "source_sha256": source["sha256"],
            "original_app": spec["app"], "rebuilt_app": read(build, "build.json")["app"],
            "execution_environment": "chatcomputer_vm", "physical_mac_verified": False,
            "coverage_reviewer": coverage["reviewer"], "known_capability_decisions": decisions,
            "coverage": {**frozen["coverage"], "verified_known_capabilities": len(verified),
                         "verified_known_percent": round(100 * len(verified) / len(capabilities), 2),
                         "selected_flow_pass_rate": comparison["selected_flow_pass_rate"]},
            "selected_flow_ids": frozen["selected_flow_ids"], "omitted_flow_ids": frozen["omitted_flow_ids"],
            "rounds": comparison["rounds"], "selected_comparisons": comparison["selected_comparisons"],
            "visual_review": {key: review[key] for key in ("reviewer", "complete", "major_differences", "minor_differences", "starting_state_issues")},
            "unknowns": spec["unknowns"], "function_analysis": "not_performed",
            "network_expectation_status": "reviewer_declared_not_enforced", "whole_app_parity": False}


def markdown(data: dict, visual: Path) -> str:
    coverage = data["coverage"]
    lines = ["# Selected Mac behavior delivery", "",
             "Original: `" + data["original_app"]["bundle_id"] + "`; independent rebuild: `" + data["rebuilt_app"]["bundle_id"] + "`.", "",
             "Environment: ChatComputer VM. This delivery does not establish physical-Mac compatibility.", "",
             "Target known coverage: " + str(coverage["target_known_capabilities"]) + "/" + str(coverage["known_capabilities"]) +
             " (" + str(coverage["target_percent"]) + "%). Verified known coverage: " + str(coverage["verified_known_capabilities"]) + "/" +
             str(coverage["known_capabilities"]) + " (" + str(coverage["verified_known_percent"]) + "%).", "",
             "Selected-flow checks: " + str(data["selected_comparisons"]) + " comparisons across " + str(data["rounds"]) +
             " rounds; " + str(coverage["selected_flow_pass_rate"]) + "% passed their explicit behavior assertions.", "",
             "The denominator is the reviewed known inventory. The selected-flow pass rate is not whole-App parity.", "",
             "All required full screenshot pairs and starting states have explicit review judgments.",
             "Minor differences remain recorded below. Review labels and capability semantics are self-declared;",
             "verification checks provenance, coverage and arithmetic. Function analysis was not performed.", "",
             "[Source/build](visual/check/plan/install/build/build.json) · [Source snapshot](visual/check/plan/install/build/source/) · " +
             "[Paired check](visual/check/comparison.json) · [Full visual review](visual/review.md)", "",
             "## Known capability decisions", ""]
    for row in data["known_capability_decisions"]:
        lines.append("- " + row["id"] + ": " + row["decision"] + ". " + row["reason"])
    lines.extend(["", "## Recorded visual differences", ""])
    differences = [row for row in read(visual, "visual-review.json")["judgments"] if row["verdict"] != "equivalent"]
    lines.extend(["- " + row["id"] + ": " + row["notes"] for row in differences] or ["No differences were recorded by the reviewer in the selected screenshot pairs."])
    lines.extend(["", "## Omitted and unknown scope", "", "Omitted report flows: " + (", ".join(data["omitted_flow_ids"]) or "none") + ".", ""])
    lines.extend(["- " + item for item in data["unknowns"]])
    lines.extend(["", "Network expectations were declared by the reviewer and were not automatically enforced.", ""])
    return "\n".join(lines)


def delivery(visual: Path, coverage_path: Path, output: Path) -> Path:
    visual = visual.resolve(strict=True)
    require(visual, "mac_visual_review")
    if output.resolve() == visual or visual in output.resolve().parents:
        raise ValueError("delivery must be outside its visual review")
    coverage = json.loads(coverage_path.read_text())
    build = visual / "check/plan/install/build"
    source = read(build, "source-index.json")
    project = Path(read(build / "plan", "rebuild-plan.json")["target"]["project"])
    entries = inventory(project, exclude=IGNORED)
    if entries != source["entries"]:
        raise ValueError("current project differs from the installed build; review and build a new attempt")
    source_review = {"project": str(project), "source_sha256": hashlib.sha256(canonical(entries)).hexdigest(),
                     "entries": len(entries), "reviewed_at": now()}
    delivery_record(visual, coverage, source_review)
    case = Case(output, "mac_delivery")
    try:
        shutil.copytree(visual, case.root / "visual", symlinks=True)
        case.record("visual/manifest.json")
        if inventory(project, exclude=IGNORED) != entries:
            raise ValueError("project changed during delivery capture")
        case.add("source-review.json", source_review)
        case.add("coverage-review.json", coverage)
        data = delivery_record(case.root / "visual", coverage, source_review)
        case.add("delivery.json", data)
        case.add("delivery.md", markdown(data, case.root / "visual").encode("utf-8"), binary=True)
        case.finish("complete", scope="selected_behavior_delivery")
        require(case.root, "mac_delivery")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="selected_behavior_delivery")
        raise


def validate_delivery(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "selected_behavior_delivery" or
            not {"visual/manifest.json", "source-review.json", "coverage-review.json", "delivery.json", "delivery.md"}.issubset(names)):
        return False
    source_review = read(root, "source-review.json")
    if timestamp(source_review["reviewed_at"]) > timestamp(manifest["updated_at"]):
        return False
    data = delivery_record(root / "visual", read(root, "coverage-review.json"), source_review)
    return canonical(data) == canonical(read(root, "delivery.json")) and (root / "delivery.md").read_text() == markdown(data, root / "visual")
