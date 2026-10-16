"""One reproducible on-device UI action with a bounded Frida method trace."""

import hashlib
import json
import math
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from copyapp.ios_mcp import IOSMCPClient
from copyapp.ictrl import ICtrlClient, DEFAULT_CLIENT
from copyapp.trace import MAX_METHODS, MAX_SECONDS, parse_method, trace_script
from copyapp.usb_tunnel import ios_mcp_tunnel, ictrl_tunnel
from copyapp.objc import MachOImage
from copyapp.verify import sha256_file


_ICTRL_FRAME = re.compile(
    r"\{\{\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\},\s*"
    r"\{\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\}\}")
_ICTRL_TAPPABLE = frozenset({"Button", "Cell", "Link", "Switch", "TextField",
                             "SearchField", "SecureTextField", "TextView", "PickerWheel"})


def _ictrl_label_in_region(page: dict, label: str, region: List[float], bundle: str) -> dict:
    if (page.get("bundle_id") != bundle or page.get("truncated") is not False or
            page.get("coordinate_space") != "points" or not isinstance(page.get("source"), str)):
        raise RuntimeError("iCTRL page source is incomplete or belongs to another app")
    matches = []
    seen = set()
    for line in page["source"].splitlines():
        kind = line.strip().split(",", 1)[0]
        if kind not in _ICTRL_TAPPABLE or f"label: '{label}'" not in line:
            continue
        # Match the complete quoted label; a prefix of another label is unsafe.
        if re.search(r"label: '([^']*)'", line).group(1) != label:
            continue
        frame = _ICTRL_FRAME.search(line)
        if frame is None:
            continue
        x, y, width, height = (float(value) for value in frame.groups())
        center = (x + width / 2, y + height / 2)
        if (width > 0 and height > 0 and
                region[0] <= center[0] <= region[2] and
                region[1] <= center[1] <= region[3]):
            key = (kind, x, y, width, height)
            if key not in seen:
                seen.add(key)
                matches.append({"label": label, "element_type": kind,
                                "x": center[0], "y": center[1]})
    if len(matches) != 1:
        raise RuntimeError(f"iCTRL expected one visible control '{label}' in region, found {len(matches)}")
    return matches[0]


class ExperimentUI:
    def __init__(self, backend: str, port: int, ictrl_client: Path,
                 identity_port: Optional[int] = None, bundle_id: Optional[str] = None):
        self.backend = backend
        self.bundle_id = bundle_id
        self.identity_client = None
        if backend == "ios-mcp":
            self.client = IOSMCPClient(port=port)
            self.client.initialize()
        elif backend == "ictrl":
            self.client = ICtrlClient(port=port, client=ictrl_client)
            if identity_port is not None:
                self.identity_client = IOSMCPClient(port=identity_port)
                self.identity_client.initialize()
        else:
            raise ValueError("unsupported experiment UI backend")

    def bounds(self) -> Tuple[float, float]:
        if self.backend == "ios-mcp":
            screen = IOSMCPClient.text_json(self.client.call_ui("get_screen_info"))
            return screen.get("width"), screen.get("height")
        info = self.client.call_ui("device_info")
        return info.get("point_width"), info.get("point_height")

    def frontmost(self) -> str:
        identity = self.client if self.backend == "ios-mcp" else getattr(self, "identity_client", None)
        if identity is not None:
            value = IOSMCPClient.text_json(identity.call_ui("get_frontmost_app"))
            return str(value.get("bundleId") or value.get("bundle_id") or "")
        info = self.client.call_ui("device_info")
        return str((info.get("system") or {}).get("foreground_app") or "")

    def launch(self, bundle: str) -> None:
        self.client.call_ui("launch_app", {"bundle_id": bundle})

    def screenshot(self, path: Path) -> str:
        if self.backend == "ios-mcp":
            data = IOSMCPClient.image_bytes(self.client.call_ui("screenshot"))
            path.write_bytes(data)
        else:
            self.client.screenshot(path)
            data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()

    def tap(self, x: float, y: float) -> Dict[str, Any]:
        result = self.client.call_ui("tap_screen" if self.backend == "ios-mcp" else "tap",
                                     {"x": x, "y": y})
        return IOSMCPClient.text_json(result) if self.backend == "ios-mcp" else result

    def observe(self) -> Dict[str, Any]:
        if self.backend == "ios-mcp":
            return IOSMCPClient.text_json(self.client.call_ui(
                "describe_screen", {"include_ocr": False, "include_screenshot": False}))
        params = {"visible_only": True, "max_children": 50}
        if getattr(self, "bundle_id", None):
            params["bundle_id"] = self.bundle_id
        value = self.client.call_ui("page_source", params)
        if self.bundle_id and value.get("bundle_id") != self.bundle_id:
            raise RuntimeError("iCTRL page source belongs to a different App")
        return value

    def tap_label(self, label: str, region_points: Optional[List[float]] = None,
                  bundle_id: Optional[str] = None) -> Dict[str, Any]:
        def inside(x: Any, y: Any) -> bool:
            return (isinstance(x, (int, float)) and not isinstance(x, bool) and
                    math.isfinite(x) and isinstance(y, (int, float)) and
                    not isinstance(y, bool) and math.isfinite(y) and
                    (region_points is None or
                     (region_points[0] <= x <= region_points[2] and
                      region_points[1] <= y <= region_points[3])))

        if self.backend == "ictrl":
            candidate = None
            if region_points is not None:
                if not bundle_id:
                    raise ValueError("bounded iCTRL label tap requires a Bundle ID")
                page = self.client.call_ui("page_source", {"bundle_id": bundle_id,
                                                            "visible_only": True,
                                                            "max_children": 50})
                candidate = _ictrl_label_in_region(page, label, region_points, bundle_id)
            query = {"element_id": label}
            if bundle_id:
                query["bundle_id"] = bundle_id
            if candidate is not None:
                query["element_type"] = candidate["element_type"]
            match = self.client.call_ui("find_element", query)
            if not match.get("exists") or not match.get("hittable") or not match.get("ref"):
                raise RuntimeError(f"iCTRL element is not hittable: {label}")
            if candidate is not None:
                if (match.get("element_type") != candidate["element_type"] or
                        not inside(match.get("center_x"), match.get("center_y")) or
                        abs(match["center_x"] - candidate["x"]) > 4 or
                        abs(match["center_y"] - candidate["y"]) > 4):
                    raise RuntimeError(f"iCTRL reference differs from region-selected control: {label}")
            result = self.client.call_ui("tap", {"ref": match["ref"]})
            return {"match": {"label": match.get("label"), "ref": match["ref"],
                              "x": match.get("center_x"), "y": match.get("center_y")},
                    "result": result}
        observation = self.observe()
        matches = []
        for item in observation.get("elements", []):
            if not isinstance(item, dict) or item.get("text") != label or not item.get("clickable"):
                continue
            rect = item.get("rect")
            if not isinstance(rect, dict):
                continue
            values = [rect.get(key) for key in ("x", "y", "width", "height")]
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
                continue
            x, y, width, height = values
            if width > 0 and height > 0 and inside(x + width / 2, y + height / 2):
                matches.append(item)
        if len(matches) != 1:
            raise RuntimeError(f"iOS MCP expected one clickable element '{label}', found {len(matches)}")
        rect = matches[0]["rect"]
        x = rect["x"] + rect["width"] / 2
        y = rect["y"] + rect["height"] / 2
        return {"match": {"label": label, "x": x, "y": y}, "result": self.tap(x, y)}


def _bounded_cleanup(label: str, callback, timeout: float = 2.0) -> str:
    result: Dict[str, str] = {}

    def run() -> None:
        try:
            callback()
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return f"{label} timed out after {timeout:g}s"
    return result.get("error", "")


def _static_targets(binary: Path, objc_index: Path, methods: List[Tuple[str, str]]) -> Tuple[str, List[dict]]:
    binary = binary.resolve(strict=True)
    if not binary.parent.name.endswith(".app"):
        raise ValueError("selected binary must be inside an .app bundle")
    index = json.loads(objc_index.read_text(encoding="utf-8"))
    digest = sha256_file(binary)
    image_base = MachOImage(binary.read_bytes()).base
    if (index.get("schema_version") != 1 or index.get("binary_sha256") != digest or
            image_base is None or
            (index.get("image_base") is not None and
             index["image_base"] != f"0x{image_base:x}")):
        raise ValueError("Objective-C index does not match selected binary and image base")
    addresses = {}
    requested = set(methods)
    for cls in index.get("classes", []):
        for method in cls.get("instance_methods", []):
            key = (cls["name"], method["selector"])
            if key not in requested:
                continue
            address = int(method["imp"], 16)
            if key in addresses and addresses[key] != address:
                raise ValueError(f"ambiguous Objective-C index method: {key}")
            addresses[key] = address
    targets = []
    for position, key in enumerate(methods):
        address = addresses.get(key)
        if address is None or address < image_base:
            raise ValueError(f"instance method missing from selected binary: {key}")
        targets.append({"index": position, "class": key[0], "selector": key[1],
                        "offset": address - image_base,
                        "app_dir": binary.parent.name, "binary_name": binary.name})
    return digest, targets


def trace_tap(udid: str, bundle: str, specs: List[str], x: float, y: float,
              duration: float, output: Path, port: Optional[int] = None,
              backend: str = "ios-mcp", ictrl_client: Path = DEFAULT_CLIENT,
              binary: Optional[Path] = None, objc_index: Optional[Path] = None) -> Tuple[Path, bool]:
    if backend not in ("ios-mcp", "ictrl"):
        raise ValueError("unsupported experiment UI backend")
    if port is None:
        tunnel = ios_mcp_tunnel(udid) if backend == "ios-mcp" else ictrl_tunnel(udid, ictrl_client)
        with tunnel as own_port:
            return _trace_tap_with_port(udid, bundle, specs, x, y, duration,
                                        output, own_port, backend, ictrl_client, binary, objc_index)
    return _trace_tap_with_port(udid, bundle, specs, x, y, duration, output, port,
                                backend, ictrl_client, binary, objc_index)


def _trace_tap_with_port(udid: str, bundle: str, specs: List[str], x: float, y: float,
                         duration: float, output: Path, port: int, backend: str,
                         ictrl_client: Path, binary: Optional[Path] = None,
                         objc_index: Optional[Path] = None) -> Tuple[Path, bool]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", bundle):
        raise ValueError("invalid bundle id")
    if not 0 <= x <= 10000 or not 0 <= y <= 10000:
        raise ValueError("invalid tap coordinate")
    if not 0 < duration <= MAX_SECONDS:
        raise ValueError("observation duration must be between 0 and 60 seconds")
    methods = [parse_method(spec) for spec in specs]
    if not methods or len(methods) > MAX_METHODS or len(set(methods)) != len(methods):
        raise ValueError("provide 1–32 unique methods")
    if (binary is None) != (objc_index is None):
        raise ValueError("--binary and --objc-index must be provided together")
    digest, static_targets = _static_targets(binary, objc_index, methods) if binary else (None, [])
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    record: Dict[str, Any] = {
        "schema_version": 1,
        "device_id_sha256_prefix": hashlib.sha256(udid.encode()).hexdigest()[:16],
        "bundle_id": bundle,
        "ui_backend": backend,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tap": {"x": x, "y": y},
        "requested_methods": specs,
        "requested_observation_seconds": duration,
        "status": "failed",
        "note": "The method trace counts calls only; it does not save arguments or return values. Screenshots may contain location data.",
    }
    if digest:
        record["static_binary_sha256"] = digest
        record["static_requested_offsets"] = [f"0x{target['offset']:x}" for target in static_targets]
        record["static_binding_limitation"] = ("The file hash pins the acquired binary; a matching loaded module "
                                                "path and offset do not prove identical in-memory code bytes.")
    session = script = None
    path = output / "experiment.json"
    stage = "connect_ui"
    try:
        ui = ExperimentUI(backend, port, ictrl_client)
        width, height = ui.bounds()
        if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            raise RuntimeError("device screen dimensions unavailable")
        if x > width or y > height:
            raise ValueError(f"tap coordinate outside device screen {width}x{height}")
        record["screen"] = {"width": width, "height": height}
        ui.launch(bundle)
        time.sleep(1)
        stage = "verify_frontmost_before"
        before = ui.frontmost()
        record["frontmost_before"] = before
        if before != bundle:
            raise RuntimeError(f"target not frontmost before tap: {before}")
        record["screenshot_before_sha256"] = ui.screenshot(output / "before.jpg")

        stage = "attach_frida"
        import frida
        device = frida.get_usb_device(timeout=5)
        if device.id != udid:
            raise RuntimeError("Frida device does not match requested UDID")
        app = next((item for item in device.enumerate_applications(scope="full")
                    if item.identifier == bundle), None)
        if app is None or not app.pid:
            raise RuntimeError("target app has no running process")
        record["pid"] = app.pid
        session = device.attach(app.pid)
        # A synchronous Frida RPC can wait forever after a tap backgrounds the
        # target. Stream individual hits to the host before that transition.
        hit_counts = [0] * len(methods)
        static_hit_counts = [0] * len(methods)
        hit_lock = threading.Lock()

        def on_message(message, _data) -> None:
            payload = message.get("payload") if isinstance(message, dict) else None
            if not isinstance(payload, dict) or payload.get("type") not in ("method_hit", "static_hit"):
                return
            index = payload.get("index")
            if type(index) is int and 0 <= index < len(hit_counts):
                with hit_lock:
                    if payload["type"] == "static_hit":
                        static_hit_counts[index] += 1
                    else:
                        hit_counts[index] += 1

        script = session.create_script(trace_script(methods, stream_hits=True,
                                                   static_targets=static_targets))
        script.on("message", on_message)
        script.load()
        baseline = script.exports_sync.snapshot()
        record["methods"] = baseline["methods"]
        if not all(item["status"] == "hooked" for item in baseline["methods"]):
            raise RuntimeError("one or more requested Objective-C methods were not hooked")
        if static_targets:
            record["static_entries"] = baseline["static_entries"]
            if len(record["static_entries"]) != len(static_targets):
                raise RuntimeError("one or more static app entries were not hooked")
        with hit_lock:
            hit_counts[:] = [0] * len(hit_counts)
            static_hit_counts[:] = [0] * len(static_hit_counts)

        stage = "tap"
        if ui.frontmost() != bundle:
            raise RuntimeError("target left foreground before tap")
        observation_start = time.monotonic()
        record["tap_result"] = ui.tap(x, y)
        time.sleep(duration)
        with hit_lock:
            record["call_counts"] = hit_counts.copy()
            if static_targets:
                record["static_call_counts"] = static_hit_counts.copy()
        record["observed_seconds"] = round(time.monotonic() - observation_start, 3)

        stage = "capture_after"
        record["frontmost_after"] = ui.frontmost()
        record["screenshot_after_sha256"] = ui.screenshot(output / "after.jpg")
        record["status"] = "complete"
    except Exception as exc:
        record["error"] = {"stage": stage, "type": type(exc).__name__,
                           "message": str(exc)[:400]}
    finally:
        # Save the observation before Frida cleanup: detach can stall after an
        # app opens another app, and the evidence must survive that stall.
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, record["status"] == "complete"
