import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from copyapp.view_tree import capture_view_tree


@contextmanager
def tunnel(_udid, *_args):
    yield 22001


@contextmanager
def identity(_udid):
    yield 22002


class ViewTreeIdentityTest(unittest.TestCase):
    def test_ictrl_scan_uses_separate_ios_mcp_foreground_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            def capture(_udid, _bundle, _output, _backend, _port,
                        _client, record, _launch, identity_port):
                self.assertEqual(identity_port, 22002)
                record["status"] = "complete"

            with patch("copyapp.view_tree.ictrl_tunnel", tunnel), \
                 patch("copyapp.view_tree.ios_mcp_tunnel", identity), \
                 patch("copyapp.view_tree._capture_with_port", side_effect=capture):
                path, complete = capture_view_tree(
                    "device", "com.example.app", Path(directory) / "case",
                    backend="ictrl", launch=False)
            self.assertTrue(complete)
            record = json.loads(path.read_text())
            self.assertEqual(record["status"], "complete")
