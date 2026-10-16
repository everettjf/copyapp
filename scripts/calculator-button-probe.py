#!/usr/bin/env python3
"""Trace Calculator's on-disk button entry and its current Objective-C IMP."""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from copyapp.experiment import ExperimentUI, _bounded_cleanup
from copyapp.usb_tunnel import ios_mcp_tunnel
from copyapp.verify import sha256_file


BUNDLE = "com.apple.calculator"
BINARY_SHA256 = "8d4e059834d4c3df36f2b5ba473863b55230cb21c7eeeee7919cafdb0dc7ff3c"
STATIC_OFFSET = 0xEB0C
HOOK = r"""
const appImages = Process.enumerateModules().filter(m =>
    m.path.includes('/Calculator.app/Calculator') && m.name === 'Calculator');
if (appImages.length !== 1) throw new Error('expected one Calculator.app image');
const app = appImages[0];
const appEntry = app.base.add(0xeb0c);
const objc = Process.getModuleByName('libobjc.A.dylib');
const getClass = new NativeFunction(objc.getExportByName('objc_getClass'), 'pointer', ['pointer']);
const getSelector = new NativeFunction(objc.getExportByName('sel_registerName'), 'pointer', ['pointer']);
const getMethod = new NativeFunction(objc.getExportByName('class_getInstanceMethod'), 'pointer', ['pointer', 'pointer']);
const getImplementation = new NativeFunction(objc.getExportByName('method_getImplementation'), 'pointer', ['pointer']);
const klass = getClass(Memory.allocUtf8String('_TtC10Calculator15CalculatorModel'));
if (klass.isNull()) throw new Error('CalculatorModel class missing');
const method = getMethod(klass, getSelector(Memory.allocUtf8String('buttonPressed:')));
if (method.isNull()) throw new Error('CalculatorModel method missing');
const liveEntry = getImplementation(method).strip('ia');
const liveModule = Process.findModuleByAddress(liveEntry);
let currentStep = '';
const hooks = [
    {kind: 'app-static-entry', address: appEntry, module: app},
    {kind: 'objc-current-imp', address: liveEntry, module: liveModule}
];
const calculate = Process.enumerateModules().find(m =>
    m.path.includes('/PrivateFrameworks/Calculate.framework/Calculate'));
if (calculate) {
    const evaluate = calculate.findExportByName('CalculatePerformExpression');
    if (evaluate) {
        hooks.push({kind: 'calculate-expression', address: evaluate, module: calculate});
        Interceptor.attach(evaluate, {
            onEnter(args) {
                this.step = currentStep;
                this.expression = args[0].readUtf8String();
                this.output = args[3];
            },
            onLeave(retval) {
                send({kind: 'calculate-expression', step: this.step,
                      expression: this.expression, result: this.output.readUtf8String(),
                      return_code: retval.toInt32()});
            }
        });
    }
}
for (const hook of hooks) {
    if (hook.kind === 'calculate-expression') continue;
    Interceptor.attach(hook.address, {onEnter(args) {
        send({kind: hook.kind, step: currentStep, button_id: args[2].toUInt32(),
              address: hook.address.toString()});
    }});
}
rpc.exports = {
    setstep(value) { currentStep = value; },
    snapshot() { return {hooks: hooks.map(h => ({kind: h.kind,
        address: h.address.toString(), module_path: h.module?.path ?? null,
        module_base: h.module?.base.toString() ?? null}))}; }
};
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(udid: str, binary: Path, output: Path) -> Path:
    if sha256_file(binary) != BINARY_SHA256:
        raise ValueError("Calculator binary differs from the selected XR case")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "hook.js").write_text(HOOK + "\n", encoding="utf-8")
    record = {"schema_version": 1, "bundle_id": BUNDLE,
              "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
              "binary_sha256": BINARY_SHA256, "static_offset": hex(STATIC_OFFSET),
              "started_at": now(), "status": "failed", "events": [], "actions": []}
    session = script = None
    stage = "connect"
    try:
        with ios_mcp_tunnel(udid) as port:
            ui = ExperimentUI("ios-mcp", port, Path())
            ui.launch(BUNDLE)
            time.sleep(0.5)
            if ui.frontmost() != BUNDLE:
                raise RuntimeError("Calculator is not frontmost")
            labels = [str(e.get("text")) for e in ui.observe().get("elements", [])]
            clear = "all clear" if "all clear" in labels else "clear"
            ui.tap_label(clear)
            record["frontmost_before"] = ui.frontmost()
            record["screenshot_before_sha256"] = ui.screenshot(output / "before.jpg")
            stage = "attach"
            from copyapp.frida_device import get_usb_device
            device = get_usb_device(udid)
            app = next((a for a in device.enumerate_applications(scope="full")
                        if a.identifier == BUNDLE and a.pid), None)
            if app is None:
                raise RuntimeError("Calculator process unavailable")
            record["pid"] = app.pid
            session = device.attach(app.pid)

            def on_message(message, _data):
                payload = message.get("payload") if isinstance(message, dict) else None
                if message.get("type") == "send" and isinstance(payload, dict):
                    record["events"].append(payload)
                elif message.get("type") == "error":
                    record["events"].append({"kind": "hook_error", "message": str(message)[:400]})

            script = session.create_script(HOOK)
            script.on("message", on_message)
            script.load()
            record["hook_snapshot"] = script.exports_sync.snapshot()
            stage = "tap"
            for label in ("7", "add", "8", "equals"):
                if ui.frontmost() != BUNDLE:
                    raise RuntimeError("Calculator left foreground")
                script.exports_sync.setstep(label)
                result = ui.tap_label(label)
                time.sleep(0.25)
                record["actions"].append({"label": label, "result": result,
                                          "events_so_far": len(record["events"])})
            script.exports_sync.setstep("")
            record["frontmost_after"] = ui.frontmost()
            record["screenshot_after_sha256"] = ui.screenshot(output / "after.jpg")
            record["after_ui"] = ui.observe()
            if record["frontmost_after"] != BUNDLE:
                raise RuntimeError("Calculator left foreground after input")
            button_events = [(e.get("kind"), e.get("step"), e.get("button_id"))
                             for e in record["events"]
                             if e.get("kind") in ("objc-current-imp", "app-static-entry")]
            expected = [(kind, step, identifier)
                        for step, identifier in (("7", 18), ("add", 8),
                                                 ("8", 19), ("equals", 9))
                        for kind in ("objc-current-imp", "app-static-entry")]
            if button_events != expected:
                raise RuntimeError("button events differ from expected app/AX call chain")
            evaluations = [e for e in record["events"]
                           if e.get("kind") == "calculate-expression"]
            if (len(evaluations) != 1 or evaluations[0].get("step") != "equals" or
                    evaluations[0].get("expression") != "(7)+(8)" or
                    evaluations[0].get("result") != "15" or
                    evaluations[0].get("return_code") != 1):
                raise RuntimeError("Calculate framework result differs from 7 + 8 = 15")
            record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"stage": stage, "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        warnings = []
        if script is not None:
            warning = _bounded_cleanup("script unload", script.unload)
            if warning:
                warnings.append(warning)
        if session is not None:
            warning = _bounded_cleanup("session detach", session.detach)
            if warning:
                warnings.append(warning)
        if warnings:
            record["cleanup_warnings"] = warnings
        record["finished_at"] = now()
        (output / "probe.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        files = sorted(p for p in output.iterdir() if p.is_file() and p.name != "manifest.json")
        (output / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "status": record["status"],
            "evidence": [{"path": p.name, "sha256": sha256_file(p)} for p in files],
        }, indent=2) + "\n")
    return output / "probe.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--udid", required=True)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.udid, args.binary, args.out)
    print(result)
    if json.loads(result.read_text())["status"] != "complete":
        raise SystemExit(1)
