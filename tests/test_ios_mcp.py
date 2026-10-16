import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from copyapp.ios_mcp import IOSMCPClient, IOSMCPError


class FakeIOSMCP(BaseHTTPRequestHandler):
    calls = []
    server_name = "copyapp-ios-mcp"

    def log_message(self, *_args):
        pass

    def _respond(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Session-Id", "test-session")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._respond({"status": "ok", "server": self.server_name,
                       "supportedProtocolVersions": ["2025-06-18"]})

    def do_POST(self):
        packet = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append((packet, self.headers.get("Mcp-Session-Id")))
        if packet["method"] == "initialize":
            result = {"protocolVersion": "2025-06-18"}
        elif packet["params"]["name"] == "screenshot":
            result = {"content": [{"type": "image", "mimeType": "image/jpeg",
                                   "data": base64.b64encode(b"\xff\xd8\xff\xd9").decode()}]}
        else:
            result = {"content": [{"type": "text", "text": '{"tapped":true}'}]}
        self._respond({"jsonrpc": "2.0", "id": packet["id"], "result": result})


class IOSMCPClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeIOSMCP)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        FakeIOSMCP.calls = []
        FakeIOSMCP.server_name = "copyapp-ios-mcp"
        self.client = IOSMCPClient(port=self.server.server_port)

    def test_ui_call_uses_session_and_rejects_shell(self):
        self.client.initialize()
        result = self.client.call_ui("tap_screen", {"x": 20, "y": 30})
        self.assertEqual(self.client.text_json(result), {"tapped": True})
        self.assertEqual(FakeIOSMCP.calls[-1][1], "test-session")
        with self.assertRaises(ValueError):
            self.client.call_ui("run_command", {"command": "id"})
        self.assertEqual(len(FakeIOSMCP.calls), 2)

    def test_device_ocr_is_blocked_before_rpc(self):
        with self.assertRaises(ValueError):
            self.client.call_ui("ocr_screen")
        with self.assertRaises(ValueError):
            self.client.call_ui("describe_screen", {"include_ocr": True})
        self.assertEqual(FakeIOSMCP.calls, [])

    def test_screenshot_bytes(self):
        self.client.initialize()
        image = self.client.image_bytes(self.client.call_ui("screenshot"))
        self.assertEqual(image, b"\xff\xd8\xff\xd9")

    def test_bad_port(self):
        with self.assertRaises(ValueError):
            IOSMCPClient(port=0)

    def test_rejects_unmodified_upstream_server(self):
        FakeIOSMCP.server_name = "ios-mcp"
        with self.assertRaises(IOSMCPError):
            self.client.initialize()


if __name__ == "__main__":
    unittest.main()
