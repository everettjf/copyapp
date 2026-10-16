"""Narrow adapter to iCTRL's authenticated, encrypted command-line client.

The upstream client owns pairing and cryptography. Copy APP passes only a UI
method allowlist and never implements or downgrades its sealed JSON-RPC wire
format. The runner must be started and USB-forwarded separately.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


ICTRL_UI_METHODS = frozenset({
    "logs", "device_info", "page_source", "screen_text", "find_element",
    "tap", "swipe", "long_press", "double_tap", "type", "launch_app", "home", "screenshot",
})
DEFAULT_CLIENT = Path(__file__).resolve().parents[2] / "toolchains" / "ictrl-macos"


class ICtrlError(RuntimeError):
    pass


class ICtrlClient:
    def __init__(self, port: int = 22224, client: Path = DEFAULT_CLIENT):
        if not 1 <= port <= 65535:
            raise ValueError("invalid localhost port")
        if not client.is_file():
            raise FileNotFoundError(f"iCTRL client not found: {client}")
        self.port = port
        self.client = client

    def _run(self, *args: str, timeout: float = 45.0) -> subprocess.CompletedProcess:
        command = [str(self.client), "--host", f"127.0.0.1:{self.port}", *args]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                    check=False)
        except subprocess.TimeoutExpired as exc:
            raise ICtrlError(
                "iCTRL command timed out; completion is unknown. Inspect runner logs before any retry."
            ) from exc
        if result.returncode:
            raise ICtrlError((result.stderr or result.stdout).strip()[:800])
        return result

    def call_ui(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if method not in ICTRL_UI_METHODS:
            raise ValueError(f"method is outside Copy APP iCTRL UI allowlist: {method}")
        result = self._run("call", method, json.dumps(params or {}, separators=(",", ":")))
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ICtrlError("iCTRL returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise ICtrlError("iCTRL returned non-object response")
        if response.get("error"):
            raise ICtrlError(f"iCTRL {method}: {str(response['error'])[:500]}")
        value = response.get("result")
        if not isinstance(value, dict):
            raise ICtrlError("iCTRL JSON-RPC result missing")
        return value

    def screenshot(self, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        self._run("shot", str(output))
        if not output.is_file() or not output.stat().st_size:
            raise ICtrlError("iCTRL screenshot file missing or empty")
        return output
