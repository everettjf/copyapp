"""Run-scoped requests to the bounded guest collector through virtio-fs.

The outbox is outside guest snapshots. Unique request IDs, request hashes and
started markers prevent stale replies and blind re-execution after restore.
This is a guest evidence channel, not an arbitrary command-execution service.
"""

import json
import fcntl
import time
from pathlib import Path
from uuid import UUID, uuid4

from copyapp.macos.case import canonical
from copyapp.macos.chatcomputer import UnknownCompletion


METHODS = frozenset({"health", "app_identity", "observe", "launch_app", "export_app", "package_identity", "install_app"})
MAX_REPLY = 8 * 1024 * 1024


def atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    with temporary.open("xb") as stream:
        stream.write(canonical(value) + b"\n")
    temporary.replace(path)


class Collector:
    def __init__(self, shared_root: Path, collector_sha256: str, timeout: float = 15):
        if (len(collector_sha256) != 64 or any(c not in "0123456789abcdef" for c in collector_sha256)
                or not 0 < timeout <= 120):
            raise ValueError("invalid collector hash or timeout")
        self.root = shared_root.resolve(strict=True)
        self.hash = collector_sha256
        self.timeout = timeout
        self.session = str(uuid4())
        self.instance = None
        self.last_request = None
        self.last_response = None
        self.closed = False
        self.requests = self.root / "inbox/copyapp-bridge" / self.session
        self.responses = self.root / "outbox/copyapp-bridge" / self.session
        self.requests.parent.mkdir(parents=True, exist_ok=True)
        self._lock = (self.requests.parent / ".host.lock").open("a+b")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.requests.mkdir(parents=True, exist_ok=False)
            atomic_json(self.root / "inbox/copyapp-bridge/active.json",
                        {"protocol_version": 2, "session_id": self.session})
        except BaseException:
            self._lock.close()
            raise

    def call(self, method: str, params=None) -> dict:
        if self.closed:
            raise RuntimeError("Collector session is closed; establish a new session")
        self.last_request, self.last_response = None, None
        try:
            return self._call(method, params)
        except BaseException as exc:
            if self.last_request is not None:
                exc.collector_evidence = {"request": self.last_request, "response": self.last_response}
            self.close()
            raise

    def _call(self, method: str, params=None) -> dict:
        if method not in METHODS:
            raise ValueError("unsupported collector method")
        if params is not None and not isinstance(params, dict):
            raise ValueError("collector parameters must be an object")
        request_id = str(uuid4())
        request = {"protocol_version": 2, "session_id": self.session,
                   "request_id": request_id, "collector_sha256": self.hash,
                   "method": method, "params": params or {}}
        if self.instance is not None:
            request["collector_instance"] = self.instance
        import hashlib
        request_hash = hashlib.sha256(canonical(request)).hexdigest()
        self.last_request, self.last_response = request, None
        atomic_json(self.requests / (request_id + ".json"), request)
        path = self.responses / (request_id + ".json")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if path.exists():
                base = self.root / "outbox"
                if (path.is_symlink() or base.resolve() != base or
                        base not in path.resolve().parents or
                        any(parent.is_symlink() for parent in path.parents
                            if parent != self.root and self.root in parent.parents) or
                        path.stat().st_size > MAX_REPLY):
                    raise ValueError("invalid collector response file")
                response = json.loads(path.read_text())
                self.last_response = response
                if (response.get("protocol_version") != 2 or
                        response.get("session_id") != self.session or
                        response.get("request_id") != request_id or
                        response.get("request_sha256") != request_hash or
                        response.get("collector_sha256") != self.hash):
                    raise ValueError("collector response source/session mismatch")
                instance = response.get("collector_instance")
                UUID(instance)
                if self.instance is not None and instance != self.instance:
                    raise ValueError("collector restarted; establish a new session")
                self.instance = instance
                if response.get("status") != "complete":
                    if response.get("completion_unknown") is True:
                        raise UnknownCompletion("Collector action outcome is unknown; inspect the guest before replay: " +
                                                str(response.get("error", "no detail"))[:2048])
                    raise RuntimeError(str(response.get("error", "collector request failed")))
                if not isinstance(response.get("result"), dict):
                    raise ValueError("invalid collector result")
                return {"request": request, "response": response}
            time.sleep(0.1)
        # Even read-only observations are not silently repeated. Preserve this
        # request in the inbox for diagnosis, and start a new session after reset.
        raise UnknownCompletion("Collector response timed out; preserve request and inspect guest readiness")

    def close(self):
        self.closed = True
        self._lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
