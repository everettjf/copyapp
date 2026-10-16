"""Observe bounded URLSession task starts during one verified UI playbook."""

import hashlib
import io
import json
import re
import threading
import time
from contextlib import nullcontext, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from copyapp.experiment import _bounded_cleanup
from copyapp.gestures import GESTURE_ACTIONS
from copyapp.ictrl import DEFAULT_CLIENT
from copyapp.playbook import run_playbook
from copyapp.usb_tunnel import ictrl_tunnel
from copyapp.verify import sha256_file, verify_case


MAX_EVENTS = 512
MAX_HOOKS = 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def network_hook_source() -> str:
    """Only host, method and a short path fingerprint cross Frida IPC."""
    import frida_tools
    bridge = Path(frida_tools.__file__).parent / "bridges" / "objc.js"
    if not bridge.is_file():
        raise RuntimeError("Frida Objective-C bridge is unavailable")
    return bridge.read_text(encoding="utf-8") + "\nconst ObjC = bridge;\n" + r"""
function pathFingerprint(path) {
    let value = 2166136261;
    for (let i = 0; i < path.length; i++)
        value = Math.imul(value ^ path.charCodeAt(i), 16777619) >>> 0;
    return ('00000000' + value.toString(16)).slice(-8);
}
if (!ObjC.available) throw new Error('Objective-C runtime unavailable');
const names = Object.keys(ObjC.classes).filter(name =>
    name === 'NSURLSessionTask' || /(?:URLSessionTask|NSCF.*Task|URLSession.*Task)/.test(name));
const observed = new Set();
let hooked = 0;
for (const name of names) {
    if (hooked >= 64) break;
    try {
        const method = ObjC.classes[name]['- resume'];
        if (!method) continue;
        const implementation = method.implementation;
        const key = implementation.toString();
        if (observed.has(key)) continue;
        observed.add(key);
        Interceptor.attach(implementation, {onEnter(args) {
            try {
                const task = new ObjC.Object(args[0]);
                let request = task.currentRequest();
                if (!request || !request.handle || request.handle.isNull()) request = task.originalRequest();
                if (!request || !request.handle || request.handle.isNull()) return;
                const url = request.URL();
                if (!url || !url.handle || url.handle.isNull()) return;
                const scheme = url.scheme().toString().toLowerCase();
                const host = url.host().toString().toLowerCase();
                const path = url.path().toString();
                const methodName = request.HTTPMethod().toString().toUpperCase();
                send({type: 'network_task_resume', scheme: scheme, host: host,
                    method: methodName, path_fingerprint: pathFingerprint(path),
                    path_depth: Math.min(path.split('/').filter(Boolean).length, 64)});
            } catch (_) { /* Task may have no URL request. */ }
        }});
        hooked++;
    } catch (_) { /* One class may reject a hook; others remain observable. */ }
}
send({type: 'network_ready', hook_count: hooked, candidate_count: names.length});
"""


def _event(payload: dict) -> dict:
    scheme = payload.get("scheme")
    host = payload.get("host")
    method = payload.get("method")
    fingerprint = payload.get("path_fingerprint")
    depth = payload.get("path_depth")
    if (scheme not in ("http", "https", "ws", "wss") or
            not isinstance(host, str) or len(host) > 253 or
            not re.fullmatch(r"[a-z0-9][a-z0-9.\-]*", host) or
            not isinstance(method, str) or not re.fullmatch(r"[A-Z]{1,16}", method) or
            not isinstance(fingerprint, str) or
            not re.fullmatch(r"[0-9a-f]{8}", fingerprint) or
            type(depth) is not int or not 0 <= depth <= 64):
        raise ValueError("network event contains invalid or unsanitized fields")
    return {"scheme": scheme, "host": host, "method": method,
            "path_fingerprint": fingerprint, "path_depth": depth}


class NetworkObserver:
    def __init__(self, output: Path):
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"network trace output is not empty: {output}")
        self.output = output
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.active = None
        self.session = None
        self.script = None
        self.errors = []
        self.events = []
        self.dropped = 0
        self.record = {"schema_version": 1, "kind": "ui_network_flow_trace",
                       "status": "failed", "started_at": _now(),
                       "scope": "URLSession task resume observations in one app process. Only scheme, host, method and an FNV32 path fingerprint are saved; request headers, query, body and raw path are omitted. Other networking APIs may be missed."}

    def start(self, udid: str, bundle: str) -> None:
        self.record["device_id_sha256_prefix"] = hashlib.sha256(udid.encode()).hexdigest()[:16]
        self.record["bundle_id"] = bundle
        from copyapp.frida_device import get_usb_device
        device = get_usb_device(udid)
        app = next((item for item in device.enumerate_applications(scope="full")
                    if item.identifier == bundle and item.pid), None)
        if app is None:
            raise RuntimeError("target app has no running process")
        self.record["pid"] = app.pid
        self.output.mkdir(parents=True, exist_ok=True)
        source = network_hook_source()
        (self.output / "hook.js").write_text(source, encoding="utf-8")
        self.session = device.attach(app.pid)
        self.script = self.session.create_script(source)
        self.script.on("message", self._on_message)
        self.script.load()
        if not self.ready.wait(10):
            raise TimeoutError("network hooks did not report readiness")
        if self.errors or not 0 < self.record.get("hook_count", 0) <= MAX_HOOKS:
            raise RuntimeError("no usable URLSession task-resume hooks")
        self.record["attached_at"] = _now()

    def _on_message(self, message, _data) -> None:
        if not isinstance(message, dict):
            return
        if message.get("type") == "error":
            with self.lock:
                self.errors.append(str(message.get("description") or "Frida network script error")[:240])
            self.ready.set()
            return
        payload = message.get("payload")
        if message.get("type") != "send" or not isinstance(payload, dict):
            return
        if payload.get("type") == "network_ready":
            count = payload.get("hook_count")
            if type(count) is int and 0 <= count <= MAX_HOOKS:
                self.record["hook_count"] = count
                self.record["candidate_count"] = payload.get("candidate_count")
            self.ready.set()
            return
        if payload.get("type") != "network_task_resume":
            return
        try:
            sanitized = _event(payload)
        except ValueError:
            with self.lock:
                self.errors.append("Frida sent an invalid network event")
            return
        with self.lock:
            if len(self.events) >= MAX_EVENTS:
                self.dropped += 1
                return
            sanitized.update({"observed_at": _now(),
                              "step_index": self.active["index"] if self.active else None})
            self.events.append(sanitized)
            if self.active:
                self.active["event_count"] += 1

    def begin_step(self, index: int, action: str) -> None:
        with self.lock:
            if self.active is not None:
                raise RuntimeError("network observation step already active")
            self.active = {"index": index, "action": action,
                           "started_at": _now(), "event_count": 0}

    def end_step(self) -> None:
        time.sleep(0.2)
        with self.lock:
            if self.active is None:
                raise RuntimeError("no active network observation step")
            self.active["finished_at"] = _now()
            self.record.setdefault("steps", []).append(self.active)
            self.active = None

    def finish(self) -> None:
        with self.lock:
            if self.active is not None:
                self.active["incomplete"] = True
                self.record.setdefault("steps", []).append(self.active)
                self.active = None
            self.record["events"] = list(self.events)
            self.record["dropped_events"] = self.dropped
            errors = list(self.errors)
        self.record["finished_at"] = _now()
        self.record["status"] = "complete" if self.record.get("attached_at") and not errors else "failed"
        if errors:
            self.record["error"] = {"type": "FridaScriptError", "message": errors[0]}
        self.output.mkdir(parents=True, exist_ok=True)
        cleanup = []
        if self.script is not None:
            warning = _bounded_cleanup("network script unload", self.script.unload)
            if warning:
                cleanup.append(warning)
        if self.session is not None:
            warning = _bounded_cleanup("network session detach", self.session.detach)
            if warning:
                cleanup.append(warning)
        if cleanup:
            self.record["cleanup_warnings"] = cleanup
        (self.output / "network.json").write_text(json.dumps(self.record, ensure_ascii=False,
                                                        indent=2) + "\n", encoding="utf-8")
        (self.output / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "ui_network_flow_trace",
            "status": self.record["status"], "bundle_id": self.record.get("bundle_id"),
            "device_id_sha256_prefix": self.record.get("device_id_sha256_prefix"),
            "evidence": [{"path": name, "sha256": sha256_file(self.output / name)}
                         for name in ("hook.js", "network.json")
                         if (self.output / name).is_file()],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_network_trace_pair(play: dict, trace: dict, bundle: str, prefix: str) -> None:
    if (play.get("status") != "complete" or play.get("bundle_id") != bundle or
            play.get("device_id_sha256_prefix") != prefix or
            trace.get("status") != "complete" or trace.get("kind") != "ui_network_flow_trace" or
            trace.get("bundle_id") != bundle or
            trace.get("device_id_sha256_prefix") != prefix or
            type(trace.get("hook_count")) is not int or
            not 0 < trace["hook_count"] <= MAX_HOOKS or
            not isinstance(trace.get("events"), list) or
            len(trace["events"]) > MAX_EVENTS or
            type(trace.get("dropped_events")) is not int or
            trace["dropped_events"] < 0):
        raise ValueError("network trace identity or capture status differs")
    actions = [(item.get("index"), item.get("action")) for item in play.get("steps", [])
               if isinstance(item, dict) and item.get("action") in
               ("tap", "tap_label", *GESTURE_ACTIONS)]
    steps = trace.get("steps", [])
    if (not isinstance(steps, list) or
            [(item.get("index"), item.get("action")) for item in steps
             if isinstance(item, dict)] != actions or len(steps) != len(actions) or
            any(not isinstance(item, dict) or item.get("incomplete") for item in steps)):
        raise ValueError("network observation steps differ from playbook actions")
    action_indexes = {index for index, _ in actions}
    for item in trace["events"]:
        if not isinstance(item, dict) or set(item) != {
                "scheme", "host", "method", "path_fingerprint", "path_depth",
                "observed_at", "step_index"}:
            raise ValueError("network trace includes unsanitized or unknown event fields")
        if _event(item) != {key: item[key] for key in (
                "scheme", "host", "method", "path_fingerprint", "path_depth")} or \
                (item["step_index"] is not None and item["step_index"] not in action_indexes):
            raise ValueError("network trace event differs from playbook steps")
        try:
            datetime.fromisoformat(item["observed_at"])
        except (TypeError, ValueError) as exc:
            raise ValueError("network event timestamp is invalid") from exc
    for step in steps:
        if (type(step.get("event_count")) is not int or
                step["event_count"] != sum(item["step_index"] == step["index"]
                                           for item in trace["events"])):
            raise ValueError("network step event count differs")


def validate_network_trace_files(output: Path, play: dict, bundle: str, prefix: str) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(output):
            raise ValueError("network trace failed hash verification")
    trace_manifest = _read(output / "manifest.json")
    trace = _read(output / "network.json")
    listed = trace_manifest.get("evidence")
    expected = {name: sha256_file(output / name)
                for name in ("hook.js", "network.json")}
    if (not isinstance(listed, list) or len(listed) != 2 or
            {item.get("path"): item.get("sha256") for item in listed
             if isinstance(item, dict)} != expected or
            trace_manifest.get("kind") != "ui_network_flow_trace" or
            trace_manifest.get("status") != "complete" or
            trace_manifest.get("bundle_id") != bundle or
            trace_manifest.get("device_id_sha256_prefix") != prefix):
        raise ValueError("network trace source or identity differs")
    validate_network_trace_pair(play, trace, bundle, prefix)
    return trace


def validate_network_flow(output: Path, bundle: str, prefix: str) -> dict:
    with redirect_stdout(io.StringIO()):
        if not verify_case(output / "playbook"):
            raise ValueError("network flow playbook failed hash verification")
    manifest = _read(output / "manifest.json")
    play = _read(output / "playbook/manifest.json")
    trace = validate_network_trace_files(output / "network", play, bundle, prefix)
    expected = {str(path.relative_to(output)): sha256_file(path)
                for child in (output / "playbook", output / "network")
                for path in child.rglob("*") if path.is_file()}
    listed = manifest.get("evidence")
    if (not isinstance(listed, list) or
            {item.get("path"): item.get("sha256") for item in listed
             if isinstance(item, dict)} != expected or len(listed) != len(expected)):
        raise ValueError("network flow evidence file set differs")
    if (manifest.get("schema_version") != 1 or manifest.get("kind") != "ui_network_flow" or
            manifest.get("status") != "complete" or
            manifest.get("bundle_id") != bundle or
            manifest.get("device_id_sha256_prefix") != prefix or
            manifest.get("source_script_sha256") !=
            sha256_file(output / "playbook/playbook.json") or
            play.get("ui_backend") != manifest.get("ui_backend") or
            type(manifest.get("event_count")) is not int or
            manifest["event_count"] != len(trace["events"])):
        raise ValueError("network flow identity or capture status differs")
    return {"manifest": manifest, "trace": trace,
            "files": sorted({"manifest.json"} | {
                item["path"] for item in manifest.get("evidence", [])})}


def run_network_flow(udid: str, backend: str, script: Path, output: Path,
                     ictrl_client: Path = DEFAULT_CLIENT) -> tuple[Path, bool]:
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"network flow output is not empty: {output}")
    plan = _read(script)
    bundle = plan.get("bundle_id")
    if not isinstance(bundle, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("playbook has no valid target Bundle ID")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    observer = NetworkObserver(output / "network")
    output.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": 1, "kind": "ui_network_flow", "status": "failed",
              "bundle_id": bundle, "ui_backend": backend,
              "device_id_sha256_prefix": prefix,
              "source_script_sha256": sha256_file(script), "started_at": _now()}
    try:
        tunnel = ictrl_tunnel(udid, ictrl_client) if backend == "ictrl" else nullcontext(None)
        with tunnel as port:
            play_path, complete = run_playbook(udid, backend, script, output / "playbook",
                                                port=port, ictrl_client=ictrl_client,
                                                trace_observer=observer)
        record["playbook_status"] = "complete" if complete else "failed"
        play = _read(play_path)
        if not complete:
            raise RuntimeError(f"playbook stopped: {play.get('error')}")
        with redirect_stdout(io.StringIO()):
            if not verify_case(output / "playbook") or not verify_case(output / "network"):
                raise ValueError("network flow child failed hash verification")
        trace = _read(output / "network/network.json")
        if trace.get("status") != "complete":
            raise RuntimeError(f"network observer stopped: {trace.get('error')}")
        if sha256_file(output / "playbook/playbook.json") != record["source_script_sha256"]:
            raise ValueError("network flow playbook differs from requested script")
        record["network_status"] = "complete"
        record["event_count"] = len(trace["events"])
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "message": str(exc)[:400]}
    finally:
        record["finished_at"] = _now()
        record["evidence"] = [
            {"path": str(path.relative_to(output)), "sha256": sha256_file(path)}
            for child in (output / "playbook", output / "network") if child.is_dir()
            for path in sorted(child.rglob("*")) if path.is_file()]
        (output / "manifest.json").write_text(json.dumps(record, ensure_ascii=False,
                                                    indent=2) + "\n", encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
