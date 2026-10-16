"""Bounded Frida call-count trace for explicitly named Objective-C methods."""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MAX_METHODS = 32
MAX_SECONDS = 60


def parse_method(spec: str) -> Tuple[str, str]:
    if "::" not in spec:
        raise ValueError("method must use ClassName::selector: syntax")
    class_name, selector = spec.split("::", 1)
    if not class_name or not selector or len(class_name) > 200 or len(selector) > 200:
        raise ValueError("invalid class or selector")
    return class_name, selector


def parse_branch_register(spec: str) -> Tuple[int, str]:
    if ":" not in spec:
        raise ValueError("branch register must use OFFSET:xN syntax")
    offset_text, register = spec.split(":", 1)
    if not re.fullmatch(r"x(?:[0-9]|[12][0-9]|30)", register):
        raise ValueError("branch register must be x0 through x30")
    try:
        offset = int(offset_text, 0)
    except ValueError as exc:
        raise ValueError("branch register offset must be an integer") from exc
    if offset < 0:
        raise ValueError("branch register offset must be nonnegative")
    return offset, register


def trace_script(methods: List[Tuple[str, str]], stream_hits: bool = False,
                 static_targets: Optional[List[dict]] = None,
                 arg2_u32_indices: Optional[List[int]] = None,
                 branch_offsets: Optional[List[int]] = None,
                 branch_return_u32_offsets: Optional[List[int]] = None,
                 branch_registers: Optional[List[Tuple[int, str]]] = None) -> str:
    indices = arg2_u32_indices or []
    if len(set(indices)) != len(indices) or any(type(i) is not int or
                                                not 0 <= i < len(methods) for i in indices):
        raise ValueError("argument capture indices must name unique requested methods")
    branches = branch_offsets or []
    if (len(branches) > 32 or len(set(branches)) != len(branches) or
            any(type(value) is not int or value < 0 for value in branches) or
            (branches and not static_targets)):
        raise ValueError("branch offsets require unique nonnegative entries and static app binding")
    return_offsets = branch_return_u32_offsets or []
    if (len(set(return_offsets)) != len(return_offsets) or
            any(type(value) is not int or value not in branches for value in return_offsets)):
        raise ValueError("return capture requires unique selected branch offsets")
    registers = branch_registers or []
    if (len(registers) > 32 or len(set(registers)) != len(registers) or
            any(type(offset) is not int or offset not in branches or
                not isinstance(register, str) or
                not re.fullmatch(r"x(?:[0-9]|[12][0-9]|30)", register)
                for offset, register in registers)):
        raise ValueError("register capture requires unique selected branch offsets and x0–x30")
    definitions = json.dumps([{"class": name, "selector": selector}
                              for name, selector in methods], ensure_ascii=True)
    targets = json.dumps(static_targets or [], ensure_ascii=True)
    capture_indices = json.dumps(indices)
    branch_values = json.dumps(branches)
    return_values = json.dumps(return_offsets)
    register_values = json.dumps([{"offset": offset, "register": register}
                                  for offset, register in registers])
    return """
const definitions = %s;
const streamHits = %s;
const staticTargets = %s;
const arg2U32Indices = new Set(%s);
const branchOffsets = %s;
const branchReturnU32Offsets = new Set(%s);
const branchRegisters = %s;
const counts = definitions.map(() => 0);
const staticCounts = definitions.map(() => 0);
const branchCounts = branchOffsets.map(() => 0);
const observed = [];
const staticObserved = [];
const branchObserved = [];
const libobjc = Process.getModuleByName("libobjc.A.dylib");
const getClass = new NativeFunction(libobjc.getExportByName("objc_getClass"), "pointer", ["pointer"]);
const getSelector = new NativeFunction(libobjc.getExportByName("sel_registerName"), "pointer", ["pointer"]);
const getMethod = new NativeFunction(libobjc.getExportByName("class_getInstanceMethod"), "pointer", ["pointer", "pointer"]);
const getImp = new NativeFunction(libobjc.getExportByName("method_getImplementation"), "pointer", ["pointer"]);
definitions.forEach((item, index) => {
    const klass = getClass(Memory.allocUtf8String(item.class));
    if (klass.isNull()) {
        observed.push({class: item.class, selector: item.selector, status: "class_missing"});
        return;
    }
    const method = getMethod(klass, getSelector(Memory.allocUtf8String(item.selector)));
    if (method.isNull()) {
        observed.push({class: item.class, selector: item.selector, status: "method_missing"});
        return;
    }
    const imp = getImp(method);
    const metadata = {class: item.class, selector: item.selector, status: "hooked", imp: imp.toString()};
    try {
        const address = imp.strip('ia');
        const module = Process.findModuleByAddress(address);
        metadata.imp_stripped = address.toString();
        if (module !== null) {
            metadata.module_name = module.name;
            metadata.module_path = module.path;
            metadata.module_base = module.base.toString();
            metadata.module_offset = address.sub(module.base).toString();
        }
        else {
            metadata.binding_status = "module_not_found";
        }
    }
    catch (error) {
        metadata.binding_status = "unavailable";
        metadata.binding_error = String(error).slice(0, 160);
    }
    observed.push(metadata);
    Interceptor.attach(imp, {onEnter(args) {
        counts[index] += 1;
        if (streamHits) {
            const hit = {type: "method_hit", index: index};
            if (arg2U32Indices.has(index)) hit.arg2_u32 = args[2].toUInt32();
            send(hit);
        }
    }});
});
staticTargets.forEach((target) => {
    const matches = Process.enumerateModules().filter(module =>
        module.name === target.binary_name &&
        module.path.endsWith('/' + target.app_dir + '/' + target.binary_name));
    if (matches.length !== 1) throw new Error('expected one loaded app image for static entry');
    const module = matches[0];
    if (!Number.isSafeInteger(target.offset) || target.offset < 0 || target.offset >= module.size)
        throw new Error('static entry offset outside loaded app image');
    const address = module.base.add(target.offset);
    staticObserved.push({index: target.index, class: target.class,
        selector: target.selector, status: 'hooked', address: address.toString(),
        module_path: module.path, module_base: module.base.toString(),
        module_offset: '0x' + target.offset.toString(16)});
    Interceptor.attach(address, {onEnter(args) {
        staticCounts[target.index] += 1;
        if (streamHits) {
            const hit = {type: 'static_hit', index: target.index};
            if (arg2U32Indices.has(target.index)) hit.arg2_u32 = args[2].toUInt32();
            send(hit);
        }
    }});
});
if (branchOffsets.length > 0) {
    const target = staticTargets[0];
    const matches = Process.enumerateModules().filter(module =>
        module.name === target.binary_name &&
        module.path.endsWith('/' + target.app_dir + '/' + target.binary_name));
    if (matches.length !== 1) throw new Error('expected one loaded app image for branch entries');
    const module = matches[0];
    branchOffsets.forEach((offset, index) => {
        if (!Number.isSafeInteger(offset) || offset < 0 || offset >= module.size)
            throw new Error('branch offset outside loaded app image');
        const address = module.base.add(offset);
        branchObserved.push({index: index, address: address.toString(),
            module_path: module.path, module_base: module.base.toString(),
            module_offset: '0x' + offset.toString(16)});
        const callbacks = {onEnter(args) {
            branchCounts[index] += 1;
            if (streamHits) send({type: 'branch_hit', index: index});
            branchRegisters.forEach(item => {
                if (item.offset !== offset || !streamHits) return;
                try {
                    const pointer = this.context[item.register].strip('ia');
                    const owner = Process.findModuleByAddress(pointer);
                    if (owner !== null && owner.path === module.path) {
                        send({type: 'branch_register', index: index,
                              register: item.register, status: 'app_image',
                              target_offset: pointer.sub(module.base).toString()});
                    } else {
                        send({type: 'branch_register', index: index,
                              register: item.register, status: 'outside_app_image'});
                    }
                } catch (error) {
                    send({type: 'branch_register', index: index,
                          register: item.register, status: 'unavailable'});
                }
            });
        }};
        if (branchReturnU32Offsets.has(offset)) {
            callbacks.onLeave = function (retval) {
                if (streamHits) send({type: 'branch_return_u32', index: index,
                                      value: retval.toUInt32()});
            };
        }
        Interceptor.attach(address, callbacks);
    });
}
rpc.exports = {snapshot() { return {methods: observed, counts: counts,
    static_entries: staticObserved, static_counts: staticCounts,
    branch_entries: branchObserved, branch_counts: branchCounts}; }};
""" % (definitions, "true" if stream_hits else "false", targets, capture_indices,
       branch_values, return_values, register_values)


def trace_methods(udid: str, bundle: str, specs: List[str], duration: int,
                  output: Path) -> Tuple[Path, bool]:
    if not 1 <= duration <= MAX_SECONDS:
        raise ValueError("trace duration must be between 1 and 60 seconds")
    methods = [parse_method(spec) for spec in specs]
    if not methods or len(methods) > MAX_METHODS or len(set(methods)) != len(methods):
        raise ValueError("provide 1–32 unique methods")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite trace: {output}")
    from copyapp.frida_device import get_usb_device
    device = get_usb_device(udid)
    app = next((item for item in device.enumerate_applications(scope="full")
                if item.identifier == bundle), None)
    if app is None or not app.pid:
        raise RuntimeError("target app is not running")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record: Dict[str, Any] = {
        "schema_version": 1, "source": "Frida in-memory Objective-C method interception",
        "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
        "bundle_id": bundle, "process_name": app.name, "pid": app.pid,
        "started_at": started, "requested_duration_seconds": duration,
        "note": "Counts cover only the successful observation window. No arguments, return values or location data were collected.",
    }
    session = None
    script = None
    try:
        session = device.attach(app.pid)
        script = session.create_script(trace_script(methods))
        script.load()
        observation_start = time.monotonic()
        time.sleep(duration)
        snapshot = script.exports_sync.snapshot()
        record.update({"status": "complete", "methods": snapshot["methods"],
                       "call_counts": snapshot["counts"],
                       "observed_seconds": round(time.monotonic() - observation_start, 3)})
    except Exception as exc:
        record.update({"status": "failed", "error": {
            "type": type(exc).__name__, "message": str(exc)[:300],
        }})
    finally:
        if script is not None:
            try:
                script.unload()
            except Exception:
                pass
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output, record["status"] == "complete"
