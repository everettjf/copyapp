"""Versioned, source-linked capability targets and reviewed rebuild coverage."""

import io
import json
import re
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.verify import sha256_file, verify_case


CAPABILITY_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")
SCOPES = {"selected", "deferred", "blocked"}
RESULTS = {"verified", "partial", "failed", "untested"}


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _verified(path: Path) -> None:
    with redirect_stdout(io.StringIO()):
        if not verify_case(path):
            raise ValueError(f"source case failed verification: {path}")


def _percent(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value.strip()


def _cell(value: object) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def _inventory(inventory: dict, report_spec: dict, selected_flows: set[str]) -> tuple[int, int]:
    if (inventory.get("schema_version") != 1 or
            inventory.get("target_bundle_id") != report_spec.get("target_bundle_id") or
            inventory.get("rebuilt_bundle_id") != report_spec.get("rebuilt_bundle_id")):
        raise ValueError("inventory schema or App identity differs from the report")
    _text(inventory.get("rationale"), "target rationale")
    unknowns = inventory.get("unknowns")
    if not isinstance(unknowns, list) or any(not isinstance(x, str) or not x.strip()
                                             for x in unknowns):
        raise ValueError("unknowns must be a list of nonempty descriptions")
    capabilities = inventory.get("capabilities")
    if not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 200:
        raise ValueError("inventory needs 1–200 capabilities")
    report_flows = {item["id"] for item in report_spec["flows"]}
    identifiers = set()
    owned_flows = set()
    total = selected_weight = 0
    for item in capabilities:
        if not isinstance(item, dict):
            raise ValueError("capability must be an object")
        identifier = item.get("id")
        if (not isinstance(identifier, str) or
                not CAPABILITY_ID.fullmatch(identifier) or identifier in identifiers):
            raise ValueError("capability IDs must be unique and stable")
        identifiers.add(identifier)
        _text(item.get("name"), f"{identifier} name")
        _text(item.get("acceptance"), f"{identifier} acceptance")
        _text(item.get("basis"), f"{identifier} evidence basis")
        weight = item.get("weight")
        if type(weight) is not int or not 1 <= weight <= 5:
            raise ValueError(f"{identifier} weight must be an integer from 1 to 5")
        scope = item.get("scope")
        if scope not in SCOPES:
            raise ValueError(f"{identifier} has invalid scope")
        flows = item.get("flow_ids")
        if (not isinstance(flows, list) or
                any(not isinstance(x, str) for x in flows) or
                len(set(flows)) != len(flows) or
                any(x not in report_flows or x in owned_flows for x in flows)):
            raise ValueError(f"{identifier} has missing, duplicate or shared report flows")
        owned_flows.update(flows)
        if scope == "selected":
            if not flows or not set(flows) <= selected_flows:
                raise ValueError(f"{identifier} selected flows are absent from rebuild plans")
            selected_weight += weight
        elif set(flows) & selected_flows:
            raise ValueError(f"{identifier} is deferred but its flow is selected")
        if scope != "selected":
            _text(item.get("reason"), f"{identifier} defer/block reason")
        total += weight
    if not selected_weight or owned_flows & selected_flows != selected_flows:
        raise ValueError("every selected rebuild flow needs exactly one selected capability")
    return total, selected_weight


def _source_plans(report: Path, plans: list[Path]) -> tuple[list[dict], set[str]]:
    if not plans or len(set(plans)) != len(plans):
        raise ValueError("provide distinct rebuild plan cases")
    report_index_hash = sha256_file(report / "report-index.json")
    selected = set()
    sources = []
    for plan in plans:
        _verified(plan)
        data = _read(plan / "rebuild-plan.json")
        spec_hash = sha256_file(report / "feature-spec.json")
        if (data.get("kind") != "rebuild_plan" or data.get("status") != "complete" or
                data.get("source_report_index_sha256") != report_index_hash or
                data.get("feature_spec_sha256") != spec_hash or
                not isinstance(data.get("flows"), list)):
            raise ValueError(f"rebuild plan is not linked to the reviewed report: {plan}")
        flow_ids = [item.get("flow_id") for item in data["flows"]]
        if (not flow_ids or any(not isinstance(x, str) for x in flow_ids) or
                len(flow_ids) != len(set(flow_ids)) or
                selected.intersection(flow_ids)):
            raise ValueError("rebuild plans contain duplicate selected flows")
        selected.update(flow_ids)
        sources.append({"case": str(plan),
                        "manifest_sha256": sha256_file(plan / "manifest.json"),
                        "rebuild_plan_sha256": sha256_file(plan / "rebuild-plan.json"),
                        "flow_ids": flow_ids})
    return sources, selected


def _plan_inputs(report: Path, plans: list[Path], inventory: dict,
                 previous: Optional[Path]) -> dict:
    _verified(report)
    spec = _read(report / "feature-spec.json")
    sources, selected = _source_plans(report, plans)
    total, target = _inventory(inventory, spec, selected)
    previous_source = None
    revision = 1
    if previous is not None:
        _verified(previous)
        old = _read(previous / "coverage-plan.json")
        if (old.get("kind") != "coverage_plan" or
                old.get("source_report") != str(report) or
                old.get("source_report_index_sha256") !=
                sha256_file(report / "report-index.json")):
            raise ValueError("previous target belongs to a different report")
        _text(inventory.get("revision_reason"), "revision reason")
        earlier = _read(previous / "inventory.json")
        current_by_id = {item["id"]: item for item in inventory["capabilities"]}
        for item in earlier["capabilities"]:
            current = current_by_id.get(item["id"])
            if (current is None or
                    any(current[key] != item[key]
                        for key in ("name", "acceptance", "basis", "weight")) or
                    not set(item["flow_ids"]) <= set(current["flow_ids"])):
                raise ValueError("revision cannot remove or weaken a known capability")
        revision = old["revision"] + 1
        previous_source = {"case": str(previous),
                           "manifest_sha256": sha256_file(previous / "manifest.json")}
    return {"schema_version": 1, "kind": "coverage_plan", "revision": revision,
            "source_report": str(report),
            "source_report_index_sha256": sha256_file(report / "report-index.json"),
            "feature_spec_sha256": sha256_file(report / "feature-spec.json"),
            "rebuild_plans": sources, "previous": previous_source,
            "known_weight": total, "selected_weight": target,
            "target_percent": _percent(target, total)}


def create_coverage_plan(report: Path, plans: list[Path], inventory_path: Path,
                         output: Path, previous: Optional[Path] = None) -> Path:
    """Freeze one target; a later revision keeps the old verified case intact."""
    report = report.resolve(strict=True)
    plans = [path.resolve(strict=True) for path in plans]
    inventory_path = inventory_path.resolve(strict=True)
    previous = previous.resolve(strict=True) if previous else None
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"coverage plan output is not empty: {output}")
    inventory = _read(inventory_path)
    record = _plan_inputs(report, plans, inventory, previous)
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "inventory.json", inventory)
    record["inventory_sha256"] = sha256_file(output / "inventory.json")
    record["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(output / "coverage-plan.json", record)
    lines = ["# Rebuild coverage target", "",
             f"- Revision: {record['revision']}; target: {record['target_percent']}% "
             f"of the known-capability weight ({record['selected_weight']}/{record['known_weight']}).",
             f"- Rationale: {inventory['rationale']}",
             "- This denominator is a reviewed known-capability inventory, not a claim that every App feature is known.",
             "", "| Capability | Weight | Scope | Report flows | Reason |",
             "| --- | ---: | --- | --- | --- |"]
    if previous is not None:
        old = _read(previous / "coverage-plan.json")
        lines[5:5] = [f"- Previous target: {old['target_percent']}% (revision {old['revision']}).",
                       f"- Revision reason: {inventory['revision_reason']}"]
    for item in inventory["capabilities"]:
        lines.append(f"| `{item['id']}` {_cell(item['name'])} | {item['weight']} | "
                     f"{item['scope']} | {', '.join(item['flow_ids']) or '—'} | "
                     f"{_cell(item.get('reason', '—'))} |")
    lines += ["", "Unknown areas: " + ("; ".join(inventory["unknowns"]) or "none declared"),
              "", "The percentage is a target. Use `copyapp coverage-delivery` with verified "
              "device deliveries and explicit per-capability review for achieved coverage.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {"schema_version": 1, "kind": "coverage_plan",
        "status": "complete", "evidence": [
            {"path": name, "sha256": sha256_file(output / name)}
            for name in ("inventory.json", "coverage-plan.json", "report.md")]})
    return output / "report.md"


def validate_coverage_plan(root: Path) -> bool:
    try:
        record = _read(root / "coverage-plan.json")
        inventory = _read(root / "inventory.json")
        report = Path(record["source_report"]).resolve(strict=True)
        plans = [Path(item["case"]).resolve(strict=True)
                 for item in record["rebuild_plans"]]
        previous = (Path(record["previous"]["case"]).resolve(strict=True)
                    if record.get("previous") else None)
        if root.resolve() in [report, *plans, previous]:
            return False
        expected = _plan_inputs(report, plans, inventory, previous)
        return (all(record.get(key) == value for key, value in expected.items()) and
                record.get("inventory_sha256") == sha256_file(root / "inventory.json"))
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _delivery_inputs(plan: Path, deliveries: list[Path], review: dict) -> dict:
    _verified(plan)
    target = _read(plan / "coverage-plan.json")
    inventory = _read(plan / "inventory.json")
    if not deliveries or len(set(deliveries)) != len(deliveries):
        raise ValueError("provide distinct agent delivery cases")
    plan_hashes = {item["rebuild_plan_sha256"] for item in target["rebuild_plans"]}
    selected_ids = {flow for item in target["rebuild_plans"] for flow in item["flow_ids"]}
    observations = {}
    sources = []
    for delivery in deliveries:
        _verified(delivery)
        data = _read(delivery / "delivery.json")
        task = _read(Path(data["task_case"]) / "task.json")
        if (data.get("kind") != "agent_delivery" or
                data.get("target_bundle_id") != inventory["target_bundle_id"] or
                data.get("rebuilt_bundle_id") != inventory["rebuilt_bundle_id"] or
                task.get("report_index_sha256") != target["source_report_index_sha256"] or
                task.get("rebuild_plan_sha256") not in plan_hashes):
            raise ValueError(f"delivery is not linked to the coverage target: {delivery}")
        for flow in data["flow_results"]:
            identifier = flow["id"]
            if identifier not in selected_ids or identifier in observations:
                raise ValueError("delivery has unknown or duplicate target flows")
            observations[identifier] = {
                "delivery": str(delivery),
                "behavior_passed": (flow.get("script_assertions_status") == "passed" or
                                    flow.get("final_view_status") == "passed"),
                "visual_review": flow.get("visual_review_status", "unreviewed")}
        sources.append({"case": str(delivery),
                        "manifest_sha256": sha256_file(delivery / "manifest.json")})
    if (review.get("schema_version") != 1 or
            not isinstance(review.get("capabilities"), list)):
        raise ValueError("coverage review has invalid schema")
    decisions = {}
    for decision in review["capabilities"]:
        if not isinstance(decision, dict):
            raise ValueError("coverage decision must be an object")
        identifier = decision.get("id")
        if identifier in decisions or decision.get("result") not in RESULTS:
            raise ValueError("coverage review has duplicate IDs or invalid result")
        _text(decision.get("notes"), f"{identifier} review notes")
        decisions[identifier] = decision
    if set(decisions) != {item["id"] for item in inventory["capabilities"]}:
        raise ValueError("review must address every inventoried capability")
    verified_weight = 0
    rows = []
    for item in inventory["capabilities"]:
        result = decisions[item["id"]]["result"]
        flows = item["flow_ids"]
        if item["scope"] != "selected" and result != "untested":
            raise ValueError("deferred or blocked capability cannot be counted as verified")
        checks = [observations.get(flow) for flow in flows]
        machine_ready = bool(checks) and all(
            check is not None and check["behavior_passed"] and
            check["visual_review"] in ("match", "minor_difference")
            for check in checks)
        if result == "verified" and not machine_ready:
            raise ValueError(f"{item['id']} has no complete behavior and visual evidence")
        if result == "verified":
            verified_weight += item["weight"]
        rows.append({"id": item["id"], "scope": item["scope"],
                     "weight": item["weight"], "result": result,
                     "flow_ids": flows, "flow_gate_passed": machine_ready,
                     "notes": decisions[item["id"]]["notes"]})
    selected_weight = target["selected_weight"]
    known_weight = target["known_weight"]
    return {"schema_version": 1, "kind": "coverage_delivery",
            "status": "target_met" if verified_weight == selected_weight else "target_not_met",
            "coverage_plan": str(plan),
            "coverage_plan_manifest_sha256": sha256_file(plan / "manifest.json"),
            "target_revision": target["revision"],
            "previous_target_percent": (
                _read(Path(target["previous"]["case"]) / "coverage-plan.json")["target_percent"]
                if target["previous"] else None),
            "revision_reason": inventory.get("revision_reason") if target["previous"] else None,
            "agent_deliveries": sources,
            "known_weight": known_weight, "selected_weight": selected_weight,
            "verified_weight": verified_weight,
            "target_percent": target["target_percent"],
            "milestone_completion_percent": _percent(verified_weight, selected_weight),
            "verified_known_percent": _percent(verified_weight, known_weight),
            "capabilities": rows, "unknowns": inventory["unknowns"]}


def create_coverage_delivery(plan: Path, deliveries: list[Path], review_path: Path,
                             output: Path) -> Path:
    plan = plan.resolve(strict=True)
    deliveries = [path.resolve(strict=True) for path in deliveries]
    review_path = review_path.resolve(strict=True)
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"coverage delivery output is not empty: {output}")
    review = _read(review_path)
    record = _delivery_inputs(plan, deliveries, review)
    output.mkdir(parents=True, exist_ok=True)
    _write(output / "review.json", review)
    record["review_sha256"] = sha256_file(output / "review.json")
    record["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(output / "coverage-delivery.json", record)
    lines = ["# Rebuild coverage delivery", "",
             f"- Target revision {record['target_revision']}: {record['target_percent']}% "
             "of known capability weight.",
             f"- Milestone completion: {record['milestone_completion_percent']}% "
             f"({record['verified_weight']}/{record['selected_weight']} selected weight).",
             f"- Verified known coverage: {record['verified_known_percent']}% "
             f"({record['verified_weight']}/{record['known_weight']} known weight).",
             "- These figures cover the reviewed known inventory and cited device flows; "
             "unknown App behavior is outside the denominator.", "",
             "| Capability | Scope | Result | Flow gate | Review note |",
             "| --- | --- | --- | --- | --- |"]
    if record["previous_target_percent"] is not None:
        lines[3:3] = [f"- Previous target: {record['previous_target_percent']}%; "
                      f"revision reason: {record['revision_reason']}"]
    for item in record["capabilities"]:
        lines.append(f"| `{item['id']}` | {item['scope']} | {item['result']} | "
                     f"{item['flow_gate_passed']} | {_cell(item['notes'])} |")
    lines += ["", "Unknown areas: " + ("; ".join(record["unknowns"]) or "none declared"),
              "", "Review notes are human judgments. The verifier checks source identity, "
              "arithmetic and selected-flow gates, not unseen App semantics.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    _write(output / "manifest.json", {"schema_version": 1, "kind": "coverage_delivery",
        "status": record["status"], "evidence": [
            {"path": name, "sha256": sha256_file(output / name)}
            for name in ("review.json", "coverage-delivery.json", "report.md")]})
    return output / "report.md"


def validate_coverage_delivery(root: Path) -> bool:
    try:
        record = _read(root / "coverage-delivery.json")
        review = _read(root / "review.json")
        plan = Path(record["coverage_plan"]).resolve(strict=True)
        deliveries = [Path(item["case"]).resolve(strict=True)
                      for item in record["agent_deliveries"]]
        if root.resolve() in [plan, *deliveries]:
            return False
        expected = _delivery_inputs(plan, deliveries, review)
        return (all(record.get(key) == value for key, value in expected.items()) and
                record.get("review_sha256") == sha256_file(root / "review.json"))
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
