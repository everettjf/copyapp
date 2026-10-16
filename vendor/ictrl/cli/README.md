# ictrl — static CLI client

A single static `aarch64-linux-musl` binary speaking the iCTRL v1 envelope
protocol. Built for the Minis sandbox, whose Alpine minirootfs ships no
`python3`: the reference client there costs an `apk add` (network round-trip,
~50MB) before the first call, then pays interpreter startup on every invocation
through an emulated syscall layer over a SQLite-backed filesystem.

Measured: **5.4ms per invocation vs 47ms** for `python3` just importing the
stdlib modules the reference client needs.

## Build & test

Both happen inside Alpine 3.21 arm64 — the same distro, arch and libc as the
target — so "it compiles" and "it runs there" are the same check.

```sh
make build   # → ./ictrl  (static, ~130KB)
make test    # runs the crypto known-answer tests in the target environment
make shell   # poke around in the build image
```

## Why the crypto is hand-rolled

SHA-256, HMAC and X25519 are implemented here rather than linked from OpenSSL
because the binary must run with no package installs and no dynamic loader.
That makes `selftest.c` load-bearing: a subtle bug would not announce itself, it
would surface as an auth failure or, worse, silently wrong plaintext. It checks
RFC 4231 HMAC vectors, RFC 7748 X25519 vectors, and a length sweep that catches
padding bugs at block boundaries — the class of bug that fixed vectors miss.

## Usage

```sh
sh ictrl.sh pair                       # tap Allow on the device
sh ictrl.sh call device_info
sh ictrl.sh call tap '{"x":100,"y":200}'
sh ictrl.sh shot screen.jpg
```

Invoke via `sh ictrl.sh`, not `./ictrl`: skill installers write files 0644, so
the binary arrives without an exec bit. The wrapper runs under `sh` (which needs
none) and fixes the mode on first use.

Keys live in `~/.ictrl/token.json` — the same file and format the Python client
uses, so the two are interchangeable. They are stored per device
(`device:<id>`, the id from the device's `GET /whoami`), so a phone paired once
is reachable over USB, the LAN and nearby without pairing again; keys an older
client stored under an address are picked up and moved on first use.

## Nearby devices (macOS)

On a Mac the same source builds natively and gains nearby discovery: reaching a
phone over Apple peer-to-peer Wi-Fi when the two are not on the same network.
The phone must have *Nearby Discovery* turned on (its notification or the iCTRL
app; it needs Remote Access) and Wi-Fi switched on, though not joined to a
network. The C CLI lists AWDL devices only; the Python client's `scan` also
finds the phone on the LAN.

```sh
cc -O2 -std=c11 -o ictrl main.c sha256.c x25519.c util.c nearby.c
./ictrl scan                                  # nearby devices: name and id
./ictrl --nearby "iPhone 15 (7f3a)" call device_info
./ictrl --nearby 7f3a shot screen.jpg         # an id prefix works too
```

The first call to a device pairs with it (approve the prompt on the phone once).
If macOS Local Network privacy refuses the connection, the CLI relays it through
the system's `/usr/bin/nc -A`. `nearby.c` uses the system dns_sd API and is not
part of the Linux build.
