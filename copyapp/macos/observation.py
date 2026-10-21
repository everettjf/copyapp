"""Save a source-bound guest identity or bounded AX observation."""

import json
import shutil
from pathlib import Path

from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.environment import environment_session


def observe_app(environment: Path, app_path: str, bundle_id: str, output: Path,
                *, ax=False, timeout: float = 30) -> Path:
    from copyapp.verify import verify_case
    environment = environment.resolve(strict=True)
    if output.resolve() == environment or environment in output.resolve().parents:
        raise ValueError("observation must be outside the source environment")
    if not verify_case(environment):
        raise ValueError("environment case is not verified")
    case = Case(output, "mac_observation")
    try:
        shutil.copytree(environment, case.root / "environment", symlinks=True)
        case.record("environment/manifest.json")
        with environment_session(environment, timeout) as (computer, collector, registered, health):
            case.add("session-health.json", health)
            identity = collector.call("app_identity", {"app_path": app_path, "bundle_id": bundle_id})
            facts = identity["response"]["result"]
            if ax:
                case.add("identity-discovery.json", identity)
                running = [process for process in facts["processes"]
                           if process.get("active") is True and process.get("terminated") is False
                           and isinstance(process.get("started_at"), (int, float))]
                if len(running) != 1:
                    raise ValueError("AX observation requires one exact foreground app process")
                identity = collector.call("app_identity", {"app_path": facts["app_path"], "bundle_id": bundle_id,
                                                           "binary_sha256": facts["binary_sha256"],
                                                           "pid": running[0]["pid"]})
                facts = identity["response"]["result"]
                case.add("identity.json", identity)
                result = collector.call("observe", {"app_path": facts["app_path"], "bundle_id": bundle_id,
                                                      "binary_sha256": facts["binary_sha256"],
                                                      "pid": running[0]["pid"]})
                case.add("ax.json", result)
                screenshot = computer.call("screenshot")
                case.add("mcp-screenshot.json", screenshot)
                data, mime = computer.image(screenshot)
                case.add("screen.png" if mime == "image/png" else "screen.jpg", data, binary=True)
                # Screenshot capture is a different observation window. Recheck
                # App identity afterwards; do not call it simultaneous with AX.
                after = collector.call("app_identity", {"app_path": facts["app_path"], "bundle_id": bundle_id,
                                                         "binary_sha256": facts["binary_sha256"],
                                                         "pid": running[0]["pid"]})
                case.add("identity-after.json", after)
                if after["response"]["result"] != facts:
                    raise ValueError("App identity or foreground changed across screenshot capture")
            else:
                case.add("identity.json", identity)
            case.add("observation.json", {"schema_version": 2, "platform": "macos", "bundle_id": bundle_id,
                                          "app": facts, "environment_manifest_sha256": digest(environment / "manifest.json"),
                                          "scope": "ax_and_screenshot" if ax else "app_identity",
                                          "simultaneous_capture": False})
        case.finish("complete", bundle_id=bundle_id, scope="ax_and_screenshot" if ax else "app_identity")
        return case.root
    except BaseException as exc:
        case.add("failure.json", {"error": type(exc).__name__, "message": str(exc)})
        case.finish("failed", bundle_id=bundle_id)
        raise


def validate_reply(value: dict, environment: dict, method: str, instance=None) -> bool:
    import hashlib
    from uuid import UUID
    request, response = value["request"], value["response"]
    UUID(request["session_id"])
    UUID(request["request_id"])
    UUID(response["collector_instance"])
    return (request.get("method") == method and request.get("protocol_version") == 2 and
            response.get("protocol_version") == 2 and response.get("status") == "complete" and
            request.get("collector_sha256") == response.get("collector_sha256") == environment["collector_sha256"] and
            request["session_id"] == response.get("session_id") and request["request_id"] == response.get("request_id") and
            response.get("request_sha256") == hashlib.sha256(canonical(request)).hexdigest() and
            response.get("guest_machine_id") == environment["guest_machine_id"] and
            (instance is None or response["collector_instance"] == instance) and
            isinstance(response.get("result"), dict))


def validate_observation(root: Path, manifest: dict, names: set) -> bool:
    from copyapp.verify import verify_case
    required = {"environment/manifest.json", "session-health.json", "identity.json", "observation.json"}
    if manifest.get("status") != "complete" or not required.issubset(names):
        return False
    if not verify_case(root / "environment"):
        return False
    environment = json.loads((root / "environment/environment.json").read_text())
    health = json.loads((root / "session-health.json").read_text())
    identity = json.loads((root / "identity.json").read_text())
    record = json.loads((root / "observation.json").read_text())
    if not validate_reply(health, environment, "health"):
        return False
    instance = health["response"]["collector_instance"]
    if (not validate_reply(identity, environment, "app_identity", instance) or
            identity["request"]["session_id"] != health["request"]["session_id"]):
        return False
    facts = identity["response"]["result"]
    if (record.get("schema_version") != 2 or record.get("platform") != "macos" or
            record.get("app") != facts or record.get("simultaneous_capture") is not False or
            record.get("environment_manifest_sha256") != digest(root / "environment/manifest.json") or
            record.get("bundle_id") != manifest.get("bundle_id") or
            facts.get("bundle_id") != manifest["bundle_id"] or
            identity["request"]["params"].get("bundle_id") != facts["bundle_id"] or
            record.get("scope") != manifest.get("scope")):
        return False
    if record["scope"] == "app_identity":
        return True
    if record["scope"] != "ax_and_screenshot" or not {"ax.json", "identity-after.json", "mcp-screenshot.json"}.issubset(names):
        return False
    ax = json.loads((root / "ax.json").read_text())
    after = json.loads((root / "identity-after.json").read_text())
    if not validate_reply(ax, environment, "observe", instance) or not validate_reply(after, environment, "app_identity", instance):
        return False
    if any(item["request"]["session_id"] != health["request"]["session_id"] for item in (ax, after)):
        return False
    params = ax["request"]["params"]
    observation = ax["response"]["result"]
    if (params.get("binary_sha256") != facts.get("binary_sha256") or
            params.get("bundle_id") != facts.get("bundle_id") or
            observation.get("app") != facts or observation.get("source_channel") != "ax" or
            observation.get("coordinate_space") != "display_points" or
            after["response"]["result"] != facts):
        return False
    nodes = observation.get("nodes")
    if not isinstance(nodes, list) or not nodes or type(observation.get("truncated")) is not bool:
        return False
    for index, node in enumerate(nodes):
        parent = node.get("parent")
        if node.get("id") != index or (parent is not None and (type(parent) is not int or not 0 <= parent < index)):
            return False
    from copyapp.macos.chatcomputer import ChatComputer
    import hashlib
    import io
    from PIL import Image
    raw = json.loads((root / "mcp-screenshot.json").read_text())
    data, mime = ChatComputer.image(raw)
    image_name = "screen.png" if mime == "image/png" else "screen.jpg"
    if image_name not in names or hashlib.sha256(data).hexdigest() != digest(root / image_name):
        return False
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    return True
