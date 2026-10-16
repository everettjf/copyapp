"""Replay a bounded UI scenario on one named iPhone with retained evidence."""

import asyncio
import hashlib
import json
import math
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from copyapp.experiment import ExperimentUI
from copyapp.ictrl import DEFAULT_CLIENT
from copyapp.ocr_file import ocr_file
from copyapp.usb_tunnel import ictrl_tunnel, ios_mcp_tunnel
from copyapp.ui_capture import capture_stable
from copyapp.verify import sha256_file


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def _fresh_launch(udid: str, bundle: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.process_control import ProcessControl

    device = await create_using_usbmux(serial=udid, connection_type="USB", autopair=False)
    try:
        async with DvtProvider(device) as provider, ProcessControl(provider) as control:
            await control.launch(bundle, kill_existing=True)
    finally:
        await device.close()


def _text(observation: Dict[str, Any], backend: str) -> str:
    if backend == "ictrl":
        return str(observation.get("source") or "")
    return "\n".join(str(item.get("text") or "") for item in observation.get("elements", [])
                     if isinstance(item, dict))


def _record_file(output: Path, path: Path, evidence: list) -> None:
    evidence.append({"path": str(path.relative_to(output)), "sha256": sha256_file(path)})


def run_playbook(udid: str, backend: str, script: Path, output: Path,
                 port: Optional[int] = None, ictrl_client: Path = DEFAULT_CLIENT,
                 trace_observer=None) -> Tuple[Path, bool]:
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    plan = json.loads(script.read_text(encoding="utf-8"))
    bundle = plan.get("bundle_id")
    scenario_id = plan.get("scenario_id")
    steps = plan.get("steps")
    if (plan.get("schema_version") != 1 or not isinstance(bundle, str) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle) or
            (scenario_id is not None and (not isinstance(scenario_id, str) or
             not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", scenario_id))) or
            not isinstance(steps, list) or not 1 <= len(steps) <= 64):
        raise ValueError("invalid UI playbook")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    script_copy = output / "playbook.json"
    shutil.copyfile(script, script_copy)
    record: Dict[str, Any] = {
        "schema_version": 1, "bundle_id": bundle, "ui_backend": backend,
        "scenario_id": scenario_id,
        "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
        "started_at": _now(), "status": "failed", "steps": [], "evidence": [],
    }
    _record_file(output, script_copy, record["evidence"])
    manifest = output / "manifest.json"
    numbers: Dict[str, int] = {}
    try:
        tunnel = (ios_mcp_tunnel(udid) if backend == "ios-mcp" else
                  ictrl_tunnel(udid, ictrl_client)) if port is None else None
        if tunnel is not None:
            with tunnel as own_port:
                _run_steps(udid, bundle, backend, steps, plan, output, own_port,
                           ictrl_client, record, numbers, trace_observer)
        else:
            _run_steps(udid, bundle, backend, steps, plan, output, port,
                       ictrl_client, record, numbers, trace_observer)
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400],
                           "step_index": len(record["steps"])}
    finally:
        if trace_observer is not None:
            try:
                trace_observer.finish()
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = {"type": type(exc).__name__,
                                   "message": f"trace cleanup: {str(exc)[:350]}",
                                   "step_index": len(record["steps"])}
        record["finished_at"] = _now()
        manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, record["status"] == "complete"


def _run_steps(udid: str, bundle: str, backend: str, steps: list, plan: dict,
               output: Path, port: int, ictrl_client: Path, record: dict,
               numbers: Dict[str, int], trace_observer=None) -> None:
    ui = ExperimentUI(backend, port, ictrl_client)
    width, height = ui.bounds()
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        raise RuntimeError("device screen bounds unavailable")
    record["screen"] = {"width": width, "height": height, "coordinate_space": "points"}
    if plan.get("fresh_launch") is True:
        asyncio.run(_fresh_launch(udid, bundle))
        for _ in range(10):
            if ui.frontmost() == bundle:
                break
            time.sleep(0.3)
        else:
            raise RuntimeError("target did not become frontmost after fresh launch")
        # SpringBoard can report the new foreground app before UIKit paints its
        # first complete navigation bar. XR / iOS 16 Clock reproduced this.
        time.sleep(2.0)
    if trace_observer is not None:
        if ui.frontmost() != bundle:
            raise RuntimeError("target is not frontmost before trace attachment")
        trace_observer.start(udid, bundle)
    for index, step in enumerate(steps, 1):
        step_started = time.monotonic()
        if not isinstance(step, dict) or step.get("action") not in (
                "observe", "tap", "tap_label", "screenshot", "expect_foreground"):
            raise ValueError(f"invalid playbook step {index}")
        wait_ms = step.get("wait_ms", 0)
        if type(wait_ms) is not int or not 0 <= wait_ms <= 5000:
            raise ValueError(f"invalid wait_ms at step {index}")
        if wait_ms:
            time.sleep(wait_ms / 1000)
        action = step["action"]
        if action == "expect_foreground":
            expected_frontmost = step.get("bundle_id")
            if (not isinstance(expected_frontmost, str) or
                    not re.fullmatch(r"[A-Za-z0-9_.-]+", expected_frontmost)):
                raise ValueError(f"invalid expected foreground app at step {index}")
            for attempt in range(1, 11):
                frontmost = ui.frontmost()
                if frontmost == expected_frontmost:
                    break
                time.sleep(0.3)
        else:
            frontmost = ui.frontmost()
            if frontmost != bundle:
                raise RuntimeError(f"target left foreground at step {index}: {frontmost}")
        item: Dict[str, Any] = {"index": index, "action": action,
                                "at": _now(), "frontmost": frontmost}
        record["steps"].append(item)
        if action == "expect_foreground":
            item["expected_frontmost"] = expected_frontmost
            item["attempts"] = attempt
            if frontmost != expected_frontmost:
                raise RuntimeError(f"expected foreground app was not reached at step {index}: {frontmost}")
        elif action == "observe":
            expected = step.get("contains", [])
            if isinstance(expected, str):
                expected = [expected]
            if not isinstance(expected, list) or any(not isinstance(s, str) for s in expected):
                raise ValueError(f"invalid contains at step {index}")
            for attempt in range(1, 6):
                value = ui.observe()
                visible = _text(value, backend)
                missing = [s for s in expected if s not in visible]
                if not missing or attempt == 5:
                    break
                time.sleep(0.3)
            path = output / f"step-{index:02d}-observe.json"
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            _record_file(output, path, record["evidence"])
            if missing:
                image_path = output / f"step-{index:02d}-observe-ocr.jpg"
                ocr_path = output / f"step-{index:02d}-observe-ocr.json"
                ui.screenshot(image_path)
                _record_file(output, image_path, record["evidence"])
                ocr_file(image_path, ocr_path)
                _record_file(output, ocr_path, record["evidence"])
                ocr_record = json.loads(ocr_path.read_text(encoding="utf-8"))
                ocr_text = "\n".join(str(entry.get("text") or "") for entry in
                                     ocr_record["result"]["texts"] if isinstance(entry, dict))
                missing = [s for s in expected if s not in ocr_text]
                item["observation_source"] = "screenshot_ocr"
                item["observation_image_path"] = str(image_path.relative_to(output))
                item["observation_image_sha256"] = sha256_file(image_path)
                item["observation_ocr_path"] = str(ocr_path.relative_to(output))
                item["observation_ocr_sha256"] = sha256_file(ocr_path)
                visible = ocr_text
            else:
                item["observation_source"] = "accessibility"
            item["attempts"] = attempt
            item["accessibility_coverage"] = value.get("ax_coverage")
            item["element_count"] = value.get("element_count", value.get("total_returned"))
            item["visible_text"] = visible[:2000]
            item["missing"] = missing
            item["evidence_path"] = str(path.relative_to(output))
            if missing:
                raise RuntimeError(f"missing visible text at step {index}: {missing}")
            extract = step.get("capture_number")
            if extract:
                name, pattern = extract.get("name"), extract.get("pattern")
                if not isinstance(name, str) or not isinstance(pattern, str):
                    raise ValueError("invalid capture_number")
                match = re.search(pattern, visible)
                if not match or not match.group(1).isdigit():
                    raise RuntimeError(f"numeric capture failed at step {index}")
                numbers[name] = int(match.group(1))
                item["captured_number"] = {"name": name, "value": numbers[name]}
            compare = step.get("compare_number")
            if compare:
                name, pattern, delta = compare.get("to"), compare.get("pattern"), compare.get("delta")
                if name not in numbers or not isinstance(pattern, str) or type(delta) is not int:
                    raise ValueError("invalid compare_number")
                match = re.search(pattern, visible)
                if not match or not match.group(1).isdigit():
                    raise RuntimeError(f"numeric comparison failed at step {index}")
                actual = int(match.group(1))
                item["number_comparison"] = {"before": numbers[name], "after": actual, "delta": delta}
                if actual != numbers[name] + delta:
                    raise RuntimeError(f"numeric delta mismatch at step {index}")
        elif action == "tap_label":
            label = step.get("label")
            if not isinstance(label, str) or not label:
                raise ValueError(f"invalid tap label at step {index}")
            region = step.get("region_points")
            if region is not None and (
                    not isinstance(region, list) or len(region) != 4 or
                    any(type(value) not in (int, float) or not math.isfinite(value)
                        for value in region) or
                    not 0 <= region[0] < region[2] <= width or
                    not 0 <= region[1] < region[3] <= height):
                raise ValueError(f"invalid tap label region at step {index}")
            if trace_observer is not None:
                trace_observer.begin_step(index, action)
            try:
                item["result"] = ui.tap_label(label, region, bundle)
            finally:
                if trace_observer is not None:
                    trace_observer.end_step()
            match = item["result"].get("match", {})
            tap_y = match.get("y") if isinstance(match, dict) else None
            if isinstance(tap_y, (int, float)) and tap_y >= height * 0.8:
                # Tab changes can expose accessibility labels before the new
                # view has finished painting; settle before observing it.
                time.sleep(2.0)
                item["post_tap_settle_ms"] = 2000
        elif action == "tap":
            x, y = step.get("x"), step.get("y")
            if (not isinstance(x, (int, float)) or isinstance(x, bool) or
                    not isinstance(y, (int, float)) or isinstance(y, bool) or
                    not 0 <= x <= width or not 0 <= y <= height):
                raise ValueError(f"invalid tap coordinates at step {index}")
            if trace_observer is not None:
                trace_observer.begin_step(index, action)
            try:
                item["result"] = ui.tap(x, y)
            finally:
                if trace_observer is not None:
                    trace_observer.end_step()
        else:
            path = output / f"step-{index:02d}-screenshot.jpg"
            if step.get("stable") is True:
                # Allow the last accessibility update to reach the rendered
                # frame before assessing screenshot stability.
                time.sleep(1.0)
                sample = output / f".step-{index:02d}-sample.jpg"
                try:
                    def capture() -> bytes:
                        ui.screenshot(sample)
                        return sample.read_bytes()

                    image, stability = capture_stable(capture, samples=6,
                                                      interval=0.35, threshold=0.012,
                                                      minimum_samples=5)
                finally:
                    sample.unlink(missing_ok=True)
                path.write_bytes(image)
                item["stability"] = stability
            else:
                ui.screenshot(path)
            item["sha256"] = sha256_file(path)
            item["evidence_path"] = str(path.relative_to(output))
            _record_file(output, path, record["evidence"])
            if step.get("stable") is True and not item["stability"]["stable"]:
                raise RuntimeError(f"screenshot did not settle at step {index}")
            if ui.frontmost() != bundle:
                raise RuntimeError(f"target left foreground during screenshot at step {index}")
            ready_contains = step.get("ready_contains")
            if ready_contains is not None:
                if not isinstance(ready_contains, str) or not ready_contains:
                    raise ValueError(f"invalid ready_contains at step {index}")
                for attempt in range(1, 6):
                    value = ui.observe()
                    visible = _text(value, backend)
                    if ready_contains in visible or attempt == 5:
                        break
                    time.sleep(0.3)
                item["ready_contains"] = ready_contains
                item["ready_attempts"] = attempt
                item["ready_visible_text"] = visible[:2000]
                if ready_contains in visible:
                    item["ready_source"] = "accessibility"
                    item["ready_found"] = True
                else:
                    ocr_path = output / f"step-{index:02d}-ready-ocr.json"
                    ocr_file(path, ocr_path)
                    _record_file(output, ocr_path, record["evidence"])
                    ocr_record = json.loads(ocr_path.read_text(encoding="utf-8"))
                    ocr_text = "\n".join(str(entry.get("text") or "") for entry in
                                         ocr_record["result"]["texts"] if isinstance(entry, dict))
                    item["ready_source"] = "screenshot_ocr"
                    item["ready_ocr_path"] = str(ocr_path.relative_to(output))
                    item["ready_ocr_sha256"] = sha256_file(ocr_path)
                    item["ready_found"] = ready_contains in ocr_text
                if not item["ready_found"]:
                    raise RuntimeError(f"screenshot target content was not ready at step {index}")
        item["duration_ms"] = round((time.monotonic() - step_started) * 1000)
