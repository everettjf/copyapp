"""Accept agent-authored UI flows only after bounded real-device replay."""

import hashlib
import io
import json
import re
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.playbook import run_playbook
from copyapp.verify import sha256_file, verify_case


SCENARIO = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verified(path: Path) -> bool:
    with redirect_stdout(io.StringIO()):
        return verify_case(path)


def _signature(steps: list) -> list:
    return [[step["action"], step.get("label") if step["action"] == "tap_label"
             else [step.get("x"), step.get("y")]]
            for step in steps if step["action"] in ("tap", "tap_label")]


def inspect_playbook(path: Path, bundle: str) -> dict:
    """Reject generic, duplicate or unbounded scripts before touching the phone."""
    plan = _read(path)
    steps = plan.get("steps")
    if (plan.get("schema_version") != 1 or plan.get("bundle_id") != bundle or
            plan.get("fresh_launch") is not True or
            not isinstance(plan.get("scenario_id"), str) or
            not SCENARIO.fullmatch(plan["scenario_id"]) or
            not isinstance(steps, list) or not 3 <= len(steps) <= 32 or
            any(not isinstance(step, dict) or step.get("action") not in
                ("observe", "tap", "tap_label", "screenshot", "expect_foreground")
                for step in steps)):
        raise ValueError("discovery playbook has invalid identity or structure")
    taps = [step for step in steps if step["action"] in ("tap", "tap_label")]
    if (not 1 <= len(taps) <= 8 or steps[0]["action"] != "observe" or
            not isinstance(steps[0].get("contains"), list) or
            not steps[0]["contains"] or
            any(not isinstance(value, str) or not value
                for value in steps[0]["contains"]) or
            steps[-1].get("action") != "screenshot" or
            steps[-1].get("stable") is not True or
            not isinstance(steps[-1].get("ready_contains"), str) or
            not steps[-1]["ready_contains"]):
        raise ValueError("discovery flow needs an observed entry, bounded action and ready final screenshot")
    for step in taps:
        if step["action"] == "tap_label":
            if not isinstance(step.get("label"), str) or not step["label"]:
                raise ValueError("tap_label needs a visible label")
        elif (type(step.get("x")) not in (int, float) or
              type(step.get("y")) not in (int, float)):
            raise ValueError("coordinate tap needs numeric points")
    for step in steps:
        if step["action"] == "screenshot" and "ready_ocr_labels" in step:
            labels = step["ready_ocr_labels"]
            if (not isinstance(labels, list) or not labels or
                    any(not isinstance(label, str) or not label.strip() for label in labels)):
                raise ValueError("screenshot ready_ocr_labels needs visible text labels")
    return {"scenario_id": plan["scenario_id"], "tap_signature": _signature(steps),
            "step_count": len(steps), "tap_count": len(taps),
            "sha256": sha256_file(path)}


def _save(output: Path, record: dict) -> Path:
    evidence = []
    for script in record["scripts"]:
        for name in (script["copy_path"], script["check_path"]):
            path = output / name
            if path.is_file():
                evidence.append({"path": name, "sha256": sha256_file(path)})
    report = output / "report.md"
    lines = ["# Copy APP UI 流程发现验收", "",
             f"- Bundle ID：`{record['bundle_id']}`",
             f"- 后端：`{record['backend']}`",
             f"- 状态：`{record['status']}`", "",
             "| 场景 | 操作数 | 真机重放 | 脚本 |", "| --- | ---: | --- | --- |"]
    for script in record["scripts"]:
        lines.append(f"| {script['scenario_id']} | {script['tap_count']} | "
                     f"{script.get('check_status', 'pending')} | "
                     f"[{script['copy_path']}]({script['copy_path']}) |")
    lines += ["", "结果只证明选定脚本在此设备与当前 App 状态完成了受限重放；"
              "不证明自动探索覆盖全部页面，也不证明点击没有未观察到的副作用。", ""]
    report.write_text("\n".join(lines), encoding="utf-8")
    evidence.append({"path": "report.md", "sha256": sha256_file(report)})
    record["evidence"] = evidence
    record["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    target = output / "manifest.json"
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target


def validate_discovery_check(output: Path, record: dict) -> bool:
    try:
        scripts = record["scripts"]
        if (record.get("schema_version") != 1 or record.get("kind") != "discovery_check" or
                record.get("status") != "complete" or
                record.get("backend") not in ("ios-mcp", "ictrl") or
                not isinstance(scripts, list) or not 3 <= len(scripts) <= 12 or
                len({item["scenario_id"] for item in scripts}) != len(scripts)):
            return False
        signatures = []
        for item in scripts:
            source = Path(item["source_path"]).resolve(strict=True)
            copied = (output / item["copy_path"]).resolve(strict=True)
            check = (output / item["check_root"]).resolve(strict=True)
            if (copied.is_symlink() or check.is_symlink() or
                    output not in copied.parents or output not in check.parents or
                    sha256_file(source) != item["source_sha256"] or
                    sha256_file(copied) != item["source_sha256"] or
                    item.get("check_status") != "complete" or
                    sha256_file(check / "manifest.json") != item["check_sha256"] or
                    sha256_file(check / "playbook.json") != item["source_sha256"] or
                    not _verified(check)):
                return False
            info = inspect_playbook(copied, record["bundle_id"])
            checked = _read(check / "manifest.json")
            first = checked.get("steps", [{}])[0]
            last = checked.get("steps", [{}])[-1]
            first_path = (check / first.get("evidence_path", "")).resolve()
            last_path = (check / last.get("evidence_path", "")).resolve()
            evidence = {entry["path"]: entry["sha256"]
                        for entry in checked.get("evidence", [])}
            if (info["scenario_id"] != item["scenario_id"] or
                    info["tap_signature"] != item["tap_signature"] or
                    checked.get("status") != "complete" or
                    checked.get("bundle_id") != record["bundle_id"] or
                    checked.get("device_id_sha256_prefix") != record["device_id_sha256_prefix"] or
                    checked.get("ui_backend") != record["backend"] or
                    checked.get("scenario_id") != item["scenario_id"] or
                    len(checked.get("steps", [])) != info["step_count"] or
                    [step.get("action") for step in checked["steps"]] !=
                    [step["action"] for step in _read(copied)["steps"]] or
                    not all(step.get("frontmost") == record["bundle_id"]
                            for step in checked["steps"] if
                            step.get("action") != "expect_foreground") or
                    not last.get("ready_found") or
                    not last.get("stability", {}).get("stable") or
                    check not in first_path.parents or
                    check not in last_path.parents or
                    not first_path.is_file() or not last_path.is_file() or
                    evidence.get(first["evidence_path"]) != sha256_file(first_path) or
                    evidence.get(last["evidence_path"]) != last.get("sha256") or
                    last.get("sha256") != sha256_file(last_path)):
                return False
            signatures.append(json.dumps(info["tap_signature"], sort_keys=True))
        return len(set(signatures)) == len(signatures)
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def accepted_playbooks(case: Path, udid: str, bundle: str, backend: str) -> list[Path]:
    """Return exact copied scripts from a fully verified device discovery case."""
    case = case.resolve(strict=True)
    manifest = _read(case / "manifest.json")
    if (manifest.get("status") != "complete" or
            manifest.get("bundle_id") != bundle or
            manifest.get("backend") != backend or
            manifest.get("device_id_sha256_prefix") !=
            hashlib.sha256(udid.encode()).hexdigest()[:16] or
            not _verified(case)):
        raise ValueError("discovery case is incomplete or belongs to another device/App/backend")
    return [(case / item["copy_path"]).resolve(strict=True)
            for item in manifest["scripts"]]


def check_discovered_flows(udid: str, bundle: str, scripts: list[Path],
                           output: Path, backend: str = "ios-mcp",
                           resume: bool = False) -> tuple[Path, bool]:
    if not udid or not bundle or backend not in ("ios-mcp", "ictrl") or \
            not 3 <= len(scripts) <= 12:
        raise ValueError("provide a device, App and 3–12 representative flows")
    output = output.resolve()
    sources = [path.resolve(strict=True) for path in scripts]
    if any(output == path or output in path.parents for path in sources):
        raise ValueError("candidate scripts must be outside the discovery output")
    inspected = [inspect_playbook(path, bundle) for path in sources]
    if (len({info["scenario_id"] for info in inspected}) != len(inspected) or
            len({json.dumps(info["tap_signature"], sort_keys=True)
                 for info in inspected}) != len(inspected)):
        raise ValueError("discovery playbooks have duplicate scenario or action paths")
    identity = {"schema_version": 1, "kind": "discovery_check", "bundle_id": bundle,
                "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                "backend": backend,
                "scripts": [{"scenario_id": info["scenario_id"],
                             "tap_signature": info["tap_signature"],
                             "tap_count": info["tap_count"],
                             "source_path": str(path), "source_sha256": info["sha256"],
                             "copy_path": f"playbooks/flow-{index:02d}.json",
                             "check_root": f"checks/flow-{index:02d}",
                             "check_path": f"checks/flow-{index:02d}/manifest.json"}
                            for index, (path, info) in enumerate(zip(sources, inspected), 1)]}
    manifest = output / "manifest.json"
    if resume:
        if not manifest.is_file():
            raise ValueError("resume requires an existing discovery check")
        record = _read(manifest)
        for key in ("schema_version", "kind", "bundle_id", "device_id_sha256_prefix",
                    "backend"):
            if record.get(key) != identity[key]:
                raise ValueError("resume target or backend differs")
        for current, expected in zip(record.get("scripts", []), identity["scripts"]):
            if any(current.get(key) != value for key, value in expected.items()):
                raise ValueError("resume playbooks differ")
        if len(record.get("scripts", [])) != len(identity["scripts"]):
            raise ValueError("resume playbooks differ")
        if record.get("status") == "complete":
            return manifest, _verified(output)
    else:
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"discovery output is not empty: {output}")
        output.mkdir(parents=True, exist_ok=True)
        record = dict(identity, status="running")
        _save(output, record)
    for item in record["scripts"]:
        script_copy = output / item["copy_path"]
        check_root = output / item["check_root"]
        if check_root.exists() and any(check_root.iterdir()):
            if item.get("check_status") == "complete" and \
                    sha256_file(check_root / "manifest.json") == item.get("check_sha256") and \
                    _verified(check_root):
                continue
            record["status"] = "needs_review"
            return _save(output, record), False
        script_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item["source_path"], script_copy)
        check_manifest, complete = run_playbook(udid, backend, script_copy, check_root)
        item["check_status"] = "complete" if complete else "failed"
        item["check_sha256"] = sha256_file(check_manifest)
        if not complete or not _verified(check_root):
            record["status"] = "needs_review"
            return _save(output, record), False
        _save(output, record)
    record["status"] = "complete"
    target = _save(output, record)
    if not _verified(output):
        record["status"] = "needs_review"
        return _save(output, record), False
    return target, True
