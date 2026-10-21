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


def xcode_fixture(project):
    """Tiny native Mac project used to exercise the real xcodebuild path."""
    path = project / "Independent.xcodeproj"
    path.mkdir()
    (path / "project.pbxproj").write_text('''// !$*UTF8*$!
{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {
  A00000000000000000000001 = { isa = PBXProject;
    buildConfigurationList = A00000000000000000000002;
    compatibilityVersion = "Xcode 14.0"; developmentRegion = en;
    knownRegions = (en, Base); mainGroup = A00000000000000000000003;
    productRefGroup = A00000000000000000000004;
    projectDirPath = ""; projectRoot = ""; targets = (A00000000000000000000005); };
  A00000000000000000000002 = { isa = XCConfigurationList;
    buildConfigurations = (A00000000000000000000006); defaultConfigurationIsVisible = 0; defaultConfigurationName = Debug; };
  A00000000000000000000003 = { isa = PBXGroup;
    children = (A00000000000000000000007, A00000000000000000000004); sourceTree = "<group>"; };
  A00000000000000000000004 = { isa = PBXGroup; children = (A00000000000000000000008); name = Products; sourceTree = "<group>"; };
  A00000000000000000000005 = { isa = PBXNativeTarget;
    buildConfigurationList = A00000000000000000000009;
    buildPhases = (A0000000000000000000000A); buildRules = (); dependencies = ();
    name = Independent; productName = Independent; productReference = A00000000000000000000008;
    productType = "com.apple.product-type.application"; };
  A00000000000000000000006 = { isa = XCBuildConfiguration; name = Debug;
    buildSettings = { SDKROOT = macosx; MACOSX_DEPLOYMENT_TARGET = 14.0; SWIFT_VERSION = 5.0; }; };
  A00000000000000000000007 = { isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = Main.swift; sourceTree = "<group>"; };
  A00000000000000000000008 = { isa = PBXFileReference; explicitFileType = wrapper.application;
    includeInIndex = 0; path = Independent.app; sourceTree = BUILT_PRODUCTS_DIR; };
  A00000000000000000000009 = { isa = XCConfigurationList;
    buildConfigurations = (A0000000000000000000000B); defaultConfigurationIsVisible = 0; defaultConfigurationName = Debug; };
  A0000000000000000000000A = { isa = PBXSourcesBuildPhase; buildActionMask = 2147483647;
    files = (A0000000000000000000000C); runOnlyForDeploymentPostprocessing = 0; };
  A0000000000000000000000B = { isa = XCBuildConfiguration; name = Debug; buildSettings = {
    PRODUCT_NAME = Independent; PRODUCT_BUNDLE_IDENTIFIER = dev.copyapp.Clone;
    INFOPLIST_FILE = Info.plist; CODE_SIGN_IDENTITY = "-"; CODE_SIGN_STYLE = Manual;
    CODE_SIGNING_ALLOWED = YES; ENABLE_HARDENED_RUNTIME = NO; SWIFT_OPTIMIZATION_LEVEL = "-Onone";
    LD_RUNPATH_SEARCH_PATHS = "$(inherited) @executable_path/../Frameworks";
  }; };
  A0000000000000000000000C = { isa = PBXBuildFile; fileRef = A00000000000000000000007; };
}; rootObject = A00000000000000000000001; }
''')


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
