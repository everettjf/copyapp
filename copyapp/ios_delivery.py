"""Source and flow checks for reviewed UI behavior; separate from deep delivery."""

import io
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.verify import sha256_file, verify_case


def behavior_delivery_links(task: Path, report: Path) -> dict:
    task, report = task.resolve(strict=True), report.resolve(strict=True)
    if (task == report or read_json(task / "manifest.json").get("kind") != "ios_analysis" or
            read_json(report / "manifest.json").get("kind") != "ios_behavior_report"):
        raise ValueError("UI delivery requires separate UI analysis and reviewed behavior report cases")
    with redirect_stdout(io.StringIO()):
        if not verify_case(task) or not verify_case(report):
            raise ValueError("UI delivery source verification failed")
    index, spec = read_json(report / "report-index.json"), read_json(report / "feature-spec.json")
    source = read_json(task / "analysis.json")
    if (source.get("status") != "complete" or
            Path(index["source_case"]).resolve() != task or
            index["source_case_index_sha256"] != sha256_file(task / "manifest.json")):
        raise ValueError("reviewed report belongs to a different UI analysis")
    required = {item["id"]: item["source_script_sha256"] for item in source["flows"]}
    final = {item["id"]: item["source_script_sha256"] for item in spec["flows"]}
    if final != required:
        raise ValueError("UI delivery requires a reviewed assertion for every collected flow")
    return {"task_case": str(task), "task_manifest_sha256": sha256_file(task / "manifest.json"),
            "report_case": str(report), "report_manifest_sha256": sha256_file(report / "manifest.json"),
            "report_index_sha256": sha256_file(report / "report-index.json"),
            "target_bundle_id": spec["target_bundle_id"],
            "flow_coverage": [{"flow_id": item["id"], "source_script_sha256": item["source_script_sha256"],
                               "assertion_count": len(item["expected"])} for item in spec["flows"]]}


def create_behavior_delivery(task: Path, report: Path, output: Path) -> Path:
    if output.exists():
        raise FileExistsError(output)
    result = behavior_delivery_links(task, report)
    output.mkdir(parents=True)
    for name in ("findings.json", "feature-spec.json"):
        shutil.copyfile(report / name, output / ("reviewed-" + name))
    write_json(output / "delivery.json", result)
    (output / "report.md").write_text(
        "# Reviewed UI behavior delivery\n\n"
        f"App: `{result['target_bundle_id']}`. Source-linked flows: {len(result['flow_coverage'])}.\n\n"
        "All collected scripts have reviewed assertions in the report. This checks source identity and "
        "selected-flow coverage; it does not certify function semantics, report reasoning or whole-App parity.\n",
        encoding="utf-8")
    seal_case(output, "ios_behavior_delivery", status="source_linked_report_ready_for_review",
              bundle_id=result["target_bundle_id"])
    return output / "report.md"


def validate_behavior_delivery(root: Path, manifest: dict) -> bool:
    result = read_json(root / "delivery.json")
    task, report = Path(result["task_case"]), Path(result["report_case"])
    return (manifest.get("status") == "source_linked_report_ready_for_review" and
            manifest.get("bundle_id") == result["target_bundle_id"] and
            result == behavior_delivery_links(task, report) and
            all((root / ("reviewed-" + name)).read_bytes() == (report / name).read_bytes()
                for name in ("findings.json", "feature-spec.json")))
