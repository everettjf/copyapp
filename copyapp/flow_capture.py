"""One bounded UI flow followed by a no-launch runtime view snapshot."""

import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from copyapp.ictrl import DEFAULT_CLIENT
from copyapp.flow_trace import FlowTrace
from copyapp.network_flow import NetworkObserver, validate_network_trace_files
from copyapp.playbook import run_playbook
from copyapp.trace import parse_method
from copyapp.usb_tunnel import ictrl_tunnel
from copyapp.verify import sha256_file, verify_case
from copyapp.gestures import GESTURE_ACTIONS
from copyapp.text_actions import TYPE_ACTION
from copyapp.view_tree import capture_view_tree


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _child_files(output: Path) -> list:
    return [{"path": str(path.relative_to(output)), "sha256": sha256_file(path)}
            for parent in (output / "playbook", output / "view-tree", output / "trace",
                           output / "network") if parent.is_dir()
            for path in sorted(parent.rglob("*")) if path.is_file()]


class ObserverGroup:
    """Keep independent Frida observers aligned to one playbook action timeline."""

    def __init__(self, observers: list):
        self.observers = observers

    def start(self, udid: str, bundle: str) -> None:
        for observer in self.observers:
            observer.start(udid, bundle)

    def begin_step(self, index: int, action: str) -> None:
        for observer in self.observers:
            observer.begin_step(index, action)

    def end_step(self) -> None:
        # Each observer has its own bounded Frida-message drain. Run those
        # drains together so one action does not get different end windows.
        with ThreadPoolExecutor(max_workers=len(self.observers)) as pool:
            futures = [pool.submit(observer.end_step) for observer in self.observers]
            errors = []
            for future in futures:
                try:
                    future.result()
                except Exception as exc:
                    errors.append(exc)
        if errors:
            raise errors[0]

    def finish(self) -> None:
        first = None
        for observer in self.observers:
            try:
                observer.finish()
            except Exception as exc:
                first = first or exc
        if first:
            raise first


def validate_flow_pair(playbook: dict, views: dict, bundle: str,
                       device_prefix: str, backend: str) -> None:
    if (playbook.get("status") != "complete" or views.get("status") != "complete" or
            playbook.get("bundle_id") != bundle or views.get("bundle_id") != bundle or
            playbook.get("device_id_sha256_prefix") != device_prefix or
            views.get("device_id_sha256_prefix") != device_prefix or
            playbook.get("ui_backend") != backend or views.get("ui_backend") != backend or
            views.get("launch_requested") is not False or
            views.get("frontmost_before") != bundle or views.get("frontmost_after") != bundle):
        raise ValueError("flow and view scan identity or completion differs")
    try:
        finished = datetime.fromisoformat(playbook["finished_at"])
        started = datetime.fromisoformat(views["started_at"])
        gap = (started - finished).total_seconds()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("flow/view timing metadata is invalid") from exc
    if not 0 <= gap <= 60:
        raise ValueError("view scan did not follow the flow within 60 seconds")


def validate_flow_trace_pair(playbook: dict, trace: dict, bundle: str,
                             device_prefix: str, binary_hashes: Optional[set] = None) -> None:
    actions = [(item["index"], item["action"]) for item in playbook.get("steps", [])
               if item.get("action") in ("tap", "tap_label", *GESTURE_ACTIONS,
                                          TYPE_ACTION)]
    steps = trace.get("steps")
    methods = trace.get("requested_methods")
    if (trace.get("status") != "complete" or trace.get("bundle_id") != bundle or
            trace.get("device_id_sha256_prefix") != device_prefix or
            not isinstance(steps, list) or not isinstance(methods, list) or not methods or
            [(item.get("index"), item.get("action")) for item in steps
             if isinstance(item, dict)] != actions or
            len(steps) != len(actions) or
            any(not isinstance(item, dict) or item.get("incomplete") or
                item.get("action") not in ("tap", "tap_label", *GESTURE_ACTIONS,
                                           TYPE_ACTION)
                for item in steps)):
        raise ValueError("trace/playbook identity or action steps differ")
    width = len(methods)
    observed_methods = trace.get("methods")
    if (not isinstance(observed_methods, list) or len(observed_methods) != width or
            any(not isinstance(item, dict) or item.get("status") != "hooked" or
                (item.get("class"), item.get("selector")) != parse_method(spec)
                for item, spec in zip(observed_methods, methods))):
        raise ValueError("flow trace method identity is invalid")
    for item in [trace] + steps:
        for field in ("call_counts", "static_call_counts"):
            counts = item.get(field)
            if (not isinstance(counts, list) or len(counts) != width or
                    any(type(value) is not int or value < 0 for value in counts)):
                raise ValueError("flow trace counts are invalid")
    for field in ("call_counts", "static_call_counts"):
        if any(sum(step[field][index] for step in steps) > trace[field][index]
               for index in range(width)):
            raise ValueError("flow trace step counts exceed total counts")
    branches = trace.get("branch_requested_offsets", [])
    if branches:
        entries = trace.get("branch_entries")
        totals = trace.get("branch_call_counts")
        static_entries = trace.get("static_entries")
        static_path = (static_entries[0].get("module_path")
                       if isinstance(static_entries, list) and static_entries and
                       isinstance(static_entries[0], dict) else None)
        if (not isinstance(branches, list) or len(branches) > 32 or
                any(not isinstance(offset, str) or not offset.startswith("0x") or
                    not offset[2:] or any(char not in "0123456789abcdef" for char in offset[2:])
                    for offset in branches) or
                len(set(branches)) != len(branches) or
                not isinstance(static_path, str) or not static_path or
                not isinstance(entries, list) or len(entries) != len(branches) or
                not isinstance(totals, list) or len(totals) != len(branches) or
                any(type(value) is not int or value < 0 for value in totals) or
                any(not isinstance(entry, dict) or entry.get("index") != index or
                    entry.get("module_offset") != branches[index] or
                    entry.get("module_path") != static_path
                    for index, entry in enumerate(entries))):
            raise ValueError("flow trace branch binding is invalid")
        for step in steps:
            counts = step.get("branch_call_counts")
            if (not isinstance(counts, list) or len(counts) != len(branches) or
                    any(type(value) is not int or value < 0 for value in counts)):
                raise ValueError("flow trace branch counts are invalid")
        if any(sum(step["branch_call_counts"][i] for step in steps) > totals[i]
               for i in range(len(branches))):
            raise ValueError("flow trace branch step counts exceed totals")
    returns = trace.get("branch_return_u32_offsets", [])
    if (not isinstance(returns, list) or any(not isinstance(offset, str) for offset in returns) or
            len(set(returns)) != len(returns) or
            any(offset not in branches for offset in returns)):
        raise ValueError("flow trace return selection differs from branch entries")
    selected_branches = {branches.index(offset) for offset in returns}
    for step in steps:
        if not returns:
            if "branch_return_u32_hits" in step:
                raise ValueError("flow trace has unrequested branch returns")
            continue
        hits = step.get("branch_return_u32_hits")
        if (not isinstance(hits, list) or len(hits) > 256 or
                any(not isinstance(hit, dict) or type(hit.get("index")) is not int or
                    hit["index"] not in selected_branches or
                    type(hit.get("value")) is not int or
                    not 0 <= hit["value"] <= 0xffffffff for hit in hits)):
            raise ValueError("flow trace raw branch returns are invalid")
    registers = trace.get("branch_registers", [])
    if (not isinstance(registers, list) or len(registers) > 32 or
            any(not isinstance(item, dict) or item.get("offset") not in branches or
                not isinstance(item.get("register"), str) or
                item["register"] not in {f"x{i}" for i in range(31)}
                for item in registers)):
        raise ValueError("flow trace register selection differs from branch entries")
    selected_registers = {(branches.index(item["offset"]), item["register"])
                          for item in registers}
    if len(selected_registers) != len(registers):
        raise ValueError("flow trace register selection contains duplicates")
    for step in steps:
        if not registers:
            if "branch_register_hits" in step:
                raise ValueError("flow trace has unrequested branch registers")
            continue
        hits = step.get("branch_register_hits")
        if (not isinstance(hits, list) or len(hits) > 256 or
                any(not isinstance(hit, dict) or type(hit.get("index")) is not int or
                    (hit["index"], hit.get("register")) not in selected_registers or
                    hit.get("status") not in ("app_image", "outside_app_image", "unavailable") or
                    (hit["status"] == "app_image" and
                     (not isinstance(hit.get("target_offset"), str) or
                      not hit["target_offset"].startswith("0x") or
                      not hit["target_offset"][2:] or
                      any(char not in "0123456789abcdef" for char in hit["target_offset"][2:]))) or
                    (hit["status"] != "app_image" and "target_offset" in hit)
                    for hit in hits)):
            raise ValueError("flow trace register pointer bindings are invalid")
    selected = trace.get("arg2_u32_methods", [])
    if (not isinstance(selected, list) or any(not isinstance(spec, str) for spec in selected) or
            len(set(selected)) != len(selected) or
            any(spec not in methods for spec in selected)):
        raise ValueError("flow trace argument capture selection is invalid")
    selected_indices = {methods.index(spec) for spec in selected}
    for step in steps:
        if not selected:
            continue
        hits = step.get("arg2_u32_hits")
        if (not isinstance(hits, list) or len(hits) > 256 or
                any(not isinstance(hit, dict) or hit.get("type") not in
                    ("method_hit", "static_hit") or hit.get("index") not in selected_indices or
                    type(hit.get("value")) is not int or
                    not 0 <= hit["value"] <= 0xffffffff for hit in hits)):
            raise ValueError("flow trace raw argument hits are invalid")
        for index in selected_indices:
            for event_type, count_field in (("method_hit", "call_counts"),
                                            ("static_hit", "static_call_counts")):
                captured = sum(hit["type"] == event_type and hit["index"] == index
                               for hit in hits)
                if (captured > step[count_field][index] or
                        (not step.get("arg2_u32_truncated") and
                         captured != step[count_field][index])):
                    raise ValueError("flow trace raw argument count differs from method hits")
    if (binary_hashes is not None and trace.get("static_binary_sha256") and
            trace["static_binary_sha256"] not in binary_hashes):
        raise ValueError("flow trace static entry belongs to another binary")


def capture_flow(udid: str, backend: str, script: Path, output: Path,
                 ictrl_client: Path = DEFAULT_CLIENT, methods: Optional[list[str]] = None,
                 binary: Optional[Path] = None,
                 objc_index: Optional[Path] = None,
                 arg2_u32_methods: Optional[list[str]] = None,
                 branch_offsets: Optional[list[int]] = None,
                 branch_return_u32_offsets: Optional[list[int]] = None,
                 branch_registers: Optional[list[tuple[int, str]]] = None,
                 network: bool = False,
                 port: Optional[int] = None) -> Tuple[Path, bool]:
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    plan = _read(script)
    bundle = plan.get("bundle_id")
    if not isinstance(bundle, str) or not bundle:
        raise ValueError("flow playbook has no target Bundle ID")
    prefix = hashlib.sha256(udid.encode()).hexdigest()[:16]
    if not methods and (binary is not None or objc_index is not None):
        raise ValueError("static entry tracing requires --method")
    if not methods and arg2_u32_methods:
        raise ValueError("argument capture requires --method")
    if not methods and branch_offsets:
        raise ValueError("branch tracing requires --method")
    if branch_return_u32_offsets and not branch_offsets:
        raise ValueError("return capture requires --branch-offset")
    if branch_registers and not branch_offsets:
        raise ValueError("register capture requires --branch-offset")
    tracer = FlowTrace(output / "trace", methods, binary, objc_index,
                       arg2_u32_methods, branch_offsets,
                       branch_return_u32_offsets, branch_registers) if methods else None
    network_observer = NetworkObserver(output / "network") if network else None
    observers = [item for item in (tracer, network_observer) if item is not None]
    observer = ObserverGroup(observers) if len(observers) > 1 else (observers[0] if observers else None)
    output.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": 1, "kind": "ui_flow_capture",
              "status": "failed", "bundle_id": bundle,
              "scenario_id": plan.get("scenario_id"), "ui_backend": backend,
              "device_id_sha256_prefix": prefix,
              "source_script_sha256": sha256_file(script),
              "started_at": _now()}
    if tracer is not None:
        record["trace_requested"] = True
    if network_observer is not None:
        record["network_requested"] = True
    stage = "playbook"
    try:
        # Reopening an iCTRL tunnel can foreground its runner. Keep one tunnel
        # across the playbook and immediate no-launch view scan.
        session = (ictrl_tunnel(udid, ictrl_client)
                   if backend == "ictrl" and port is None else nullcontext(port))
        with session as shared_port:
            play_path, play_ok = run_playbook(udid, backend, script, output / "playbook",
                                              port=shared_port, ictrl_client=ictrl_client,
                                              trace_observer=observer)
            record["playbook_status"] = "complete" if play_ok else "failed"
            with redirect_stdout(io.StringIO()):
                if not verify_case(output / "playbook"):
                    raise ValueError("playbook evidence hash mismatch")
            play = _read(play_path)
            if not play_ok:
                raise RuntimeError(f"playbook stopped: {play.get('error')}")
            if tracer is not None:
                stage = "trace"
                with redirect_stdout(io.StringIO()):
                    if not verify_case(output / "trace"):
                        raise ValueError("trace evidence hash mismatch")
                trace = _read(output / "trace" / "trace.json")
                if trace.get("status") != "complete":
                    raise RuntimeError(f"trace stopped: {trace.get('error')}")
                validate_flow_trace_pair(play, trace, bundle, prefix)
                record["trace_status"] = "complete"
            if network_observer is not None:
                stage = "network"
                network_trace = validate_network_trace_files(output / "network",
                                                             play, bundle, prefix)
                record["network_status"] = "complete"
                record["network_event_count"] = len(network_trace["events"])
            stage = "view_tree"
            tree_path, tree_ok = capture_view_tree(udid, bundle, output / "view-tree",
                                                   backend=backend, port=shared_port,
                                                   ictrl_client=ictrl_client, launch=False)
            record["view_tree_status"] = "complete" if tree_ok else "failed"
            with redirect_stdout(io.StringIO()):
                if not verify_case(output / "view-tree"):
                    raise ValueError("view tree evidence hash mismatch")
            views = _read(tree_path)
            if not tree_ok:
                raise RuntimeError(f"view scan stopped: {views.get('error')}")
            validate_flow_pair(play, views, bundle, prefix, backend)
            if sha256_file(output / "playbook" / "playbook.json") != record["source_script_sha256"]:
                raise ValueError("saved playbook differs from requested script")
            record["playbook_finished_at"] = play["finished_at"]
            record["view_tree_started_at"] = views["started_at"]
            record["node_count"] = views["node_count"]
            record["window_count"] = views["window_count"]
            record["status"] = "complete"
            stage = "session_cleanup"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = {"stage": stage, "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        record["finished_at"] = _now()
        record["evidence"] = _child_files(output)
        (output / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    return output / "manifest.json", record["status"] == "complete"
