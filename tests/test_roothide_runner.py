import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.decrypt_package import _run_roothide_helper
from copyapp.root_bridge import _spawned_effective_uid, resolve_jailbreak_executable


class RootHideRunnerTest(unittest.TestCase):
    def test_spawned_uid_comes_from_suspended_frida_child(self):
        class Script:
            def on(self, name, callback):
                self.callback = callback

            def load(self):
                self.callback({"type": "send", "payload": 501}, None)

        class Session:
            def __init__(self):
                self.detached = False

            def create_script(self, source):
                self.source = source
                return Script()

            def detach(self):
                self.detached = True

        class Device:
            def attach(self, pid):
                self.pid = pid
                self.session = Session()
                return self.session

        device = Device()
        self.assertEqual(_spawned_effective_uid(device, 17), 501)
        self.assertEqual(device.pid, 17)
        self.assertIn("geteuid", device.session.source)
        self.assertTrue(device.session.detached)

    def test_resolved_executable_rejects_untrusted_device_path(self):
        with patch("copyapp.root_bridge.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, b"/tmp/../bin/sh\n")):
            with self.assertRaisesRegex(RuntimeError, "invalid jailbreak executable"):
                resolve_jailbreak_executable(["ssh", "device"], "/bin/sh")

    def test_roothide_command_preserves_arguments_and_records_failure(self):
        command = ["/usr/bin/timeout", "5", "/rootfs/var/mobile/Media/helper",
                   "decrypt", "com.example; touch /tmp/unsafe", "/app", "/out"]
        calls = []

        def run(argv, **_kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 23, b"helper failed\n", b"")

        with tempfile.TemporaryDirectory() as root, \
                patch("copyapp.decrypt_package.subprocess.run", side_effect=run):
            output = Path(root) / "device-run"
            result = _run_roothide_helper(["ssh", "device"], "device-123",
                                          command, output)
            self.assertEqual(shlex.split(calls[0][-1]), command)
            self.assertEqual(result["exit_code"], 23)
            self.assertEqual((output / "output.txt").read_bytes(), b"helper failed\n")
            self.assertEqual(json.loads((output / "result.json").read_text())["command"],
                             command)
