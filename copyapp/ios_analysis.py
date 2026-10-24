"""Resumable UI-first analysis with optional, separately attributed enhancement."""

import asyncio
import hashlib
import io
import plistlib
import re
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zipfile import ZipFile

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from copyapp.ictrl import DEFAULT_CLIENT
from copyapp.ios_capabilities import collect_capabilities
from copyapp.ios_cases import read_json, seal_case, write_json
from copyapp.playbook import run_playbook
from copyapp.verify import checked_path, sha256_file, verify_case


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _analysis_missing(plan: dict, request: Optional[dict]) -> list:
    missing = list(plan["operations"]["analyze"]["missing"])
    if (request and request.get("device_decryption") and
            plan.get("capability_model_version", 1) >= 2):
        missing += [item for item in plan["operations"]["decrypt-device"]["missing"]
                    if item not in missing]
    return missing


def enhancement_settings(decrypt: bool, ui_backend: str, ssh_port: int, ssh_user: str,
                         ssh_identity: Path, ssh_known_hosts: Path, helper: Path) -> dict:
    """Pin public collection settings without reading credential contents."""
    return {"device_decryption": decrypt, "survey_ui_backend": ui_backend,
            "ssh_port": ssh_port, "ssh_user": ssh_user,
            "ssh_identity_ref": str(ssh_identity.resolve()),
            "ssh_known_hosts_ref": str(ssh_known_hosts.resolve()),
            "helper": {"path": str(helper.resolve()),
                       "sha256": sha256_file(helper) if helper.is_file() else None} if decrypt else None}


def _validate_enhancement_settings(value: dict) -> None:
    required = {"device_decryption", "survey_ui_backend", "ssh_port", "ssh_user",
                "ssh_identity_ref", "ssh_known_hosts_ref", "helper"}
    if (not isinstance(value, dict) or set(value) != required or
            type(value["device_decryption"]) is not bool or
            value["survey_ui_backend"] not in ("usb", "ios-mcp") or
            type(value["ssh_port"]) is not int or not 1 <= value["ssh_port"] <= 65535 or
            value["ssh_user"] not in ("root", "mobile") or
            any(not isinstance(value[key], str) or not Path(value[key]).is_absolute()
                for key in ("ssh_identity_ref", "ssh_known_hosts_ref"))):
        raise ValueError("invalid enhanced collection settings")
    helper = value["helper"]
    if (helper is not None and
            (not isinstance(helper, dict) or set(helper) != {"path", "sha256"} or
             not isinstance(helper["path"], str) or not Path(helper["path"]).is_absolute() or
             (helper["sha256"] is not None and
              (not isinstance(helper["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", helper["sha256"])))) or
            value["device_decryption"] != (helper is not None)):
        raise ValueError("invalid enhanced helper identity")


async def target_identity(udid: str, bundle: str) -> dict:
    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        values = await device.get_value()
        if values.get("UniqueDeviceID") != udid:
            raise ValueError("target device identity differs from requested UDID")
        async with InstallationProxyService(device) as proxy:
            apps = await proxy.get_apps(application_type="Any", bundle_identifiers=[bundle])
        if bundle not in apps:
            raise ValueError("target App is not installed on the requested device")
        app = apps[bundle]
        return {"device": {key: values.get(key) for key in
                           ("UniqueDeviceID", "ProductType", "ProductVersion", "BuildVersion")},
                "app": {"bundle_id": bundle, "name": app.get("CFBundleDisplayName") or app.get("CFBundleName"),
                        "version": app.get("CFBundleShortVersionString"),
                        "build": app.get("CFBundleVersion")}}
    finally:
        await device.close()


def _verified(root):
    with redirect_stdout(io.StringIO()):
        if not verify_case(root):
            raise ValueError(f"case verification failed: {root}")


def _enhancement_complete(root: Path, bundle: str, prefix: str, identity: dict,
                           request: Optional[dict] = None) -> bool:
    from copyapp.analyze import _stage_valid

    _verified(root)
    index = read_json(root / "analysis-index.json")
    steps = index.get("steps", {})
    if (not all(name in steps for name in ("survey", "bundle", "sandbox")) or
            any(record.get("ok") is not True for record in steps.values())):
        return False
    survey = read_json(root / "survey/manifest.json")
    if request is not None:
        _validate_enhancement_settings(request)
        if (request["device_decryption"] != ("decryption" in steps) or
                survey.get("ui_backend") != request["survey_ui_backend"]):
            return False
    app = read_json(root / "survey/app.json")
    acquired = read_json(root / "acquired/acquisition.json")
    sandbox = read_json(root / "sandbox-index.json")
    with ZipFile(root / "acquired/bundle-snapshot.ipa") as archive:
        names = [name for name in archive.namelist()
                 if re.fullmatch(r"Payload/[^/]+\.app/Info.plist", name)]
        if len(names) != 1 or archive.getinfo(names[0]).file_size > 4 * 1024 * 1024:
            return False
        packaged = plistlib.loads(archive.read(names[0]))
    expected_app, device = identity["app"], identity["device"]
    if (survey.get("bundle_id") != bundle or survey.get("device_id_sha256_prefix") != prefix or
            app.get("CFBundleIdentifier") != bundle or packaged.get("CFBundleIdentifier") != bundle or
            any(not isinstance(device.get(key), str) or not device[key] or
                survey.get("device", {}).get(key) != device[key]
                for key in ("ProductType", "ProductVersion", "BuildVersion"))):
        return False
    stage_records = [acquired, sandbox]
    if "decryption" in steps:
        _verified(root / "decrypted")
        decryption = read_json(root / "decrypted/decryption.json")
        stage_records.append(decryption)
        if (request is not None and request["helper"]["sha256"] is not None and
                decryption.get("recovery_strategy") != "source_snapshot_unencrypted" and
                decryption.get("helper_sha256") != request["helper"]["sha256"]):
            return False
    for live, survey_key, stage_key in (("version", "CFBundleShortVersionString", "installed_version"),
                                        ("build", "CFBundleVersion", "installed_build")):
        value = expected_app.get(live)
        if (not isinstance(value, str) or not value or app.get(survey_key) != value or
                packaged.get(survey_key) != value or
                any(record.get(stage_key) != value for record in stage_records)):
            return False
    return all(name in ("survey", "bundle", "sandbox", "decryption") and
               _stage_valid(root, name, record, device["UniqueDeviceID"], bundle)
               for name, record in steps.items())


def _script_inputs(scripts: list[Path], bundle: str) -> list[dict]:
    if not 1 <= len(scripts) <= 12:
        raise ValueError("provide 1–12 bounded representative playbooks")
    records = []
    for number, path in enumerate(scripts, 1):
        data = read_json(path)
        identifier = data.get("scenario_id")
        if (data.get("schema_version") != 1 or data.get("bundle_id") != bundle or
                data.get("fresh_launch") is not True or not isinstance(identifier, str) or
                not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", identifier) or
                identifier in [item["id"] for item in records] or
                not isinstance(data.get("steps"), list) or not 1 <= len(data["steps"]) <= 64):
            raise ValueError("playbooks require unique scenario IDs, exact App and a fresh launch")
        records.append({"id": identifier, "script": f"scripts/flow-{number:02d}.json",
                        "source_script_sha256": sha256_file(path),
                        "case": f"flows/flow-{number:02d}"})
    return records


def _package_inputs(packages: list[Path], bundle: str) -> list[dict]:
    records = []
    if len(packages) > 4:
        raise ValueError("provide at most four independent package inputs")
    for number, root in enumerate(packages, 1):
        _verified(root)
        manifest = read_json(root / "manifest.json")
        if (manifest.get("kind") not in ("ios_package", "ios_offline_package") or
                manifest.get("status") != "complete" or manifest.get("bundle_id") != bundle):
            raise ValueError("package input is incomplete or belongs to another App")
        records.append({"case": f"packages/package-{number:02d}", "kind": manifest["kind"],
                        "manifest_sha256": sha256_file(root / "manifest.json")})
    if len({row["manifest_sha256"] for row in records}) != len(records):
        raise ValueError("package inputs must be distinct")
    return records


def package_association(root: Path, identity: dict) -> dict:
    index = read_json(root / "package-index.json")
    app = identity["app"]
    if index.get("bundle_id") != app["bundle_id"]:
        raise ValueError("package App identity differs")
    matched = all(isinstance(app.get(key), str) and app[key] and app[key] == index.get(key)
                  for key in ("version", "build"))
    return {"relation": "metadata_match" if matched else "bundle_only",
            "package_version": index.get("version"), "package_build": index.get("build"),
            "runtime_binary_identity": "not_verified",
            "limitation": "Matching version/build does not prove the same device variant or loaded code."}


def collect_ios_analysis(udid: str, bundle: str, scripts: list[Path], output: Path,
                          mode: str = "standard", resume: bool = False,
                          retry_failed: bool = False, ictrl_client: Path = DEFAULT_CLIENT,
                          ssh_port: int = 22222,
                          ssh_identity: Path = Path("cases/ssh/id_ed25519"),
                          ssh_known_hosts: Path = Path("cases/ssh-known-hosts"),
                          enhanced_collector=None,
                          package_cases: Optional[list[Path]] = None,
                          enhancement_request: Optional[dict] = None) -> tuple[Path, bool]:
    if (not re.fullmatch(r"[A-Fa-f0-9-]{16,80}", udid) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle)):
        raise ValueError("invalid device or Bundle ID")
    if mode not in ("auto", "standard", "enhanced"):
        raise ValueError("invalid analysis mode")
    inputs = {"udid": udid, "bundle_id": bundle, "requested_mode": mode,
              "flows": _script_inputs(scripts, bundle)}
    if enhancement_request is not None:
        _validate_enhancement_settings(enhancement_request)
        if mode == "standard":
            raise ValueError("standard collection cannot request device enhancement")
        inputs["enhancement_request"] = enhancement_request
    if package_cases:
        inputs["packages"] = _package_inputs(package_cases, bundle)
        if any(root.resolve() == output.resolve() or root.resolve() in output.resolve().parents
               for root in package_cases):
            raise ValueError("analysis output cannot be inside its package source")
    if resume:
        _verified(output)
        if read_json(output / "inputs.json") != inputs:
            raise ValueError("resume device, App, mode or scripts differ")
        state = read_json(output / "analysis.json")
        if state["status"] == "complete":
            return output / "manifest.json", True
    else:
        if output.exists():
            raise FileExistsError(output)
        output.mkdir(parents=True)
        write_json(output / "inputs.json", inputs)
        for source, item in zip(scripts, inputs["flows"]):
            target = output / item["script"]
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, target)
        for source, item in zip(package_cases or [], inputs.get("packages", [])):
            shutil.copytree(source, output / item["case"])
        state = {"status": "failed", "started_at": _now(), "flows": [],
                 "enhancement": {"status": "skipped_optional", "reason": "not collected"}}
    try:
        capabilities = output / "capabilities"
        if not capabilities.exists():
            collect_capabilities(udid, capabilities, mode, ssh_port, ssh_identity,
                                 ssh_known_hosts, ictrl_client)
        _verified(capabilities)
        plan = read_json(capabilities / "capabilities.json")
        readiness = plan
        state["selected_mode"], state["ui_backend"] = plan["selected_mode"], plan["ui_backend"]
        if resume:
            checks = output / "capability-checks"
            checks.mkdir(exist_ok=True)
            probe = checks / f"check-{len(list(checks.iterdir())) + 1:03d}"
            collect_capabilities(udid, probe, mode, ssh_port, ssh_identity, ssh_known_hosts, ictrl_client)
            _verified(probe)
            current = read_json(probe / "capabilities.json")
            accepted = (current["device"]["UniqueDeviceID"] == udid and
                        current["requested_mode"] == mode and
                        current["selected_mode"] == plan["selected_mode"] and
                        current["ui_backend"] == plan["ui_backend"] and
                        not _analysis_missing(current, enhancement_request))
            state.setdefault("capability_checks", []).append({
                "case": str(probe.relative_to(output)), "manifest_sha256": sha256_file(probe / "manifest.json"),
                "accepted_for_resume": accepted})
            if not accepted:
                raise RuntimeError("required capabilities unavailable or the selected route changed on resume; "
                                   "inspect the fresh probe before retrying or starting a new case")
            readiness = current
        missing = _analysis_missing(readiness, enhancement_request)
        if missing:
            raise RuntimeError("required analysis capabilities unavailable: " + ", ".join(missing))
        before = asyncio.run(target_identity(udid, bundle))
        if (output / "identity-before.json").exists():
            if read_json(output / "identity-before.json") != before:
                raise ValueError("App or device identity changed since the saved attempt")
        else:
            write_json(output / "identity-before.json", before)
        if inputs.get("packages"):
            state["packages"] = [{**item, "association": package_association(output / item["case"], before)}
                                  for item in inputs["packages"]]
        if plan["selected_mode"] == "enhanced":
            if enhanced_collector is None:
                raise ValueError("enhanced analysis requires the device collection stage")
            enhanced = output / "enhanced"
            if not enhanced.exists():
                if not enhanced_collector(enhanced):
                    raise RuntimeError("enhanced device collection failed; inspect retained child")
            if not _enhancement_complete(enhanced, bundle, hashlib.sha256(udid.encode()).hexdigest()[:16],
                                         before, enhancement_request):
                if not resume or not retry_failed or not enhanced_collector(enhanced):
                    raise RuntimeError("enhanced collection is incomplete; inspect it before --resume --retry-failed")
                if not _enhancement_complete(enhanced, bundle, hashlib.sha256(udid.encode()).hexdigest()[:16],
                                             before, enhancement_request):
                    raise RuntimeError("retried enhancement still differs from the current device/App build")
            state["enhancement"] = {"status": "complete", "case": "enhanced",
                                     "analysis_index_sha256": sha256_file(enhanced / "analysis-index.json")}
        records = []
        for item in inputs["flows"]:
            child = output / item["case"]
            reused = False
            if child.exists():
                _verified(child)
                old = read_json(child / "manifest.json")
                if old.get("status") == "complete":
                    reused = True
                elif not retry_failed:
                    raise RuntimeError("failed flow retained; inspect current UI before --resume --retry-failed")
                else:
                    attempts = output / "attempts"
                    attempts.mkdir(exist_ok=True)
                    archive = attempts / f"{child.name}-{len(list(attempts.iterdir())) + 1:02d}"
                    shutil.move(str(child), str(archive))
            if not reused:
                _, complete = run_playbook(udid, plan["ui_backend"], output / item["script"], child,
                                           ictrl_client=ictrl_client, mode=plan["selected_mode"])
                _verified(child)
                if not complete:
                    raise RuntimeError(f"flow failed: {item['id']}; inspect saved result before replay")
            record = read_json(child / "manifest.json")
            if (record.get("bundle_id") != bundle or record.get("ui_backend") != plan["ui_backend"] or
                    record.get("device_id_sha256_prefix") != hashlib.sha256(udid.encode()).hexdigest()[:16] or
                    sha256_file(child / "playbook.json") != item["source_script_sha256"]):
                raise ValueError("saved flow source identity differs")
            records.append({**item, "manifest_sha256": sha256_file(child / "manifest.json")})
            state["flows"] = records
            write_json(output / "analysis.json", state)
        after = asyncio.run(target_identity(udid, bundle))
        write_json(output / "identity-after.json", after)
        if before != after:
            raise ValueError("device or App identity changed during analysis")
        state["status"] = "complete"
        state.pop("error", None)
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
    finally:
        state["finished_at"] = _now()
        write_json(output / "analysis.json", state)
        (output / "TASK.md").write_text(
            "# Review the observed iOS behavior\n\n"
            f"Collection status: {state['status']}.\n\n"
            "Inspect identity-before.json, capabilities/, each flows/ screenshot and accessibility observation. "
            "A complete collection is input readiness, not a reviewed report. Write findings.json and a concrete "
            "feature-spec.json with reviewed assertions, citations and source_script_sha256 for each selected flow. "
            "Use copyapp report to produce a separately verified report. UI evidence cannot establish private "
            "sandbox structure, function semantics, server behavior or whole-App coverage.\n",
            encoding="utf-8")
        seal_case(output, "ios_analysis", status=state["status"], bundle_id=bundle,
                  device_id_sha256_prefix=hashlib.sha256(udid.encode()).hexdigest()[:16])
    return output / "manifest.json", state["status"] == "complete"


def validate_ios_analysis(root: Path, manifest: dict) -> bool:
    inputs, state = read_json(root / "inputs.json"), read_json(root / "analysis.json")
    udid, bundle = inputs["udid"], inputs["bundle_id"]
    if "enhancement_request" in inputs:
        _validate_enhancement_settings(inputs["enhancement_request"])
        if inputs["requested_mode"] == "standard":
            return False
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    if (manifest.get("bundle_id") != bundle or manifest.get("status") != state.get("status") or
            state.get("status") not in ("complete", "failed") or
            manifest.get("device_id_sha256_prefix") != prefix):
        return False
    scripts = [checked_path(root, item["script"]) for item in inputs["flows"]]
    if _script_inputs(scripts, bundle) != inputs["flows"]:
        return False
    if state["status"] == "failed":
        return isinstance(state.get("error"), dict)
    _verified(root / "capabilities")
    plan = read_json(root / "capabilities/capabilities.json")
    before = read_json(root / "identity-before.json")
    if (before != read_json(root / "identity-after.json") or
            before["device"]["UniqueDeviceID"] != udid or before["app"]["bundle_id"] != bundle or
            plan["device"]["UniqueDeviceID"] != udid or plan["requested_mode"] != inputs["requested_mode"] or
            state.get("selected_mode") != plan["selected_mode"] or
            state.get("ui_backend") != plan["ui_backend"]):
        return False
    if len(state["flows"]) != len(inputs["flows"]):
        return False
    checks = state.get("capability_checks", [])
    if not isinstance(checks, list) or len({item["case"] for item in checks}) != len(checks):
        return False
    readiness = plan
    for item in checks:
        probe = checked_path(root, item["case"])
        _verified(probe)
        current = read_json(probe / "capabilities.json")
        accepted = (current["device"]["UniqueDeviceID"] == udid and
                    current["requested_mode"] == inputs["requested_mode"] and
                    current["selected_mode"] == plan["selected_mode"] and
                    current["ui_backend"] == plan["ui_backend"] and
                    not _analysis_missing(current, inputs.get("enhancement_request")))
        if (item["manifest_sha256"] != sha256_file(probe / "manifest.json") or
                item.get("accepted_for_resume") is not accepted):
            return False
        readiness = current
    if checks and checks[-1]["accepted_for_resume"] is not True:
        return False
    if _analysis_missing(readiness, inputs.get("enhancement_request")):
        return False
    if inputs.get("packages"):
        roots = [checked_path(root, item["case"]) for item in inputs["packages"]]
        if _package_inputs(roots, bundle) != inputs["packages"]:
            return False
        if state.get("packages") != [{**item, "association": package_association(child, before)}
                                      for item, child in zip(inputs["packages"], roots)]:
            return False
    elif state.get("packages"):
        return False
    for source, saved in zip(inputs["flows"], state["flows"]):
        child = checked_path(root, source["case"])
        _verified(child)
        flow = read_json(child / "manifest.json")
        if (saved != {**source, "manifest_sha256": sha256_file(child / "manifest.json")} or
                flow.get("status") != "complete" or flow.get("bundle_id") != bundle or
                flow.get("ui_backend") != plan["ui_backend"] or
                flow.get("execution_mode") != plan["selected_mode"] or
                flow.get("device_id_sha256_prefix") != prefix or
                sha256_file(child / "playbook.json") != source["source_script_sha256"]):
            return False
        from copyapp.compare_playbooks import _load_run
        from copyapp.playbook import _text
        with redirect_stdout(io.StringIO()):
            _, script = _load_run(child, require_comparable=False)
        for requested, observed in zip(script["steps"], flow["steps"]):
            if requested.get("action") == "observe" and observed.get("observation_source") == "accessibility":
                raw = read_json(checked_path(child, observed["evidence_path"]))
                visible = _text(raw, plan["ui_backend"])
                expected = requested.get("contains", [])
                expected = [expected] if isinstance(expected, str) else expected
                if any(value not in visible for value in expected):
                    return False
    if plan["selected_mode"] == "enhanced":
        return _enhancement_complete(root / "enhanced", bundle, prefix, before,
                                     inputs.get("enhancement_request")) and state["enhancement"] == {
            "status": "complete", "case": "enhanced",
            "analysis_index_sha256": sha256_file(root / "enhanced/analysis-index.json")}
    return state["enhancement"]["status"] == "skipped_optional"
