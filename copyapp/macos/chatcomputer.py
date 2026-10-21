"""Bounded stdio MCP client for ChatComputer's existing public tool vocabulary.

Only one caller owns a process. An uncertain action is never retried: the caller
must inspect the desktop. Text replies remain raw evidence, not identity facts.
"""

import base64
import json
import os
import selectors
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional


MAX_MESSAGE = 48 * 1024 * 1024
MAX_IMAGE = 32 * 1024 * 1024
INPUT_TOOLS = frozenset({"click", "move", "drag", "scroll", "type", "key", "save_file"})
TOOLS = INPUT_TOOLS | frozenset({"status", "screenshot", "elements", "text", "wait",
                               "snapshot_list", "snapshot_take", "snapshot_restore",
                               "snapshot_delete", "put_file", "outbox", "share_list",
                               "share_add", "share_remove", "release"})


class ChatComputerError(RuntimeError):
    pass


class UnknownCompletion(ChatComputerError):
    """An action may have happened even though its reply was not received."""


class ChatComputer:
    def __init__(self, executable: str = "chatcomputer", timeout: float = 30,
                 data_dir: Optional[Path] = None):
        if not 0 < timeout <= 300:
            raise ValueError("MCP timeout must be in (0, 300]")
        self.executable = executable
        self.timeout = timeout
        self.data_dir = data_dir
        self.process = None
        self._stderr = None
        self._selector = None
        self._buffer = bytearray()
        self._next_id = 0
        self._tools = set()
        self._lock = threading.Lock()

    def __enter__(self):
        executable = shutil.which(self.executable)
        if executable is None:
            raise FileNotFoundError("ChatComputer is not installed or executable is not on PATH")
        environment = os.environ.copy()
        if self.data_dir is not None:
            environment["CC_DATA_DIR"] = str(self.data_dir.resolve())
        self._stderr = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen([executable, "mcp"], stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self._stderr,
                                            env=environment)
            os.set_blocking(self.process.stdin.fileno(), False)
            self._selector = selectors.DefaultSelector()
            self._selector.register(self.process.stdout, selectors.EVENT_READ)
            self.server_info = self._request("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "Copy APP", "version": "0.1.2"}}).get("serverInfo")
            if (not isinstance(self.server_info, dict) or
                    self.server_info.get("name") != "chatcomputer"):
                raise ChatComputerError("unexpected MCP server identity")
            self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})
            catalog = self._request("tools/list", {})
            if not isinstance(catalog.get("tools"), list):
                raise ChatComputerError("invalid MCP tool catalog")
            names = [tool.get("name") for tool in catalog["tools"] if isinstance(tool, dict)]
            if (len(names) != len(catalog["tools"]) or
                    any(not isinstance(name, str) or not name for name in names) or
                    len(set(names)) != len(names)):
                raise ChatComputerError("invalid or duplicate MCP tool names")
            self._tools = set(names)
            if not {"status", "screenshot", "release"}.issubset(self._tools):
                raise ChatComputerError("ChatComputer lacks required public tools")
            return self
        except BaseException:
            self.close()
            raise

    def _write(self, value: dict):
        data = json.dumps(value, allow_nan=False, ensure_ascii=False).encode() + b"\n"
        if len(data) > 1024 * 1024:
            raise ValueError("MCP request exceeds limit")
        deadline = time.monotonic() + self.timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdin, selectors.EVENT_WRITE)
            offset = 0
            while offset < len(data):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("ChatComputer stopped reading its MCP request")
                try:
                    offset += os.write(self.process.stdin.fileno(), data[offset:offset + 65536])
                except BlockingIOError:
                    continue

    def _line(self, deadline: float) -> bytes:
        while True:
            if b"\n" in self._buffer:
                line, _, remainder = self._buffer.partition(b"\n")
                self._buffer = bytearray(remainder)
                return bytes(line)
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._selector.select(remaining):
                raise TimeoutError("ChatComputer MCP response exceeded deadline")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise EOFError("ChatComputer closed its MCP response stream")
            self._buffer.extend(chunk)
            if len(self._buffer) > MAX_MESSAGE:
                raise ChatComputerError("MCP response exceeds limit")

    def _request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        expected = self._next_id
        self._write({"jsonrpc": "2.0", "id": expected, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            response = json.loads(self._line(deadline))
            if not isinstance(response, dict) or response.get("jsonrpc") != "2.0":
                raise ChatComputerError("malformed JSON-RPC response")
            if "id" not in response and isinstance(response.get("method"), str):
                continue  # Notifications do not extend the original deadline.
            if type(response.get("id")) is not int or response["id"] != expected:
                raise ChatComputerError("MCP response ID mismatch; reconnect before further input")
            if "error" in response:
                raise ChatComputerError("MCP error: " + json.dumps(response["error"]))
            result = response.get("result")
            if not isinstance(result, dict):
                raise ChatComputerError("invalid MCP result")
            return result

    def call(self, name: str, arguments: Optional[dict] = None) -> dict:
        if self.process is None:
            raise ChatComputerError("MCP session is closed; inspect state after reconnecting")
        if name not in TOOLS or name not in self._tools:
            raise ValueError("unsupported ChatComputer tool: " + name)
        with self._lock:
            try:
                result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
                if (not isinstance(result.get("content"), list) or
                        type(result.get("isError", False)) is not bool):
                    raise ChatComputerError("malformed MCP tool response")
            except (OSError, EOFError, TimeoutError, ValueError, ChatComputerError) as exc:
                self.close()
                if name in INPUT_TOOLS or name.startswith("snapshot_"):
                    raise UnknownCompletion("Completion unknown for " + name +
                                            "; inspect state before replay") from exc
                raise ChatComputerError(str(exc)) from exc
            if result.get("isError"):
                raise ChatComputerError(self.text(result))
            return result

    @staticmethod
    def text(result: dict) -> str:
        return "\n".join(item["text"] for item in result.get("content", [])
                         if isinstance(item, dict) and item.get("type") == "text"
                         and isinstance(item.get("text"), str))

    @staticmethod
    def image(result: dict) -> tuple:
        images = [item for item in result.get("content", [])
                  if isinstance(item, dict) and item.get("type") == "image"]
        if len(images) != 1:
            raise ChatComputerError("expected exactly one screenshot")
        item = images[0]
        if item.get("mimeType") not in ("image/png", "image/jpeg"):
            raise ChatComputerError("unsupported screenshot media type")
        data = base64.b64decode(item["data"], validate=True)
        if not data or len(data) > MAX_IMAGE:
            raise ChatComputerError("screenshot is empty or exceeds limit")
        return data, item["mimeType"]

    def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
        if self._selector is not None:
            self._selector.close()
            self._selector = None
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    def __exit__(self, *_):
        # Releasing input is explicit in the caller: a broken connection cannot
        # safely be re-opened just to send another command during cleanup.
        self.close()
