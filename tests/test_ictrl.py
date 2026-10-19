import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from copyapp.ictrl import ICtrlClient, ICtrlError


class ICtrlClientTest(unittest.TestCase):
    def test_passes_only_allowed_json_rpc_through_localhost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "args.json"
            fake = root / "ictrl"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                f"open({str(log)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
                "print(json.dumps({'jsonrpc':'2.0','id':1,'result':{'ok':True}}))\n"
            )
            os.chmod(fake, 0o700)
            client = ICtrlClient(port=22224, client=fake)
            self.assertEqual(client.call_ui("tap", {"ref": "abc"}), {"ok": True})
            self.assertEqual(json.loads(log.read_text()), [
                "--host", "127.0.0.1:22224", "call", "tap", '{"ref":"abc"}',
            ])
            with self.assertRaises(ValueError):
                client.call_ui("config", {"stop_server": True})

    def test_rejects_json_rpc_error(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "ictrl"
            fake.write_text("#!/usr/bin/env python3\n"
                            "print('{\"jsonrpc\":\"2.0\",\"id\":1,\"error\":{\"code\":401}}')\n")
            os.chmod(fake, 0o700)
            with self.assertRaises(ICtrlError):
                ICtrlClient(client=fake).call_ui("logs")

    def test_dropped_reply_is_unknown_completion_and_never_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Path(directory) / "ictrl"
            client.touch()
            for error in ("malformed HTTP response", "empty HTTP response", "read failed: reset"):
                with self.subTest(error=error), \
                     patch("copyapp.ictrl.subprocess.run", return_value=
                           subprocess.CompletedProcess([], 1, "", "ictrl: " + error)) as run:
                    with self.assertRaisesRegex(ICtrlError, "completion is unknown"):
                        ICtrlClient(client=client).call_ui("tap", {"x": 10, "y": 20})
                    run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
