#!/usr/bin/env python3
"""Record the Maps URL emitted by a real Compass coordinate tap on one iPhone."""

import argparse
import hashlib
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from copyapp.experiment import ExperimentUI, _bounded_cleanup
from copyapp.usb_tunnel import ios_mcp_tunnel
from copyapp.verify import sha256_file


HOOK = r"""
const objc = Process.getModuleByName('libobjc.A.dylib');
const getClass = new NativeFunction(objc.getExportByName('objc_getClass'), 'pointer', ['pointer']);
const getSelector = new NativeFunction(objc.getExportByName('sel_registerName'), 'pointer', ['pointer']);
const getMethod = new NativeFunction(objc.getExportByName('class_getInstanceMethod'), 'pointer', ['pointer', 'pointer']);
const getImplementation = new NativeFunction(objc.getExportByName('method_getImplementation'), 'pointer', ['pointer']);
const sendObject = new NativeFunction(objc.getExportByName('objc_msgSend'), 'pointer', ['pointer', 'pointer']);
const klass = getClass(Memory.allocUtf8String('UIApplication'));
if (klass.isNull()) throw new Error('UIApplication class missing');
const absoluteString = getSelector(Memory.allocUtf8String('absoluteString'));
const utf8String = getSelector(Memory.allocUtf8String('UTF8String'));
const hooks = [];
for (const selectorName of ['openURL:', 'openURL:options:completionHandler:']) {
    const method = getMethod(klass, getSelector(Memory.allocUtf8String(selectorName)));
    if (method.isNull()) continue;
    const implementation = getImplementation(method).strip('ia');
    hooks.push({selector: selectorName, implementation: implementation.toString()});
    Interceptor.attach(implementation, {onEnter(args) {
        try {
            const string = sendObject(args[2], absoluteString);
            const bytes = sendObject(string, utf8String);
            send({kind: 'url', selector: selectorName, url: bytes.readUtf8String()});
        } catch (error) {
            send({kind: 'hook_error', selector: selectorName, message: String(error).slice(0, 160)});
        }
    }});
}
rpc.exports = {snapshot() { return {hooks}; }};
"""


def run(udid: str, bundle: str, output: Path) -> Path:
    if bundle not in ("com.apple.compass", "dev.copyapp.compass"):
        raise ValueError("this pilot accepts only original Compass and Copy Compass")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "hook.js").write_text(HOOK + "\n", encoding="utf-8")
    shutil.copy2(__file__, output / "runner.py")
    record = {
        "schema_version": 1,
        "scenario_id": "compass-coordinate-maps-url",
        "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
        "bundle_id": bundle,
        "ui_backend": "ios-mcp",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "failed",
        "url_events": [],
    }
    session = script = None
    stage = "connect_ui"
    try:
        with ios_mcp_tunnel(udid) as port:
            ui = ExperimentUI("ios-mcp", port, Path())
            ui.launch(bundle)
            time.sleep(1.5)
            if ui.frontmost() != bundle:
                raise RuntimeError("target app did not become frontmost")
            observation = ui.observe()
            (output / "before-ui.json").write_text(json.dumps(observation, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
            record["before_screenshot_sha256"] = ui.screenshot(output / "before.jpg")
            stage = "attach_frida"
            from copyapp.frida_device import get_usb_device
            device = get_usb_device(udid)
            app = next((item for item in device.enumerate_applications(scope="full")
                        if item.identifier == bundle), None)
            if app is None or not app.pid:
                raise RuntimeError("target process not found")
            record["pid"] = app.pid
            session = device.attach(app.pid)

            def on_message(message, _data) -> None:
                value = message.get("payload") if isinstance(message, dict) else None
                if isinstance(value, dict) and value.get("kind") in ("url", "hook_error"):
                    record["url_events"].append(value)

            script = session.create_script(HOOK)
            script.on("message", on_message)
            script.load()
            record["hook_snapshot"] = script.exports_sync.snapshot()
            if not record["hook_snapshot"]["hooks"]:
                raise RuntimeError("no UIApplication URL-opening method was hooked")
            stage = "tap"
            if ui.frontmost() != bundle:
                raise RuntimeError("target left foreground before coordinate tap")
            record["tap"] = {"x": 207, "y": 712, "result": ui.tap(207, 712)}
            for _ in range(15):
                time.sleep(0.35)
                if ui.frontmost() == "com.apple.Maps":
                    break
            record["frontmost_after"] = ui.frontmost()
            if record["frontmost_after"] == "com.apple.Maps":
                time.sleep(1.2)
            record["after_screenshot_sha256"] = ui.screenshot(output / "after.jpg")
            record["url_events"] = list(record["url_events"])
            maps_urls = [event["url"] for event in record["url_events"]
                         if event.get("kind") == "url" and event.get("url", "").startswith("maps:")]
            if not maps_urls:
                raise RuntimeError("no Maps URL was observed during the coordinate tap")
            if record["frontmost_after"] != "com.apple.Maps":
                raise RuntimeError("Apple Maps did not become frontmost")
            match = re.fullmatch(r"maps:ll=(-?\d+\.\d+),(-?\d+\.\d+)&trackingMode=2", maps_urls[-1])
            if not match:
                raise RuntimeError("Maps URL does not match expected location handoff format")
            lat, lon = map(float, match.groups())
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise RuntimeError("Maps URL contains out-of-range coordinates")
            record["maps_url"] = maps_urls[-1]
            record["maps_coordinate"] = {"latitude": lat, "longitude": lon}
            record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"stage": stage, "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        cleanup = []
        if script is not None:
            warning = _bounded_cleanup("script unload", script.unload)
            if warning:
                cleanup.append(warning)
        if session is not None:
            warning = _bounded_cleanup("session detach", session.detach)
            if warning:
                cleanup.append(warning)
        if cleanup:
            record["cleanup_warnings"] = cleanup
        record["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (output / "experiment.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                                 encoding="utf-8")
        files = sorted(path for path in output.iterdir() if path.is_file() and path.name != "manifest.json")
        manifest = {"schema_version": 1, "status": record["status"],
                    "evidence": [{"path": path.name, "sha256": sha256_file(path)} for path in files]}
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    return output / "experiment.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--udid", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.udid, args.bundle, args.out)
    print(result)
    if json.loads(result.read_text())["status"] != "complete":
        raise SystemExit(1)
