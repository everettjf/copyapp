"""Record transport readiness without claiming an App or VM has been verified."""

import io
import platform
import plistlib
import shutil
import sys
from pathlib import Path

from PIL import Image

from copyapp.macos.case import Case, digest
from copyapp.macos.chatcomputer import ChatComputer, ChatComputerError


def executable_facts(executable: str) -> dict:
    located = shutil.which(executable)
    if located is None:
        return {"available": False, "requested": executable}
    path = Path(located).resolve(strict=True)
    result = {"available": True, "path": str(path), "sha256": digest(path)}
    info = path.parent.parent / "Info.plist"
    if info.is_file():
        metadata = plistlib.loads(info.read_bytes())
        result.update(bundle_id=metadata.get("CFBundleIdentifier"),
                      version=metadata.get("CFBundleShortVersionString"),
                      build=metadata.get("CFBundleVersion"))
    return result


def doctor(output: Path, executable: str = "chatcomputer", data_dir=None,
           timeout: float = 30) -> tuple:
    case = Case(output, "mac_doctor")
    record = {"schema_version": 2, "platform": "macos", "scope": "chatcomputer_transport",
              "host": {"system": platform.system(), "release": platform.mac_ver()[0],
                       "architecture": platform.machine()},
              "ready": False, "exact_app_identity_ready": False,
              "repairs": [], "probes": {}}
    try:
        record["chatcomputer"] = executable_facts(executable)
        if sys.platform != "darwin":
            raise ChatComputerError("ChatComputer requires a macOS host")
        if not record["chatcomputer"]["available"]:
            raise ChatComputerError("Install ChatComputer from its official distribution, then finish its setup")
        with ChatComputer(executable, timeout, data_dir) as client:
            record["server_info"] = client.server_info
            status = client.call("status")
            case.add("mcp-status.json", status)
            record["probes"]["status"] = {"available": True, "text": client.text(status)}
            # A status prose line alone is insufficient: demand a guest image.
            shot = client.call("screenshot")
            case.add("mcp-screenshot.json", shot)
            data, mime = client.image(shot)
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                image.verify()
            if width <= 0 or height <= 0:
                raise ChatComputerError("invalid guest screenshot size")
            case.add("screen.png", data, binary=True)
            record["probes"]["screenshot"] = {"available": True, "width": width,
                                                  "height": height, "mime_type": mime}
            record["ready"] = True
    except (OSError, ValueError, ChatComputerError) as exc:
        record["repairs"].append(str(exc))
    record["repairs"].append("Exact guest and App identity require the Mac collector; transport readiness is not analysis readiness")
    case.add("doctor.json", record)
    case.finish("complete" if record["ready"] else "needs_setup", scope=record["scope"])
    return case.root, record["ready"]
