"""Simulated desktop for replay contracts, never live VM acceptance evidence."""

import base64
import copy
import hashlib
import io
from contextlib import contextmanager
from uuid import uuid4

from PIL import Image

from copyapp.macos.case import canonical
from copyapp.macos.chatcomputer import ChatComputer, ChatComputerError, UnknownCompletion


class Desktop:
    def __init__(self, shared, registered, source, target, *, lose_type_reply=False):
        self.root = shared.resolve()
        self.registered, self.source, self.target = registered, source, target
        self.session, self.instance = str(uuid4()), str(uuid4())
        self.running, self.value = False, ""
        self.lose_type_reply = lose_type_reply
        self.calls, self.closed = [], False

    def facts(self, *, exact=False):
        process = {"pid": 42, "started_at": 1000.0, "cpu_type": 0x0100000C,
                   "active": True, "terminated": False}
        info = next(row for row in self.source["entries"] if row["path"] == "Contents/Info.plist")
        result = {key: self.source["app"][key] for key in ("bundle_id", "binary_sha256", "version", "build")}
        result.update(app_path=self.target, executable_path=self.target + "/Contents/MacOS/CopyAppMacCollector",
                      info_plist_sha256=info["sha256"], processes=[process] if self.running else [],
                      foreground={"pid": 42 if self.running else 99, "bundle_id": result["bundle_id"] if self.running else "com.apple.finder",
                                  "app_path": self.target if self.running else "/System/Library/CoreServices/Finder.app"})
        if exact:
            result["process"] = process
        return result

    def rpc(self, method, params=None):
        request = {"protocol_version": 2, "session_id": self.session, "request_id": str(uuid4()),
                   "collector_sha256": self.registered["collector_sha256"], "method": method, "params": params or {}}
        if method == "health":
            result = {"capabilities": ["observe", "launch_app", "package_identity"],
                      "guest_machine_id": self.registered["guest_machine_id"], "os_version": self.registered["guest_os"]}
        elif method == "package_identity":
            result = {"app": self.facts(), "package_sha256": self.source["package_sha256"],
                      "entry_count": len(self.source["entries"]), "consistency": "two_matching_inventories"}
        elif method == "launch_app":
            self.running = True
            result = self.facts(exact=True)
        elif method == "app_identity": result = self.facts(exact="pid" in (params or {}))
        elif method == "observe":
            result = {"app": self.facts(exact=True), "source_channel": "ax", "coordinate_space": "display_points",
                      "display": {"x": 0, "y": 0, "width": 16, "height": 12}, "truncated": False,
                      "nodes": [{"id": 0, "parent": None, "role": "AXApplication", "enabled": True},
                                {"id": 1, "parent": 0, "role": "AXWindow", "title": "Document", "enabled": True},
                                {"id": 2, "parent": 1, "role": "AXTextField", "identifier": "editor", "value": self.value,
                                 "enabled": True, "frame": {"x": 1, "y": 1, "width": 12, "height": 8}}]}
        else: raise ValueError("unknown simulated RPC")
        return {"request": request, "response": {
            "protocol_version": 2, "session_id": self.session, "request_id": request["request_id"],
            "request_sha256": hashlib.sha256(canonical(request)).hexdigest(),
            "collector_instance": self.instance, "collector_sha256": self.registered["collector_sha256"],
            "guest_machine_id": self.registered["guest_machine_id"], "status": "complete", "result": copy.deepcopy(result)}}

    def input(self, method, params=None):
        if self.closed:
            raise ChatComputerError("simulated connection is closed")
        self.calls.append((method, params))
        if method == "type":
            self.value = params["text"]
            if self.lose_type_reply:
                self.closed = True
                raise UnknownCompletion("simulated input executed but reply was lost")
        if method == "key" and params["combo"] == "cmd+q": self.running = False
        if method == "key" and params["combo"] == "cmd+s":
            runs = list((self.root / "outbox/copyapp-runs").iterdir())
            assert len(runs) == 1
            (runs[0] / "output.json").write_bytes(canonical({"text": self.value}))
        content = [{"type": "text", "text": "simulated command completed"}]
        if method == "screenshot":
            data = io.BytesIO()
            Image.new("RGB", (16, 12), "blue").save(data, "PNG")
            content.append({"type": "image", "mimeType": "image/png", "data": base64.b64encode(data.getvalue()).decode()})
        return {"isError": False, "content": content}

    @contextmanager
    def session_context(self, *_):
        desktop = self

        class Computer:
            call = staticmethod(desktop.input)
            image = staticmethod(ChatComputer.image)

        class Collector:
            root = desktop.root
            call = staticmethod(desktop.rpc)

        yield Computer(), Collector(), self.registered, self.rpc("health")
