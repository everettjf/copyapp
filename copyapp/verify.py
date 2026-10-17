"""Check saved case files against the hashes recorded during acquisition."""

import hashlib
import io
import json
import posixpath
import re
import sqlite3
import tarfile
from contextlib import redirect_stdout
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable
from zipfile import BadZipFile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_path(root: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if name.is_absolute() or not name.parts or ".." in name.parts:
        raise ValueError(f"invalid evidence path: {relative}")
    path = root.joinpath(*name.parts).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(f"evidence path escapes case: {relative}")
    return path


def compare(root: Path, records: Iterable[Dict[str, str]]) -> bool:
    ok = True
    for item in records:
        relative = str(item["path"])
        try:
            path = checked_path(root, relative)
            match = path.is_file() and sha256_file(path) == item["sha256"]
        except (OSError, ValueError):
            match = False
        print(f"{'OK' if match else 'MISMATCH'} {relative}")
        ok &= match
    return ok


def verify_survey(directory: Path) -> bool:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    return compare(directory, manifest["evidence"])


def verify_acquisition(directory: Path) -> bool:
    manifest = json.loads((directory / "acquisition.json").read_text(encoding="utf-8"))
    app_name = posixpath.basename(manifest["remote_bundle_path"])
    if not app_name.endswith(".app") or "/" in app_name:
        raise ValueError("invalid acquired app name")
    records = [{"path": "bundle/" + app_name + "/" + item["relative"],
                "sha256": item["sha256"]} for item in manifest["files"]]
    records.append({"path": "bundle-snapshot.ipa", "sha256": manifest["snapshot_sha256"]})
    return compare(directory, records)


def install_transport_complete(record: dict) -> bool:
    """Check the saved installation method without conflating USB and TrollStore."""
    transport = record.get("transport", "trollstore")
    if transport == "trollstore":
        return (record.get("helper_exit_code") == 0 and
                record.get("staged_sha256") == record.get("ipa_sha256"))
    if transport == "usb":
        return (record.get("usb_install_completed") is True and
                record.get("installed_profile_validated") is True and
                isinstance(record.get("installed_path"), str) and
                record["installed_path"].startswith("/") and
                record["installed_path"].endswith(".app"))
    return False


def verify_install(directory: Path) -> bool:
    """Recheck saved IPA identity; this cannot prove the phone still has it installed."""
    try:
        from copyapp.ipa import analyze_ipa
        record = json.loads((directory / "install.json").read_text(encoding="utf-8"))
        ipa_name = record.get("ipa")
        if (record.get("schema_version") != 1 or record.get("status") != "installed" or
                not install_transport_complete(record) or
                not isinstance(record.get("device_id"), str) or
                not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", record["device_id"]) or
                not isinstance(ipa_name, str) or not ipa_name):
            return False
        ipa = Path(ipa_name)
        if (not ipa.is_file() or ipa.is_symlink() or
                sha256_file(ipa) != record["ipa_sha256"]):
            return False
        package = analyze_ipa(ipa)
        ok = (package.get("bundle_id") == record.get("bundle_id") and
              package.get("version") == record.get("version") and
              package.get("build") == record.get("build"))
        print(f"{'OK' if ok else 'MISMATCH'} install.json / IPA")
        return ok
    except (OSError, ValueError, TypeError, KeyError, BadZipFile,
            json.JSONDecodeError):
        return False


def _verify_silent(directory: Path) -> bool:
    with redirect_stdout(io.StringIO()):
        return verify_case(directory)


def verify_case(directory: Path) -> bool:
    if (directory / "report-index.json").is_file():
        index = json.loads((directory / "report-index.json").read_text(encoding="utf-8"))
        return compare(directory, index["artifacts"].values())
    if (directory / "analysis-index.json").is_file():
        index = json.loads((directory / "analysis-index.json").read_text(encoding="utf-8"))
        records = list(index["artifacts"].values())
        ok = compare(directory, records)
        if (directory / "survey" / "manifest.json").is_file():
            ok = verify_survey(directory / "survey") and ok
        if (directory / "acquired" / "acquisition.json").is_file():
            ok = verify_acquisition(directory / "acquired") and ok
        if (directory / "decrypted" / "manifest.json").is_file():
            ok = _verify_silent(directory / "decrypted") and ok
        return ok
    if (directory / "manifest.json").is_file():
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        ok = verify_survey(directory)
        if manifest.get("kind") == "copy_workflow":
            try:
                from copyapp.copy_workflow import validate_copy_workflow
                return ok and validate_copy_workflow(directory.resolve(), manifest)
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                return False
        if manifest.get("kind") == "agent_discovery":
            try:
                from copyapp.discovery_agent import validate_discovery_agent
                return ok and validate_discovery_agent(directory.resolve(), manifest)
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                return False
        if manifest.get("kind") == "report_portfolio":
            try:
                from copyapp.report_portfolio import validate_report_portfolio
                return ok and validate_report_portfolio(directory.resolve(), manifest)
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                return False
        if manifest.get("kind") == "discovery_check":
            try:
                from copyapp.discover_check import validate_discovery_check
                return ok and validate_discovery_check(directory.resolve(), manifest)
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                return False
        if manifest.get("kind") == "decrypted_package":
            try:
                from copyapp.decrypt_package import validate_decrypt_package_case
                return ok and validate_decrypt_package_case(directory, manifest)
            except (KeyError, OSError, ValueError, TypeError, BadZipFile,
                    json.JSONDecodeError):
                return False
        if manifest.get("kind") == "ui_network_flow":
            try:
                from copyapp.network_flow import validate_network_flow
                validate_network_flow(directory, manifest["bundle_id"],
                                      manifest["device_id_sha256_prefix"])
                return ok
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                return False
        if manifest.get("kind") == "sandbox_file_capture":
            try:
                from copyapp.sandbox_capture import validate_sandbox_file_capture
                return ok and validate_sandbox_file_capture(directory)
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                return False
        if manifest.get("kind") == "plist_schema":
            try:
                from copyapp.plist_schema import validate_plist_schema_case
                return ok and validate_plist_schema_case(directory)
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                return False
        if manifest.get("kind") == "ipa_static_index":
            try:
                index = json.loads((directory / "ipa-index.json").read_text(encoding="utf-8"))
                source = Path(manifest["source_ipa"]).resolve(strict=True)
                source_ok = (manifest.get("schema_version") == 1 and
                             source.is_file() and
                             sha256_file(source) == manifest.get("ipa_sha256") ==
                             index.get("ipa_sha256") and
                             str(source) == str(Path(index["source"]).resolve()))
            except (OSError, ValueError, KeyError, TypeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "ghidra_indirect_follow":
            try:
                from copyapp.indirect_follow import discover_blr_sites
                from copyapp.native_disasm import rank_native_candidates
                from copyapp.report import (_validate_flow_capture,
                                            _validate_ghidra_direct_queue)
                root = directory.resolve()
                run = json.loads((root / "run.json").read_text(encoding="utf-8"))
                queue_root = root / "queue"
                flow_root = root / "branch-flow"
                queue = json.loads((queue_root / "queue.json").read_text(encoding="utf-8"))
                source = json.loads((queue_root / "sources/candidates/candidates.json").read_text(
                    encoding="utf-8"))
                native_root = queue_root / "sources/native"
                native = json.loads((native_root / "index.json").read_text(encoding="utf-8"))
                observed = rank_native_candidates(source["candidates"],
                                                  run["binary_sha256"],
                                                  run["function_limit"])
                selected_sites = discover_blr_sites(source, native_root, native,
                                                    observed, run["branch_limit"])
                flow = _validate_flow_capture(flow_root, run["bundle_id"],
                                              run["device_id_sha256_prefix"],
                                              {run["binary_sha256"]})
                checked = _validate_ghidra_direct_queue(
                    queue_root, run["bundle_id"], run["device_id_sha256_prefix"],
                    {run["binary_sha256"]})["record"]
                source_ok = (
                    manifest.get("schema_version") == 1 and
                    manifest.get("status") == "complete" and
                    run.get("schema_version") == 1 and
                    run.get("kind") == "ghidra_indirect_follow" and
                    run.get("status") == "complete" and
                    manifest.get("binary_sha256") == run.get("binary_sha256") and
                    source.get("bundle_id") == run.get("bundle_id") and
                    source.get("device_id_sha256_prefix") ==
                    run.get("device_id_sha256_prefix") and
                    sha256_file(root / "sources/objc-index.json") ==
                    run.get("objc_index_sha256") and
                    sha256_file(root / "sources/investigation-manifest.json") ==
                    run.get("source_investigation_manifest_sha256") and
                    selected_sites == run.get("selected_sites") and
                    sha256_file(flow_root / "playbook/playbook.json") ==
                    run.get("source_script_sha256") and
                    sha256_file(flow_root / "manifest.json") ==
                    queue.get("branch_flow_manifest_sha256") and
                    flow["trace"] is not None and
                    checked.get("status") == "complete" and
                    checked.get("disabled_analyzer") == run.get("disabled_analyzer") and
                    len(checked["selected"]) == run.get("function_count") and
                    sum(item.get("origin") == "runtime_indirect_target"
                        for item in checked["selected"]) ==
                    run.get("runtime_indirect_count") and
                    run.get("runtime_indirect_count", 0) > 0
                )
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "app_preparation":
            try:
                root = directory.resolve()
                analysis = root / "analysis"
                preparation = root / "preparation"
                index = json.loads((analysis / "analysis-index.json").read_text(encoding="utf-8"))
                state = json.loads((analysis / "run-state.json").read_text(encoding="utf-8"))
                scripts = manifest["scripts"]
                expected = {"survey", "bundle", "sandbox"}
                if manifest.get("decrypt") is True:
                    expected.add("decryption")
                source_ok = (
                    manifest.get("schema_version") == 1 and
                    manifest.get("status") in ("analysis_ready", "preparation_incomplete",
                                                "needs_semantic_review") and
                    manifest.get("ui_backend") in ("usb", "ios-mcp") and
                    manifest.get("investigation_backend") in ("ios-mcp", "ictrl") and
                    manifest.get("provider") in ("none", "ghidra-direct", "ghidra", "hopper") and
                    state.get("bundle_id") == manifest.get("bundle_id") and
                    state.get("device_id_sha256_prefix") ==
                    manifest.get("device_id_sha256_prefix") and
                    state.get("decrypt_requested") == manifest.get("decrypt") and
                    set(index["steps"]) == expected and
                    all(item.get("ok") is True for item in index["steps"].values()) and
                    sha256_file(analysis / "analysis-index.json") ==
                    manifest.get("analysis_index_sha256") and
                    _verify_silent(analysis) and
                    isinstance(scripts, list) and 1 <= len(scripts) <= 12 and
                    len({item["sha256"] for item in scripts}) == len(scripts) and
                    all(root not in Path(item["path"]).resolve(strict=True).parents and
                        sha256_file(Path(item["path"])) == item["sha256"] and
                        json.loads(Path(item["path"]).read_text(encoding="utf-8")).get(
                            "bundle_id") == manifest["bundle_id"] for item in scripts)
                )
                if source_ok and manifest.get("preparation_manifest_sha256") is not None:
                    prepared = json.loads((preparation / "manifest.json").read_text(
                        encoding="utf-8"))
                    source_ok = (
                        sha256_file(preparation / "manifest.json") ==
                        manifest["preparation_manifest_sha256"] and
                        prepared.get("analysis_case") == str(analysis) and
                        prepared.get("analysis_index_sha256") ==
                        manifest["analysis_index_sha256"] and
                        prepared.get("bundle_id") == manifest.get("bundle_id") and
                        prepared.get("device_id_sha256_prefix") ==
                        manifest.get("device_id_sha256_prefix") and
                        prepared.get("scripts") == scripts and
                        prepared.get("ui_backend") == manifest.get("investigation_backend") and
                        prepared.get("provider") == manifest.get("provider") and
                        prepared.get("disabled_analyzer") ==
                        manifest.get("disabled_analyzer") and
                        prepared.get("rebuilt_bundle_id") ==
                        manifest.get("rebuilt_bundle_id") and
                        prepared.get("status") == manifest.get("preparation_status") and
                        _verify_silent(preparation)
                    )
                if source_ok and manifest.get("status") == "needs_semantic_review":
                    source_ok = (
                        manifest.get("preparation_status") == "needs_semantic_review" and
                        manifest.get("preparation_manifest_sha256") is not None
                    )
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "rebuild_preparation":
            try:
                report = Path(manifest["report"]).resolve(strict=True)
                plan = directory / "plan"
                task = directory / "task"
                spec = json.loads((report / "feature-spec.json").read_text(encoding="utf-8"))
                selected = manifest["selected_flow_ids"]
                known = [item["id"] for item in spec["flows"]]
                source_ok = (
                    manifest.get("schema_version") == 1 and
                    report != directory.resolve() and
                    directory.resolve() not in report.parents and
                    report not in directory.resolve().parents and
                    sha256_file(report / "report-index.json") ==
                    manifest.get("report_index_sha256") and
                    sha256_file(report / "feature-spec.json") ==
                    manifest.get("feature_spec_sha256") and
                    _verify_silent(report) and
                    isinstance(selected, list) and 1 <= len(selected) <= 12 and
                    len(set(selected)) == len(selected) and
                    all(item in known for item in selected) and
                    sha256_file(plan / "manifest.json") ==
                    manifest.get("plan_manifest_sha256") and
                    _verify_silent(plan)
                )
                if source_ok:
                    planned = json.loads((plan / "rebuild-plan.json").read_text(encoding="utf-8"))
                    source_ok = (
                        planned.get("source_report_index_sha256") ==
                        manifest["report_index_sha256"] and
                        planned.get("ui_backend") == manifest.get("ui_backend") and
                        [item["flow_id"] for item in planned["flows"]] == selected
                    )
                if source_ok and manifest.get("status") != "plan_ready":
                    task_data = json.loads((task / "task.json").read_text(encoding="utf-8"))
                    source_ok = (
                        sha256_file(task / "manifest.json") ==
                        manifest.get("task_manifest_sha256") and
                        _verify_silent(task) and
                        task_data.get("status") == manifest.get("status") and
                        task_data.get("report_index_sha256") ==
                        manifest["report_index_sha256"] and
                        task_data.get("rebuild_plan_sha256") ==
                        sha256_file(plan / "rebuild-plan.json") and
                        task_data.get("device_udid") == manifest.get("device_udid") and
                        (manifest.get("project_dir") is None or
                         task_data.get("project_dir") == manifest["project_dir"])
                    )
                elif source_ok:
                    source_ok = manifest.get("task_manifest_sha256") is None
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "analysis_preparation":
            try:
                analysis = Path(manifest["analysis_case"]).resolve(strict=True)
                investigation = Path(manifest["investigation_case"]).resolve()
                survey = json.loads((analysis / "survey/manifest.json").read_text(encoding="utf-8"))
                scripts = manifest["scripts"]
                source_ok = (
                    manifest.get("schema_version") == 1 and
                    analysis != directory.resolve() and
                    investigation != directory.resolve() and
                    analysis != investigation and
                    manifest.get("bundle_id") == survey.get("bundle_id") and
                    manifest.get("device_id_sha256_prefix") ==
                    survey.get("device_id_sha256_prefix") and
                    sha256_file(analysis / "analysis-index.json") ==
                    manifest.get("analysis_index_sha256") and
                    _verify_silent(analysis) and
                    isinstance(scripts, list) and 1 <= len(scripts) <= 12 and
                    len({item["sha256"] for item in scripts}) == len(scripts) and
                    all(sha256_file(Path(item["path"])) == item["sha256"] and
                        json.loads(Path(item["path"]).read_text(encoding="utf-8")).get("bundle_id") ==
                        manifest.get("bundle_id") for item in scripts)
                )
                child = investigation / "manifest.json"
                if source_ok and manifest.get("investigation_manifest_sha256") is not None:
                    source_ok = (
                        child.is_file() and
                        sha256_file(child) == manifest["investigation_manifest_sha256"] and
                        _verify_silent(investigation)
                    )
                if source_ok and manifest.get("status") == "needs_semantic_review":
                    task = json.loads((directory / "draft/task.json").read_text(encoding="utf-8"))
                    source_ok = (
                        child.is_file() and
                        json.loads(child.read_text(encoding="utf-8")).get("status") == "complete" and
                        manifest.get("investigation_manifest_sha256") == sha256_file(child) and
                        task.get("kind") == "agent_semantic_review_task" and
                        task.get("analysis_index_sha256") == manifest.get("analysis_index_sha256") and
                        task.get("app_investigation_sha256") == sha256_file(child) and
                        task.get("target_bundle_id") == manifest.get("bundle_id") and
                        _verify_silent(investigation) and
                        _verify_silent(directory / "draft")
                    )
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "draft_analysis" and (directory / "task.json").is_file():
            try:
                task = json.loads((directory / "task.json").read_text(encoding="utf-8"))
                analysis = Path(task["analysis_case"]).resolve(strict=True)
                investigation = Path(task["app_investigation_case"]).resolve(strict=True)
                report = directory / "report"
                source_ok = (
                    manifest.get("status") == "complete" and
                    task.get("schema_version") == 1 and
                    task.get("kind") == "agent_semantic_review_task" and
                    task.get("status") == "needs_semantic_review" and
                    task.get("target_bundle_id") == manifest.get("bundle_id") and
                    task.get("device_id_sha256_prefix") ==
                    manifest.get("device_id_sha256_prefix") and
                    len({analysis, investigation, directory.resolve()}) == 3 and
                    sha256_file(analysis / "analysis-index.json") ==
                    task.get("analysis_index_sha256") == manifest.get("analysis_index_sha256") and
                    sha256_file(investigation / "manifest.json") ==
                    task.get("app_investigation_sha256") ==
                    manifest.get("app_investigation_sha256") and
                    sha256_file(report / "report-index.json") ==
                    task.get("draft_report_index_sha256") and
                    _verify_silent(analysis) and _verify_silent(investigation) and
                    _verify_silent(report)
                )
                if source_ok:
                    spec = json.loads((directory / "feature-spec.json").read_text(encoding="utf-8"))
                    source_ok = (spec.get("review_status") == "needs_semantic_review" and
                                 len(task.get("flows", [])) == len(spec.get("flows", [])) and
                                 all(record.get("id") == flow.get("id") and
                                     record.get("source_script_sha256") ==
                                     flow.get("source_script_sha256") and
                                     sha256_file(checked_path(directory,
                                         f"report/evidence/app.all/flows/flow-{index:02d}/flow/playbook/playbook.json")) ==
                                     record.get("source_script_sha256") and
                                     all(checked_path(directory, name).is_file()
                                         for name in record.get("evidence_paths", []))
                                     for index, (record, flow) in
                                     enumerate(zip(task["flows"], spec["flows"]), 1)))
            except (KeyError, OSError, ValueError, TypeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "agent_implementation_task":
            try:
                task = json.loads((directory / "task.json").read_text(encoding="utf-8"))
                report = Path(task["report"]).resolve(strict=True)
                plan = Path(task["rebuild_plan"]).resolve(strict=True)
                source_ok = (
                    task.get("schema_version") == 1 and
                    task.get("kind") == "agent_implementation_task" and
                    task.get("status") == manifest.get("status") and
                    report != directory.resolve() and plan != directory.resolve() and
                    manifest.get("source_report_index_sha256") == task.get("report_index_sha256") and
                    manifest.get("source_rebuild_plan_sha256") == task.get("rebuild_plan_sha256") and
                    sha256_file(report / "report-index.json") == task.get("report_index_sha256") and
                    sha256_file(plan / "rebuild-plan.json") == task.get("rebuild_plan_sha256") and
                    _verify_silent(report) and _verify_silent(plan)
                )
            except (KeyError, OSError, ValueError, TypeError, tarfile.TarError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "agent_execution":
            try:
                run = json.loads((directory / "run.json").read_text(encoding="utf-8"))
                task = Path(run["task_case"]).resolve(strict=True)
                task_data = json.loads((task / "task.json").read_text(encoding="utf-8"))
                source_ok = (
                    run.get("schema_version") == 1 and
                    run.get("kind") == "agent_execution" and
                    run.get("status") == manifest.get("status") and
                    task != directory.resolve() and
                    (run.get("task_kind") is None or
                     run.get("task_kind") == task_data.get("kind")) and
                    ((all(run.get(name) is None for name in (
                        "expected_report_case", "expected_analysis_delivery_case",
                        "expected_install_case", "expected_rebuild_check_case",
                        "expected_visual_review_case", "expected_agent_delivery_case"))) or
                     (run.get("task_kind") == "agent_semantic_review_task" and
                      run.get("expected_report_case") ==
                      str(directory.resolve() / "reviewed-report") and
                      run.get("expected_analysis_delivery_case") ==
                      str(directory.resolve() / "analysis-delivery") and
                      all(run.get(name) is None for name in (
                          "expected_install_case", "expected_rebuild_check_case",
                          "expected_visual_review_case", "expected_agent_delivery_case"))) or
                     (run.get("task_kind") == "agent_implementation_task" and
                      run.get("expected_install_case") ==
                      str(directory.resolve() / "install") and
                      run.get("expected_rebuild_check_case") ==
                      str(directory.resolve() / "rebuild-check") and
                      run.get("expected_visual_review_case") ==
                      str(directory.resolve() / "visual-review") and
                      run.get("expected_agent_delivery_case") ==
                      str(directory.resolve() / "agent-delivery") and
                      run.get("expected_report_case") is None and
                      run.get("expected_analysis_delivery_case") is None)) and
                    run.get("task_manifest_sha256") == manifest.get("task_manifest_sha256") and
                    sha256_file(task / "manifest.json") == run.get("task_manifest_sha256") and
                    _verify_silent(task)
                )
            except (KeyError, OSError, ValueError, TypeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "visual_review":
            try:
                from copyapp.visual_review import validate_review
                review = json.loads((directory / "review.json").read_text(encoding="utf-8"))
                check = Path(review["rebuild_check_case"]).resolve(strict=True)
                source_ok = (check != directory.resolve() and
                             manifest.get("status") == review.get("status") and
                             manifest.get("rebuild_check_manifest_sha256") ==
                             review.get("rebuild_check_manifest_sha256") and
                             validate_review(review, check))
            except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "agent_delivery":
            try:
                from copyapp.agent_run import _source_tree_hash
                from copyapp.agent_delivery import (_post_action_script_assertions,
                                                    source_snapshot_tree_hash)
                delivery = json.loads((directory / "delivery.json").read_text(encoding="utf-8"))
                task = Path(delivery["task_case"]).resolve(strict=True)
                check = Path(delivery["rebuild_check_case"]).resolve(strict=True)
                installation = Path(delivery["installation_record"]).resolve(strict=True)
                if delivery.get("source_snapshot") and delivery.get("ipa_snapshot"):
                    source_snapshot = checked_path(directory, delivery["source_snapshot"])
                    ipa_snapshot = checked_path(directory, delivery["ipa_snapshot"])
                    artifacts_ok = (
                        sha256_file(source_snapshot) == delivery.get("source_snapshot_sha256") and
                        source_snapshot_tree_hash(source_snapshot) == delivery.get("source_project_sha256") and
                        sha256_file(ipa_snapshot) == delivery.get("ipa_snapshot_sha256") ==
                        delivery.get("ipa_sha256")
                    )
                else:
                    ipa = Path(delivery["ipa"]).resolve(strict=True)
                    project = Path(delivery["source_project"]).resolve(strict=True)
                    artifacts_ok = (sha256_file(ipa) == delivery.get("ipa_sha256") and
                                    _source_tree_hash(project) == delivery.get("source_project_sha256"))
                source_ok = (
                    delivery.get("schema_version") == 1 and
                    delivery.get("kind") == "agent_delivery" and
                    delivery.get("status") == manifest.get("status") and
                    len({task, check, directory.resolve()}) == 3 and
                    manifest.get("task_manifest_sha256") == delivery.get("task_manifest_sha256") and
                    manifest.get("rebuild_check_manifest_sha256") == delivery.get("rebuild_check_manifest_sha256") and
                    manifest.get("installation_record_sha256") == delivery.get("installation_record_sha256") and
                    sha256_file(task / "manifest.json") == delivery.get("task_manifest_sha256") and
                    sha256_file(check / "manifest.json") == delivery.get("rebuild_check_manifest_sha256") and
                    sha256_file(installation) == delivery.get("installation_record_sha256") and
                    artifacts_ok and
                    _verify_silent(task) and _verify_silent(check)
                )
                if source_ok and "script_assertions_status" in (
                        delivery.get("flow_results") or [{}])[0]:
                    task_data = json.loads((task / "task.json").read_text(encoding="utf-8"))
                    selected = {item["id"]: item for item in task_data["flows"]}
                    results = delivery["flow_results"]
                    source_ok = (
                        len(results) == len(selected) and
                        {item["id"] for item in results} == set(selected) and
                        all(item.get("script_assertions") ==
                            _post_action_script_assertions(
                                Path(selected[item["id"]]["original_script"])) and
                            item.get("script_assertions_status") ==
                            ("passed" if item["script_assertions"] else "not_configured")
                            for item in results)
                    )
                    if source_ok:
                        counted = sum(
                            item.get("script_assertions_status") == "passed" or
                            item.get("final_view_status") == "passed" or
                            item.get("visual_checks_status") == "passed"
                            for item in results)
                        source_ok = counted == delivery.get("asserted_flow_count")
                run_path = delivery.get("agent_run_case")
                if source_ok and run_path is not None:
                    run = Path(run_path).resolve(strict=True)
                    source_ok = (run not in (task, check, directory.resolve()) and
                                 sha256_file(run / "manifest.json") ==
                                 delivery.get("agent_run_manifest_sha256") and
                                 _verify_silent(run))
                review_path = delivery.get("visual_review_case")
                if source_ok and review_path is not None:
                    review_case = Path(review_path).resolve(strict=True)
                    review = json.loads((review_case / "review.json").read_text(encoding="utf-8"))
                    source_ok = (review_case not in (task, check, directory.resolve()) and
                                 sha256_file(review_case / "manifest.json") ==
                                 delivery.get("visual_review_manifest_sha256") and
                                 Path(review.get("rebuild_check_case", "")).resolve() == check and
                                 review.get("rebuild_check_manifest_sha256") ==
                                 delivery.get("rebuild_check_manifest_sha256") and
                                 _verify_silent(review_case))
                    if source_ok:
                        by_flow = {}
                        for pair in review["pairs"]:
                            by_flow.setdefault(pair["flow_id"], []).append(pair["verdict"])
                        results = delivery["flow_results"]
                        source_ok = all(
                            item.get("visual_review_status") == (
                                "major_difference" if "major_difference" in by_flow.get(item["id"], []) else
                                "minor_difference" if "minor_difference" in by_flow.get(item["id"], []) else
                                "match") and
                            len(by_flow.get(item["id"], [])) == item.get("screenshot_pairs")
                            for item in results)
                        source_ok = (source_ok and
                                     delivery.get("visual_unreviewed_flow_count") == 0 and
                                     delivery.get("visual_major_difference_flow_count") == sum(
                                         item.get("visual_review_status") == "major_difference"
                                         for item in results) and
                                     delivery.get("visual_minor_difference_flow_count") == sum(
                                         item.get("visual_review_status") == "minor_difference"
                                         for item in results))
                elif source_ok:
                    source_ok = (delivery.get("visual_review_manifest_sha256") is None and
                                 not any("visual_review_status" in item
                                         for item in delivery.get("flow_results", [])) and
                                 "visual_reviewed" not in delivery.get("status", ""))
            except (KeyError, OSError, ValueError, TypeError, tarfile.TarError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "analysis_delivery":
            try:
                from copyapp.analysis_delivery import validate_analysis_delivery
                delivery = json.loads((directory / "delivery.json").read_text(encoding="utf-8"))
                task = Path(delivery["task_case"]).resolve(strict=True)
                report = Path(delivery["report_case"]).resolve(strict=True)
                run = (Path(delivery["agent_run"]["case"]).resolve(strict=True)
                       if delivery.get("agent_run") else None)
                if directory.resolve() in (task, report, run):
                    return False
                expected = validate_analysis_delivery(task, report, run)
                source_ok = (
                    delivery.get("schema_version") == 1 and
                    delivery.get("kind") == "analysis_delivery" and
                    delivery.get("status") == manifest.get("status") ==
                    "source_linked_report_ready_for_review" and
                    all(delivery.get(key) == value for key, value in expected.items()) and
                    manifest.get("task_manifest_sha256") == delivery.get("task_manifest_sha256") and
                    manifest.get("report_index_sha256") == delivery.get("report_index_sha256") and
                    sha256_file(directory / "reviewed-findings.json") ==
                    delivery.get("findings_sha256") == sha256_file(report / "findings.json") and
                    sha256_file(directory / "reviewed-feature-spec.json") ==
                    delivery.get("feature_spec_sha256") ==
                    sha256_file(report / "feature-spec.json")
                )
            except (KeyError, OSError, ValueError, TypeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "sqlite_schema":
            try:
                from copyapp.sqlite_schema import validate_sqlite_schema_case
                return ok and validate_sqlite_schema_case(directory)
            except (KeyError, OSError, ValueError, TypeError, sqlite3.DatabaseError,
                    json.JSONDecodeError):
                return False
        if manifest.get("kind") == "visual_audit":
            try:
                from copyapp.visual_audit import compute_visual_audit
                audit = json.loads((directory / "audit.json").read_text(encoding="utf-8"))
                source = Path(audit["rebuild_check_case"]).resolve(strict=True)
                if source == directory.resolve():
                    return False
                expected = compute_visual_audit(
                    source, audit["roi_pixels"],
                    audit["max_normalized_mean_absolute_rgb"],
                    audit["max_changed_pixel_fraction"],
                    audit["difference_threshold"])
                source_ok = (
                    audit.get("status") == manifest.get("status") and
                    manifest.get("rebuild_check_manifest_sha256") ==
                    audit.get("rebuild_check_manifest_sha256") and
                    set(audit) == set(expected) | {"created_at"} and
                    all(audit.get(key) == value for key, value in expected.items())
                )
            except (KeyError, OSError, ValueError, TypeError):
                source_ok = False
            return ok and source_ok
        if manifest.get("kind") == "branch_observation_map":
            mapped = json.loads((directory / "branch-map.json").read_text(encoding="utf-8"))
            binary_path = mapped.get("binary_path")
            sources = mapped.get("sources")
            if (not isinstance(binary_path, str) or not binary_path or
                    not isinstance(sources, list) or not sources or len(sources) > 32 or
                    not isinstance(mapped.get("binary_sha256"), str)):
                return False
            binary = Path(binary_path)
            if not binary.is_file() or sha256_file(binary) != mapped["binary_sha256"]:
                return False
            for item in sources:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    return False
                source = Path(item["path"])
                source_manifest = source / "manifest.json"
                if (source.resolve() == directory.resolve() or not source_manifest.is_file() or
                        sha256_file(source_manifest) != item.get("manifest_sha256")):
                    return False
                source_data = json.loads(source_manifest.read_text(encoding="utf-8"))
                if (source_data.get("kind") != "ui_flow_capture" or
                        source_data.get("status") != "complete" or
                        not verify_case(source)):
                    return False
        return ok
    if (directory / "acquisition.json").is_file():
        return verify_acquisition(directory)
    if (directory / "install.json").is_file():
        return verify_install(directory)
    raise FileNotFoundError("no analysis, survey or acquisition manifest")
