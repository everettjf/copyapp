#!/usr/bin/env python3
"""Capture a reversible, identical CoreMotion heading offset in both Compass apps.

The hook changes only the target process's CMDeviceMotion.heading return value.
It is removed when the Frida script unloads; no device setting is changed.
"""

import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from copyapp.experiment import ExperimentUI, _bounded_cleanup
from copyapp.usb_tunnel import ios_mcp_tunnel
from copyapp.verify import sha256_file


HOOK = r"""
const objc = Process.getModuleByName('libobjc.A.dylib');
const getClass = new NativeFunction(objc.getExportByName('objc_getClass'), 'pointer', ['pointer']);
const getSelector = new NativeFunction(objc.getExportByName('sel_registerName'), 'pointer', ['pointer']);
const getMethod = new NativeFunction(objc.getExportByName('class_getInstanceMethod'), 'pointer', ['pointer', 'pointer']);
const getImplementation = new NativeFunction(objc.getExportByName('method_getImplementation'), 'pointer', ['pointer']);
const klass = getClass(Memory.allocUtf8String('CMDeviceMotion'));
if (klass.isNull()) throw new Error('CMDeviceMotion class missing');
const method = getMethod(klass, getSelector(Memory.allocUtf8String('heading')));
if (method.isNull()) throw new Error('CMDeviceMotion heading getter missing');
const implementation = getImplementation(method).strip('ia');
const original = new NativeFunction(implementation, 'double', ['pointer', 'pointer']);
let offset = 0;
let calls = 0;
let lastRaw = null;
Interceptor.replace(implementation, new NativeCallback(function (self, command) {
    const raw = original(self, command);
    calls++;
    lastRaw = raw;
    return offset !== 0 && Number.isFinite(raw) && raw >= 0 ? (raw + offset + 360) %% 360 : raw;
}, 'double', ['pointer', 'pointer']));
rpc.exports = {
    setoffset(value) {
        if (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > 90)
            throw new Error('offset must be a finite angle within 90 degrees');
        offset = value;
        return offset;
    },
    snapshot() { return {implementation: implementation.toString(), calls, last_raw: lastRaw, offset}; }
};
""".replace("%%", "%")

VIEW_HOOK = r"""
const objc = Process.getModuleByName('libobjc.A.dylib');
const getClass = new NativeFunction(objc.getExportByName('objc_getClass'), 'pointer', ['pointer']);
const getSelector = new NativeFunction(objc.getExportByName('sel_registerName'), 'pointer', ['pointer']);
const getMethod = new NativeFunction(objc.getExportByName('class_getInstanceMethod'), 'pointer', ['pointer', 'pointer']);
const getImplementation = new NativeFunction(objc.getExportByName('method_getImplementation'), 'pointer', ['pointer']);
const getIvar = new NativeFunction(objc.getExportByName('class_getInstanceVariable'), 'pointer', ['pointer', 'pointer']);
const getIvarOffset = new NativeFunction(objc.getExportByName('ivar_getOffset'), 'long', ['pointer']);
const sendVoid = new NativeFunction(objc.getExportByName('objc_msgSend'), 'void', ['pointer', 'pointer']);
const dispatch = Process.getModuleByName('libdispatch.dylib');
const mainQueue = dispatch.getExportByName('_dispatch_main_q');
const dispatchAsync = new NativeFunction(dispatch.getExportByName('dispatch_async_f'),
                                         'void', ['pointer', 'pointer', 'pointer']);
const klass = getClass(Memory.allocUtf8String('CompassBearingView'));
if (klass.isNull()) throw new Error('CompassBearingView missing');
const selector = getSelector(Memory.allocUtf8String('setCompassHeading:'));
const method = getMethod(klass, selector);
if (method.isNull()) throw new Error('setCompassHeading: missing');
const implementation = getImplementation(method).strip('ia');
const layout = getMethod(klass, getSelector(Memory.allocUtf8String('layoutSubviews')));
const endAngleOffset = getIvarOffset(getIvar(klass, Memory.allocUtf8String('_endAngle')));
const startAngleOffset = getIvarOffset(getIvar(klass, Memory.allocUtf8String('_startAngle')));
const bearingOffset = getIvarOffset(getIvar(klass, Memory.allocUtf8String('_bearing')));
const radiusOffset = getIvarOffset(getIvar(klass, Memory.allocUtf8String('_radius')));
const innerRadiusOffset = getIvarOffset(getIvar(klass, Memory.allocUtf8String('_innerRadius')));
const outerRadiusOffset = getIvarOffset(getIvar(klass, Memory.allocUtf8String('_outerRadius')));
const rotating = getClass(Memory.allocUtf8String('CompassRotatingView'));
const angleOffset = getIvarOffset(getIvar(rotating, Memory.allocUtf8String('_angle')));
const compassHeadingOffset = getIvarOffset(getIvar(rotating, Memory.allocUtf8String('_compassHeading')));
const updateSelector = getSelector(Memory.allocUtf8String('updateLayer'));
const layoutSelector = getSelector(Memory.allocUtf8String('layoutIfNeeded'));
let instance = null;
let baseAngle = null;
let offset = 0;
let calls = 0;
let layouts = 0;
function applyOffset() {
    if (instance === null || baseAngle === null) return;
    instance.add(angleOffset).writeDouble(baseAngle - offset * Math.PI / 180);
    sendVoid(instance, updateSelector);
    sendVoid(instance, layoutSelector);
}
const updateOnMain = new NativeCallback(function () { applyOffset(); }, 'void', ['pointer']);
Interceptor.attach(getImplementation(layout).strip('ia'), {
    onEnter(args) { instance = args[0]; layouts++; }
});
Interceptor.attach(implementation, {
    onEnter(args) { instance = args[0]; calls++; },
    onLeave() {
        if (instance === null) return;
        baseAngle = instance.add(angleOffset).readDouble();
        if (offset !== 0) applyOffset();
    }
});
rpc.exports = {
    setoffset(value) {
        if (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > 90)
            throw new Error('offset must be a finite angle within 90 degrees');
        if (instance === null) throw new Error('bearing view instance not observed');
        if (offset === 0 || baseAngle === null)
            baseAngle = instance.add(angleOffset).readDouble();
        offset = value;
        dispatchAsync(mainQueue, ptr(0), updateOnMain);
        return offset;
    },
    snapshot() { return {implementation: implementation.toString(), calls,
                         last_raw: instance ? instance.add(compassHeadingOffset).readDouble() : null,
                         offset, instance: instance?.toString() ?? null,
                         bearing_state: instance ? instance.add(bearingOffset).readDouble() : null,
                         radius: instance ? instance.add(radiusOffset).readDouble() : null,
                         inner_radius: instance ? instance.add(innerRadiusOffset).readDouble() : null,
                         outer_radius: instance ? instance.add(outerRadiusOffset).readDouble() : null,
                         start_angle: instance ? instance.add(startAngleOffset).readDouble() : null,
                         end_angle: instance ? instance.add(endAngleOffset).readDouble() : null,
                         layouts, view_angle: instance ? instance.add(angleOffset).readDouble() : null,
                         base_angle: baseAngle}; }
};
"""


def red_pixels(path: Path) -> int:
    with Image.open(path) as source:
        image = source.convert("RGB")
    if image.size != (414, 896):
        raise RuntimeError(f"unexpected screen size: {image.size}")
    return sum(1 for red, green, blue in image.crop((130, 140, 285, 270)).getdata()
               if red >= 25 and red >= green * 1.5 and red >= blue * 1.5)


def run(udid: str, bundle: str, output: Path, angle: float) -> Path:
    if bundle not in ("com.apple.compass", "dev.copyapp.compass"):
        raise ValueError("this pilot accepts only original Compass and Copy Compass")
    if not 5 <= angle <= 90:
        raise ValueError("angle must be between 5 and 90 degrees")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    hook = VIEW_HOOK if bundle == "com.apple.compass" else HOOK
    (output / "hook.js").write_text(hook + "\n", encoding="utf-8")
    shutil.copy2(__file__, output / "runner.py")
    record = {
        "schema_version": 1,
        "scenario_id": "compass-locked-bearing-motion-offset",
        "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
        "bundle_id": bundle,
        "ui_backend": "ios-mcp",
        "offset_degrees": angle,
        "hook_mode": "CompassBearingView._angle + updateLayer" if bundle == "com.apple.compass"
                     else "CMDeviceMotion.heading",
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "failed",
        "stages": [],
        "evidence": [],
    }
    session = script = None
    stage = "connect_ui"
    try:
        with ios_mcp_tunnel(udid) as port:
            ui = ExperimentUI("ios-mcp", port, Path())
            ui.launch(bundle)
            time.sleep(2.5)
            if ui.frontmost() != bundle:
                raise RuntimeError("target app did not become frontmost")

            stage = "attach_frida"
            from copyapp.frida_device import get_usb_device
            device = get_usb_device(udid)
            app = next((item for item in device.enumerate_applications(scope="full")
                        if item.identifier == bundle), None)
            if app is None or not app.pid:
                raise RuntimeError("target app process not found")
            session = device.attach(app.pid)
            script = session.create_script(hook)
            script.load()
            record["pid"] = app.pid
            initial = script.exports_sync.snapshot()
            record["instrumented_method"] = initial["implementation"]

            def capture(label: str) -> dict:
                if ui.frontmost() != bundle:
                    raise RuntimeError(f"target left foreground before {label}")
                path = output / f"{label}.jpg"
                ui.screenshot(path)
                item = {
                    "label": label, "screenshot": path.name,
                    "heading_probe": script.exports_sync.snapshot(),
                    "red_pixels": red_pixels(path),
                }
                observation = output / f"{label}-ui.json"
                observation.write_text(json.dumps(ui.observe(), ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
                item["ui"] = observation.name
                record["stages"].append(item)
                return item

            def is_locked(item: dict) -> bool:
                if bundle == "com.apple.compass":
                    bearing = item["heading_probe"].get("bearing_state")
                    if bearing is None:
                        return item["red_pixels"] > 10
                    return bearing < 1e300
                return item["red_pixels"] > 10

            stage = "unlocked"
            baseline = capture("unlocked")
            if is_locked(baseline):
                ui.tap(207, 325)
                time.sleep(0.9)
                baseline = capture("unlocked-reset")
            if is_locked(baseline):
                raise RuntimeError("bearing marker remained visible before lock")

            stage = "locked"
            ui.tap(207, 325)
            time.sleep(0.9)
            locked = capture("locked")
            if not is_locked(locked):
                raise RuntimeError("bearing marker did not appear after tap")

            stage = "offset"
            script.exports_sync.setoffset(angle)
            time.sleep(1.0)
            displaced = capture("offset")

            stage = "restored"
            script.exports_sync.setoffset(0)
            time.sleep(1.0)
            restored = capture("restored")
            if displaced["red_pixels"] <= locked["red_pixels"] + 100:
                raise RuntimeError("heading offset did not create a visible red deviation sector")
            if restored["red_pixels"] >= displaced["red_pixels"] - 100:
                raise RuntimeError("deviation sector did not shrink after restoring heading")
            record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"stage": stage, "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        cleanup = []
        if script is not None:
            def reset_offset() -> None:
                script.exports_sync.setoffset(0)
                for _ in range(10):
                    snapshot = script.exports_sync.snapshot()
                    angle_now = snapshot.get("view_angle")
                    angle_base = snapshot.get("base_angle")
                    if snapshot.get("offset") == 0 and (angle_now is None or angle_base is None or
                                                         abs(angle_now - angle_base) < 0.0001):
                        return
                    time.sleep(0.1)
                raise RuntimeError("bearing-view angle restoration was not confirmed")

            warning = _bounded_cleanup("offset reset", reset_offset)
            if warning:
                cleanup.append(warning)
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
        record_path = output / "experiment.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        files = sorted(path for path in output.iterdir() if path.is_file() and path.name != "manifest.json")
        manifest = {
            "schema_version": 1,
            "status": record["status"],
            "evidence": [{"path": path.name, "sha256": sha256_file(path)} for path in files],
        }
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    return output / "experiment.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--udid", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--angle", type=float, default=45.0)
    args = parser.parse_args()
    result = run(args.udid, args.bundle, args.out, args.angle)
    print(result)
    if json.loads(result.read_text())["status"] != "complete":
        raise SystemExit(1)
