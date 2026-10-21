"""Reviewed Mac behavior reports; consistency checks cannot certify semantics."""

import json
import re
import shutil
from pathlib import Path, PurePosixPath

from copyapp.macos.case import Case, canonical, digest


ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}\Z")
ASSERTIONS = {"expect_text", "expect_file", "expect_stopped"}


def read(root: Path, name: str):
    return json.loads((root / name).read_text())


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("expected a bounded ASCII identifier")
    return value


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 32768:
        raise ValueError("expected nonempty bounded review text")
    return value


def unique_rows(rows, name):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError("missing or oversized " + name)
    identifiers = [identifier(row["id"]) for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate " + name + " identifiers")
    return set(identifiers)


def flow_source(root: Path, flow_id: str) -> dict:
    """Return recomputed source facts, never values asserted by the reviewer."""
    from copyapp.verify import verify_case
    manifest = read(root, "manifest.json")
    if (manifest.get("kind") != "mac_playbook" or not verify_case(root) or
            manifest.get("scenario_id") != flow_id):
        raise ValueError("report needs a complete verified Mac flow with its scenario ID")
    script = read(root, "playbook.json")
    steps = [index for index, step in enumerate(script["steps"], 1) if step["action"] in ASSERTIONS]
    if not steps or manifest["behavior_assertions"] != len(steps):
        raise ValueError("each report flow needs explicit behavior assertions")
    source = read(root, "source/package/app-index.json")
    return {"id": flow_id, "manifest_sha256": digest(root / "manifest.json"),
            "source_script_sha256": digest(root / "playbook.json"),
            "package_sha256": source["package_sha256"], "app": source["app"],
            "environment_manifest_sha256": digest(root / "source/environment/manifest.json"),
            "assertion_steps": steps}


def validate_review(review: dict, sources: dict, source_roots: dict, data_roots: dict = None) -> list:
    data_roots = data_roots or {}
    canonical(review)
    if (type(review.get("schema_version")) is not int or review["schema_version"] != 2 or review.get("platform") != "macos" or
            review.get("scope") != "behavior_analysis" or
            set(review) != {"schema_version", "platform", "scope", "reviewer", "summary", "findings",
                            "flows", "capabilities", "inventory_note", "unknowns"}):
        raise ValueError("expected a Mac behavior review with explicit scope")
    text(review["reviewer"]); text(review["summary"]); text(review["inventory_note"])
    unknowns = review["unknowns"]
    if not isinstance(unknowns, list) or not unknowns or len(unknowns) > 200:
        raise ValueError("record unknown behavior explicitly; selected flows are not whole-App coverage")
    for unknown in unknowns:
        text(unknown)
    findings = review["findings"]
    finding_ids = unique_rows(findings, "findings")
    flow_ids = unique_rows(review["flows"], "flows")
    unique_rows(review["capabilities"], "capabilities")
    if flow_ids != set(sources):
        raise ValueError("review must cover exactly the supplied flow evidence")
    citations = []
    cited_data = set()
    finding_flows = {}
    for finding in findings:
        if set(finding) != {"id", "statement", "certainty", "evidence"}:
            raise ValueError("invalid finding fields")
        text(finding["statement"])
        if finding["certainty"] not in {"observed", "inferred"}:
            raise ValueError("findings must distinguish observation and inference")
        refs = finding["evidence"]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 64:
            raise ValueError("each finding needs bounded source citations")
        linked = set()
        for ref in refs:
            if set(ref) == {"data_id", "path"}:
                if ref["data_id"] not in data_roots or ref["path"] != "structure.json":
                    raise ValueError("data citations must refer to a supplied verified structure.json")
                root = data_roots[ref["data_id"]]
                citations.append({"finding_id": finding["id"], **ref, "sha256": digest(root / "structure.json")})
                cited_data.add(ref["data_id"])
                continue
            if set(ref) != {"flow_id", "path"} or ref["flow_id"] not in sources:
                raise ValueError("citation refers to an unknown flow")
            name = ref["path"]
            if (not isinstance(name, str) or str(PurePosixPath(name)) != name or
                    PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or
                    not name.startswith("steps/")):
                raise ValueError("citations must refer to captured flow-step evidence")
            root = source_roots[ref["flow_id"]]
            names = {item["path"] for item in read(root, "manifest.json")["evidence"]}
            if name not in names:
                raise ValueError("citation is not a recorded evidence file")
            citations.append({"finding_id": finding["id"], **ref, "sha256": digest(root / name)})
            linked.add(ref["flow_id"])
        finding_flows[finding["id"]] = linked
    if cited_data != set(data_roots):
        raise ValueError("each supplied data structure needs an explicit reviewed citation")
    for flow in review["flows"]:
        if set(flow) != {"id", "source_script_sha256", "expected_behavior", "findings"}:
            raise ValueError("invalid specification flow")
        source = sources[flow["id"]]
        text(flow["expected_behavior"])
        selected = flow["findings"]
        if (flow["source_script_sha256"] != source["source_script_sha256"] or
                not isinstance(selected, list) or not selected or len(set(selected)) != len(selected) or
                not set(selected).issubset(finding_ids) or
                any(flow["id"] not in finding_flows[item] for item in selected)):
            raise ValueError("specification flow has no matching reviewed source")
    for capability in review["capabilities"]:
        if set(capability) != {"id", "title", "flow_ids", "disposition", "reason"}:
            raise ValueError("invalid known-capability inventory entry")
        text(capability["title"]); text(capability["reason"])
        linked = capability["flow_ids"]
        if (capability["disposition"] not in {"available", "deferred", "blocked"} or
                not isinstance(linked, list) or len(set(linked)) != len(linked) or
                not set(linked).issubset(flow_ids) or
                (capability["disposition"] == "available" and not linked)):
            raise ValueError("invalid capability scope or evidence links")
    return citations


def specification(review: dict, sources: dict) -> dict:
    first = sources[sorted(sources)[0]]
    return {"schema_version": 2, "platform": "macos", "scope": "behavior_analysis",
            "app": first["app"], "package_sha256": first["package_sha256"],
            "environment_manifest_sha256": first["environment_manifest_sha256"],
            "flows": review["flows"], "capabilities": review["capabilities"],
            "coverage_basis": "reviewed_known_inventory_only", "inventory_note": review["inventory_note"],
            "unknowns": review["unknowns"], "function_analysis": "not_performed"}


def report_markdown(review: dict, citations: list) -> str:
    # Review prose stays verbatim; links are generated only from validated paths.
    lines = ["# Mac behavior analysis", "", review["summary"], "",
             "Reviewer (self-declared): " + review["reviewer"], "",
             "Scope: selected behavior evidence. Native function analysis was not performed.", "",
             "## Findings", ""]
    for finding in review["findings"]:
        lines.extend(["### " + finding["id"] + " (" + finding["certainty"] + ")", "", finding["statement"], ""])
        for cite in citations:
            if cite["finding_id"] == finding["id"]:
                from urllib.parse import quote
                source_id = cite.get("flow_id", cite.get("data_id"))
                prefix = "evidence/" if "flow_id" in cite else "data-evidence/"
                path = prefix + source_id + "/" + cite["path"]
                lines.append("- [" + source_id + ": " + cite["path"] + "](" + quote(path) + ")")
        lines.append("")
    lines.extend(["## Known inventory", "", review["inventory_note"], ""])
    for capability in review["capabilities"]:
        lines.append("- " + capability["id"] + ": " + capability["title"] + " — " +
                     capability["disposition"] + "; " + capability["reason"])
    lines.extend(["", "## Unknown behavior", ""] + ["- " + value for value in review["unknowns"]])
    if any("data_id" in cite for cite in citations):
        lines.extend(["", "Data citations describe saved key/type or SQLite structure only. They do not prove",
                      "App ownership, transactional database consistency or simultaneous UI/file observations.",
                      "Scalar values, rows and SQL bodies were omitted; structure names may themselves be private."])
    lines.extend(["", "Hash verification checks source consistency, not the truth or completeness of this review.", ""])
    return "\n".join(lines)


def data_sources(data: dict, sources: dict, roots: dict) -> tuple:
    from copyapp.macos.data_schema import report_data_source
    if not isinstance(data, dict) or len(data) > 12:
        raise ValueError("supply at most twelve named Mac data structure cases")
    paths, records = {}, {}
    for source_id, value in data.items():
        identifier(source_id)
        root = Path(value).resolve(strict=True)
        record = report_data_source(root, source_id)
        signatures = {(row["package_sha256"], row["environment_manifest_sha256"],
                       read(roots[key], "playbook.json")["app_path"], row["app"]["bundle_id"]) for key, row in sources.items()}
        if signatures != {(record["package_sha256"], record["environment_manifest_sha256"],
                           record["guest_app_path"], record["bundle_id"])}:
            raise ValueError("data evidence must identify the same exact App, package and environment as report flows")
        paths[source_id], records[source_id] = root, record
    return paths, records


def report(flows: dict, review_path: Path, output: Path, *, discovery: Path = None, data: dict = None) -> Path:
    if discovery is not None:
        from copyapp.macos.discovery import accepted_flows
        if flows:
            raise ValueError("choose explicit flows or an accepted discovery case")
        discovery = discovery.resolve(strict=True)
        if output.resolve() == discovery or discovery in output.resolve().parents:
            raise ValueError("report must be outside its source discovery")
        flows = accepted_flows(discovery)
    if not isinstance(flows, dict) or not 1 <= len(flows) <= 12:
        raise ValueError("supply one to twelve named Mac flow cases")
    roots, sources = {}, {}
    for flow_id, value in flows.items():
        identifier(flow_id)
        root = Path(value).resolve(strict=True)
        if output.resolve() == root or root in output.resolve().parents:
            raise ValueError("report must be outside its source cases")
        roots[flow_id] = root
        sources[flow_id] = flow_source(root, flow_id)
    signatures = {(row["package_sha256"], row["environment_manifest_sha256"]) for row in sources.values()}
    if len(signatures) != 1:
        raise ValueError("report flows must use the same package and registered environment")
    data_roots, data_records = data_sources(data if data is not None else {}, sources, roots)
    if any(output.resolve() == root or root in output.resolve().parents for root in data_roots.values()):
        raise ValueError("report must be outside its data structure inputs")
    review = json.loads(review_path.read_text())
    citations = validate_review(review, sources, roots, data_roots)
    link = None
    if discovery is not None:
        from copyapp.macos.discovery import report_link
        link = report_link(discovery, sources, review)
    case = Case(output, "mac_behavior_report")
    try:
        if discovery is not None:
            shutil.copytree(discovery, case.root / "discovery", symlinks=True)
            case.record("discovery/manifest.json")
            case.add("discovery-link.json", link)
        if data_records:
            for source_id, root in data_roots.items():
                shutil.copytree(root, case.root / "data-evidence" / source_id, symlinks=True)
                case.record("data-evidence/" + source_id + "/manifest.json")
            case.add("data-sources.json", [data_records[key] for key in sorted(data_records)])
        for flow_id, root in roots.items():
            shutil.copytree(root, case.root / "evidence" / flow_id, symlinks=True)
            case.record("evidence/" + flow_id + "/manifest.json")
        case.add("sources.json", [sources[key] for key in sorted(sources)])
        case.add("review.json", review)
        case.add("citations.json", citations)
        case.add("feature-spec.json", specification(review, sources))
        case.add("report.md", report_markdown(review, citations).encode("utf-8"), binary=True)
        case.finish("complete", scope="behavior_analysis")
        if not verify_report(case.root, case.manifest, {row["path"] for row in case.manifest["evidence"]}):
            raise ValueError("copied report evidence changed during creation")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="behavior_analysis")
        raise


def verify_report(root: Path, manifest: dict, names: set) -> bool:
    required = {"sources.json", "review.json", "citations.json", "feature-spec.json", "report.md"}
    if (manifest.get("status") != "complete" or manifest.get("scope") != "behavior_analysis" or
            not required.issubset(names)):
        return False
    saved = read(root, "sources.json")
    if not isinstance(saved, list) or not 1 <= len(saved) <= 12:
        return False
    sources, roots = {}, {}
    for source in saved:
        flow_id = identifier(source["id"])
        if flow_id in sources or "evidence/" + flow_id + "/manifest.json" not in names:
            return False
        roots[flow_id] = root / "evidence" / flow_id
        actual = flow_source(roots[flow_id], flow_id)
        if actual != source:
            return False
        sources[flow_id] = actual
    if (saved != [sources[key] for key in sorted(sources)] or
            len({(row["package_sha256"], row["environment_manifest_sha256"]) for row in saved}) != 1):
        return False
    review = read(root, "review.json")
    data_roots = {}
    if "data-sources.json" in names or (root / "data-evidence").exists() or (root / "data-sources.json").exists():
        if "data-sources.json" not in names:
            return False
        saved_data = read(root, "data-sources.json")
        if not isinstance(saved_data, list) or not 1 <= len(saved_data) <= 12:
            return False
        for source in saved_data:
            source_id = identifier(source["id"])
            if source_id in data_roots or "data-evidence/" + source_id + "/manifest.json" not in names:
                return False
            data_roots[source_id] = root / "data-evidence" / source_id
        data_roots, actual = data_sources(data_roots, sources, roots)
        if saved_data != [actual[key] for key in sorted(actual)]:
            return False
    citations = validate_review(review, sources, roots, data_roots)
    discovery_fields = {"discovery/manifest.json", "discovery-link.json"}
    if discovery_fields & names or (root / "discovery").exists() or (root / "discovery-link.json").exists():
        from copyapp.macos.discovery import report_link
        if (not discovery_fields.issubset(names) or
                read(root, "discovery-link.json") != report_link(root / "discovery", sources, review)):
            return False
    return (read(root, "citations.json") == citations and
            read(root, "feature-spec.json") == specification(review, sources) and
            (root / "report.md").read_text() == report_markdown(review, citations))
