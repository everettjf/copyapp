"""Record bounded Frida method hits during named UI playbook action steps."""

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.experiment import _bounded_cleanup, _static_targets
from copyapp.trace import MAX_METHODS, parse_branch_register, parse_method, trace_script
from copyapp.verify import sha256_file


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FlowTrace:
    def __init__(self, output: Path, specs: list[str], binary: Optional[Path] = None,
                 objc_index: Optional[Path] = None,
                 arg2_u32_methods: Optional[list[str]] = None,
                 branch_offsets: Optional[list[int]] = None,
                 branch_return_u32_offsets: Optional[list[int]] = None,
                 branch_registers: Optional[list[tuple[int, str]]] = None):
        methods = [parse_method(spec) for spec in specs]
        if not methods or len(methods) > MAX_METHODS or len(set(methods)) != len(methods):
            raise ValueError("provide 1–32 unique methods")
        if (binary is None) != (objc_index is None):
            raise ValueError("--binary and --objc-index must be provided together")
        branches = branch_offsets or []
        if (branches and binary is None) or len(branches) > 32 or len(set(branches)) != len(branches) or any(
                type(offset) is not int or offset < 0 for offset in branches):
            raise ValueError("branch offsets require unique static app entries")
        returns = branch_return_u32_offsets or []
        if (len(set(returns)) != len(returns) or
                any(type(offset) is not int or offset not in branches for offset in returns)):
            raise ValueError("return capture requires unique selected branch offsets")
        registers = branch_registers or []
        if (len(registers) > 32 or len(set(registers)) != len(registers) or
                any(type(offset) is not int or offset not in branches or
                    parse_branch_register(f"{offset}:{register}") != (offset, register)
                    for offset, register in registers)):
            raise ValueError("register capture requires unique selected branch offsets")
        requested_args = arg2_u32_methods or []
        if len(set(requested_args)) != len(requested_args) or any(
                spec not in specs for spec in requested_args):
            raise ValueError("argument capture requires unique traced methods")
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"trace output is not empty: {output}")
        self.output = output
        self.methods = methods
        self.specs = specs
        self.arg2_u32_indices = [specs.index(spec) for spec in requested_args]
        self.branch_offsets = branches
        self.branch_return_u32_offsets = returns
        self.branch_registers = registers
        self.digest, self.static_targets = (
            _static_targets(binary, objc_index, methods) if binary else (None, []))
        self.session = None
        self.script = None
        self.lock = threading.Lock()
        self.active = None
        self.counts = [0] * len(methods)
        self.static_counts = [0] * len(methods)
        self.branch_counts = [0] * len(branches)
        self.steps = []
        self.errors = []
        self.record = {"schema_version": 1, "kind": "ui_flow_method_trace",
                       "status": "failed", "requested_methods": specs,
                       "started_at": _now(), "steps": self.steps,
                       "note": "Action-step hits are temporal observations, not proof of causal or exclusive dispatch. Raw argument 2 is saved only for explicitly selected methods; its meaning and type require separate evidence."}
        if requested_args:
            self.record["arg2_u32_methods"] = requested_args
        if branches:
            self.record["branch_requested_offsets"] = [f"0x{offset:x}" for offset in branches]
        if returns:
            self.record["branch_return_u32_offsets"] = [f"0x{offset:x}" for offset in returns]
            self.record["branch_return_limitation"] = (
                "Raw low 32 bits of the function return register. Type and meaning require static or additional runtime evidence; asynchronous callbacks may finish after a tap window.")
        if registers:
            self.record["branch_registers"] = [
                {"offset": f"0x{offset:x}", "register": register}
                for offset, register in registers]
            self.record["branch_register_limitation"] = (
                "The selected register is interpreted as a code pointer only when it maps into the loaded app image. The binding is a runtime module offset, not proof of identical in-memory and acquired file bytes.")
        if self.digest:
            self.record["static_binary_sha256"] = self.digest
            self.record["static_requested_offsets"] = [
                f"0x{target['offset']:x}" for target in self.static_targets]
            self.record["static_binding_limitation"] = (
                "The acquired file hash and loaded module path/offset do not prove identical in-memory code bytes.")

    def start(self, udid: str, bundle: str) -> None:
        self.record["device_id_sha256_prefix"] = hashlib.sha256(udid.encode()).hexdigest()[:16]
        self.record["bundle_id"] = bundle
        from copyapp.frida_device import get_usb_device
        device = get_usb_device(udid)
        app = next((item for item in device.enumerate_applications(scope="full")
                    if item.identifier == bundle), None)
        if app is None or not app.pid:
            raise RuntimeError("target app has no running process")
        self.record["pid"] = app.pid
        self.record["process_name"] = app.name
        source = trace_script(self.methods, stream_hits=True,
                              static_targets=self.static_targets,
                              arg2_u32_indices=self.arg2_u32_indices,
                              branch_offsets=self.branch_offsets,
                              branch_return_u32_offsets=self.branch_return_u32_offsets,
                              branch_registers=self.branch_registers)
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "hook.js").write_text(source, encoding="utf-8")
        self.session = device.attach(app.pid)
        self.script = self.session.create_script(source)
        self.script.on("message", self._on_message)
        self.script.load()
        baseline = self.script.exports_sync.snapshot()
        observed = baseline["methods"]
        if (len(observed) != len(self.methods) or
                any(item.get("status") != "hooked" for item in observed)):
            raise RuntimeError("one or more requested Objective-C methods were not hooked")
        static_entries = baseline.get("static_entries", [])
        if len(static_entries) != len(self.static_targets):
            raise RuntimeError("one or more static app entries were not hooked")
        branch_entries = baseline.get("branch_entries", [])
        if len(branch_entries) != len(self.branch_offsets):
            raise RuntimeError("one or more branch entries were not hooked")
        self.record["methods"] = observed
        if self.static_targets:
            self.record["static_entries"] = static_entries
        if self.branch_offsets:
            self.record["branch_entries"] = branch_entries
        with self.lock:
            self.counts = [0] * len(self.methods)
            self.static_counts = [0] * len(self.methods)
            self.branch_counts = [0] * len(self.branch_offsets)
        self.record["attached_at"] = _now()

    def _on_message(self, message, _data) -> None:
        if not isinstance(message, dict):
            return
        if message.get("type") == "error":
            with self.lock:
                self.errors.append(str(message.get("description") or "Frida script error")[:240])
            return
        payload = message.get("payload")
        if not isinstance(payload, dict) or payload.get("type") not in (
                "method_hit", "static_hit", "branch_hit", "branch_return_u32",
                "branch_register"):
            return
        index = payload.get("index")
        width = (len(self.branch_offsets) if payload["type"] in
                 ("branch_hit", "branch_return_u32", "branch_register") else len(self.methods))
        if type(index) is not int or not 0 <= index < width:
            return
        with self.lock:
            if payload["type"] == "branch_register":
                register = payload.get("register")
                status = payload.get("status")
                target = payload.get("target_offset")
                if ((self.branch_offsets[index], register) not in self.branch_registers or
                        status not in ("app_image", "outside_app_image", "unavailable") or
                        (status == "app_image" and
                         (not isinstance(target, str) or not target.startswith("0x"))) or
                        (status != "app_image" and target is not None)):
                    self.errors.append("selected branch register has invalid pointer binding")
                elif self.active is not None:
                    hits = self.active["branch_register_hits"]
                    if len(hits) < 256:
                        hit = {"index": index, "register": register, "status": status}
                        if target is not None:
                            hit["target_offset"] = target
                        hits.append(hit)
                    else:
                        self.active["branch_register_truncated"] = True
                return
            if payload["type"] == "branch_return_u32":
                value = payload.get("value")
                if (self.branch_offsets[index] not in self.branch_return_u32_offsets or
                        type(value) is not int or not 0 <= value <= 0xffffffff):
                    self.errors.append("selected branch return lacks valid raw uint32")
                elif self.active is not None:
                    hits = self.active["branch_return_u32_hits"]
                    if len(hits) < 256:
                        hits.append({"index": index, "value": value})
                    else:
                        self.active["branch_return_u32_truncated"] = True
                return
            if payload["type"] == "branch_hit":
                self.branch_counts[index] += 1
                if self.active is not None:
                    self.active["branch_call_counts"][index] += 1
                return
            target = self.static_counts if payload["type"] == "static_hit" else self.counts
            target[index] += 1
            if self.active is not None:
                key = "static_call_counts" if payload["type"] == "static_hit" else "call_counts"
                self.active[key][index] += 1
                if index in self.arg2_u32_indices:
                    value = payload.get("arg2_u32")
                    if type(value) is not int or not 0 <= value <= 0xffffffff:
                        self.errors.append("selected method hit lacks valid raw argument 2")
                    elif len(self.active["arg2_u32_hits"]) < 256:
                        self.active["arg2_u32_hits"].append({"type": payload["type"],
                                                              "index": index, "value": value})
                    else:
                        self.active["arg2_u32_truncated"] = True

    def begin_step(self, index: int, action: str) -> None:
        with self.lock:
            if self.active is not None:
                raise RuntimeError("trace step already active")
            self.active = {"index": index, "action": action, "started_at": _now(),
                           "call_counts": [0] * len(self.methods),
                           "static_call_counts": [0] * len(self.methods)}
            if self.arg2_u32_indices:
                self.active["arg2_u32_hits"] = []
            if self.branch_offsets:
                self.active["branch_call_counts"] = [0] * len(self.branch_offsets)
            if self.branch_return_u32_offsets:
                self.active["branch_return_u32_hits"] = []
            if self.branch_registers:
                self.active["branch_register_hits"] = []

    def end_step(self) -> None:
        # Give Frida's asynchronous host messages a short bounded drain window.
        time.sleep(0.2)
        with self.lock:
            if self.active is None:
                raise RuntimeError("no active trace step")
            self.active["finished_at"] = _now()
            self.steps.append(self.active)
            self.active = None

    def finish(self) -> None:
        if self.active is not None:
            with self.lock:
                self.active["incomplete"] = True
                self.steps.append(self.active)
                self.active = None
        with self.lock:
            self.record["call_counts"] = self.counts.copy()
            self.record["static_call_counts"] = self.static_counts.copy()
            if self.branch_offsets:
                self.record["branch_call_counts"] = self.branch_counts.copy()
            errors = self.errors.copy()
        self.record["finished_at"] = _now()
        self.record["status"] = "complete" if self.record.get("attached_at") and not errors else "failed"
        if errors:
            self.record["error"] = {"type": "FridaScriptError", "message": errors[0]}
        self.output.mkdir(parents=True, exist_ok=True)
        path = self.output / "trace.json"
        path.write_text(json.dumps(self.record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cleanup = []
        if self.script is not None:
            warning = _bounded_cleanup("script unload", self.script.unload)
            if warning:
                cleanup.append(warning)
        if self.session is not None:
            warning = _bounded_cleanup("session detach", self.session.detach)
            if warning:
                cleanup.append(warning)
        if cleanup:
            self.record["cleanup_warnings"] = cleanup
            path.write_text(json.dumps(self.record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [{"path": name, "sha256": sha256_file(self.output / name)}
                 for name in ("hook.js", "trace.json") if (self.output / name).is_file()]
        (self.output / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "kind": "ui_flow_method_trace",
            "status": self.record["status"], "bundle_id": self.record.get("bundle_id"),
            "device_id_sha256_prefix": self.record.get("device_id_sha256_prefix"),
            "evidence": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
