"""Mac provenance and failure-mode checks alongside the unchanged iOS suite."""

import base64
import io
import json
import os
import plistlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from copyapp.macos.case import Case, canonical, digest
from copyapp.macos.chatcomputer import ChatComputer, ChatComputerError, UnknownCompletion
from copyapp.macos.doctor import doctor
from copyapp.macos.package import app_facts, index_app
from copyapp.verify import verify_case


def make_app(root, *, platform=1, cpu=0x0100000C):
    app = root / "Example.app"
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "test.copyapp.example", "CFBundleExecutable": "Example",
        "CFBundlePackageType": "APPL", "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0"}))
    header = struct.pack("<8I", 0xFEEDFACF, cpu, 0, 2, 1, 24, 0, 0)
    command = struct.pack("<6I", 0x32, 24, platform, 0x0e0000, 0x0e0000, 0)
    (app / "Contents/MacOS/Example").write_bytes(header + command)
    (app / "Contents/MacOS/Example").chmod(0o755)
    return app


def make_server(root: Path, *, behavior="normal"):
    """A real child process, testing framing/deadlines rather than mocking reads."""
    image = io.BytesIO()
    Image.new("RGB", (16, 12), "blue").save(image, format="PNG")
    encoded = base64.b64encode(image.getvalue()).decode()
    script = root / "chatcomputer"
    log = root / "calls.jsonl"
    source = '''import json,sys,time
from pathlib import Path
log=Path(LOG)
for line in sys.stdin:
    request=json.loads(line)
    if 'id' not in request: continue
    method=request['method']
    if method=='initialize': result={'serverInfo':{'name':'chatcomputer','version':'0.9.11'}}
    elif method=='tools/list': result={'tools':[{'name':s} for s in ['status','screenshot','release','click']]}
    else:
        name=request['params']['name']
        with log.open('a') as out: out.write(json.dumps(request)+'\\n')
        if name=='click' and BEHAVIOR=='disconnect': sys.exit(0)
        if name=='click' and BEHAVIOR=='timeout': time.sleep(5)
        if name=='screenshot': result={'isError':False,'content':[{'type':'image','mimeType':'image/png','data':IMAGE}]}
        else: result={'isError':False,'content':[{'type':'text','text':'Virtual Mac: running, desktop ready'}]}
    ident=request['id']+1 if BEHAVIOR=='wrong-id' else request['id']
    print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result}),flush=True)
'''
    # Source literals are Python literals, not shell fragments.
    source = (source.replace("LOG", repr(str(log))).replace("BEHAVIOR", repr(behavior))
              .replace("IMAGE", repr(encoded)))
    script.write_text("#!" + sys.executable + "\n" + source)
    script.chmod(0o755)
    return str(script), log


class MacPackageTests(unittest.TestCase):
    def test_snapshot_is_portable_and_source_changes_do_not_mutate_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = make_app(root)
            (app / "Contents/Resources").mkdir()
            (app / "Contents/Resources/alias").symlink_to("../Info.plist")
            case = index_app(app, root / "case")
            self.assertTrue(verify_case(case))
            (app / "Contents/MacOS/Example").write_bytes(b"updated on source")
            self.assertTrue(verify_case(case))
            (case / "app/Example.app/Contents/MacOS/Example").write_bytes(b"tampered")
            self.assertFalse(verify_case(case))

    def test_complete_inventory_detects_added_file_and_link_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case = index_app(make_app(root), root / "case")
            extra = case / "app/Example.app/Contents/extra"
            extra.write_bytes(b"injected")
            self.assertFalse(verify_case(case))
            extra.unlink()
            extra.symlink_to("Info.plist")
            self.assertFalse(verify_case(case))

    def test_snapshot_does_not_copy_protected_system_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = make_app(root)
            with patch("shutil.copystat", side_effect=PermissionError("restricted system flags")):
                case = index_app(app, root / "case")
            self.assertTrue(verify_case(case))

    def test_rejects_ios_and_intel_as_native_mac(self):
        for platform, cpu in ((2, 0x0100000C), (1, 0x01000007)):
            with self.subTest(platform=platform, cpu=cpu), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    app_facts(make_app(Path(folder), platform=platform, cpu=cpu))

    def test_rejects_external_bundle_symlink_and_nested_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = make_app(root)
            (root / "outside").write_text("outside")
            link = app / "Contents/link"
            link.symlink_to("../../outside")
            with self.assertRaises(ValueError):
                index_app(app, root / "case")
            link.unlink()
            with self.assertRaises(ValueError):
                index_app(app, app / "case")

    def test_legacy_looking_file_cannot_bypass_mac_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            case = index_app(make_app(root), root / "case")
            (case / "report-index.json").write_text('{"artifacts":{}}')
            (case / "app/Example.app/Contents/MacOS/Example").write_bytes(b"wrong")
            self.assertFalse(verify_case(case))

    def test_rejects_kind_platform_scope_and_app_identity_changes(self):
        for key, value in (("kind", "mac_unknown"), ("platform", "ios"),
                           ("scope", "installed"), ("bundle_id", "other.app")):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                case = index_app(make_app(root), root / "case")
                manifest = json.loads((case / "manifest.json").read_text())
                manifest[key] = value
                (case / "manifest.json").write_bytes(canonical(manifest))
                self.assertFalse(verify_case(case))

    def test_records_full_and_arm64_slice_hashes_for_universal(self):
        with tempfile.TemporaryDirectory() as folder:
            app = make_app(Path(folder))
            executable = app / "Contents/MacOS/Example"
            arm64 = executable.read_bytes()
            offset = 4096
            fat = struct.pack(">7I", 0xCAFEBABE, 1, 0x0100000C, 0, offset, len(arm64), 12)
            executable.write_bytes(fat.ljust(offset, b"\0") + arm64)
            facts = app_facts(app)
            self.assertNotEqual(facts["binary_sha256"], facts["arm64_sha256"])


class MacMCPTests(unittest.TestCase):
    def test_real_stdio_session_image_and_input(self):
        with tempfile.TemporaryDirectory() as folder:
            executable, log = make_server(Path(folder))
            with ChatComputer(executable, timeout=2) as client:
                self.assertIn("desktop ready", client.text(client.call("status")))
                data, mime = client.image(client.call("screenshot"))
                self.assertEqual(mime, "image/png")
                self.assertTrue(data.startswith(b"\x89PNG"))
                client.call("click", {"x": 2, "y": 3})
                client.call("release")
            calls = [json.loads(line)["params"]["name"] for line in log.read_text().splitlines()]
            self.assertEqual(calls, ["status", "screenshot", "click", "release"])

    def test_dropped_or_late_action_response_is_unknown_and_never_retried(self):
        for behavior in ("disconnect", "timeout"):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as folder:
                executable, log = make_server(Path(folder), behavior=behavior)
                with ChatComputer(executable, timeout=0.3) as client:
                    with self.assertRaises(UnknownCompletion):
                        client.call("click", {"x": 1, "y": 1})
                    with self.assertRaises(ChatComputerError):
                        client.call("click", {"x": 1, "y": 1})
                self.assertEqual(len(log.read_text().splitlines()), 1)

    def test_rejects_wrong_response_id(self):
        with tempfile.TemporaryDirectory() as folder:
            executable, _ = make_server(Path(folder), behavior="wrong-id")
            with self.assertRaises(ChatComputerError):
                with ChatComputer(executable, timeout=2):
                    self.fail("must not admit a mismatched JSON-RPC response")

    def test_doctor_ready_is_only_transport_and_image_tampering_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable, _ = make_server(root)
            with patch("copyapp.macos.doctor.sys.platform", "darwin"):
                case, ready = doctor(root / "doctor", executable, timeout=2)
            self.assertTrue(ready)
            self.assertTrue(verify_case(case))
            record = json.loads((case / "doctor.json").read_text())
            self.assertFalse(record["exact_app_identity_ready"])
            (case / "screen.png").write_bytes(b"not the captured screen")
            self.assertFalse(verify_case(case))

    def test_unavailable_tooling_is_a_verifiable_needs_setup_case(self):
        with tempfile.TemporaryDirectory() as folder:
            case, ready = doctor(Path(folder) / "doctor", "/does/not/exist")
            self.assertFalse(ready)
            self.assertTrue(verify_case(case))
            self.assertEqual(json.loads((case / "manifest.json").read_text())["status"], "needs_setup")


if __name__ == "__main__":
    unittest.main()
