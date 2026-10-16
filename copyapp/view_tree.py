"""Capture the frontmost app's UIKit view structure through its Frida process."""

import hashlib
import json
import re
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from copyapp.experiment import ExperimentUI, _bounded_cleanup
from copyapp.ictrl import DEFAULT_CLIENT
from copyapp.usb_tunnel import ictrl_tunnel, ios_mcp_tunnel
from copyapp.verify import sha256_file


MAX_NODES = 500
MAX_DEPTH = 20
SCAN_JS = r"""
const maxNodes = 500;
const maxDepth = 20;
function safeString(value) {
    try { return value === null || value === undefined ? null : String(value).slice(0, 200); }
    catch (_) { return null; }
}
function frame(value) {
    try {
        const values = Array.isArray(value)
            ? [value[0][0], value[0][1], value[1][0], value[1][1]]
            : [value.origin.x, value.origin.y, value.size.width, value.size.height];
        const numbers = values.map(Number);
        if (!numbers.every(Number.isFinite)) return null;
        return {x: numbers[0], y: numbers[1],
                width: numbers[2], height: numbers[3]};
    } catch (_) { return null; }
}
ObjC.schedule(ObjC.mainQueue, function () {
    try {
        if (!ObjC.available) throw new Error('Objective-C runtime unavailable');
        const app = ObjC.classes.UIApplication.sharedApplication();
        const windows = app.windows();
        const nodes = [];
        const roots = [];
        let truncated = false;
        function walk(view, parent, depth, sibling) {
            if (nodes.length >= maxNodes || depth > maxDepth) { truncated = true; return; }
            const id = nodes.length;
            const node = {id: id, parent: parent, depth: depth, sibling: sibling,
                          class_name: safeString(view.$className), frame: frame(view.frame()),
                          hidden: Boolean(view.isHidden()), alpha: Number(view.alpha()),
                          accessibility_label: safeString(view.accessibilityLabel()),
                          accessibility_identifier: safeString(view.accessibilityIdentifier())};
            try {
                if (view.isKindOfClass_(ObjC.classes.UILabel)) {
                    node.text = safeString(view.text());
                    const font = view.font();
                    if (font) {
                        node.font_name = safeString(font.fontName());
                        node.font_point_size = Number(font.pointSize());
                    }
                } else if (view.isKindOfClass_(ObjC.classes.UIButton))
                    node.title = safeString(view.currentTitle());
                else if (view.isKindOfClass_(ObjC.classes.UITextField))
                    node.text = safeString(view.text());
            } catch (error) { node.content_error = safeString(error); }
            nodes.push(node);
            const children = view.subviews();
            const count = Number(children.count());
            node.subview_count = count;
            for (let i = 0; i < count; i++) walk(children.objectAtIndex_(i), id, depth + 1, i);
        }
        const count = Number(windows.count());
        for (let i = 0; i < count; i++) {
            const window = windows.objectAtIndex_(i);
            roots.push({window_index: i, class_name: safeString(window.$className),
                        key_window: Boolean(window.isKeyWindow()),
                        window_level: Number(window.windowLevel()), frame: frame(window.frame()),
                        root_node: nodes.length});
            walk(window, null, 0, i);
        }
        send({type: 'view_tree', roots: roots, nodes: nodes, truncated: truncated,
              max_nodes: maxNodes, max_depth: maxDepth});
    } catch (error) {
        send({type: 'view_tree_error', message: safeString(error)});
    }
});
"""


def _script_source() -> str:
    import frida_tools
    bridge = Path(frida_tools.__file__).parent / "bridges" / "objc.js"
    if not bridge.is_file():
        raise RuntimeError("Frida Objective-C bridge is unavailable")
    return bridge.read_text(encoding="utf-8") + "\nconst ObjC = bridge;\n" + SCAN_JS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def capture_view_tree(udid: str, bundle: str, output: Path,
                      backend: str = "ios-mcp", port: Optional[int] = None,
                      ictrl_client: Path = DEFAULT_CLIENT,
                      launch: bool = True) -> Tuple[Path, bool]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid bundle id")
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported UI backend")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {"schema_version": 1, "kind": "uikit_view_tree",
                              "bundle_id": bundle,
                              "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
                              "ui_backend": backend, "started_at": _now(), "status": "failed",
                              "launch_requested": launch,
                              "scope": "Current UIKit windows and bounded subview tree, plus accessibility observation when available. SwiftUI content may be drawn without UILabel nodes. Runtime observations are not original source."}
    manifest = output / "manifest.json"
    stage = "connect_ui"
    try:
        tunnel = (ios_mcp_tunnel(udid) if backend == "ios-mcp" else
                  ictrl_tunnel(udid, ictrl_client)) if port is None else None
        with ExitStack() as stack:
            own_port = stack.enter_context(tunnel) if tunnel is not None else port
            identity_port = None
            if backend == "ictrl":
                try:
                    identity_port = stack.enter_context(ios_mcp_tunnel(udid))
                except (OSError, RuntimeError, TimeoutError) as exc:
                    record["identity_tunnel_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            _capture_with_port(udid, bundle, output, backend, own_port,
                               ictrl_client, record, launch, identity_port)
    except Exception as exc:
        record["error"] = {"stage": record.get("stage", stage), "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        record.pop("stage", None)
        record["finished_at"] = _now()
        record["evidence"] = [{"path": name, "sha256": sha256_file(output / name)}
                              for name in ("screenshot.jpg", "scan.js", "view-tree.json",
                                           "accessibility.json")
                              if (output / name).is_file()]
        manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, record["status"] == "complete"


def _capture_with_port(udid: str, bundle: str, output: Path, backend: str,
                       port: int, ictrl_client: Path, record: dict, launch: bool,
                       identity_port: Optional[int] = None) -> None:
    record["stage"] = "connect_ui"
    ui = ExperimentUI(backend, port, ictrl_client,
                      identity_port=identity_port, bundle_id=bundle)
    record["frontmost_backend"] = "ios-mcp" if identity_port is not None or backend == "ios-mcp" else "ictrl"
    if launch:
        ui.launch(bundle)
        time.sleep(0.5)
    record["stage"] = "verify_frontmost"
    before = ui.frontmost()
    record["frontmost_before"] = before
    if before != bundle:
        raise RuntimeError(f"target not frontmost: {before}")
    ui.screenshot(output / "screenshot.jpg")

    record["stage"] = "attach_frida"
    from copyapp.frida_device import get_usb_device
    device = get_usb_device(udid)
    app = next((item for item in device.enumerate_applications(scope="full")
                if item.identifier == bundle and item.pid), None)
    if app is None:
        raise RuntimeError("target app process is unavailable")
    record["pid"] = app.pid
    source = _script_source()
    (output / "scan.js").write_text(source, encoding="utf-8")
    session = script = None
    try:
        session = device.attach(app.pid)
        ready = threading.Event()
        result = {}

        def on_message(message, _data) -> None:
            if not isinstance(message, dict):
                return
            if message.get("type") == "error":
                result["error"] = str(message.get("description") or message)[:400]
                ready.set()
            payload = message.get("payload")
            if message.get("type") == "send" and isinstance(payload, dict) and \
                    payload.get("type") in ("view_tree", "view_tree_error"):
                result["payload"] = payload
                ready.set()

        script = session.create_script(source)
        script.on("message", on_message)
        script.load()
        record["stage"] = "scan_views"
        if not ready.wait(12):
            raise TimeoutError("UIKit view scan did not finish within 12 seconds")
        if result.get("error"):
            raise RuntimeError(result["error"])
        payload = result.get("payload", {})
        if payload.get("type") != "view_tree":
            raise RuntimeError(str(payload.get("message") or "view scan failed"))
        nodes = payload.get("nodes")
        roots = payload.get("roots")
        if (not isinstance(nodes, list) or not isinstance(roots, list) or
                len(nodes) > MAX_NODES or any(not isinstance(node, dict) for node in nodes)):
            raise RuntimeError("Frida returned invalid view tree")
        (output / "view-tree.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
        record.update({"node_count": len(nodes), "window_count": len(roots),
                       "truncated": payload.get("truncated"),
                       "frontmost_after": ui.frontmost()})
        if record["frontmost_after"] != bundle:
            raise RuntimeError("target left foreground during view scan")
        record["stage"] = "observe_accessibility"
        try:
            observation = ui.observe()
            (output / "accessibility.json").write_text(
                json.dumps(observation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            record["accessibility_element_count"] = observation.get(
                "element_count", observation.get("total_returned"))
        except Exception as exc:
            record["accessibility_error"] = {"type": type(exc).__name__,
                                             "message": str(exc)[:240]}
        record["frontmost_after"] = ui.frontmost()
        if record["frontmost_after"] != bundle:
            raise RuntimeError("target left foreground after accessibility observation")
        record["status"] = "complete"
    finally:
        if script is not None:
            warning = _bounded_cleanup("script unload", script.unload)
            if warning:
                record.setdefault("cleanup_warnings", []).append(warning)
        if session is not None:
            warning = _bounded_cleanup("session detach", session.detach)
            if warning:
                record.setdefault("cleanup_warnings", []).append(warning)
