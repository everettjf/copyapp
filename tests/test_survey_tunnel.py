import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from copyapp.cli import command_survey


class SurveyTunnelTest(unittest.IsolatedAsyncioTestCase):
    async def test_ios_mcp_survey_owns_exact_device_tunnel(self):
        seen = []

        @contextmanager
        def tunnel(udid):
            seen.append(("open", udid))
            try:
                yield 34567
            finally:
                seen.append(("close", udid))

        async def collector(udid, bundle, output, launch, backend, client):
            seen.append(("collect", client.port))
            self.assertEqual((udid, bundle, launch, backend),
                             ("device-123", "com.example.app", True, "ios-mcp"))
            return 0

        with tempfile.TemporaryDirectory() as root, \
                patch("copyapp.cli.ios_mcp_tunnel", tunnel), \
                patch("copyapp.cli._command_survey", collector):
            result = await command_survey("device-123", "com.example.app",
                                          Path(root), True, "ios-mcp")
        self.assertEqual(result, 0)
        self.assertEqual(seen, [("open", "device-123"),
                                ("collect", 34567), ("close", "device-123")])
