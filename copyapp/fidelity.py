"""Bounded, reviewed reconstruction milestones; never a pixel-similarity claim.

These new cases deliberately leave historical strict delivery validators alone.
They reference retained verified cases rather than duplicating large UI archives.
"""

import json
from pathlib import Path

from copyapp.verify import sha256_file, verify_case


KINDS = {"fidelity_plan", "fidelity_check"}
WEIGHTS = {"behavior": 40, "layout": 40, "details": 20}


def read(root, name):
    value = json.loads((root / name).read_text())
    if not isinstance(value, dict):
        raise ValueError("expected an object: " + name)
    return value


def require(root, kinds):
    if read(root, "manifest.json").get("kind") not in kinds or not verify_case(root):
        raise ValueError("expected a verified " + "/".join(sorted(kinds)) + " case")


def reference(root):
    return {"path": str(root.resolve(strict=True)), "manifest_sha256": sha256_file(root / "manifest.json")}


def resolve(ref, kinds):
    if not isinstance(ref, dict) or set(ref) != {"path", "manifest_sha256"}:
        raise ValueError("invalid source reference")
    root = Path(ref["path"]).resolve(strict=True)
    if sha256_file(root / "manifest.json") != ref["manifest_sha256"]:
        raise ValueError("source manifest changed")
    require(root, kinds)
    return root


def contract(task):
    require(task, {"mac_rebuild_plan", "agent_implementation_task"})
    if read(task, "manifest.json")["kind"] == "mac_rebuild_plan":
        data = read(task, "rebuild-plan.json")
        return {"platform": "macos", "report_sha256": data["report_manifest_sha256"],
                "project": data["target"]["project"], "bundle_id": data["target"]["bundle_id"],
                "flow_ids": data["selected_flow_ids"], "capability_ids": data["target_capability_ids"]}
    data = read(task, "task.json")
    if data["status"] not in {"ready_for_agent", "selected_flows_ready"}:
        raise ValueError("resolve task evidence gaps before setting a reconstruction milestone")
    return {"platform": "ios", "report_sha256": data["report_index_sha256"],
            "project": data["project_dir"], "bundle_id": data["rebuilt_bundle_id"],
            "flow_ids": [row["id"] for row in data["flows"]], "device_udid": data["device_udid"]}


def policy(fidelity=80, max_iterations=3):
    if type(fidelity) is not int or not 0 <= fidelity <= 100:
        raise ValueError("fidelity must be an integer from 0 to 100")
    if type(max_iterations) is not int or not 1 <= max_iterations <= 20:
        raise ValueError("max-iterations must be an integer from 1 to 20")
    return {"fidelity": fidelity, "max_iterations": max_iterations,
            "weights": dict(WEIGHTS), "score_kind": "reviewed_selected_scope_grade",
            "core_behavior_required": True, "full_image_review_required": True,
            "whole_app_parity": False}


def plan_data(task, fidelity, max_iterations):
    return {"schema_version": 1, "kind": "fidelity_plan", "task": reference(task),
            "contract": contract(task), "policy": policy(fidelity, max_iterations)}


def brief(data):
    p = data["policy"]
    return ("# Bounded reconstruction milestone\n\n"
            f"Target grade: {p['fidelity']}/100. At most {p['max_iterations']} implementation/check cycles, "
            "including the first cycle. Paired replay repetitions are not additional implementation cycles.\n\n"
            "Work on the frozen selected scope. Core behavior, source/install identity and full-image review "
            "are required at every target. Grade = behavior 40% + layout 40% + details 20%; behavior is "
            "100 only when all selected flow assertions pass. Layout/details are explicit reviewer judgments "
            "with cited image IDs, not measured similarity percentages or known-capability coverage.\n\n"
            "Review every saved screenshot pair once; reuse only exact image hashes already inspected. "
            "Keep every difference, and classify its impact explicitly. A visible major difference may be "
            "non-blocking for this milestone; it must not be relabelled as minor or erased. Broken core "
            "flows, wrong identities, unreviewed images and blocking issues prevent target_met.\n\n"
            "Use fidelity-check with this plan, the verified visual review (Mac) or agent delivery with "
            "visual review (iOS), and the explicit grade review. After the first cycle, pass the previous "
            "fidelity-check. Only continue after continue. Stop after target_met or iteration_limit. "
            "At the limit, deliver the current runnable artifacts and remaining issues as incomplete; "
            "never claim target achievement. No automatic input retries or additional agent processes.\n\n"
            "A new build may use a fresh guest App path while preserving this report, project, Bundle ID "
            "and selected scope. Keep all previous attempts. A changed target/scope needs a new plan. "
            "The iteration chain records submitted cycles; it is not a global process or wall-clock limiter.\n\n"
            "Historical strict delivery, release gates and capability coverage retain their own meanings. "
            "A fidelity milestone does not certify complete App parity, physical-device compatibility "
            "or runtime function semantics. A 100 target additionally requires no recorded image differences.\n")


def save(root, kind, files):
    if root.exists():
        raise FileExistsError("refusing to overwrite fidelity evidence")
    root.mkdir(parents=True)
    for name, data in files.items():
        (root / name).write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    manifest = {"schema_version": 1, "platform": "cross_platform", "kind": kind, "status": "complete",
                "evidence": [{"path": name, "sha256": sha256_file(root / name)} for name in files]}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return root


def create_plan(task, output, fidelity=80, max_iterations=3):
    task = task.resolve(strict=True)
    if output.resolve() == task or task in output.resolve().parents:
        raise ValueError("use a fidelity plan outside its source task")
    data = plan_data(task, fidelity, max_iterations)
    return save(output, "fidelity_plan", {"fidelity-plan.json": data, "TASK.md": brief(data)})


def visual_context(evidence, frozen, *, live_source=False):
    """Bind grades to the actual selected source, installed build and full review."""
    manifest = read(evidence, "manifest.json")
    if manifest.get("status") == "failed" and manifest.get("kind") in {"mac_rebuild_check", "rebuild_check", "mac_build", "mac_install"}:
        # Failed artifacts cannot verify as complete execution. Retain that fact
        # while consuming a cycle; none of their assertions/grades can pass.
        return {"platform": frozen["platform"], "core_behavior_passed": False,
                "source_sha256": None, "pairs": [],
                "guard_issues": ["failed attempt; execution and full-image review incomplete"],
                "failed_manifest_sha256": sha256_file(evidence / "manifest.json")}
    require(evidence, {"mac_visual_review", "agent_delivery"})
    kind = read(evidence, "manifest.json")["kind"]
    if kind == "mac_visual_review":
        from copyapp.macos.build import IGNORED
        from copyapp.macos.package import inventory
        review = read(evidence, "visual-review.json")
        build = evidence / "check/plan/install/build"
        source = read(build, "source-index.json")
        if contract(build / "plan") != frozen:
            raise ValueError("paired build belongs to a different fidelity scope")
        if live_source and inventory(Path(frozen["project"]), exclude=IGNORED) != source["entries"]:
            raise ValueError("current project differs from the paired installed build")
        comparison = read(evidence / "check", "comparison.json")
        core = (comparison["behavior_passed"] == comparison["selected_comparisons"] and
                set(row["flow_id"] for row in comparison["flows"]) == set(frozen["flow_ids"]))
        rows = review["judgments"]
        pairs = [{"id": row["id"], "verdict": row["verdict"]} for row in rows]
        guards = []
        if review["starting_state_issues"]:
            guards.append("starting states not equivalent")
        if review["dimension_mismatches"]:
            guards.append("image dimensions differ")
        return {"platform": "macos", "core_behavior_passed": core,
                "source_sha256": source["sha256"], "pairs": pairs, "guard_issues": guards,
                "install_manifest_sha256": sha256_file(evidence / "check/plan/install/manifest.json")}
    delivery = read(evidence, "delivery.json")
    if contract(Path(delivery["task_case"])) != frozen:
        raise ValueError("iOS delivery belongs to a different fidelity scope")
    if live_source:
        from copyapp.agent_run import _source_tree_hash
        if _source_tree_hash(Path(frozen["project"])) != delivery["source_project_sha256"]:
            raise ValueError("current project differs from the delivered source")
    if not delivery["visual_review_case"] or delivery["visual_unreviewed_flow_count"]:
        raise ValueError("complete iOS image review is required")
    review = read(Path(delivery["visual_review_case"]), "review.json")
    selected = set(frozen["flow_ids"])
    pairs = [{"id": row["flow_id"] + ".step-" + str(row["step"]), "verdict": row["verdict"]}
             for row in review["pairs"] if row["flow_id"] in selected]
    return {"platform": "ios", "core_behavior_passed": delivery["asserted_flow_count"] == len(selected),
            "source_sha256": delivery["source_project_sha256"], "pairs": pairs, "guard_issues": [],
            "installed_ipa_sha256": delivery["ipa_snapshot_sha256"]}


def review_template(context):
    ids = [row["id"] for row in context["pairs"]]
    return {"schema_version": 1, "reviewer": "",
            "dimensions": {key: {"score": None, "notes": "", "pair_ids": ids} for key in ("layout", "details")},
            "differences": [{"pair_id": row["id"], "impact": None, "reason": ""}
                            for row in context["pairs"] if row["verdict"] not in {"match", "equivalent"}],
            "blocking_issues": []}


def evaluate(p, context, review, iteration):
    if p != policy(p["fidelity"], p["max_iterations"]):
        raise ValueError("unsupported grading policy")
    if type(iteration) is not int or not 1 <= iteration <= p["max_iterations"]:
        raise ValueError("iteration outside frozen budget")
    if (set(review) != {"schema_version", "reviewer", "dimensions", "differences", "blocking_issues"} or
            type(review["schema_version"]) is not int or review["schema_version"] != 1 or
            not isinstance(review["reviewer"], str) or not review["reviewer"].strip()):
        raise ValueError("explicit grade reviewer required")
    ids = {row["id"] for row in context["pairs"]}
    dims = review["dimensions"]
    if not isinstance(dims, dict) or set(dims) != {"layout", "details"}:
        raise ValueError("review layout and details separately")
    for dim in dims.values():
        if (not isinstance(dim, dict) or set(dim) != {"score", "notes", "pair_ids"} or
                type(dim["score"]) is not int or not 0 <= dim["score"] <= 100 or
                not isinstance(dim["notes"], str) or len(dim["notes"].strip()) < 12 or
                not isinstance(dim["pair_ids"], list) or (ids and not dim["pair_ids"]) or
                any(not isinstance(value, str) for value in dim["pair_ids"]) or
                len(set(dim["pair_ids"])) != len(dim["pair_ids"]) or not set(dim["pair_ids"]).issubset(ids)):
            raise ValueError("each grade needs an integer, concrete notes and unique saved image IDs")
        if not ids and dim["score"] != 0:
            raise ValueError("failed attempts without reviewed images must have zero visual grades")
    differences = review["differences"]
    expected = [row["id"] for row in context["pairs"] if row["verdict"] not in {"match", "equivalent"}]
    if not isinstance(differences, list) or [row.get("pair_id") for row in differences] != expected:
        raise ValueError("acknowledge every recorded image difference in review order")
    for row in differences:
        if (set(row) != {"pair_id", "impact", "reason"} or row["impact"] not in {"blocking", "non_blocking"} or
                not isinstance(row["reason"], str) or len(row["reason"].strip()) < 12):
            raise ValueError("every difference needs an explicit impact and reason")
    blockers = review["blocking_issues"]
    if not isinstance(blockers, list) or any(not isinstance(x, str) or len(x.strip()) < 12 for x in blockers):
        raise ValueError("blocking issues must be concrete strings")
    blockers = list(blockers) + context["guard_issues"]
    if not context["core_behavior_passed"]:
        blockers.append("selected core behavior assertions not all passed")
    if any(row["impact"] == "blocking" for row in differences):
        blockers.append("reviewed image difference blocks this milestone")
    if p["fidelity"] == 100 and differences:
        blockers.append("100 target requires no recorded image differences")
    score = (100 * WEIGHTS["behavior"] if context["core_behavior_passed"] else 0)
    score += sum(dims[key]["score"] * WEIGHTS[key] for key in ("layout", "details"))
    met = not blockers and score >= p["fidelity"] * 100
    return {"grade": score / 100, "target": p["fidelity"], "iteration": iteration,
            "max_iterations": p["max_iterations"], "target_met": met,
            "decision": "target_met" if met else "iteration_limit" if iteration == p["max_iterations"] else "continue",
            "blocking_issues": blockers, "recorded_differences": len(differences),
            "scope": "reviewed_selected_scope_milestone", "similarity_percent": None,
            "known_capability_coverage": None, "strict_delivery_certified": False}


def check_data(plan, evidence, review, previous=None, *, live_source=False):
    require(plan, {"fidelity_plan"})
    frozen = read(plan, "fidelity-plan.json")
    context = visual_context(evidence, frozen["contract"], live_source=live_source)
    iteration = 1
    if previous is not None:
        require(previous, {"fidelity_check"})
        prior = read(previous, "fidelity-check.json")
        if prior["plan"] != reference(plan) or prior["result"]["decision"] != "continue":
            raise ValueError("previous cycle must continue the same frozen plan")
        if prior["evidence"]["manifest_sha256"] == reference(evidence)["manifest_sha256"]:
            raise ValueError("do not consume a new cycle by regrading the same evidence")
        iteration = prior["result"]["iteration"] + 1
    return {"schema_version": 1, "kind": "fidelity_check", "plan": reference(plan),
            "evidence": reference(evidence), "previous": reference(previous) if previous else None,
            "context": context, "review": review,
            "result": evaluate(frozen["policy"], context, review, iteration)}


def report(data):
    result = data["result"]
    dims = data["review"]["dimensions"]
    return ("# Reconstruction milestone\n\n"
            f"Decision: **{result['decision']}**. Reviewed grade {result['grade']}/100; target {result['target']}. "
            f"Cycle {result['iteration']}/{result['max_iterations']}.\n\n"
            "Grade reflects explicit selected-scope reviewer judgments, not objective image similarity, "
            "known-capability coverage or strict delivery acceptance.\n\n"
            f"Reviewer: {data['review']['reviewer']}. Layout: {dims['layout']['score']}/100; "
            f"details: {dims['details']['score']}/100; core behavior passed: {data['context']['core_behavior_passed']}.\n\n"
            f"Layout: {dims['layout']['notes']}\n\nDetails: {dims['details']['notes']}\n\n"
            "[Grade, image citations and every difference decision](fidelity-check.json). "
            f"[Frozen task](<{data['plan']['path']}/TASK.md>) · "
            f"[Retained source evidence](<{data['evidence']['path']}>)\n\n"
            f"Recorded image differences: {result['recorded_differences']}.\n\n"
            + "\n".join("- " + x for x in result["blocking_issues"]) + "\n\n"
            + ("Stop implementation. Retain remaining differences and deliver the scoped artifacts.\n" if result["decision"] == "target_met" else
               "Stop at the iteration limit. Deliver current runnable artifacts and gaps as incomplete.\n" if result["decision"] == "iteration_limit" else
               "A further implementation cycle is available; fix observed issues before any new run.\n"))


def create_check(plan, evidence, review_path, output, previous=None):
    plan, evidence = plan.resolve(strict=True), evidence.resolve(strict=True)
    previous = previous.resolve(strict=True) if previous else None
    if any(output.resolve() == path or path in output.resolve().parents for path in (plan, evidence, previous) if path):
        raise ValueError("use a separate new check directory")
    data = check_data(plan, evidence, read(review_path.parent, review_path.name), previous, live_source=True)
    return save(output, "fidelity_check", {"fidelity-check.json": data, "report.md": report(data)})


def verify_fidelity(root):
    from copyapp.verify import checked_path
    try:
        manifest = read(root, "manifest.json")
        kind = manifest["kind"]
        names = {"fidelity-plan.json", "TASK.md"} if kind == "fidelity_plan" else {"fidelity-check.json", "report.md"}
        if (set(manifest) != {"schema_version", "platform", "kind", "status", "evidence"} or
                type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or
                manifest["platform"] != "cross_platform" or kind not in KINDS or manifest["status"] != "complete" or
                {row["path"] for row in manifest["evidence"]} != names or len(manifest["evidence"]) != 2):
            return False
        if any((root / row["path"]).is_symlink() or sha256_file(checked_path(root, row["path"])) != row["sha256"]
               for row in manifest["evidence"]):
            return False
        if kind == "fidelity_plan":
            saved = read(root, "fidelity-plan.json")
            task = resolve(saved["task"], {"mac_rebuild_plan", "agent_implementation_task"})
            expected = plan_data(task, saved["policy"]["fidelity"], saved["policy"]["max_iterations"])
            return saved == expected and (root / "TASK.md").read_text() == brief(expected)
        saved = read(root, "fidelity-check.json")
        plan = resolve(saved["plan"], {"fidelity_plan"})
        evidence = Path(saved["evidence"]["path"]).resolve(strict=True)
        if reference(evidence) != saved["evidence"]:
            return False
        # visual_context verifies complete evidence, or explicitly retains a
        # failed attempt which can only continue/stop as incomplete.
        previous = None
        if saved["previous"] is not None:
            # Check decreasing iterations before recursing, including tampered cycles.
            previous = Path(saved["previous"]["path"]).resolve(strict=True)
            if read(previous, "fidelity-check.json")["result"]["iteration"] != saved["result"]["iteration"] - 1:
                return False
            previous = resolve(saved["previous"], {"fidelity_check"})
        expected = check_data(plan, evidence, saved["review"], previous)
        return saved == expected and (root / "report.md").read_text() == report(expected)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return False
