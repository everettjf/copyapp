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
was performed in that early inventory. Guest permissions were granted later;
the named live snapshot results below remain separate from this historical case.

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

## Bound the collector's file polling around snapshots

New collector builds advertise optional `quiesce` support. After the input-lease
preflight succeeds, snapshot take/restore asks that collector to pause its own
shared-filesystem polling for 30 guest-clock seconds, then submits the VM operation
once. The collector closes its acknowledgment before pausing; it resumes polling
automatically after the bound. The host retains its exclusive bridge lock and
rotates to a fresh epoch as before. Interrupted calls still require inspection.

The case records `before/quiesce.json` and binds the request, acknowledgment,
collector instance and pre-snapshot session. It records
`collector_polling_quiesced: true` and `all_guest_file_io_quiesced: false`. This
does not quiesce Finder, other processes or external services. The mitigation
targets a hypothesis about in-flight shared-filesystem I/O; passing local protocol
tests alone cannot establish that it fixes live VM resume. Historical collectors
and cases without this advertised capability retain their existing semantics.

A separate unlocked-host diagnostic at
`output/macos-snapshot-unlocked-20261021/` obtained a successful snapshot RPC and
full post-take images retaining the synthetic unsaved text and Wrapping Off. Its
collector reconnection nevertheless timed out, and Finder could not finish opening
the bridge directory. The case stays failed, no restore was submitted, and no
snapshot input was repeated. A temporary readonly nonce share did not visibly
resolve the problem and was removed. After observed normal editor cleanup, normal
guest restart and relaunch of the unchanged verified collector restored health.
This supports visual preservation in that experiment, not a complete snapshot
acceptance or a proven quiescence fix.

A wider, bounded query of the Virtualization service for the original failed
operation found a `NSOSStatusErrorDomain` `-25308` decryption failure at
15:48:19 PDT. Apple's [error definition](https://developer.apple.com/documentation/security/errsecinteractionnotallowed)
means security-service interaction was not allowed. Host lock observations from
that development run make lock-related key access a hypothesis; the exact cause
and exact-instant lock state remain unproven. No keychain or secret contents were
read or altered. Raw diagnostic messages remain local.

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

Replay retains `failed-mcp-request.json` when a ChatComputer call fails: the
transport ID, server identity, exact JSON-RPC request and last received response
(or null when none arrived). This is separate from cleanup failure evidence, so a
failed release cannot replace the interrupted input's diagnostic. Its failed
case records `completion_unknown`, `needs_inspection` and `action_retried: false`.
ChatComputer's unstructured error replies can represent either a refusal before
dispatch or a failure after dispatch. For input/file/VM mutations, Copy APP treats
such a reply as an unknown outcome, closes that MCP transport and does not infer
non-execution from its text. Read-only errors do not assert an unknown mutation.

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
local collector; no actual VM disk/memory was restored in those tests.

On the named macOS 27.0.1 guest, the first actual take saved its snapshot but the
collector's new shared-file session timed out. Both failed attempts remain under
`cases/macos-p0-20261021/snapshot-take-live-{1,2}`. A GUI refresh of the bridge
directory restored health without restarting the collector; session rotation alone
did not resolve the failure. The collector now enumerates that directory before
reading the host's atomically replaced active epoch. This changes no request ID,
start marker or retry rule.

With the new pinned collector, `snapshot-take-directory-refresh-1` and
`snapshot-restore-directory-refresh-1` in that same local directory verified actual
save/restore metadata and fresh MCP/collector sessions, with one retained safety
snapshot on restore. This is evidence for this named VM and build. App-state
restoration, live takeover/interrupted input and all paired sample comparisons
remain separate acceptance requirements; the operation still records
`behavior_restoration_verified: false` and `shared_data_reset: false`.

The named guest also has a controlled reply-loss diagnostic at
`cases/macos-live-response-loss-20261021/`. Its local harness submits one real
`type` request to the pinned ChatComputer/collector environment, withholds the
matching genuine successful reply at the client receive boundary, and closes
that MCP process. Production replay saves `interrupted-playbook-1` with a null
last response, `completion_unknown`, `needs_inspection` and `action_retried: false`;
`verify` rejects it as incomplete. The harness retains the withheld envelope
separately rather than adding it to the failed production case. A fresh collector
session's verified `post-loss-readonly-observation-1` shows exactly one copy of the
probe text, and its complete screenshot was opened. Only after that inspection,
`observed-normal-exit-1` asserts the observed text and quits normally. The input
was never repeated. This tests controlled post-dispatch reply loss against a real
guest; it does not establish human-takeover behavior, an unplanned network failure
or snapshot App-state restoration. The diagnostic harness is local evidence and
does not alter production transport code.

A later live App-state probe found a failure, retained at
`cases/macos-fixture-snapshot-behavior-20261021/`. Its verified `baseline-1`
contains unsaved `Alpha β` / emoji text and Wrapping Off in the independent editor.
`snapshot-take-1` created the uniquely requested manual snapshot
`3BF59B3B-6B33-451E-883B-282BCD5B9303`, but returned an agent-disconnected error.
It remains a failed unknown-completion case and is rejected by `verify`; it was
not retried or converted into a successful take. The separate verified metadata
inventory matches its exact requested name, addition, current ID and ancestry.
No restore was submitted.

The desktop subsequently became ready. The collector needed an explicit relaunch
through its same verified deployment; a fresh probe and `environment-3` recheck
the same guest and retained Accessibility grant. The unchanged editor binary
has a new PID/start time and a blank document with Wrapping Off, as shown by the
verified acquisition, identity and `post-take-ui-inspection-1` full screen/AX.
The unsaved test text was not preserved. These observations are consistent with
a cold restart; the precise saved-state resume failure is unconfirmed.
`post-take-observed-cleanup-1` asserts that observed state, resets On and exits
normally. See `snapshot-app-state-findings.json` for exact source and image hashes.

That historical App-state attempt remains failed. Save needed work before snapshot
operations and use discardable fixture state for recovery experiments. A metadata
record with `memoryBytes` is insufficient evidence of memory or App-state restoration.

## Named quiesced App-state observation

A later experiment under `output/macos-quiesced-snapshot-20261021/` uses the exact
upgraded collector `f6356939…` with measured guest Accessibility access. Its
`environment-1`, `baseline-1`, `snapshot-take-1`, `post-take-ui-1`,
`mutated-state-2`, `snapshot-restore-1`, `post-restore-ui-1` and
`restored-cleanup-1` verify. The take is
`CC589797-EC03-4E2D-B98F-2198E960EF25`; restore preserves safety snapshot
`F55D3D5B-EF73-4E53-9955-E6C955764DB6`.

The unchanged editor process (PID 1997 and identical start time/hash) retains its
unsaved Unicode text and Wrapping Off after take. The intervening playbook changes
the text and sets Wrapping On. Restore returns the original text, 14-character /
four-word status and Wrapping Off, with fresh MCP/collector epochs and unchanged
collector instance. Full cited screens and structured AX were reviewed. Final
normal input resets wrapping On and quits; the stopped-process assertion passes.
The initial mutation's disabled AX text-area selection was rejected before input;
its failure remains preserved, and the revised coordinate script followed actual
state inspection. See `snapshot-app-state-review.json` and its companion report
for the 26 source/image hashes.

This is a separate manual App-state conclusion for one document and one named
take/restore cycle. The operation cases still describe metadata/reconnect only,
with their existing false behavior and disk/memory-verification flags. Quiescence
is limited to the collector's polling and does not establish all-guest I/O safety,
shared-folder rollback, universal reliability or the cause of earlier failures.
Those failed cases are unchanged.

The checked upstream implementation is revision
`c774a4ceadc7dc17a589a1de8f5a40fe36c2a649`:
[tool arguments](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/ComputerControl/ControlCommand.swift),
[external control and lease handling](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Apps/ChatComputer/ExternalControl.swift),
[snapshot lifecycle](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/VMKit/VirtualMachineController.swift),
[stored snapshot/state format](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/VMKit/SnapshotStore.swift).
