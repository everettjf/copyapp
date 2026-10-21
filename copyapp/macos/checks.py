"""Predeclared Mac paired replay and reproducible screenshot measurements."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

from copyapp.macos.acquire import acquire_app
from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.install import environment_for
from copyapp.macos.playbook import INPUT, run_playbook
from copyapp.macos.report import read, text
from copyapp.macos.ui import frame, validate_ui


def require(root: Path, kind: str):
    from copyapp.verify import verify_case
    if not verify_case(root) or read(root, "manifest.json").get("kind") != kind:
        raise ValueError("expected a verified " + kind + " case")


def captures(script: dict) -> list:
    result = []
    for index, step in enumerate(script["steps"], 1):
        prefix = "steps/" + str(index).zfill(2)
        if step["action"] == "launch":
            result.append(prefix + "/after")
        elif step["action"] not in {"expect_file", "expect_stopped"}:
            result.append(prefix + "/before")
            if step["action"] in INPUT - {"quit"}:
                result.append(prefix + "/after")
    return result


def has_start_assertion(script: dict) -> bool:
    for step in script["steps"][1:]:
        if step["action"] == "expect_text" and step.get("match", "equals") == "equals":
            return True
        if step["action"] in INPUT or step["action"] == "launch":
            break
    return False


def install_plan(install: Path) -> tuple:
    require(install, "mac_install")
    plan = install / "build/plan"
    return plan, read(plan, "rebuild-plan.json")


def validate_conditions(conditions: dict, install: Path):
    plan, frozen = install_plan(install)
    if (not isinstance(conditions, dict) or set(conditions) != {"schema_version", "platform", "reviewer", "expected_ui",
                                                             "network_expectation", "flows", "masks"} or
            type(conditions.get("schema_version")) is not int or conditions["schema_version"] != 2 or
            conditions.get("platform") != "macos"):
        raise ValueError("invalid Mac comparison conditions")
    text(conditions["reviewer"]); text(conditions["network_expectation"])
    validate_ui(conditions["expected_ui"])
    flows, masks = conditions["flows"], conditions["masks"]
    if (not isinstance(flows, list) or [row["id"] for row in flows] != frozen["selected_flow_ids"] or
            not isinstance(masks, list) or len(masks) > 512):
        raise ValueError("declare conditions for every selected flow in plan order")
    profiles = {}
    for row in flows:
        if set(row) != {"id", "starting_state", "window_frame", "input_data", "reset_policy"}:
            raise ValueError("invalid flow conditions")
        for key in ("starting_state", "input_data", "reset_policy"):
            text(row[key])
        frame(row["window_frame"])
        script = read(plan / "report/evidence" / row["id"], "playbook.json")
        if not has_start_assertion(script):
            raise ValueError("paired replay needs an exact initial text assertion before the first input")
        profiles[row["id"]] = captures(script)
    seen = set()
    for mask in masks:
        if (not isinstance(mask, dict) or set(mask) != {"flow_id", "capture", "rect", "reason"} or
                mask["flow_id"] not in profiles or mask["capture"] not in profiles[mask["flow_id"]]):
            raise ValueError("mask refers to an unplanned capture")
        text(mask["reason"])
        rect = mask["rect"]
        if (not isinstance(rect, list) or len(rect) != 4 or any(type(value) is not int for value in rect) or
                min(rect[:2]) < 0 or min(rect[2:]) <= 0):
            raise ValueError("mask needs positive integer pixel bounds")
        key = (mask["flow_id"], mask["capture"], *rect)
        if key in seen:
            raise ValueError("duplicate comparison mask")
        seen.add(key)
        original = plan / "report/evidence" / mask["flow_id"]
        with Image.open(screen(original, mask["capture"])) as image:
            if rect[0] + rect[2] > image.width or rect[1] + rect[3] > image.height:
                raise ValueError("mask is outside the original captured screen")
    for flow_id, prefixes in profiles.items():
        for prefix in prefixes:
            rectangles = [mask["rect"] for mask in masks if mask["flow_id"] == flow_id and mask["capture"] == prefix]
            if rectangles:
                original = screen(plan / "report/evidence" / flow_id, prefix)
                measure(original, original, rectangles)


def check_record(install: Path, conditions: dict, rounds: int) -> dict:
    validate_conditions(conditions, install)
    if type(rounds) is not int or not 1 <= rounds <= 5:
        raise ValueError("paired rounds must be between one and five")
    _, frozen = install_plan(install)
    return {"schema_version": 2, "platform": "macos", "scope": "paired_replay_preparation",
            "install_manifest_sha256": digest(install / "manifest.json"),
            "selected_flow_ids": frozen["selected_flow_ids"], "rounds": rounds,
            "readiness": "ready_for_replay", "behavior_checked": False,
            "network_expectation_status": "reviewer_declared_not_enforced"}


def check_plan(install: Path, conditions_path: Path, output: Path, rounds: int = 3) -> Path:
    install = install.resolve(strict=True)
    if output.resolve() == install or install in output.resolve().parents:
        raise ValueError("check plan must be outside its installation")
    conditions = json.loads(conditions_path.read_text())
    check_record(install, conditions, rounds)
    case = Case(output, "mac_check_plan")
    try:
        shutil.copytree(install, case.root / "install", symlinks=True)
        case.record("install/manifest.json")
        case.add("conditions.json", conditions)
        case.add("check-plan.json", check_record(case.root / "install", conditions, rounds))
        case.finish("complete", scope="paired_replay_preparation")
        require(case.root, "mac_check_plan")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="paired_replay_preparation")
        raise


def validate_check_plan(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "paired_replay_preparation" or
            not {"install/manifest.json", "conditions.json", "check-plan.json"}.issubset(names)):
        return False
    saved = read(root, "check-plan.json")
    return canonical(saved) == canonical(check_record(root / "install", read(root, "conditions.json"), saved["rounds"]))


def screen(root: Path, prefix: str) -> Path:
    names = {row["path"] for row in read(root, "manifest.json")["evidence"]}
    matches = [root / (prefix + suffix) for suffix in ("/screen.png", "/screen.jpg") if prefix + suffix in names]
    if len(matches) != 1:
        raise ValueError("capture must have exactly one recorded screenshot")
    return matches[0]


def measure(original: Path, rebuilt: Path, masks: list) -> dict:
    with Image.open(original) as first, Image.open(rebuilt) as second:
        if first.width * first.height > 16_777_216 or second.width * second.height > 16_777_216:
            raise ValueError("comparison screenshot exceeds the 16-megapixel bound")
        sizes = {"original_size": list(first.size), "rebuilt_size": list(second.size),
                 "dimensions_match": first.size == second.size}
        if first.size != second.size:
            return dict(sizes, unmasked_pixels=None, mean_absolute_error=None, changed_pixel_fraction=None)
        mask = Image.new("L", first.size, 255)
        draw = ImageDraw.Draw(mask)
        for rect in masks:
            x, y, width, height = rect
            if min(x, y) < 0 or min(width, height) <= 0 or x + width > first.width or y + height > first.height:
                raise ValueError("declared mask is outside a fresh screenshot")
            draw.rectangle((x, y, x + width - 1, y + height - 1), fill=0)
        count = mask.histogram()[255]
        if count == 0:
            raise ValueError("comparison cannot mask the entire screen")
        difference = ImageChops.difference(first.convert("RGB"), second.convert("RGB"))
        error = sum(ImageStat.Stat(difference, mask).mean) / (3 * 255)
        channels = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        changed = ImageChops.multiply(maximum.point(lambda value: 255 if value else 0), mask).histogram()[255]
        return dict(sizes, unmasked_pixels=count, mean_absolute_error=round(error, 8),
                    changed_pixel_fraction=round(changed / count, 8))


def timestamp(value: str):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("evidence timestamps must include a timezone")
    return result


def comparison(root: Path) -> dict:
    plan = root / "plan"
    require(plan, "mac_check_plan")
    install = plan / "install"
    frozen = read(plan, "check-plan.json")
    conditions = read(plan, "conditions.json")
    implementation, task = install_plan(install)
    rebuilt_acquisition = root / "rebuilt-acquisition"
    require(rebuilt_acquisition, "mac_app_acquisition")
    built_package = read(install / "build/package", "app-index.json")
    acquired = read(rebuilt_acquisition / "package", "app-index.json")
    if (acquired["package_sha256"] != built_package["package_sha256"] or acquired["app"] != built_package["app"] or
            read(rebuilt_acquisition, "acquisition.json")["guest_app_path"] != task["target"]["app_path"] or
            digest(rebuilt_acquisition / "environment/manifest.json") != digest(environment_for(install / "build") / "manifest.json")):
        raise ValueError("rebuilt acquisition differs from installed source build or environment")
    previous = timestamp(read(plan, "manifest.json")["updated_at"])
    seen_runs, seen_sessions, pairs, flows = set(), set(), [], []
    for round_number in range(1, frozen["rounds"] + 1):
        for flow in conditions["flows"]:
            flow_id = flow["id"]
            row = {"round": round_number, "flow_id": flow_id, "original": None, "rebuilt": None}
            paths = {}
            for side in ("original", "rebuilt"):
                relative = "runs/r" + str(round_number).zfill(2) + "/" + flow_id + "/" + side
                child = root / relative
                require(child, "mac_playbook")
                manifest = read(child, "manifest.json")
                started, finished = timestamp(manifest["started_at"]), timestamp(manifest["updated_at"])
                session = read(child, "session-health.json")["request"]["session_id"]
                if (started < previous or finished < started or manifest["run_id"] in seen_runs or session in seen_sessions or
                        read(child, "expected-ui.json") != conditions["expected_ui"] or
                        read(child, "starting-window.json") != flow["window_frame"]):
                    raise ValueError("paired replay must use fresh ordered runs and the predeclared UI conditions")
                previous = finished
                seen_runs.add(manifest["run_id"]); seen_sessions.add(session)
                source_flow = implementation / "report/evidence" / flow_id
                expected_script = read(source_flow, "playbook.json") if side == "original" else read(implementation, "scripts/" + flow_id + ".json")
                source = read(child / "source/package", "app-index.json")
                expected_package = read(source_flow / "source/package", "app-index.json") if side == "original" else acquired
                if (read(child, "playbook.json") != expected_script or source["package_sha256"] != expected_package["package_sha256"] or
                        digest(child / "source/environment/manifest.json") != digest(rebuilt_acquisition / "environment/manifest.json")):
                    raise ValueError("paired flow is bound to another script, build or environment")
                row[side] = {"path": relative, "manifest_sha256": digest(child / "manifest.json"),
                             "behavior_assertions": manifest["behavior_assertions"]}
                paths[side] = child
            flows.append(row)
            for prefix in captures(expected_script):
                original, rebuilt = screen(paths["original"], prefix), screen(paths["rebuilt"], prefix)
                masks = [mask for mask in conditions["masks"] if mask["flow_id"] == flow_id and mask["capture"] == prefix]
                pairs.append({"id": "r" + str(round_number).zfill(2) + "." + flow_id + "." + prefix.replace("/", "-"),
                              "round": round_number, "flow_id": flow_id, "capture": prefix,
                              "original": {"path": original.relative_to(root).as_posix(), "sha256": digest(original)},
                              "rebuilt": {"path": rebuilt.relative_to(root).as_posix(), "sha256": digest(rebuilt)},
                              "masks": masks, "metrics": measure(original, rebuilt, [mask["rect"] for mask in masks])})
    return {"schema_version": 2, "platform": "macos", "scope": "selected_flow_comparison",
            "check_plan_manifest_sha256": digest(plan / "manifest.json"),
            "rebuilt_acquisition_manifest_sha256": digest(rebuilt_acquisition / "manifest.json"),
            "rounds": frozen["rounds"], "flows": flows, "screenshot_pairs": pairs,
            "selected_comparisons": len(flows), "behavior_passed": len(flows), "selected_flow_pass_rate": 100.0,
            "visual_review": "not_reviewed", "network_expectation_status": "reviewer_declared_not_enforced"}


def rebuild_check(plan: Path, output: Path, timeout: float = 30) -> Path:
    plan = plan.resolve(strict=True)
    require(plan, "mac_check_plan")
    if output.resolve() == plan or plan in output.resolve().parents:
        raise ValueError("paired check must be outside its preparation")
    case = Case(output, "mac_rebuild_check")
    try:
        shutil.copytree(plan, case.root / "plan", symlinks=True)
        case.record("plan/manifest.json")
        require(case.root / "plan", "mac_check_plan")
        conditions = read(case.root / "plan", "conditions.json")
        settings = read(case.root / "plan", "check-plan.json")
        install = case.root / "plan/install"
        implementation, task = install_plan(install)
        acquire_app(environment_for(install / "build"), task["target"]["app_path"], task["target"]["bundle_id"],
                    case.root / "rebuilt-acquisition", timeout)
        case.record("rebuilt-acquisition/manifest.json")
        # Validate the acquired build before any original or rebuilt input.
        if read(case.root / "rebuilt-acquisition/package", "app-index.json")["package_sha256"] != read(install / "build/package", "app-index.json")["package_sha256"]:
            raise ValueError("rebuilt package changed since installation")
        for round_number in range(1, settings["rounds"] + 1):
            for flow in conditions["flows"]:
                flow_id = flow["id"]
                source = implementation / "report/evidence" / flow_id
                for side in ("original", "rebuilt"):
                    relative = "runs/r" + str(round_number).zfill(2) + "/" + flow_id + "/" + side
                    case.finish("collecting", active_run={"round": round_number, "flow_id": flow_id, "side": side})
                    acquisition = source / "source" if side == "original" else case.root / "rebuilt-acquisition"
                    script = source / "playbook.json" if side == "original" else implementation / "scripts" / (flow_id + ".json")
                    run_playbook(acquisition, script, case.root / relative, timeout,
                                 expected_ui=conditions["expected_ui"], starting_window=flow["window_frame"])
                    case.record(relative + "/manifest.json")
        data = comparison(case.root)
        case.add("comparison.json", data)
        from copyapp.macos.visual import template, review_task
        case.add("visual-judgments-template.json", template(data))
        case.add("VISUAL_REVIEW.md", review_task(data).encode("utf-8"), binary=True)
        case.finish("complete", scope="selected_flow_comparison", active_run=None)
        require(case.root, "mac_rebuild_check")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="selected_flow_comparison")
        raise


def validate_check(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "selected_flow_comparison" or
            manifest.get("active_run") is not None or
            not {"plan/manifest.json", "rebuilt-acquisition/manifest.json", "comparison.json", "visual-judgments-template.json", "VISUAL_REVIEW.md"}.issubset(names)):
        return False
    saved = read(root, "comparison.json")
    actual = comparison(root)
    required = {row[side]["path"] + "/manifest.json" for row in actual["flows"] for side in ("original", "rebuilt")}
    from copyapp.macos.visual import template, review_task
    return (required.issubset(names) and canonical(saved) == canonical(actual) and read(root, "visual-judgments-template.json") == template(actual) and
            (root / "VISUAL_REVIEW.md").read_text() == review_task(actual))
