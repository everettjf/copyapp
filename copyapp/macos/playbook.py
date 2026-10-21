"""Bounded Mac replay with exact App identity and explicit behavior assertions."""

import io
import json
import math
import shutil
import time
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image

from copyapp.macos.case import Case, canonical, digest, now
from copyapp.macos.environment import environment_session
from copyapp.macos.observation import validate_reply


INPUT = {"click", "click_element", "key", "type", "scroll", "drag", "quit"}
ACTIONS = INPUT | {"launch", "screenshot", "expect_text", "expect_file", "expect_stopped", "wait"}
ATTRIBUTES = {"title", "value", "description", "identifier"}


def validate_script(script: dict):
    canonical(script)  # Reject non-finite JSON before collecting or sending input.
    steps = script.get("steps")
    if (type(script.get("schema_version")) is not int or script["schema_version"] != 2 or script.get("platform") != "macos" or
            not isinstance(script.get("bundle_id"), str) or not script["bundle_id"] or
            not isinstance(script.get("scenario_id"), str) or not script["scenario_id"] or
            not isinstance(script.get("app_path"), str) or not script["app_path"].startswith("/") or
            not isinstance(steps, list) or not 1 <= len(steps) <= 64 or
            not isinstance(steps[0], dict) or steps[0].get("action") != "launch"):
        raise ValueError("invalid Mac playbook identity, step count or initial launch")
    for step in steps:
        if not isinstance(step, dict) or step.get("action") not in ACTIONS:
            raise ValueError("unsupported Mac playbook action")
        action = step["action"]
        fields = {
            "launch": set(), "screenshot": set(), "quit": set(), "expect_stopped": set(),
            "wait": {"seconds"}, "key": {"combo"}, "type": {"text"},
            "click": {"x", "y", "button", "count", "modifiers"},
            "click_element": {"selector", "button", "count", "modifiers"},
            "scroll": {"x", "y", "direction", "amount"}, "drag": {"x1", "y1", "x2", "y2"},
            "expect_text": {"selector", "text", "attribute", "match"},
            "expect_file": {"path", "text_equals", "json_equals", "sha256"},
        }
        if set(step) - fields[action] - {"action", "id", "note"}:
            raise ValueError("unsupported parameters for Mac action: " + action)
        if action in {"click_element", "expect_text"}:
            selector = step.get("selector")
            if (not isinstance(selector, dict) or not selector or
                    not set(selector).issubset({"title", "identifier", "role", "window"}) or
                    any(not isinstance(value, str) or not value for value in selector.values())):
                raise ValueError("an explicit bounded element selector is required")
        if action == "expect_text":
            if (not isinstance(step.get("text"), str) or len(step["text"]) > 16384 or
                    (step.get("match", "equals") == "contains" and not step["text"]) or
                    step.get("attribute", "value") not in ATTRIBUTES or
                    step.get("match", "equals") not in {"equals", "contains"}):
                raise ValueError("invalid text assertion")
        if action == "type" and (not isinstance(step.get("text"), str) or not 1 <= len(step["text"]) <= 16384):
            raise ValueError("invalid bounded text input")
        if action == "key" and (not isinstance(step.get("combo"), str) or not 1 <= len(step["combo"]) <= 120):
            raise ValueError("invalid key combination")
        if action in {"click", "scroll", "drag"}:
            keys = ("x1", "y1", "x2", "y2") if action == "drag" else ("x", "y")
            if any(type(step.get(key)) is not int or step[key] < 0 for key in keys):
                raise ValueError("coordinates must be nonnegative screenshot pixel integers")
        if action in {"click", "click_element"}:
            if (step.get("button", "left") not in {"left", "right", "middle"} or
                    type(step.get("count", 1)) is not int or step.get("count", 1) not in {1, 2, 3}):
                raise ValueError("invalid click button/count")
            modifiers = step.get("modifiers", [])
            if (not isinstance(modifiers, list) or
                    any(not isinstance(value, str) or value not in {"cmd", "shift", "option", "ctrl", "fn"}
                        for value in modifiers) or len(set(modifiers)) != len(modifiers)):
                raise ValueError("invalid click modifiers")
        if action == "scroll":
            if (step.get("direction") not in {"up", "down", "left", "right"} or
                    type(step.get("amount", 3)) is not int or not 1 <= step.get("amount", 3) <= 50):
                raise ValueError("invalid scroll")
        if action == "wait" and (type(step.get("seconds")) not in {int, float} or not 0 < step["seconds"] <= 10):
            raise ValueError("wait must be bounded to ten seconds")
        if action == "expect_file":
            relative = step.get("path")
            if (not isinstance(relative, str) or not relative or PurePosixPath(relative).is_absolute() or
                    ".." in PurePosixPath(relative).parts or str(PurePosixPath(relative)) != relative or
                    len(set(step) & {"text_equals", "json_equals", "sha256"}) != 1):
                raise ValueError("file assertion requires a run-relative path and one content assertion")
            if "text_equals" in step and not isinstance(step["text_equals"], str):
                raise ValueError("text output assertions require a string")
            if "sha256" in step and (not isinstance(step["sha256"], str) or len(step["sha256"]) != 64 or
                                     any(char not in "0123456789abcdef" for char in step["sha256"])):
                raise ValueError("file hash must be a lowercase SHA-256 digest")


def output_bytes(path: Path, run_folder: Path, limit: int = 8 << 20) -> bytes:
    """Bounded, stable output read; do not assert against a changing save file."""
    import os
    import stat
    if (run_folder not in path.resolve(strict=True).parents or
            any(parent.is_symlink() for parent in [path, *path.parents]
                if parent == run_folder or run_folder in parent.parents)):
        raise ValueError("expected output is linked or escapes the run workspace")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError("output must be a bounded regular file")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    stamp = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if len(data) != before.st_size or stamp(before) != stamp(after) or stamp(after) != stamp(current):
        raise ValueError("output changed during capture; inspect state before a new run")
    return data


def select_node(tree: dict, selector: dict) -> dict:
    if tree.get("source_channel") != "ax" or tree.get("truncated") is not False:
        raise ValueError("element selection requires an untruncated AX observation")
    nodes = tree["nodes"]
    matches = []
    for node in nodes:
        if any(node.get(key) != value for key, value in selector.items() if key != "window"):
            continue
        if "window" in selector:
            parent, seen = node, set()
            while parent.get("role") != "AXWindow":
                index = parent.get("parent")
                if type(index) is not int or index in seen or not 0 <= index < len(nodes):
                    parent = {}; break
                seen.add(index)
                parent = nodes[index]
            if parent.get("title") != selector["window"]:
                continue
        matches.append(node)
    if len(matches) != 1:
        raise ValueError("selector must match exactly one element; found " + str(len(matches)))
    return matches[0]


def same_build(facts: dict, source: dict):
    index = source["app"]
    for key in ("bundle_id", "binary_sha256", "version", "build"):
        if facts.get(key) != index[key]:
            raise ValueError("guest App differs from acquired build: " + key)
    info = next(row for row in source["entries"] if row["path"] == "Contents/Info.plist")
    if facts.get("info_plist_sha256") != info["sha256"]:
        raise ValueError("guest App Info.plist differs from acquisition")


def capture(case: Case, prefix: str, computer, collector, params: dict, source: dict) -> dict:
    identity = collector.call("app_identity", params)
    facts = identity["response"]["result"]
    same_build(facts, source)
    running = [row for row in facts["processes"] if row.get("active") is True and row.get("terminated") is False]
    if (len(running) != 1 or running[0].get("cpu_type") != 0x0100000C or
            type(running[0].get("started_at")) not in {int, float}):
        raise ValueError("capture requires one exact foreground native arm64 process with launch time")
    pid = running[0]["pid"]
    if facts.get("foreground", {}).get("pid") != pid:
        raise ValueError("App lost foreground before capture")
    exact = dict(params, pid=pid)
    tree = collector.call("observe", exact)
    case.add(prefix + "/identity.json", identity)
    case.add(prefix + "/ax.json", tree)
    screenshot = computer.call("screenshot")
    data, mime = computer.image(screenshot)
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        image.verify()
    case.add(prefix + "/mcp.json", screenshot)
    image_name = prefix + ("/screen.png" if mime == "image/png" else "/screen.jpg")
    case.add(image_name, data, binary=True)
    after = collector.call("app_identity", params)
    case.add(prefix + "/identity-after.json", after)
    if facts != after["response"]["result"]:
        raise ValueError("App identity or foreground changed across capture")
    observed = tree["response"]["result"]
    if any(observed["app"].get(key) != facts.get(key) for key in
           ("bundle_id", "binary_sha256", "app_path", "info_plist_sha256", "foreground")):
        raise ValueError("AX observation identifies another App")
    return {"prefix": prefix, "image": image_name, "width": width, "height": height,
            "pid": pid, "tree": observed}


def run_playbook(acquisition: Path, script_path: Path, output: Path, timeout: float = 30,
                 expected_ui=None, starting_window=None) -> Path:
    from copyapp.verify import verify_case
    acquisition = acquisition.resolve(strict=True)
    if output.resolve() == acquisition or acquisition in output.resolve().parents:
        raise ValueError("playbook case must be outside its acquisition")
    if not verify_case(acquisition):
        raise ValueError("acquisition is not verified")
    manifest = json.loads((acquisition / "manifest.json").read_text())
    if manifest.get("kind") != "mac_app_acquisition":
        raise ValueError("Mac replay requires a guest-bound package acquisition")
    script = json.loads(script_path.read_text())
    validate_script(script)
    target = json.loads((acquisition / "acquisition.json").read_text())
    source = json.loads((acquisition / "package/app-index.json").read_text())
    if script["bundle_id"] != target["bundle_id"] or script["app_path"] != target["guest_app_path"]:
        raise ValueError("playbook target differs from acquisition")
    if expected_ui is not None:
        from copyapp.macos.ui import validate_ui
        validate_ui(expected_ui)
    if starting_window is not None:
        from copyapp.macos.ui import frame
        frame(starting_window)
    case = Case(output, "mac_playbook")
    if expected_ui is not None:
        case.add("expected-ui.json", expected_ui)
    if starting_window is not None:
        case.add("starting-window.json", starting_window)
    case.add("playbook.json", script)
    shutil.copytree(acquisition, case.root / "source", symlinks=True)
    case.record("source/manifest.json")
    run_id = str(uuid4())
    case.manifest.update(scenario_id=script["scenario_id"], bundle_id=script["bundle_id"],
                         run_id=run_id, steps=[], behavior_assertions=0,
                         source_manifest_sha256=digest(acquisition / "manifest.json"))
    params = {"app_path": script["app_path"], "bundle_id": script["bundle_id"],
              "binary_sha256": source["app"]["binary_sha256"]}
    try:
        with environment_session(acquisition / "environment", timeout) as (computer, collector, environment, health):
            case.add("session-health.json", health)
            if expected_ui is not None:
                from copyapp.macos.ui import check_ui
                check_ui(expected_ui, health)
            if not {"observe", "launch_app", "package_identity"}.issubset(health["response"]["result"].get("capabilities", [])):
                raise ValueError("collector build lacks Mac replay capabilities")
            outbox = collector.root / "outbox"
            workspace = outbox / "copyapp-runs"
            if outbox.is_symlink() or outbox.resolve() != outbox or workspace.is_symlink():
                raise ValueError("run workspace must stay inside the real shared outbox")
            run_folder = collector.root / "outbox/copyapp-runs" / run_id
            run_folder.mkdir(parents=True, exist_ok=False)
            guest_output = "/Volumes/My Shared Files/outbox/copyapp-runs/" + run_id
            package = collector.call("package_identity", params)
            case.add("package-before.json", package)
            if package["response"]["result"]["package_sha256"] != source["package_sha256"]:
                raise ValueError("installed package changed before replay")
            try:
                for index, step in enumerate(script["steps"], 1):
                    prefix = "steps/" + str(index).zfill(2)
                    action = step["action"]
                    entry = {"index": index, "action": action, "started_at": now(), "status": "started"}
                    case.add(prefix + "/request.json", step)
                    case.manifest["steps"].append(entry)
                    case.finish("collecting")
                    if action == "launch":
                        lease = computer.call("move", {"x": 0, "y": 0})
                        case.add(prefix + "/lease.json", lease)
                        launched = collector.call("launch_app", params)
                        case.add(prefix + "/launch.json", launched)
                        same_build(launched["response"]["result"], source)
                        observed = capture(case, prefix + "/after", computer, collector, params, source)
                        if index == 1 and starting_window is not None:
                            from copyapp.macos.ui import check_window
                            check_window(observed["tree"], starting_window)
                    elif action == "expect_stopped":
                        deadline, attempt = time.monotonic() + 5, 0
                        while True:
                            stopped = collector.call("app_identity", params)
                            if all(row.get("terminated") is True for row in stopped["response"]["result"]["processes"]):
                                break
                            attempt += 1
                            case.add(prefix + "/poll-" + str(attempt) + ".json", stopped)
                            if time.monotonic() >= deadline:
                                raise ValueError("App did not stop within the bounded wait")
                            time.sleep(0.1)
                        case.add(prefix + "/stopped.json", stopped)
                        case.manifest["behavior_assertions"] += 1
                    elif action == "expect_file":
                        path = run_folder.joinpath(*PurePosixPath(step["path"]).parts)
                        data = output_bytes(path, run_folder)
                        if "text_equals" in step and data.decode("utf-8") != step["text_equals"]:
                            raise ValueError("output text differs")
                        if "json_equals" in step and canonical(json.loads(data)) != canonical(step["json_equals"]):
                            raise ValueError("output JSON differs")
                        import hashlib
                        if "sha256" in step and hashlib.sha256(data).hexdigest() != step["sha256"]:
                            raise ValueError("output file hash differs")
                        case.add(prefix + "/output.bin", data, binary=True)
                        case.manifest["behavior_assertions"] += 1
                    else:
                        observed = capture(case, prefix + "/before", computer, collector, params, source)
                        if action == "expect_text":
                            node = select_node(observed["tree"], step["selector"])
                            value = node.get(step.get("attribute", "value"))
                            if not isinstance(value, str) or (step["text"] != value if step.get("match", "equals") == "equals" else step["text"] not in value):
                                raise ValueError("AX text assertion failed")
                            case.add(prefix + "/assertion.json", {"node": node, "expected": step["text"], "observed": value})
                            case.manifest["behavior_assertions"] += 1
                        elif action == "wait":
                            time.sleep(step["seconds"])
                        elif action != "screenshot":
                            tool, arguments = action, {}
                            if action == "click_element":
                                node = select_node(observed["tree"], step["selector"])
                                if node.get("enabled") is not True:
                                    raise ValueError("selected element is disabled")
                                frame, display = node["frame"], observed["tree"]["display"]
                                if frame["width"] <= 0 or frame["height"] <= 0:
                                    raise ValueError("selected element has no visible frame")
                                x = (frame["x"] + frame["width"] / 2 - display["x"]) * observed["width"] / display["width"]
                                y = (frame["y"] + frame["height"] / 2 - display["y"]) * observed["height"] / display["height"]
                                if not math.isfinite(x) or not math.isfinite(y):
                                    raise ValueError("invalid element coordinates")
                                arguments = {"x": round(x), "y": round(y)}
                                tool = "click"
                            elif action in {"click", "scroll", "drag"}:
                                keys = ("x1", "y1", "x2", "y2") if action == "drag" else ("x", "y")
                                arguments = {key: step[key] for key in keys}
                            elif action == "key": arguments = {"combo": step["combo"]}
                            elif action == "type": arguments = {"text": step["text"].replace("{{output_dir}}", guest_output)}
                            elif action == "quit": tool, arguments = "key", {"combo": "cmd+q"}
                            for x, y in ((arguments.get("x"), arguments.get("y")),
                                         (arguments.get("x1"), arguments.get("y1")),
                                         (arguments.get("x2"), arguments.get("y2"))):
                                if x is not None and not (0 <= x < observed["width"] and 0 <= y < observed["height"]):
                                    raise ValueError("input coordinate is outside the observed screen")
                            if tool == "click":
                                arguments.update(button=step.get("button", "left"), count=step.get("count", 1))
                                if "modifiers" in step:
                                    arguments["modifiers"] = step["modifiers"]
                            if tool == "scroll": arguments.update(direction=step["direction"], amount=step.get("amount", 3))
                            case.add(prefix + "/input.json", {"tool": tool, "arguments": arguments})
                            result = computer.call(tool, arguments)
                            case.add(prefix + "/input-result.json", result)
                            if action != "quit":
                                capture(case, prefix + "/after", computer, collector, params, source)
                    entry.update(status="complete", finished_at=now())
                    case.finish("collecting")
                package = collector.call("package_identity", params)
                case.add("package-after.json", package)
                if package["response"]["result"]["package_sha256"] != source["package_sha256"]:
                    raise ValueError("installed package changed during replay")
                if expected_ui is not None:
                    ending = collector.call("health")
                    case.add("ending-health.json", ending)
                    check_ui(expected_ui, ending)
            finally:
                import sys
                primary_failure = sys.exc_info()[0] is not None
                try:
                    released = computer.call("release")
                    case.add("control-release.json", released)
                except BaseException as cleanup:
                    case.add("control-release-failure.json", {"error": type(cleanup).__name__, "message": str(cleanup)})
                    if not primary_failure:
                        raise
        case.finish("complete", scope="selected_flow_only")
        return case.root
    except BaseException as exc:
        if isinstance(getattr(exc, "collector_evidence", None), dict):
            case.add("failed-collector-request.json", exc.collector_evidence)
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", scope="selected_flow_only")
        raise


def validate_playbook(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    from copyapp.macos.chatcomputer import ChatComputer
    import hashlib
    from uuid import UUID
    required = {"playbook.json", "source/manifest.json", "session-health.json",
                "package-before.json", "package-after.json", "control-release.json"}
    if (manifest.get("status") != "complete" or manifest.get("scope") != "selected_flow_only" or
            not required.issubset(names) or not verify_case(root / "source")):
        return False
    if json.loads((root / "source/manifest.json").read_text()).get("kind") != "mac_app_acquisition":
        return False
    script = json.loads((root / "playbook.json").read_text())
    validate_script(script)
    source = json.loads((root / "source/package/app-index.json").read_text())
    target = json.loads((root / "source/acquisition.json").read_text())
    environment = json.loads((root / "source/environment/environment.json").read_text())
    health = json.loads((root / "session-health.json").read_text())
    UUID(manifest["run_id"])
    if (manifest.get("scenario_id") != script["scenario_id"] or
            manifest.get("bundle_id") != script["bundle_id"] or
            script["bundle_id"] != target["bundle_id"] or script["app_path"] != target["guest_app_path"] or
            manifest.get("source_manifest_sha256") != digest(root / "source/manifest.json") or
            not validate_reply(health, environment, "health")):
        return False
    instance = health["response"]["collector_instance"]
    session = health["request"]["session_id"]
    ids = {health["request"]["request_id"]}
    params = {"app_path": script["app_path"], "bundle_id": script["bundle_id"],
              "binary_sha256": source["app"]["binary_sha256"]}

    def saved(name):
        if name not in names:
            raise ValueError("missing replay evidence: " + name)
        return json.loads((root / name).read_text())

    def rpc(name, method, expected):
        value = saved(name)
        request = value["request"]
        if (not validate_reply(value, environment, method, instance) or
                request.get("session_id") != session or request.get("params") != expected or
                request["request_id"] in ids):
            raise ValueError("replay request source, parameters or uniqueness mismatch")
        ids.add(request["request_id"])
        return value["response"]["result"]

    def mcp(name):
        value = saved(name)
        if type(value.get("isError", False)) is not bool or value.get("isError") or not isinstance(value.get("content"), list):
            raise ValueError("invalid input/control reply")
        return value

    def package(name):
        value = rpc(name, "package_identity", params)
        same_build(value["app"], source)
        if (value.get("package_sha256") != source["package_sha256"] or
                value.get("entry_count") != len(source["entries"]) or
                value.get("consistency") != "two_matching_inventories"):
            raise ValueError("installed package does not match acquisition")

    def captured(prefix):
        facts = rpc(prefix + "/identity.json", "app_identity", params)
        same_build(facts, source)
        running = [row for row in facts["processes"] if row.get("active") is True and row.get("terminated") is False]
        if (len(running) != 1 or running[0].get("cpu_type") != 0x0100000C or
                type(running[0].get("pid")) is not int or type(running[0].get("started_at")) not in {int, float}):
            raise ValueError("capture does not have one native foreground process")
        pid = running[0]["pid"]
        if facts.get("foreground", {}).get("pid") != pid:
            raise ValueError("capture foreground PID mismatch")
        tree = rpc(prefix + "/ax.json", "observe", dict(params, pid=pid))
        if (any(tree["app"].get(key) != value for key, value in facts.items()) or
                tree["app"].get("process") != running[0] or tree.get("source_channel") != "ax" or
                tree.get("coordinate_space") != "display_points" or type(tree.get("truncated")) is not bool):
            raise ValueError("AX capture belongs to another process or channel")
        nodes = tree.get("nodes")
        if not isinstance(nodes, list) or not nodes or len(nodes) > 2000:
            raise ValueError("invalid bounded AX nodes")
        for index, node in enumerate(nodes):
            parent = node.get("parent")
            if node.get("id") != index or (parent is not None and (type(parent) is not int or not 0 <= parent < index)):
                raise ValueError("invalid AX node ancestry")
        display = tree.get("display", {})
        if any(type(display.get(key)) not in {int, float} or not math.isfinite(display[key])
               for key in ("x", "y", "width", "height")) or display["width"] <= 0 or display["height"] <= 0:
            raise ValueError("invalid display geometry")
        shot = mcp(prefix + "/mcp.json")
        data, mime = ChatComputer.image(shot)
        filename = prefix + ("/screen.png" if mime == "image/png" else "/screen.jpg")
        if filename not in names or digest(root / filename) != hashlib.sha256(data).hexdigest():
            raise ValueError("screenshot bytes differ from raw MCP response")
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            image.verify()
        if rpc(prefix + "/identity-after.json", "app_identity", params) != facts:
            raise ValueError("App changed across screenshot capture")
        return {"width": width, "height": height, "tree": tree, "pid": pid}

    package("package-before.json")
    steps = manifest.get("steps")
    if not isinstance(steps, list) or len(steps) != len(script["steps"]):
        return False
    assertions = 0
    guest_output = "/Volumes/My Shared Files/outbox/copyapp-runs/" + manifest["run_id"]
    for index, (step, entry) in enumerate(zip(script["steps"], steps), 1):
        action = step["action"]
        prefix = "steps/" + str(index).zfill(2)
        if (entry.get("index") != index or entry.get("action") != action or entry.get("status") != "complete" or
                saved(prefix + "/request.json") != step):
            return False
        if action == "launch":
            mcp(prefix + "/lease.json")
            launched = rpc(prefix + "/launch.json", "launch_app", params)
            same_build(launched, source)
            observed = captured(prefix + "/after")
            if launched.get("process", {}).get("pid") != observed["pid"]:
                return False
            if index == 1 and "starting-window.json" in names:
                from copyapp.macos.ui import check_window
                check_window(observed["tree"], saved("starting-window.json"))
        elif action == "expect_stopped":
            stopped = rpc(prefix + "/stopped.json", "app_identity", params)
            same_build(stopped, source)
            if any(row.get("terminated") is not True for row in stopped["processes"]):
                return False
            assertions += 1
        elif action == "expect_file":
            name = prefix + "/output.bin"
            if name not in names:
                return False
            data = (root / name).read_bytes()
            if (len(data) > 8 << 20 or
                    ("text_equals" in step and data.decode("utf-8") != step["text_equals"]) or
                    ("json_equals" in step and canonical(json.loads(data)) != canonical(step["json_equals"])) or
                    ("sha256" in step and digest(root / name) != step["sha256"])):
                return False
            assertions += 1
        else:
            observed = captured(prefix + "/before")
            if action == "expect_text":
                node = select_node(observed["tree"], step["selector"])
                value = node.get(step.get("attribute", "value"))
                if (not isinstance(value, str) or
                        (value != step["text"] if step.get("match", "equals") == "equals" else step["text"] not in value) or
                        saved(prefix + "/assertion.json") != {"node": node, "expected": step["text"], "observed": value}):
                    return False
                assertions += 1
            elif action in INPUT:
                tool = action
                if action == "click_element":
                    node = select_node(observed["tree"], step["selector"])
                    if node.get("enabled") is not True:
                        return False
                    frame, display = node["frame"], observed["tree"]["display"]
                    if frame["width"] <= 0 or frame["height"] <= 0:
                        return False
                    arguments = {"x": round((frame["x"] + frame["width"] / 2 - display["x"]) * observed["width"] / display["width"]),
                                 "y": round((frame["y"] + frame["height"] / 2 - display["y"]) * observed["height"] / display["height"])}
                    tool = "click"
                elif action in {"click", "scroll", "drag"}:
                    keys = ("x1", "y1", "x2", "y2") if action == "drag" else ("x", "y")
                    arguments = {key: step[key] for key in keys}
                elif action == "key": arguments = {"combo": step["combo"]}
                elif action == "type": arguments = {"text": step["text"].replace("{{output_dir}}", guest_output)}
                else: tool, arguments = "key", {"combo": "cmd+q"}
                if tool == "click":
                    arguments.update(button=step.get("button", "left"), count=step.get("count", 1))
                    if "modifiers" in step:
                        arguments["modifiers"] = step["modifiers"]
                if tool == "scroll": arguments.update(direction=step["direction"], amount=step.get("amount", 3))
                for x, y in ((arguments.get("x"), arguments.get("y")), (arguments.get("x1"), arguments.get("y1")), (arguments.get("x2"), arguments.get("y2"))):
                    if x is not None and not (0 <= x < observed["width"] and 0 <= y < observed["height"]):
                        return False
                if saved(prefix + "/input.json") != {"tool": tool, "arguments": arguments}:
                    return False
                mcp(prefix + "/input-result.json")
                if action != "quit":
                    captured(prefix + "/after")
    package("package-after.json")
    if "expected-ui.json" in names:
        from copyapp.macos.ui import check_ui
        expected_ui = saved("expected-ui.json")
        check_ui(expected_ui, health)
        rpc("ending-health.json", "health", {})
        check_ui(expected_ui, saved("ending-health.json"))
    mcp("control-release.json")
    return type(manifest.get("behavior_assertions")) is int and manifest["behavior_assertions"] == assertions
