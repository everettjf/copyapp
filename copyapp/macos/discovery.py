"""Accept reviewed representative Mac flows without launching another agent."""

import hashlib
import shutil
from pathlib import Path

from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.report import flow_source, identifier, read, text, unique_rows


def discovery_sources(flows: dict) -> tuple:
    if not isinstance(flows, dict) or not 3 <= len(flows) <= 12:
        raise ValueError("discovery needs three to twelve completed representative Mac flows")
    roots, sources, fingerprints = {}, {}, set()
    for flow_id, value in flows.items():
        identifier(flow_id)
        root = Path(value).resolve(strict=True)
        source = flow_source(root, flow_id)
        script = read(root, "playbook.json")
        # Renaming one replay does not make it a different representative flow.
        effective = {key: value for key, value in script.items() if key != "scenario_id"}
        fingerprint = hashlib.sha256(canonical(effective)).hexdigest()
        if fingerprint in fingerprints:
            raise ValueError("discovery contains duplicate effective playbooks")
        fingerprints.add(fingerprint)
        roots[flow_id] = root
        sources[flow_id] = {**source, "guest_app_path": script["app_path"],
                            "effective_script_sha256": fingerprint}
    if len({(row["package_sha256"], row["environment_manifest_sha256"], row["guest_app_path"])
            for row in sources.values()}) != 1:
        raise ValueError("discovery flows must use one exact original App and registered environment")
    return roots, sources


def validate_review(review: dict, sources: dict):
    if (set(review) != {"schema_version", "platform", "scope", "reviewer", "selection_note",
                        "flows", "capabilities", "inventory_note", "unknowns"} or
            type(review.get("schema_version")) is not int or review["schema_version"] != 2 or
            review.get("platform") != "macos" or review.get("scope") != "representative_flow_discovery"):
        raise ValueError("expected a reviewed Mac discovery inventory")
    for field in ("reviewer", "selection_note", "inventory_note"):
        text(review[field])
    if unique_rows(review["flows"], "discovery flows") != set(sources):
        raise ValueError("discovery review must cover exactly the accepted replays")
    for row in review["flows"]:
        if set(row) != {"id", "source_script_sha256", "purpose", "selection_reason"}:
            raise ValueError("each discovered flow needs its source hash, purpose and selection reason")
        text(row["purpose"]); text(row["selection_reason"])
        if row["source_script_sha256"] != sources[row["id"]]["source_script_sha256"]:
            raise ValueError("discovery flow review refers to a different saved script")
    unique_rows(review["capabilities"], "discovery capabilities")
    covered = set()
    for row in review["capabilities"]:
        if set(row) != {"id", "title", "flow_ids", "disposition", "reason"}:
            raise ValueError("invalid discovered capability inventory")
        text(row["title"]); text(row["reason"])
        linked = row["flow_ids"]
        if (row["disposition"] not in {"available", "deferred", "blocked"} or
                not isinstance(linked, list) or any(not isinstance(value, str) for value in linked) or
                len(set(linked)) != len(linked) or not set(linked).issubset(sources) or
                (row["disposition"] == "available" and not linked)):
            raise ValueError("discovered capabilities need explicit disposition and evidence links")
        if row["disposition"] == "available":
            covered.update(linked)
    if covered != set(sources):
        raise ValueError("every discovered flow must support an available known capability")
    unknowns = review["unknowns"]
    if not isinstance(unknowns, list) or not 1 <= len(unknowns) <= 200:
        raise ValueError("record unknown behavior; discovery does not establish whole-App completeness")
    for value in unknowns: text(value)


def record(sources: dict) -> dict:
    first = sources[sorted(sources)[0]]
    return {"schema_version": 2, "platform": "macos", "scope": "representative_flow_discovery",
            "readiness": "ready_for_behavior_review", "selected_flow_ids": sorted(sources),
            "flow_count": len(sources), "app": first["app"], "guest_app_path": first["guest_app_path"],
            "package_sha256": first["package_sha256"],
            "environment_manifest_sha256": first["environment_manifest_sha256"],
            "review_truth_verified": False, "whole_app_coverage_verified": False,
            "reconstruction_verified": False}


def task(review: dict, sources: dict) -> str:
    from urllib.parse import quote
    lines = ["# Review discovered Mac behavior", "",
             "Readiness: accepted representative flow inputs. No semantic report or reconstruction is complete.", "",
             "Read review.json, sources.json and every linked flow's raw evidence. The discovery",
             "reviewer and selection reasons are self-declared; hashes cannot certify their truth.", "",
             "Continue in the current agent session. Do not launch another coding-agent CLI.", "",
             "Write the formal behavior review with observed/inferred findings and step citations.",
             "Use mac report --discovery <THIS_CASE> --review <REVIEW_JSON> --out <NEW_CASE>.",
             "Retain all discovered capability IDs in the report, including deferred and blocked ones.",
             "Explain changed dispositions and newly found capabilities. Review all recorded unknowns",
             "and carry unresolved ones into the formal report; source checks cannot decide that semantics.", "",
             "## Accepted representative flows", ""]
    by_id = {row["id"]: row for row in review["flows"]}
    for flow_id in sorted(sources):
        row = by_id[flow_id]
        prefix = "flows/" + flow_id
        lines.extend(["- " + flow_id + ": " + row["purpose"],
                      "  " + row["selection_reason"],
                      "  [Saved playbook](" + quote(prefix + "/playbook.json") + ") · " +
                      "[Evidence manifest](" + quote(prefix + "/manifest.json") + ")"])
    lines.extend(["", "## Known inventory", "", review["inventory_note"], ""])
    for row in review["capabilities"]:
        lines.append("- " + row["id"] + ": " + row["title"] + " — " + row["disposition"] + "; " + row["reason"])
    lines.extend(["", "## Recorded unknowns", ""] + ["- " + value for value in review["unknowns"]] + [""])
    return "\n".join(lines)


def discover_check(flows: dict, review_path: Path, output: Path) -> Path:
    roots, sources = discovery_sources(flows)
    for root in roots.values():
        if output.resolve() == root or root in output.resolve().parents:
            raise ValueError("discovery must be outside its source flows")
    review = read(review_path.parent, review_path.name)
    validate_review(review, sources)
    case = Case(output, "mac_discovery")
    try:
        for flow_id, root in roots.items():
            shutil.copytree(root, case.root / "flows" / flow_id, symlinks=True)
            case.record("flows/" + flow_id + "/manifest.json")
        case.add("sources.json", [sources[key] for key in sorted(sources)])
        case.add("review.json", review)
        case.add("discovery.json", record(sources))
        case.add("TASK.md", task(review, sources).encode("utf-8"), binary=True)
        case.finish("complete", scope="representative_flow_discovery", readiness="ready_for_behavior_review")
        from copyapp.verify import verify_case
        if not verify_case(case.root):
            raise ValueError("copied discovery evidence changed during acceptance")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="representative_flow_discovery")
        raise


def validate_discovery(root: Path, manifest: dict, names: set) -> bool:
    if (manifest.get("status") != "complete" or manifest.get("scope") != "representative_flow_discovery" or
            manifest.get("readiness") != "ready_for_behavior_review" or
            not {"sources.json", "review.json", "discovery.json", "TASK.md"}.issubset(names)):
        return False
    saved = read(root, "sources.json")
    if not isinstance(saved, list) or not 3 <= len(saved) <= 12:
        return False
    flows = {}
    for source in saved:
        flow_id = identifier(source["id"])
        if flow_id in flows or "flows/" + flow_id + "/manifest.json" not in names:
            return False
        flows[flow_id] = root / "flows" / flow_id
    _, sources = discovery_sources(flows)
    review = read(root, "review.json")
    validate_review(review, sources)
    return (saved == [sources[key] for key in sorted(sources)] and read(root, "discovery.json") == record(sources) and
            (root / "TASK.md").read_text() == task(review, sources))


def accepted_flows(root: Path) -> dict:
    from copyapp.verify import verify_case
    if not verify_case(root) or read(root, "manifest.json").get("kind") != "mac_discovery":
        raise ValueError("a verified representative Mac discovery case is required")
    return {flow_id: root / "flows" / flow_id for flow_id in read(root, "discovery.json")["selected_flow_ids"]}


def report_link(discovery: Path, sources: dict, review: dict) -> dict:
    flows = accepted_flows(discovery)
    if set(flows) != set(sources) or any(flow_source(root, flow_id) != sources[flow_id] for flow_id, root in flows.items()):
        raise ValueError("report must use the discovery's exact accepted replay evidence")
    inventory = {row["id"] for row in read(discovery, "review.json")["capabilities"]}
    if not inventory.issubset(row["id"] for row in review["capabilities"]):
        raise ValueError("formal report cannot silently drop discovered known capabilities")
    return {"discovery_manifest_sha256": digest(discovery / "manifest.json"),
            "accepted_flow_ids": sorted(flows), "discovered_capability_ids": sorted(inventory)}
