#!/usr/bin/env python3
"""Measure the screenshot and find_element optimizations against a real device.

Two things are compared, each against the code path it replaced:

  screenshot  PNG (the old default) vs JPEG (the new one), same screen, same
              scale. Reports wire bytes and the client's envelope-decrypt time
              alongside the device-side encode time, because response SIZE — not
              device time — is what dominates a screenshot end to end.

  locate      A deliberately WRONG label, which is the expensive path: it used
              to run exact/id/contains as three separate accessibility queries
              (~3s each) before falling back to a snapshot anyway. Now one
              snapshot answers all three. A correct label is timed too, to prove
              the fast path didn't regress.

Crypto and transport are imported from ictrl_rpc so this can't drift from the
real client.

Usage:
    ./ictrl_bench.py --host 10.0.0.5:8200                     # full run
    ./ictrl_bench.py --host 10.0.0.5:8200 --label "let's talk!"
    ./ictrl_bench.py --host 10.0.0.5:8200 --probe-only        # reachability only
"""
from __future__ import annotations

import argparse
import base64
import json
import socket
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import ictrl_rpc as rpc  # noqa: E402  (path set above)


def probe(host: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Is anything listening, and does it look like iCTRL?"""
    hostname, _, port = host.partition(":")
    port = int(port or 8200)
    try:
        with socket.create_connection((hostname, port), timeout=timeout):
            pass
    except OSError as e:
        return False, f"no TCP connection to {host} ({e.__class__.__name__}: {e})"
    try:
        with urllib.request.urlopen(f"http://{host}/", timeout=timeout) as r:
            body = (r.read(400) or b"").decode("utf-8", "replace")
        if "iCTRL" in body or "jsonrpc" in body.lower():
            return True, "iCTRL server responding"
        return True, "port open, but the response doesn't look like iCTRL"
    except Exception as e:  # noqa: BLE001 — any failure is just "not usable yet"
        return False, f"port open but HTTP failed ({e.__class__.__name__}: {e})"


def timed_call(host: str, method: str, params: dict, timeout: float = 60.0):
    """One RPC, returning (result, wall_ms, error_or_None)."""
    t0 = time.perf_counter()
    try:
        out = rpc.call(host, method, params, timeout=timeout)
    except SystemExit as e:
        return None, (time.perf_counter() - t0) * 1000, str(e)
    wall = (time.perf_counter() - t0) * 1000
    if "error" in out:
        return None, wall, json.dumps(out["error"], ensure_ascii=False)
    return out.get("result", {}), wall, None


def decrypt_ms(payload_len: int, reps: int = 3) -> float:
    """Cost of running `payload_len` bytes through the envelope keystream.

    Uses the same primitive as the real client, so this is the work a client
    actually performs on a response of this size.
    """
    body = b"\x00" * payload_len
    key, nonce = b"k" * 32, b"n" * 16
    best = float("inf")
    for _ in range(reps):
        t0 = time.perf_counter()
        rpc._keystream_xor(key, nonce, body)
        best = min(best, (time.perf_counter() - t0) * 1000)
    return best


def bench_screenshot(host: str, reps: int) -> list[dict]:
    """PNG vs JPEG on the same screen. Interleaved so drift hits both equally."""
    print("\n" + "=" * 72)
    print("SCREENSHOT — PNG (old default) vs JPEG (new default)")
    print("=" * 72)

    variants = [
        ("png",        {"format": "png",  "scale": 2}),
        ("jpeg q0.6",  {"format": "jpeg", "scale": 2, "quality": 0.6}),
        ("jpeg q0.4",  {"format": "jpeg", "scale": 2, "quality": 0.4}),
    ]
    samples: dict[str, list[tuple[float, int]]] = {n: [] for n, _ in variants}

    for i in range(reps):
        for name, params in variants:
            result, wall, err = timed_call(host, "screenshot", params)
            if err:
                print(f"  ✗ {name}: {err}")
                continue
            data = result.get("data", "")
            # `bytes` is the encoded image; the wire body is that base64'd.
            raw = int(result.get("bytes") or 0) or len(base64.b64decode(data or ""))
            samples[name].append((wall, len(data) or raw * 4 // 3))
        print(f"  round {i + 1}/{reps} done")

    rows = []
    print(f"\n  {'variant':12} {'wire B':>10} {'rpc ms':>9} {'decrypt ms':>11}")
    print("  " + "-" * 46)
    base_wire = base_dec = None
    for name, _ in variants:
        got = samples[name]
        if not got:
            continue
        wall = statistics.median(w for w, _ in got)
        wire = int(statistics.median(b for _, b in got))
        dec = decrypt_ms(wire)
        if name == "png":
            base_wire, base_dec = wire, dec
        rows.append({"variant": name, "wire": wire, "rpc_ms": wall, "decrypt_ms": dec})
        print(f"  {name:12} {wire:10,} {wall:9.0f} {dec:11.1f}")

    if base_wire:
        print("\n  vs PNG:")
        for r in rows:
            if r["variant"] == "png":
                continue
            print(f"    {r['variant']:12} {base_wire / r['wire']:5.2f}x smaller   "
                  f"{base_dec / max(r['decrypt_ms'], 1e-6):5.2f}x faster to decrypt")
    return rows


def parse_locate_line(line: str) -> dict:
    """Pull the phase breakdown out of a `🔎 locate ...` log line."""
    phases = {}
    inside = line[line.find("[") + 1:line.find("]")] if "[" in line else ""
    for part in inside.split():
        key, _, val = part.partition("=")
        phases[key] = val
    total = ""
    if "total=" in line:
        total = line.split("total=")[-1].strip()
    return {"phases": phases, "total": total}


def bench_locate(host: str, good_label: str | None, bad_label: str, reps: int) -> None:
    print("\n" + "=" * 72)
    print("FIND_ELEMENT — the miss path is what got 4.7x faster")
    print("=" * 72)

    cases = [("miss (wrong label)", bad_label, "contains")]
    if good_label:
        cases.append(("hit (correct label)", good_label, "contains"))

    for name, label, mode in cases:
        walls = []
        for _ in range(reps):
            _, wall, err = timed_call(host, "find_element",
                                      {"element_id": label, "match": mode}, timeout=90)
            walls.append(wall)
            if err and "No element matching" not in err and "not found" not in err.lower():
                print(f"  note: {name} returned: {err[:160]}")
        print(f"\n  {name}: label={label!r}")
        print(f"    client wall: median {statistics.median(walls):.0f}ms "
              f"(min {min(walls):.0f} / max {max(walls):.0f}, n={len(walls)})")

    print("\n  Device-side phase breakdown (from GET /logs):")
    for line in fetch_locate_lines(host)[-len(cases) * reps:]:
        p = parse_locate_line(line)
        if p["phases"]:
            print(f"    {p['phases']}  total={p['total']}")


def fetch_locate_lines(host: str) -> list[str]:
    """`🔎 locate` lines from the log, via a single-use stream ticket."""
    try:
        out = rpc.call(host, "stream_ticket", {})
        ticket = out.get("result", {}).get("ticket")
        if not ticket:
            return []
        with urllib.request.urlopen(f"http://{host}/logs?ticket={ticket}", timeout=20) as r:
            body = (r.read() or b"").decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  (couldn't fetch logs: {e})")
        return []
    return [ln for ln in body.splitlines() if "locate" in ln]


def timing_summary(host: str) -> None:
    print("\n" + "=" * 72)
    print("TIMING SUMMARY (device-side, from GET /logs)")
    print("=" * 72)
    try:
        out = rpc.call(host, "stream_ticket", {})
        ticket = out.get("result", {}).get("ticket")
        with urllib.request.urlopen(f"http://{host}/logs?ticket={ticket}", timeout=20) as r:
            body = (r.read() or b"").decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  couldn't fetch: {e}")
        return
    if "=== Timing summary" in body:
        print(body.split("=== Timing summary (ms) ===")[-1].strip()[:2000])
    else:
        print("  (no timing summary in the log yet)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1:8200")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--label", help="a label that EXISTS on screen (fast-path check)")
    ap.add_argument("--bad-label", default="Zzz No Such Element Zzz",
                    help="a label that does NOT exist (drives the expensive path)")
    ap.add_argument("--probe-only", action="store_true",
                    help="just check reachability and exit")
    args = ap.parse_args()

    print(f"probing {args.host} …")
    ok, why = probe(args.host)
    print(("  ✅ " if ok else "  ❌ ") + why)
    if not ok:
        print("\nDevice not reachable — install and start the runner, then re-run:")
        print(f"  ./Scripts/ictrl_bench.py --host {args.host}")
        return 1
    if args.probe_only:
        return 0

    if not rpc.load_token(args.host):
        print(f"\n❌ no cached key for {args.host} — pair first:")
        print(f"  ./Scripts/ictrl_rpc.py --host {args.host} pair --name bench")
        return 1

    info, _, err = timed_call(args.host, "device_info", {})
    if err:
        print(f"❌ device_info failed: {err}")
        return 1
    caps = info.get("capabilities", [])
    print(f"\ndevice: {info.get('device_name')}  server {info.get('server_version')}")
    for need in ("screenshot_jpeg", "reset", "nonui_lane"):
        print(f"  {'✅' if need in caps else '❌'} {need}")
    if "screenshot_jpeg" not in caps:
        print("\n❌ this build predates the optimizations — install the new runner first.")
        return 1

    bench_screenshot(args.host, args.reps)
    bench_locate(args.host, args.label, args.bad_label, args.reps)
    timing_summary(args.host)
    return 0


if __name__ == "__main__":
    sys.exit(main())
