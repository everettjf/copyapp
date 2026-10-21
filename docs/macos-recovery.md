# Mac snapshots, interrupted operations and reconnects

This development workflow uses the pinned ChatComputer public snapshot tools.
Copy APP never swaps VM disks itself, deletes snapshots, reads pairing secrets or
disables safety saves. These commands apply to the explicitly registered virtual
Mac; they are unrelated to iOS USB identities or physical-Mac snapshots.

## Inspect public metadata without changing the VM

```sh
.venv/bin/copyapp mac snapshot-inspect \
  --vm-directory "$HOME/.chatcomputer/ChatComputer.vm" \
  --out cases/mac-snapshot-inventory
.venv/bin/copyapp verify cases/mac-snapshot-inventory
```

This records the public VM identity files and bounded snapshot/state JSON metadata.
It reads no disk image, saved-memory file, credentials or pairing token. It can run
before guest control permissions are ready; a complete metadata case does not make
the guest ready. Incomplete staging directories, an interrupted restore and a
current ID with no valid snapshot remain inspectable facts, not repaired states.
Mutation commands refuse those conditions or missing ancestry.

The named development inventory at
`cases/macos-p0-20261021/snapshot-inventory-1` verified the actual VM at
`agentInstalled`, with zero snapshots and no restore in progress. No take/restore
was performed. The existing guest permission question remains unanswered.

## Take a reviewed baseline

Finish normal ChatComputer setup and deploy/register the verified collector first.
Choose a quiet test VM and inspect its desktop. Then:

```sh
.venv/bin/copyapp mac snapshot-take --environment cases/mac-environment \
  --out cases/mac-baseline-snapshot
.venv/bin/copyapp verify cases/mac-baseline-snapshot
```

The command checks the exact pinned VM, ChatComputer executable and collector.
It obtains status/screenshot/health, then uses a normal input-lease request
(`move 0,0`) before the snapshot. An already active human takeover rejects that
request before `snapshot_take` is submitted. Copy APP generates a unique name and
submits the snapshot action once. It resolves the full resulting UUID from stable
public snapshot metadata, rather than treating the tool's prose as exact identity.
An upstream initial snapshot may also appear on the first operation.

After the action, Copy APP closes the old MCP connection, rotates the collector
session while retaining its exclusive host lock, and obtains fresh status,
screenshot and health through a new MCP connection. Old request/output files are
preserved. Metadata, guest/OS/build identity and both sessions are source-linked
into the case. A memory restore can retain the same collector instance UUID;
instance change is recorded rather than asserted as a requirement.

## Restore a pinned Copy APP snapshot with a safety save

```sh
.venv/bin/copyapp mac snapshot-restore --snapshot cases/mac-baseline-snapshot \
  --out cases/mac-restored
.venv/bin/copyapp verify cases/mac-restored
```

Restoration requires a verified `snapshot-take` case and unchanged target metadata
in that exact VM. Copy APP submits the full UUID with `save_current: true`. There
is no no-save option. Verification requires one newly retained safety snapshot,
correct ancestry, the selected final current ID, unchanged previous snapshots,
fresh MCP/collector sessions and the pinned guest identity. It does not hash the
saved disk or memory, or certify that an App returned to the intended state.

Snapshots exclude host shared inbox/outbox contents and external services. Copy
APP does not delete/reset shared files; use fresh run IDs and output paths after
restoration. Acquire/recheck the installed App package, inspect the new screenshot
and assert its initial UI state before further input. Validate persistence and
outputs with actual playbooks; a reconnect is not a behavior comparison.

## Takeover and unknown results

The snapshot API has **no atomic expected-input-lease condition**. The preflight
move detects an existing takeover but cannot close a race where someone takes
over immediately before the queued snapshot command. The case explicitly records
`takeover_guard: preflight_input_lease_only` and
`atomic_takeover_exclusion_verified: false`. This limitation is separate from
normal key/mouse input, for which ChatComputer checks its lease. Keep snapshot
work on a quiet dedicated test VM; do not programmatically hand back human control.

A timeout, disconnect or an error after snapshot commitment does not prove that
the operation did nothing. Copy APP saves the failed MCP request/reply, any
available current metadata and a `needs_inspection` diagnostic. It never repeats
the action, resumes it automatically, or reconnects merely to send cleanup input.
Failed cases are retained and are not accepted by `verify` as completed operations.

Inspect the GUI and use a new read-only inventory after an uncertain result.
Review the full IDs, the proposed unique name in the failed request and any new
safety snapshot. Re-establish exact collector/guest and App state before a new
explicit operation. Do not treat the failed case as a successful take case, and
do not repeat an interrupted input just because a connection was re-opened.

## Evidence boundary

The complete operation scope is `snapshot_metadata_and_reconnect`, with
`behavior_restoration_verified`, `shared_data_reset` and
`disk_or_memory_bytes_verified` all false. Hashes establish saved evidence
consistency, not the truth of a UI interpretation or hidden VM state. The current
snapshot transition/reconnect tests use a simulated metadata controller and a real
local collector; no actual VM disk/memory was restored in those tests. Live
takeover, interrupted connection, restored App/data state and all paired sample
comparisons remain acceptance requirements.

The checked upstream implementation is revision
`c774a4ceadc7dc17a589a1de8f5a40fe36c2a649`:
[tool arguments](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/ComputerControl/ControlCommand.swift),
[external control and lease handling](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Apps/ChatComputer/ExternalControl.swift),
[snapshot lifecycle](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/VMKit/VirtualMachineController.swift),
[stored snapshot/state format](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/VMKit/SnapshotStore.swift).
