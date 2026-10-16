#!/usr/bin/env python3
"""iCTRL client — pairing + encrypted-envelope JSON-RPC (protocol v1).

All request-path crypto is HMAC-SHA256 only, so this is portable to any language
with an HMAC primitive. X25519 appears only in LAN pairing (mode A).

Usage:
    ./ictrl_rpc.py --host 10.0.0.5:8200 pair --name my-laptop
    ./ictrl_rpc.py --host 10.0.0.5:8200 call device_info
    ./ictrl_rpc.py --host 10.0.0.5:8200 call tap '{"x":100,"y":200}'
    ./ictrl_rpc.py --host 10.0.0.5:8200 shot out.jpg          # JPEG by default

Discovery (the phone has Nearby Discovery on): found on the LAN from any OS,
and over Apple peer-to-peer Wi-Fi from macOS with no shared network needed:
    ./ictrl_rpc.py scan                                       # list discoverable devices
    ./ictrl_rpc.py --nearby "iPhone 15 (7f3a)" call device_info
    ./ictrl_rpc.py --nearby 7f3a shot out.jpg                 # name or id prefix

Keys are cached in ~/.ictrl/token.json, one per DEVICE (its stable id, from
GET /whoami), so a phone paired once is reachable over USB, the LAN and nearby
alike, and two phones that take turns at one address (USB forwarding to
127.0.0.1) never overwrite each other's key. Pairing is a one-time step per
device; with --nearby it happens on first use: approve the prompt once.

Two notes for anything that moves a lot of data (server 1.5.0+):

  screenshot defaults to JPEG. The whole response body is decrypted through the
  envelope keystream, so response size — not device capture time — is what
  dominates a screenshot. A JPEG is several times smaller than the equivalent
  PNG; ask for {"format":"png"} only when you need lossless output.

  If UI calls start timing out and the log shows kAXErrorServerNotFound, the
  accessibility connection has dropped. Call `reset`, then launch_app the target
  app. device_info / logs / config keep working throughout — they run off the UI
  queue — so use them to diagnose while UI methods are blocked.
"""
from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import hmac
import http.client
import json
import os
import secrets
import select
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

STORE = os.path.expanduser("~/.ictrl/token.json")

LABEL_MAC = b"ictrl-v1|mac"
LABEL_ENC_REQ = b"ictrl-v1|enc-req"
LABEL_ENC_RESP = b"ictrl-v1|enc-resp"
LABEL_PAIR = b"ictrl-pair"
LABEL_WRAP = b"ictrl-wrap"


def _hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def _keystream_xor(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """PRF-CTR: keystream_i = HMAC(key, nonce || be32(i)).

    Both halves are written for bulk data, because a screenshot response runs
    entirely through here and a naive version dominates its end-to-end time:

    1. The HMAC inner/outer pads depend only on the key, so they're computed once
       and `.copy()`-ed per block. `hmac.new()` in the loop would re-absorb the
       key for every 32-byte block — tens of thousands of times on one image.
    2. The XOR goes through Python's big integers, whose C implementation beats a
       per-byte `zip()` comprehension by an order of magnitude.

    Prefer `format="jpeg"` on screenshot (the default since server 1.5.0): a
    smaller response is the real fix — this loop is merely no longer the
    bottleneck.
    """
    block = key.ljust(64, b"\0") if len(key) <= 64 else hashlib.sha256(key).digest().ljust(64, b"\0")
    inner = hashlib.sha256(bytes(b ^ 0x36 for b in block))
    outer = hashlib.sha256(bytes(b ^ 0x5C for b in block))

    out = bytearray()
    counter = 0
    while len(out) < len(data):
        i = inner.copy()
        i.update(nonce + counter.to_bytes(4, "big"))
        o = outer.copy()
        o.update(i.digest())
        out += o.digest()
        counter += 1

    n = len(data)
    if n == 0:
        return b""
    return (int.from_bytes(data, "big") ^ int.from_bytes(bytes(out[:n]), "big")).to_bytes(n, "big")


class _NcSocket:
    """The parts of a socket http.client uses, over nc's stdin/stdout. Two
    separate pipes: with one socketpair for both directions, nc's half-close
    of one side cuts a longer reply short."""

    def __init__(self, proc):
        self._proc = proc

    def sendall(self, data):
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

    def makefile(self, mode, *args, **kwargs):
        # A descriptor of its own: urllib closes the connection once the
        # headers are in, and the response goes on reading from this copy.
        return os.fdopen(os.dup(self._proc.stdout.fileno()), "rb")

    def settimeout(self, timeout):
        pass

    def close(self):
        pass


class _ZonedHTTPConnection(http.client.HTTPConnection):
    """Dial a zoned link-local IPv6 host ("fe80::1%awdl0"); every other host
    connects as usual.

    Directly first: the socket bound to the interface (macOS routes to an
    AWDL peer only then, and a bound socket also accepts the reply arriving on
    that restricted interface) plus SO_RECV_ANYIF for good measure. macOS
    Local Network privacy can still refuse the process outright — an instant
    EHOSTUNREACH, typically for an interpreter run from a context that was
    never granted access. Apple's own /usr/bin/nc is not subject to it, so
    the connection then goes through `nc -A` instead, for the rest of this
    run."""

    _via_nc = False             # set once a direct connection was refused
    _DIRECT_TIMEOUT = 4.0       # a refusal is instant; a dropped SYN-ACK is not

    def connect(self):
        host = self.host.strip("[]")
        if "%" not in host:
            return super().connect()
        timeout = self.timeout if isinstance(self.timeout, (int, float)) else 30.0
        if not _ZonedHTTPConnection._via_nc:
            try:
                self.sock = self._direct(host, min(timeout, self._DIRECT_TIMEOUT))
                return
            except OSError as exc:
                # A timeout usually means the address went stale (AWDL
                # addresses change when the link comes back): let the caller
                # look the device up again rather than wait out nc too. Only
                # an outright refusal — Local Network privacy — goes to nc.
                if exc.errno not in _REFUSED:
                    raise
                if not os.access(_NC, os.X_OK):
                    raise OSError(f"cannot reach {host}: {exc}. If 'No route to host', allow Local "
                                  "Network access for the app running this client (System Settings "
                                  "› Privacy & Security › Local Network)") from exc
                # A stale address is refused the same way; only a relay that
                # then gets through shows the refusal was this process's.
                self._nc = self._relay(host, timeout)
                _ZonedHTTPConnection._via_nc = True
                self.sock = _NcSocket(self._nc)
                return
        self._nc = self._relay(host, timeout)
        self.sock = _NcSocket(self._nc)

    def _direct(self, host, timeout):
        addr, zone = host.split("%", 1)
        index = socket.if_nametoindex(zone)
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.IPPROTO_IPV6, _IPV6_BOUND_IF, index)
            try:
                sock.setsockopt(socket.SOL_SOCKET, _SO_RECV_ANYIF, 1)
            except OSError:
                pass
            sock.settimeout(timeout)
            sock.connect((addr, self.port, 0, index))
            sock.settimeout(self.timeout)
            return sock
        except OSError:
            sock.close()
            raise

    def _relay(self, host, timeout):
        secs = str(max(1, int(timeout)))
        # -A: SO_RECV_ANYIF. -G: connect timeout; -w: idle timeout, so a silent
        # peer ends the read. -v reports "... succeeded!" once connected.
        proc = subprocess.Popen([_NC, "-6", "-A", "-v", "-G", secs, "-w", secs, host, str(self.port)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        line = b""
        deadline = time.time() + timeout
        while b"\n" not in line:
            left = deadline - time.time()
            if left <= 0 or not select.select([proc.stderr], [], [], left)[0]:
                break
            chunk = os.read(proc.stderr.fileno(), 512)
            if not chunk:
                break
            line += chunk
        if b"succeeded" not in line:
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    pipe.close()
                except OSError:
                    pass
            if proc.poll() is None:
                proc.kill()
            msg = line.decode("utf-8", "replace").strip() or "no answer"
            raise OSError(f"AWDL connection to {host} port {self.port} failed: {msg}")
        return proc

    def close(self):
        # nc is left to finish: it exits once the peer closes (the server
        # answers with Connection: close) or after its idle timeout. Stopping
        # it here would cut off a response that is still being read.
        super().close()
        self._nc = None


class _ZonedHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_ZonedHTTPConnection, req)


_IPV6_BOUND_IF = 125            # <netinet6/in6.h>, macOS
_SO_RECV_ANYIF = 0x1104         # <sys/socket.h> (private), macOS: accept input on a restricted interface
_NC = "/usr/bin/nc"
_REFUSED = {errno.EHOSTUNREACH, errno.ENETUNREACH, errno.EPERM, errno.EACCES}
# No proxy, ever: every iCTRL host is loopback, on the LAN or link-local, and
# a proxy taken from http_proxy cannot reach any of them (a link-local
# address not even in principle).
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _ZonedHandler)


# The device id the last response carried (X-ICTRL-Device), or None.
_answered_by: list = [None]


def _post(url: str, obj: dict, timeout: float) -> tuple[int, dict]:
    body = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    _answered_by[0] = None
    try:
        with _opener.open(req, timeout=timeout) as resp:
            _answered_by[0] = resp.headers.get(DEVICE_HEADER)
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        _answered_by[0] = e.headers.get(DEVICE_HEADER) if e.headers else None
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": {"message": raw.decode("utf-8", "replace")}}


def whoami(host: str, timeout: float = 5.0) -> dict | None:
    """GET /whoami: {device_id, name, …}; None when the server predates it."""
    try:
        with _opener.open(f"http://{host}/whoami", timeout=timeout) as resp:
            info = json.loads(resp.read() or b"{}")
            return info if info.get("device_id") else None
    except (urllib.error.HTTPError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- token store
#
# The store maps a name to a key record. Current records are named
# "device:<device id>" — one per device, whatever the channel. Older clients
# named them by address ("host:port") or, for nearby devices, "nearby:<id>";
# such a record is still used, and is copied under its device name once a
# call made with it succeeds (the old entry stays for older clients). Stores
# written by the pre-v1 plaintext-token client had their single record
# flattened at the top level ("host"/"token"/…); those carry no key and are
# ignored.

DEVICE_HEADER = "X-ICTRL-Device"
# address -> device id, so the id need not be asked for on every call. Only a
# shortcut: each response names its device, and a mismatch corrects it.
ADDRESS_CACHE = os.path.expanduser("~/.ictrl/devices.json")


def device_store_key(device_id: str) -> str:
    return f"device:{device_id}"


def _address_cache(update: dict | None = None) -> dict:
    try:
        with open(ADDRESS_CACHE) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        data = {}
    if update:
        data.update(update)
        os.makedirs(os.path.dirname(ADDRESS_CACHE), exist_ok=True)
        with open(ADDRESS_CACHE, "w") as fh:
            json.dump(data, fh, indent=2)
    return data


def device_id_for(host: str, fresh: bool = False) -> str | None:
    """The id of the device at `host` (cached, else GET /whoami); None for a
    server too old to say."""
    if not fresh:
        known = _address_cache().get(host)
        if known:
            return known
    info = whoami(host)
    if not info:
        return None
    _address_cache({host: info["device_id"]})
    return info["device_id"]


def _is_record(value) -> bool:
    """A usable v1 entry: a dict carrying the 32-byte key and its id."""
    return isinstance(value, dict) and "key" in value and "tok" in value


def load_token(host: str) -> dict | None:
    try:
        with open(STORE) as fh:
            entry = json.load(fh).get(host)
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return entry if _is_record(entry) else None


def list_hosts() -> dict:
    """Every device with a usable key, keyed by host:port."""
    try:
        with open(STORE) as fh:
            return {h: r for h, r in json.load(fh).items() if _is_record(r)}
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def save_token(host: str, record: dict) -> None:
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    # Drop legacy/plaintext leftovers rather than carrying them forward, so the
    # file stays a clean host -> record map.
    all_tokens = list_hosts()
    all_tokens[host] = record
    with open(STORE, "w") as fh:
        json.dump(all_tokens, fh, indent=2)
    os.chmod(STORE, 0o600)


def _addresses(record: dict) -> list:
    """Addresses a device record was last used at, most recent first."""
    return [a.lstrip("@") for a in record.get("addresses", record.get("hosts", []))]


def _remember_address(device_id: str, record: dict, host: str, name: str | None = None) -> None:
    """Save `record` as this device's key, noting the address it was used at.

    Addresses are stored with an "@" prefix: older clients find a record by
    searching the file for the quoted address ("10.0.0.5:8200"), and a bare
    copy inside this list would lead them to the wrong record's key."""
    rec = dict(record)
    rec.pop("hosts", None)
    rec["device_id"] = device_id
    if name:
        rec["device_name"] = name
    seen = [a for a in _addresses(record) if a != host]
    rec["addresses"] = ["@" + a for a in [host] + seen[:4]]
    save_token(device_store_key(device_id), rec)


# --------------------------------------------------------------------- nearby
#
# Nearby discovery: the phone advertises "_ictrl._tcp" over Apple peer-to-peer
# Wi-Fi (AWDL) only, with TXT "v" (protocol) and "id" (stable device id). macOS
# only, through the system dns_sd API (ctypes, standard library). The address
# is link-local and changes, so devices are keyed by id and re-resolved; a
# short-lived cache spares the lookup on back-to-back calls.

NEARBY_CACHE = os.path.expanduser("~/.ictrl/nearby_cache.json")
NO_NEARBY_HINT = ("no devices found — on the phone, turn on Nearby Discovery (iCTRL notification or app) "
                  "and keep Wi-Fi switched on; it need not be joined to a network")
NEARBY_CACHE_TTL = 30           # seconds; AWDL addresses change when the link restarts
_DNSSD_FLAGS = 0x100000 | 0x20000   # kDNSServiceFlagsIncludeAWDL | IncludeP2P


def _txt(raw: bytes) -> dict:
    out, i = {}, 0
    while i < len(raw):
        n = raw[i]
        k, _, v = raw[i + 1:i + 1 + n].decode("utf-8", "replace").partition("=")
        out[k] = v
        i += 1 + n
    return out


def nearby_scan(wait: float = 3.0, want=None) -> list[dict]:
    """Find iCTRL devices that have Nearby Discovery on: over Apple
    peer-to-peer Wi-Fi (macOS) and on the LAN. Each result is
    {name, id, host, channel: "lan"|"awdl"}; a device seen both ways appears
    twice. Stops early once `want(device)` is true, else collects for `wait` s.
    """
    if sys.platform != "darwin":
        return _mdns_scan(wait, want)
    import ctypes
    try:
        lib = ctypes.CDLL("/usr/lib/system/libsystem_dnssd.dylib")
    except OSError:
        return _mdns_scan(wait, want)
    lib.DNSServiceRefSockFD.restype = ctypes.c_int
    awdl = socket.if_nametoindex("awdl0") if hasattr(socket, "if_nametoindex") else 0
    ref_t = ctypes.c_void_p
    browse_t = ctypes.CFUNCTYPE(None, ref_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32,
                                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p)
    resolve_t = ctypes.CFUNCTYPE(None, ref_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32,
                                 ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint16, ctypes.c_uint16,
                                 ctypes.c_void_p, ctypes.c_void_p)
    addr_t = ctypes.CFUNCTYPE(None, ref_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32,
                              ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p)
    refs, found, devices, keep = [], {}, [], []

    def on_addr(_r, _f, _i, err, _h, sa, _ttl, ctx):
        dev = found.get(ctx)
        if err or not sa or not dev or dev.get("host"):
            return
        family = ctypes.string_at(sa, 2)[1]
        if dev["channel"] == "awdl" and family == socket.AF_INET6:
            addr = socket.inet_ntop(socket.AF_INET6, ctypes.string_at(sa, 28)[8:24])
            dev["host"] = f"[{addr}%awdl0]:{dev.pop('port')}"
        elif dev["channel"] == "lan" and family == socket.AF_INET:
            addr = socket.inet_ntop(socket.AF_INET, ctypes.string_at(sa, 16)[4:8])
            if addr.startswith("169.254."):             # link-local: the USB link, not the LAN
                return
            dev["host"] = f"{addr}:{dev.pop('port')}"
        else:
            return
        devices.append(dev)

    def on_resolve(_r, _f, ifi, err, _full, target, port, txt_len, txt, ctx):
        dev = found.get(ctx)
        if err or not dev or "port" in dev or dev.get("host"):
            return
        info = _txt(ctypes.string_at(txt, txt_len)) if txt_len else {}
        dev.update(id=info.get("id", ""), v=info.get("v", ""), port=socket.ntohs(port))
        proto = 2 if dev["channel"] == "awdl" else 1    # kDNSServiceProtocol_IPv6 / _IPv4
        ref = ref_t()
        if lib.DNSServiceGetAddrInfo(ctypes.byref(ref), _DNSSD_FLAGS, dev["ifi"], proto, target,
                                     cb_addr, ctypes.c_void_p(ctx)) == 0:
            refs.append(ref)

    def on_browse(_r, flags, ifi, err, name, typ, dom, _ctx):
        if err or not flags & 0x2:                       # kDNSServiceFlagsAdd
            return
        ctx = len(found) + 1
        found[ctx] = {"name": name.decode("utf-8", "replace"), "ifi": ifi,
                      "channel": "awdl" if awdl and ifi == awdl else "lan"}
        ref = ref_t()
        if lib.DNSServiceResolve(ctypes.byref(ref), _DNSSD_FLAGS, ifi, name, typ, dom,
                                 cb_resolve, ctypes.c_void_p(ctx)) == 0:
            refs.append(ref)

    cb_browse, cb_resolve, cb_addr = browse_t(on_browse), resolve_t(on_resolve), addr_t(on_addr)
    keep += [cb_browse, cb_resolve, cb_addr]
    browse = ref_t()
    if lib.DNSServiceBrowse(ctypes.byref(browse), _DNSSD_FLAGS, 0, b"_ictrl._tcp", None,
                            cb_browse, None) != 0:
        raise SystemExit("DNSServiceBrowse failed")
    refs.append(browse)
    deadline = time.time() + wait
    try:
        while time.time() < deadline:
            if want and any(want(d) for d in devices):
                break
            fds = {lib.DNSServiceRefSockFD(r): r for r in refs}
            ready, _, _ = select.select(list(fds), [], [], max(0.0, min(0.25, deadline - time.time())))
            for fd in ready:
                lib.DNSServiceProcessResult(fds[fd])
    finally:
        for r in refs:
            lib.DNSServiceRefDeallocate(r)
    return _dedupe(devices)


def _dedupe(devices: list[dict]) -> list[dict]:
    """One entry per device and channel (a LAN answer can arrive on several
    interfaces), sorted by name, LAN before AWDL."""
    seen, out = set(), []
    for d in devices:
        key = (d.get("id") or d["name"], d["channel"])
        if key in seen:
            continue
        seen.add(key)
        out.append({k: d[k] for k in ("name", "id", "host", "channel") if k in d})
    return sorted(out, key=lambda d: (d["name"].lower(), d["channel"] != "lan"))


def _dns_name(msg: bytes, i: int) -> tuple[str, int]:
    """A (possibly compressed) DNS name at offset i -> (name, offset after it)."""
    labels, jumped, end, hops = [], False, i, 0
    while True:
        n = msg[i]
        if n == 0:
            i += 1
            break
        if n & 0xC0 == 0xC0:                         # compression pointer
            hops += 1
            if hops > 32:                            # a pointer loop in a hostile packet
                raise ValueError("DNS name pointer loop")
            if not jumped:
                end = i + 2
            jumped = True
            i = ((n & 0x3F) << 8) | msg[i + 1]
            continue
        labels.append(msg[i + 1:i + 1 + n].decode("utf-8", "replace"))
        i += 1 + n
    return ".".join(labels), (end if jumped else i)


def _parse_mdns(msg: bytes, instances: dict, srv: dict, txt: dict, addrs: dict) -> None:
    """Collect PTR/SRV/TXT/A records of one mDNS response into the dicts.
    Raises IndexError/ValueError on a malformed packet."""
    counts = [int.from_bytes(msg[k:k + 2], "big") for k in (4, 6, 8, 10)]
    i = 12
    for _ in range(counts[0]):
        _, i = _dns_name(msg, i)
        i += 4
    for _ in range(sum(counts[1:])):
        rname, i = _dns_name(msg, i)
        if i + 10 > len(msg):
            raise IndexError("truncated record")
        rtype = int.from_bytes(msg[i:i + 2], "big")
        rdlen = int.from_bytes(msg[i + 8:i + 10], "big")
        rdata_at, i = i + 10, i + 10 + rdlen
        if i > len(msg):
            raise IndexError("truncated record data")
        if rtype == 12:                                  # PTR -> instance
            inst, _ = _dns_name(msg, rdata_at)
            if inst.endswith("._ictrl._tcp.local"):
                instances[inst] = inst.split("._ictrl._tcp", 1)[0]
        elif rtype == 33 and rdlen >= 7:                 # SRV -> port, target
            target, _ = _dns_name(msg, rdata_at + 6)
            srv[rname] = (int.from_bytes(msg[rdata_at + 4:rdata_at + 6], "big"), target)
        elif rtype == 16:                                # TXT
            txt[rname] = _txt(msg[rdata_at:rdata_at + rdlen])
        elif rtype == 1 and rdlen == 4:                  # A
            addr = socket.inet_ntoa(msg[rdata_at:rdata_at + 4])
            if not addr.startswith("169.254."):
                addrs.setdefault(rname, addr)


def _mdns_scan(wait: float, want=None) -> list[dict]:
    """LAN discovery without dns_sd (Linux and others): one mDNS question for
    _ictrl._tcp.local, asked from an ordinary port so responders answer by
    unicast (RFC 6762 §6.7), which needs no multicast group membership."""
    q = b"".join(bytes([len(p)]) + p.encode() for p in ("_ictrl", "_tcp", "local")) + b"\0"
    packet = b"\0\0\0\0\0\1\0\0\0\0\0\0" + q + b"\0\x0c\0\x01"      # PTR IN
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
    sock.settimeout(0.3)
    instances, srv, txt, addrs = {}, {}, {}, {}
    try:
        sock.sendto(packet, ("224.0.0.251", 5353))
    except OSError:
        return []
    deadline, last_send = time.time() + wait, time.time()
    devices: list[dict] = []
    while time.time() < deadline:
        if time.time() - last_send > 1.0:                # a second ask covers a lost packet
            sock.sendto(packet, ("224.0.0.251", 5353))
            last_send = time.time()
        try:
            msg, _ = sock.recvfrom(9000)
        except (socket.timeout, OSError):
            msg = None
        if msg and len(msg) > 12:
            try:
                _parse_mdns(msg, instances, srv, txt, addrs)
            except (IndexError, ValueError):
                pass                                     # malformed or hostile packet: skip it
        devices = []
        for inst, name in instances.items():
            if inst in srv and srv[inst][1] in addrs:
                info = txt.get(inst, {})
                devices.append({"name": name, "id": info.get("id", ""), "channel": "lan",
                                "host": f"{addrs[srv[inst][1]]}:{srv[inst][0]}"})
        if want and any(want(d) for d in devices):
            break
    sock.close()
    return _dedupe(devices)


def _nearby_cache(update: dict | None = None) -> dict:
    try:
        with open(NEARBY_CACHE) as fh:
            cache = json.load(fh)
    except (OSError, json.JSONDecodeError):
        cache = {}
    if update is not None:
        cache.update(update)
        os.makedirs(os.path.dirname(NEARBY_CACHE), exist_ok=True)
        with open(NEARBY_CACHE, "w") as fh:
            json.dump(cache, fh)
    return cache


def _matches(dev: dict, query: str) -> bool:
    q = query.lower()
    return dev["name"].lower() == q or (len(q) >= 4 and dev.get("id", "").startswith(q))


def nearby_target(query: str, fresh: bool = False) -> tuple[str, str, str]:
    """Resolve a nearby device by name or id prefix -> (device id, host, name)."""
    if not fresh:
        now = time.time()
        for dev_id, ent in _nearby_cache().items():
            if now - ent.get("ts", 0) < NEARBY_CACHE_TTL and _matches({"id": dev_id, **ent}, query):
                return dev_id, ent["host"], ent["name"]
    devices = nearby_scan(wait=6.0, want=lambda d: _matches(d, query))
    hits = [d for d in devices if _matches(d, query) and d.get("host")]
    if not hits:
        raise SystemExit(f"no nearby device matches {query!r} — run `scan`. On" + NO_NEARBY_HINT.split(" — on", 1)[1])
    if len({d["id"] for d in hits}) > 1:
        raise SystemExit(f"{query!r} matches several devices; use the id: "
                         + ", ".join(f"{d['name']} ({d['id'][:8]})" for d in hits))
    # The LAN when the device is on it (sorted first), else peer-to-peer Wi-Fi.
    dev = hits[0]
    _nearby_cache({dev["id"]: {"name": dev["name"], "host": dev["host"], "ts": time.time()}})
    return dev["id"], dev["host"], dev["name"]


def nearby_call(query: str, method: str, params: dict | None, client_name: str) -> dict:
    """Call a nearby device; pairs on first use (the user approves on the phone)
    and re-resolves once if the cached address has gone stale."""
    did, host, name = nearby_target(query)
    try:
        return device_call(host, method, params, device_id=did, pair_as=client_name, device_name=name)
    except OSError:                       # includes URLError / timeouts
        did, host, name = nearby_target(query, fresh=True)
        return device_call(host, method, params, device_id=did, pair_as=client_name, device_name=name)


# --------------------------------------------------------------------- X25519
#
# RFC 7748 X25519, so pairing needs nothing beyond the standard library. Uses
# `cryptography` when it is installed; otherwise a plain Montgomery ladder. The
# private key is single-use (one per pairing), so the pure-Python fallback's
# lack of constant-time arithmetic exposes nothing reusable.

_X25519_BASE = (9).to_bytes(32, "little")


def _x25519(scalar: bytes, u: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey, X25519PublicKey)
        from cryptography.hazmat.primitives import serialization
        priv = X25519PrivateKey.from_private_bytes(scalar)
        if u == _X25519_BASE:
            return priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        return priv.exchange(X25519PublicKey.from_public_bytes(u))
    except ImportError:
        pass
    p = 2**255 - 19
    k = bytearray(scalar)
    k[0] &= 248
    k[31] &= 127
    k[31] |= 64
    k = int.from_bytes(k, "little")
    x1 = int.from_bytes(u, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in reversed(range(255)):
        bit = (k >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a, b = (x2 + z2) % p, (x2 - z2) % p
        aa, bb = a * a % p, b * b % p
        e = (aa - bb) % p
        c, d = (x3 + z3) % p, (x3 - z3) % p
        da, cb = d * a % p, c * b % p
        x3 = (da + cb) ** 2 % p
        z3 = x1 * (da - cb) ** 2 % p
        x2 = aa * bb % p
        z2 = e * (aa + 121665 * e) % p
    if swap:
        x2, z2 = x3, z3
    return (x2 * pow(z2, p - 2, p) % p).to_bytes(32, "little")


# -------------------------------------------------------------------- pairing

def pair(host: str, client_name: str, plain: bool, timeout: float = 90.0,
         store_key: str | None = None) -> dict:
    """Pair with the device. BLOCKS until the user taps Allow on-screen."""
    url = f"http://{host}/pair"
    if plain:
        status, resp = _post(url, {"client_name": client_name, "plain": True}, timeout)
        if status != 200:
            raise SystemExit(f"pair failed ({status}): {resp}")
        key = bytes.fromhex(resp["token"])
    else:
        # X25519; the device wraps K against our public key.
        priv = secrets.token_bytes(32)
        pub = _x25519(priv, _X25519_BASE)
        print(f"key fingerprint: {hashlib.sha256(pub).hexdigest()[:8]}  "
              "(verify it matches the on-device prompt)", file=sys.stderr)
        status, resp = _post(url, {
            "client_name": client_name,
            "pub": base64.b64encode(pub).decode(),
        }, timeout)
        if status != 200:
            raise SystemExit(f"pair failed ({status}): {resp}")
        device_pub = base64.b64decode(resp["pub"])
        shared = _x25519(priv, device_pub)
        k_wrap = _hmac(shared, LABEL_PAIR + pub + device_pub)
        pad = _hmac(k_wrap, LABEL_WRAP)
        key = bytes(a ^ b for a, b in zip(bytes.fromhex(resp["token_ct"]), pad))

    record = {
        "tok": hashlib.sha256(key).digest()[:4].hex(),
        "key": key.hex(),
        "client_name": client_name,
        "expires": resp.get("expires"),
    }
    save_token(store_key or host, record)
    return record


# ------------------------------------------------------------------ transport

def _call_with(host: str, record: dict, method: str, params: dict | None,
               timeout: float, rpc_id: int) -> tuple[int, dict]:
    """One enveloped call with `record`'s key: (200, decrypted response) or
    (HTTP status, error body)."""
    key = bytes.fromhex(record["key"])
    tok = record["tok"]

    body = json.dumps({"jsonrpc": "2.0", "method": method,
                       "params": params or {}, "id": rpc_id}).encode()
    nonce = secrets.token_bytes(16)
    ts = int(time.time())

    k_enc = _hmac(key, LABEL_ENC_REQ + nonce)
    k_mac = _hmac(key, LABEL_MAC + nonce)
    ct = _keystream_xor(k_enc, nonce, body)
    signed = b"v1" + bytes.fromhex(tok) + ts.to_bytes(8, "big") + nonce + ct
    tag = _hmac(k_mac, signed)

    status, resp = _post(f"http://{host}/rpc", {
        "v": 1, "tok": tok, "ts": ts, "nonce": nonce.hex(),
        "ct": base64.b64encode(ct).decode(), "tag": tag.hex(),
    }, timeout)
    if status != 200:
        return status, resp

    # Response is sealed under the same nonce with the response-direction key.
    resp_ct = base64.b64decode(resp["ct"])
    expect = _hmac(k_mac, b"resp" + nonce + resp_ct)
    if not hmac.compare_digest(expect, bytes.fromhex(resp["tag"])):
        raise SystemExit("response MAC mismatch — discarding")
    k_enc_resp = _hmac(key, LABEL_ENC_RESP + nonce)
    return 200, json.loads(_keystream_xor(k_enc_resp, nonce, resp_ct))


def call(host: str, method: str, params: dict | None = None,
         timeout: float = 60.0, rpc_id: int = 1, store_key: str | None = None) -> dict:
    """One enveloped JSON-RPC call. Returns the decrypted response object.

    The key is the one stored for the device at `host` (see device_call);
    `store_key` instead names a record explicitly."""
    if not store_key:
        return device_call(host, method, params, timeout=timeout, rpc_id=rpc_id)
    record = load_token(store_key)
    if not record:
        raise SystemExit(f"no token for {store_key} — run `pair` first")
    status, out = _call_with(host, record, method, params, timeout, rpc_id)
    if status != 200:
        raise SystemExit(f"rpc failed ({status}): {json.dumps(out)}")
    return out


def _key_for(host: str, device_id: str | None) -> tuple[dict | None, str | None]:
    """(record, the older name it was found under or None) for this device."""
    if device_id:
        rec = load_token(device_store_key(device_id))
        if rec:
            return rec, None
        for older in (f"nearby:{device_id}", host):
            rec = load_token(older)
            if rec:
                return rec, older
        return None, None
    rec = load_token(host)                # server too old to name itself
    return rec, None


def device_call(host: str, method: str, params: dict | None = None, *,
                device_id: str | None = None, timeout: float = 60.0, rpc_id: int = 1,
                pair_as: str | None = None, device_name: str | None = None) -> dict:
    """Call the device at `host` with the key stored for that DEVICE.

    The device id comes from the caller (nearby discovery), the address cache
    or GET /whoami. Every response names the device that sent it; when that is
    not the one expected — another phone now behind this address — the cache
    is corrected and a refused call is retried once with the right key.
    `pair_as`: pair under this client name when there is no key yet."""
    did = device_id or device_id_for(host)
    switched = False
    for attempt in range(2):
        record, older = _key_for(host, did)
        if record is None:
            # Never pair because a response named another device: that header
            # is unauthenticated, and whoever answers at an address could
            # otherwise get this client to pair with it unasked.
            if not pair_as or switched:
                raise SystemExit(f"no key for the device at {host} — run `pair` first")
            print(f"pairing with {device_name or host} — approve the prompt on the phone", file=sys.stderr)
            record = pair(host, pair_as, plain=False,
                          store_key=device_store_key(did) if did else None)
            older = None
            if did:
                _remember_address(did, record, host, device_name)
        status, out = _call_with(host, record, method, params, timeout, rpc_id)
        answered = _answered_by[0]
        if answered and answered != did:
            _address_cache({host: answered})
            if status == 401 and attempt == 0:
                did = answered
                switched = True
                continue
            did = answered
        if status != 200:
            raise SystemExit(f"rpc failed ({status}): {json.dumps(out)}")
        # First success with a record kept under an older name, or from a new
        # address: store it as this device's key.
        if did and (older or (_addresses(record) or [None])[0] != host):
            _remember_address(did, record, host, device_name or record.get("device_name"))
        return out
    raise SystemExit("rpc failed: the device at this address changed twice")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1:8200")
    ap.add_argument("--nearby", metavar="NAME_OR_ID",
                    help="reach a discovered device by name or id instead of --host "
                         "(over the LAN, else peer-to-peer Wi-Fi on macOS)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scan", help="list devices with Nearby Discovery on (LAN everywhere; AWDL on macOS)")
    sc.add_argument("--wait", type=float, default=3.0, help="seconds to listen (default 3)")

    p = sub.add_parser("pair", help="pair with the device (blocks on approval)")
    p.add_argument("--name", default=os.uname().nodename)
    p.add_argument("--plain", action="store_true",
                   help="plaintext grant; localhost/USB only")

    c = sub.add_parser("call", help="make an RPC call")
    c.add_argument("method")
    c.add_argument("params", nargs="?", default="{}")

    sub.add_parser("list", help="list paired devices")

    s = sub.add_parser("shot", help="save a screenshot to a file")
    s.add_argument("path", nargs="?", default="screenshot.jpg")
    s.add_argument("--format", default="jpeg", choices=["jpeg", "png"])
    s.add_argument("--quality", type=float, default=0.6,
                   help="JPEG quality 0.1-1.0 (default 0.6); ignored for PNG")
    s.add_argument("--scale", type=float, default=2.0)

    args = ap.parse_args()
    client_name = os.uname().nodename

    def rpc(method: str, params: dict | None = None) -> dict:
        if args.nearby:
            return nearby_call(args.nearby, method, params, client_name)
        return call(args.host, method, params)

    if args.cmd == "scan":
        devices = nearby_scan(wait=args.wait)
        if not devices:
            print(NO_NEARBY_HINT)
        by_id: dict = {}
        for d in devices:
            by_id.setdefault(d["id"] or d["name"], []).append(d)
        for dev_id, ways in by_id.items():
            reach = ", ".join(f"LAN {d['host']}" if d["channel"] == "lan" else "nearby (AWDL)" for d in ways)
            paired = "  paired" if _key_for("", dev_id)[0] else ""
            print(f"{ways[0]['name']:28s} id={dev_id[:8]}  {reach}{paired}")
        return 0
    if args.cmd == "list":
        hosts = list_hosts()
        if not hosts:
            print("no paired devices — run `pair` first")
        devices = {h: r for h, r in hosts.items() if h.startswith("device:")}
        for h, r in sorted(devices.items(), key=lambda kv: kv[1].get("device_name", "")):
            seen = ", ".join(_addresses(r)[:3])
            print(f"{r.get('device_name') or '?':24s} id={h.split(':', 1)[1][:8]}  tok={r['tok']}  {seen}")
        older = {h: r for h, r in hosts.items() if not h.startswith("device:")}
        if older:
            print("by address (older entries; moved to their device on next use):")
        for h, r in sorted(older.items()):
            name = r.get("device_name") or r.get("client_name", "")
            print(f"  {h:24s} tok={r['tok']}  {name}")
    elif args.cmd == "pair":
        if args.nearby:
            did, host, name = nearby_target(args.nearby)
        else:
            host = args.host
            info = whoami(host)
            did, name = (info["device_id"], info.get("name")) if info else (None, None)
            if did:
                _address_cache({host: did})
        rec = pair(host, args.name, args.plain and not args.nearby,
                   store_key=device_store_key(did) if did else None)
        if did:
            _remember_address(did, rec, host, name)
        print(f"paired — tok={rec['tok']} {name or host} (key cached in {STORE}"
              + (f" for device {did[:8]})" if did else ")"))
    elif args.cmd == "shot":
        params = {"format": args.format, "scale": args.scale}
        if args.format == "jpeg":
            params["quality"] = args.quality
        t0 = time.time()
        result = rpc("screenshot", params).get("result", {})
        if "data" not in result:
            print(f"screenshot failed: {json.dumps(result, ensure_ascii=False)}")
            return 1
        blob = base64.b64decode(result["data"])
        with open(args.path, "wb") as fh:
            fh.write(blob)
        # Print the point-space and scale too, not just the pixel size. A caller
        # looking at the saved image only sees its pixel dimensions, and guessing
        # the divisor from device_scale is wrong whenever the shot was
        # downscaled: a 1206x2622 screen saved at scale 2 is an 804x1748 file, so
        # dividing by 3 puts a tap ~200pt off target.
        px_w = int(result.get("pixel_width", 0))
        px_h = int(result.get("pixel_height", 0))
        pt_w = int(result.get("point_width", 0))
        pt_h = int(result.get("point_height", 0))
        sc = result.get("scale", 0)
        print(f"{args.path}  {len(blob):,} B  {result.get('format')}  "
              f"{px_w}x{px_h}px  ->  {pt_w}x{pt_h}pt  (scale {sc}: tap_x = px/{sc}, tap_y = py/{sc})  "
              f"{(time.time() - t0) * 1000:.0f}ms end-to-end")
    else:
        out = rpc(args.method, json.loads(args.params))
        print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
