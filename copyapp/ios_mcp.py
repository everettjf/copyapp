"""Small localhost-only client for the jailbroken iOS MCP UI service.

The USB mux tunnel must be started separately.  This client deliberately
exposes only UI observation and control tools; it never forwards arbitrary
shell, file, package, or device-management calls from an agent.
"""

import base64
import http.client
import json
from typing import Any, Dict, Optional


UI_TOOLS = frozenset({
    "get_frontmost_app", "get_screen_info", "get_ui_elements",
    "describe_screen", "screenshot",
    "tap_screen", "tap_element", "swipe_screen", "long_press", "double_tap",
    "input_text", "type_text",
    "launch_app", "press_home", "wake_and_home",
})


class IOSMCPError(RuntimeError):
    pass


class IOSMCPClient:
    def __init__(self, port: int = 22223, timeout: float = 10.0):
        if not 1 <= port <= 65535:
            raise ValueError("invalid localhost port")
        self.port = port
        self.timeout = timeout
        self.protocol_version = "2025-06-18"
        self.session_id: Optional[str] = None
        self._request_id = 0

    def _http(self, method: str, path: str, payload: Optional[dict] = None) -> Dict[str, Any]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Accept": "application/json", "MCP-Protocol-Version": self.protocol_version}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.timeout)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            if response.getheader("Mcp-Session-Id"):
                self.session_id = response.getheader("Mcp-Session-Id")
            raw = response.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise IOSMCPError("response exceeds 16 MiB")
            if response.status != 200:
                raise IOSMCPError(f"HTTP {response.status}: {raw[:256].decode(errors='replace')}")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise IOSMCPError("expected JSON object")
            return result
        except (OSError, json.JSONDecodeError) as exc:
            raise IOSMCPError(str(exc)) from exc
        finally:
            connection.close()

    def health(self) -> Dict[str, Any]:
        result = self._http("GET", "/health")
        if result.get("server") != "copyapp-ios-mcp" or result.get("status") != "ok":
            raise IOSMCPError("unexpected service on local tunnel")
        return result

    def request(self, method: str, params: Optional[dict] = None) -> Dict[str, Any]:
        self._request_id += 1
        packet = {"jsonrpc": "2.0", "id": self._request_id, "method": method,
                  "params": params or {}}
        result = self._http("POST", "/mcp", packet)
        if result.get("id") != self._request_id:
            raise IOSMCPError("JSON-RPC response id mismatch")
        if "error" in result:
            raise IOSMCPError(f"JSON-RPC error: {result['error']}")
        value = result.get("result")
        if not isinstance(value, dict):
            raise IOSMCPError("JSON-RPC result missing")
        return value

    def initialize(self) -> Dict[str, Any]:
        health = self.health()
        supported = health.get("supportedProtocolVersions", [])
        if "2025-06-18" not in supported:
            raise IOSMCPError("service does not support MCP 2025-06-18")
        result = self.request("initialize", {
            "protocolVersion": self.protocol_version,
            "capabilities": {}, "clientInfo": {"name": "copyapp", "version": "0.1.0"},
        })
        self.protocol_version = result.get("protocolVersion", self.protocol_version)
        return result

    def call_ui(self, name: str, arguments: Optional[dict] = None) -> Dict[str, Any]:
        if name not in UI_TOOLS:
            raise ValueError(f"tool is outside Copy APP UI allowlist: {name}")
        if name == "describe_screen" and (arguments or {}).get("include_ocr"):
            raise ValueError("device OCR is disabled; use Copy APP host OCR on a screenshot")
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise IOSMCPError(f"{name}: {self.first_text(result)[:400]}")
        return result

    @staticmethod
    def first_text(result: Dict[str, Any]) -> str:
        for item in result.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                return str(item.get("text", ""))
        return ""

    @staticmethod
    def text_json(result: Dict[str, Any]) -> Any:
        value = IOSMCPClient.first_text(result)
        if not value:
            raise IOSMCPError("tool returned no text")
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"text": value}

    @staticmethod
    def image_bytes(result: Dict[str, Any]) -> bytes:
        for item in result.get("content", []):
            if isinstance(item, dict) and item.get("type") == "image":
                if item.get("mimeType") != "image/jpeg":
                    raise IOSMCPError("unexpected screenshot format")
                try:
                    return base64.b64decode(item["data"], validate=True)
                except (KeyError, ValueError) as exc:
                    raise IOSMCPError("invalid screenshot data") from exc
        raise IOSMCPError("tool returned no screenshot")
