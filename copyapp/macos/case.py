"""Versioned Mac evidence; this never relaxes the legacy iOS validators."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


KINDS = frozenset({"mac_doctor", "mac_app_index", "mac_collector_build",
                   "mac_collector_deployment", "mac_environment", "mac_observation", "mac_app_acquisition",
                   "mac_playbook", "mac_behavior_report", "mac_rebuild_plan"})


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(path: Path) -> str:
    from copyapp.verify import sha256_file
    return sha256_file(path)


class Case:
    def __init__(self, root: Path, kind: str):
        if kind not in KINDS:
            raise ValueError("unknown Mac case kind")
        if root.exists():
            raise FileExistsError("refusing to overwrite case: " + str(root))
        root.mkdir(parents=True)
        self.root = root.resolve()
        self.manifest = {"schema_version": 2, "platform": "macos", "kind": kind,
                         "status": "collecting", "started_at": now(), "evidence": []}
        self.finish("collecting")

    def add(self, relative: str, value, *, binary=False):
        from copyapp.verify import checked_path
        path = checked_path(self.root, relative)
        if path.exists() or path.name == "manifest.json":
            raise FileExistsError("refusing to overwrite evidence")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if binary else canonical(value) + b"\n")
        self.record(relative)

    def record(self, relative: str):
        from copyapp.verify import checked_path
        path = checked_path(self.root, relative)
        if any(item["path"] == relative for item in self.manifest["evidence"]):
            raise ValueError("duplicate evidence path")
        self.manifest["evidence"].append({"path": relative, "sha256": digest(path)})

    def finish(self, status: str, **fields):
        self.manifest.update(fields)
        self.manifest.update(status=status, updated_at=now())
        temporary = self.root / ".manifest.tmp"
        temporary.write_bytes(canonical(self.manifest) + b"\n")
        temporary.replace(self.root / "manifest.json")


def verify_mac_case(root: Path) -> bool:
    """Check all saved bytes and then the kind-specific identity and contracts."""
    from copyapp.verify import checked_path
    try:
        manifest = json.loads((root / "manifest.json").read_text())
        if (type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 2 or
                manifest.get("platform") != "macos" or manifest.get("kind") not in KINDS or
                manifest.get("status") not in {"complete", "needs_setup", "failed"}):
            return False
        records = manifest["evidence"]
        if not isinstance(records, list) or not records:
            return False
        names = set()
        for item in records:
            name = item["path"]
            if (not isinstance(name, str) or name in names or name == "manifest.json" or
                    str(PurePosixPath(name)) != name or
                    not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64):
                return False
            names.add(name)
            path = checked_path(root, name)
            # File links cannot silently replace a captured regular file.
            if root.joinpath(*PurePosixPath(name).parts).is_symlink() or digest(path) != item["sha256"]:
                return False
        if manifest["kind"] == "mac_doctor":
            if "doctor.json" not in names:
                return False
            doctor = json.loads((root / "doctor.json").read_text())
            ready = doctor.get("ready")
            if type(ready) is not bool or doctor.get("platform") != "macos":
                return False
            if (manifest["status"] == "complete") != ready:
                return False
            if ready and (doctor.get("scope") != "chatcomputer_transport" or
                          not {"mcp-status.json", "mcp-screenshot.json", "screen.png"}.issubset(names) or
                          doctor.get("exact_app_identity_ready") is not False):
                return False
            if ready:
                from PIL import Image
                import io
                from copyapp.macos.chatcomputer import ChatComputer
                raw = json.loads((root / "mcp-screenshot.json").read_text())
                image, _ = ChatComputer.image(raw)
                if hashlib.sha256(image).hexdigest() != digest(root / "screen.png"):
                    return False
                with Image.open(io.BytesIO(image)) as opened:
                    opened.verify()
            return True
        if manifest["kind"] == "mac_collector_build":
            from copyapp.macos.setup import validate_build
            return validate_build(root, manifest, names)
        if manifest["kind"] == "mac_collector_deployment":
            from copyapp.macos.deploy import validate_deployment
            return validate_deployment(root, manifest, names)
        if manifest["kind"] == "mac_environment":
            from copyapp.macos.environment import validate_environment
            return validate_environment(root, manifest, names)
        if manifest["kind"] == "mac_observation":
            from copyapp.macos.observation import validate_observation
            return validate_observation(root, manifest, names)
        if manifest["kind"] == "mac_app_acquisition":
            from copyapp.macos.acquire import validate_acquisition
            return validate_acquisition(root, manifest, names)
        if manifest["kind"] == "mac_playbook":
            from copyapp.macos.playbook import validate_playbook
            return validate_playbook(root, manifest, names)
        if manifest["kind"] == "mac_behavior_report":
            from copyapp.macos.report import verify_report
            return verify_report(root, manifest, names)
        if manifest["kind"] == "mac_rebuild_plan":
            from copyapp.macos.rebuild import validate_plan
            return validate_plan(root, manifest, names)
        from copyapp.macos.package import validate_index
        return validate_index(root, manifest, names)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
