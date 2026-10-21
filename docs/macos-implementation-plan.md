# macOS support implementation and acceptance plan

This is an implementation plan, not a claim of released macOS support. Keep the
published iOS v0.1.2 commands, USB transports, historical cases and verification
semantics working. Add macOS alongside iOS; do not reinterpret a Mac as an iPhone.

## Architecture

The current coding agent owns discovery, semantic review and independent source
implementation. Copy APP owns cases and acceptance. ChatComputer owns the virtual
Mac, computer input, screenshots and snapshots. A bounded Copy APP collector in
the guest supplies exact app/process identity and structured acquisition. Do not
launch another coding agent or ChatComputer's built-in model loop.

Pin the installed ChatComputer build. Its current MCP returns text and images,
not structured AX objects. Do not parse prose into identity assertions. The guest
collector must supply Bundle ID, executable path/hash, process and window identity.
Use a run-scoped request/result exchange through the existing shared folders if
P0 verifies atomic writes and recovery. Never depend on upstream's planned shell
API. Read neither ChatComputer credentials nor guest pairing secrets.

macOS cases use schema version 2 and explicit `platform: macos` and execution
environment. iOS v1 cases retain their existing validators. A static package index
does not prove installation, launch, UI behavior or binary runtime provenance.
Every new case kind needs a semantic validator; unknown Mac kinds must fail.

## Scope

First acceptance environment: Apple Silicon macOS 27 host and macOS 27 guest,
ChatComputer v0.9.11 (record actual version and hash). Native arm64 AppKit/SwiftUI
apps; universal bundles retain full-file and selected-slice hashes. Begin with
independent `.app`, ZIP and DMG distribution. No initial promise for Intel/Rosetta,
encrypted store packages, drivers, system extensions, hardware-dependent or
account/payment workflows. Electron behavior compatibility is a later named test.

UI/static/file evidence produces a **behavior analysis** report, never an
unsupported deep function report. Optional Frida/Ghidra/Hopper evidence is a
separate capability and cannot be invented to satisfy a gate.

## Work and evidence ledger

| Stage | Required work | Acceptance evidence | State |
| --- | --- | --- | --- |
| P0 | Pin ChatComputer; ready desktop, input lease, screenshots, coordinates; file exchange; exact identity; snapshot recovery | Live probe cases, including failures; restart must not accept stale results | In progress |
| P1 | `copyapp mac` CLI; target/environment identity; versioned cases and validators; old iOS compatibility | Positive cases and negative tampering/cross-platform tests; baseline and final iOS suite | In progress |
| P2 | Guest collector; app/package/data acquisition; AX/window observations; bounded playbooks | Same-name app rejection, ambiguous element rejection, output and persistence assertions | In progress |
| P3 | Discovery, reviewed report/specification, coverage plan, agent task, host build, guest install, paired check, visual review, delivery | End-to-end source-linked cases with explicit scope and remaining differences | In progress |
| P4 | Control takeover, interrupted action, reconnect, snapshot restore, time and data resets | No blind action retries; new run/session identity; rejected old results | In progress |
| P5 | Agent-first bilingual docs, wheel resources, examples and clean installation | Installed-wheel checks; two sample applications and one physical Mac recheck | In progress |
| M2 | Optional runtime/native function investigation | Debug fixture first, then named third-party build; report actual entitlement limits | Pending |

First-stage effort estimate is 13–20 developer days, revised after P0. This is not
a deadline or a reason to reduce scope. No tag/release until acceptance completes.

## Required evidence model

### Development evidence recorded on 2026-10-21

- Branch: `codex/macos-chatcomputer-support`.
- Existing iOS baseline: 346 tests passed before modifications.
- Separate `copyapp mac` commands now cover doctor, inspect, build/prepare-collector,
  connect, observe, acquire, playbook, report, rebuild-plan, build-app, install,
  check-plan, rebuild-check, visual-review, delivery, share-probe,
  share-probe-check, import-app, discover-check, data-file and data-schema, with versioned
  `mac_*` semantic validators. These are development commands, not completed
  end-to-end reconstruction or a new release.
- Local TextEdit package snapshot passed its byte/identity verifier after a
  protected-system-flag copying failure was retained and the byte-copy path fixed.
- The bounded Swift collector compiled and passed code-signature verification,
  self-test and a **local filesystem** request/response probe. This is not guest
  acceptance. The local probe does not request Accessibility or screen permissions.
- Local integration tests exercise package export and exact source linking, followed
  by simulated UI replay, output assertions, reviewed report/specification and a
  frozen rebuild task. Rehashed input/script, citation, function-analysis and coverage
  tampering is rejected. Lost input replies are not retried. No simulated desktop
  or local helper test counts as live guest behavior evidence.
- Build/install development now includes actual Swift and Xcode fixture builds,
  code-signature checks, source snapshots and a local bounded-collector install into
  an isolated test directory. Existing targets are refused without mutation; source,
  log, recipe and install-receipt tampering is rejected. The test's simulated VM
  registration does not turn this local filesystem test into a guest or physical-Mac
  behavior result. Failed compiler, Xcode and installation diagnostics are retained
  under ignored `cases/macos-build-install-debug*-20261021/`.
- Full regression: 369 tests passed, including the existing iOS tests. The installed
  wheel check passed with the collector source and new Mac CLI entry points;
  development wheel SHA-256:
  `a19a73d2350c87f606a9e8e10b7a55a38d2b590db1565bbc70b0e8aea7a699d4`.
  Logs: `/tmp/copyapp-dual-platform-report-20261021.log` and
  `/tmp/copyapp-macos-report-wheel-20261021.log`. This is a local development wheel,
  not a published v0.1.2 artifact or a new release.
- Build/install regression: 373 tests passed, including real local Swift and Xcode
  builds and refusal to replace an installed fixture. The isolated wheel check
  includes `build-app` and `install`; development SHA-256:
  `24e364561c4d0317259eae38636b160153634d3db869e12ad7ea370989a52970`.
  Logs: `/tmp/copyapp-dual-platform-build-install-20261021.log` and
  `/tmp/copyapp-macos-build-install-wheel-20261021.log`. No iOS device execution
  path changed in this stage; these tests do not add a new named-device result.
- Paired-delivery regression: 376 tests passed. The simulated desktop runs one
  selected flow on both sides for three rounds, checks all 24 screenshot pairs,
  retains a minor judgment despite zero pixel error and binds explicit capability
  decisions to the installed source. Missing review, major differences, unknown
  starting states, source drift, forged counts/metrics/coverage and changed UI
  settings are rejected. This is protocol evidence, not one of the required live
  sample-app comparisons. The installed wheel passed; development SHA-256:
  `56fbbd89cbc7cd045e4d457ad309704d10eb3cea68c872e4632e58f27bd2ef3e`.
  Logs: `/tmp/copyapp-dual-platform-paired-delivery-20261021.log` and
  `/tmp/copyapp-macos-paired-delivery-wheel-20261021.log`.
- ChatComputer's guest OS and control Agent have been installed. GUI setup is at
  the guest permissions stage, awaiting the user's response to the permission
  request. No guest or host permission grant is inferred from continued coding.
  The earlier transport probe correctly records `needs_setup`. Live guest identity,
  UI replay, snapshot restore, paired reconstruction and physical-Mac gates remain open.
- The live GUI was rechecked at step 4. Guest Finder can open
  `/Volumes/My Shared Files/inbox` through the visible VM window, while the CLI
  still reports incomplete setup. A fresh nonce was then copied once through guest
  Finder from inbox to outbox; the returned bytes matched and both cases verified:
  `cases/macos-p0-20261021/shared-request-1` and `shared-result-1`.
  The payload SHA-256 is
  `78f5ca048c14584c38e05f7df3004fe4a252ca214ceb19ab74d81233bbb0d0cd`.
  Navigating out of and back into the inbox refreshed Finder's view after host
  publication. This is a shared-byte roundtrip with a self-declared transfer actor,
  not verified collector identity, automated input recovery or complete P0
  acceptance. No security grant was clicked; the permission question is unanswered.
- Static ZIP and DMG imports of the saved TextEdit 1.21 (419) package both verified
  against the source's 118 inventory entries and package SHA-256
  `a262263b53e27e9db6ca505d81f0fe54d0352267e3ddb97c2ec0be82978627c5`.
  Cases: `cases/macos-real-distribution-20261021/imported-zip` and `imported-dmg`.
  The native DMG mount retained read-only/noexec/nosuid/nodev/nobrowse restrictions
  and was ejected. DMG re-verification remounts the saved image read-only; this
  currently requires macOS 27's diskutil image interface. These static cases prove
  neither launch nor behavior. See [the acquisition guide](macos-acquisition.md).
- Distribution/share regression: 384 tests passed, including existing iOS tests,
  ZIP traversal/collision/link and rehashed-provenance rejection, a native DMG
  import, and simulated shared-byte checks. The installed wheel passed with all
  three new commands; development SHA-256:
  `1cf5e788e7d98f68bc59e993ee637889fcd082bf1d71f3a5f7f062c6dbbb10e3`.
  Logs: `/tmp/copyapp-dual-platform-distribution-20261021.log` and
  `/tmp/copyapp-macos-distribution-wheel-20261021.log`. This is not a release or
  a new iPhone device result; no iOS device execution path changed in this stage.
- Discovery development accepts three to twelve distinct completed replay cases,
  reviewed selection reasons and a known/deferred/blocked inventory. Its handoff
  is `ready_for_behavior_review`, not a completed report. `mac report --discovery`
  binds the exact accepted replay manifests and retains discovered capability IDs;
  interpretation and unresolved unknowns still require agent review. Duplicate
  effective scripts, wrong script hashes, fabricated counts and dropped inventory
  are rejected in the existing simulated-desktop integration test. This adds no
  live sample-app acceptance. See [the discovery guide](macos-discovery.md).
- Discovery regression: all 384 tests passed, including expanded simulated flow
  acceptance/report checks and the unchanged iOS suite. The installed wheel passed
  with `discover-check`; development SHA-256:
  `35989922638368abc290d5e68405ca47abe2aea66216948f4f4e695b93857bc9`.
  Logs: `/tmp/copyapp-dual-platform-discovery-20261021.log` and
  `/tmp/copyapp-macos-discovery-wheel-20261021.log`.
- Selected-data development adds `mac data-file` for one bounded regular file at
  an explicit sandbox, exact Bundle-ID preference or support-folder path. The
  native collector binds the App build, rejects linked/special/oversized files,
  compares two source reads and exports the matching bytes. Association conventions
  and explicit support paths do not prove App ownership; the case explicitly denies
  atomic database and complete-App-data coverage. A newly compiled/signed collector
  passed verification at `cases/macos-data-collector-20261021/build-2`; the first
  failed compiler attempt is retained as `build-1`.
- Data-capture regression: all 384 tests passed. Expanded integration checks use
  the actual local collector and a uniquely owned temporary support directory;
  they request no TCC grants and do not count as guest data acceptance. Empty-file
  capture, linked/FIFO/oversized/missing rejection, byte/source/claim tampering and
  independence from later external file changes are checked. Existing iOS tests
  remain passing. The installed wheel passed with `data-file`; development SHA-256:
  `1d0eb05cbb6e886be4a312ef4c104a8908f50232484c2b60b9d1b1b3b6ab52a2`.
  Logs: `/tmp/copyapp-dual-platform-data-20261021.log` and
  `/tmp/copyapp-macos-data-wheel-20261021.log`.
- Data-structure development adds bounded binary/XML plist key/type extraction
  and detached read-only SQLite metadata extraction, without scalar values, rows,
  SQL bodies/defaults or merged WAL/SHM. `mac report --data ID=CASE` requires
  verified structure cases from the same exact App path, package and environment;
  data findings cannot stand in for a flow's captured behavior. Reports retain
  immutable source cases and revalidate structure from their raw bytes. Their
  archived children still contain private raw data and stay local.
- Structure/report regression: all 384 tests passed, including the unchanged iOS
  suite and expanded local-collector integration. Binary/XML plist, SQLite quoted
  identifiers/foreign keys, omission of marked values/rows/SQL, source/structure
  tampering, a separate valid environment registration, forbidden raw citations
  and data-only behavior claims are checked. A report with data evidence and its
  rebuild plan both verify; these are local/simulated protocol checks, not live
  guest or physical-Mac acceptance. The installed wheel passed; development SHA-256:
  `55a2794d5868ee9874cfaedf471c0ea476cebbac3a9713bcf33bf1cc7b9fe23e`.
  Logs: `/tmp/copyapp-dual-platform-data-schema-20261021.log` and
  `/tmp/copyapp-macos-data-schema-wheel-20261021.log`.
- The repository Mac skill and bilingual entry prompts route Mac targets directly
  to this development workflow. Existing iOS skills and historical v1 validation
  retain their scope. Live sandbox capture,
  live discovery acceptance, live guest install/launch,
  live paired delivery and actual sample/physical-Mac evidence remain unfinished.

Record host/guest OS builds, VM registration and snapshot identity, tool versions,
app Bundle ID/version/path, architecture, signing facts and full package inventory.
Runtime observations additionally bind PID/start time and executable hash. Record
script hash, requests, outcomes, timestamps, screenshots, structured AX observations
and output-file hashes. Keep observations, inference and unknowns separate.

Snapshots do not reset host shared folders or network services. Give every run its
own workspace, request IDs and results; re-establish the session after restoring.
Record both host and guest clocks. Persistence assertions run through actual quit
and relaunch within the flow. Pin language, appearance, scaling, window placement,
input data and network expectations before comparing original and rebuilt runs.

Do not overwrite installed apps or unrelated user data. Install rebuilds under a
separate Bundle ID. Preserve signed originals and separately identify any re-signed
or instrumented copies. No blanket SIP changes or credential copying.

## Release acceptance

1. Two sample apps: one owned fixture and one actual desktop app. At least three
   selected flows per app, three rounds each: 18 original/rebuild comparisons.
2. Cover menus, shortcuts, file dialogs, multiple windows, output correctness and
   quit/relaunch persistence. Validate every selected behavior, not screenshots alone.
3. Exercise takeover, connection interruption and snapshot recovery. Never repeat
   an action solely because its response was lost; inspect state first.
4. Tampered executable, script, screenshot, output, source link, target identity or
   incomplete result must be rejected. Same display name is not app identity.
5. Review all required screenshot pairs with explicit judgments. Image metrics do
   not certify visual equivalence; masks are declared before acceptance.
6. Freeze the known-capability denominator before implementation. Keep target,
   verified known coverage and selected-flow pass rate separate. Disclose unknowns.
7. At least one sample's selected flows pass on a physical Mac. Keep VM and physical
   results separate. Never describe a VM check as physical-Mac acceptance.
8. Existing iOS suite and installed wheel pass. Changes to iOS device execution
   require the affected named-device recheck, with failed evidence preserved.

## Sources checked during planning

- [ChatComputer command vocabulary](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/ComputerControl/ControlCommand.swift)
- [MCP response contract](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/ComputerControl/MCPSession.swift)
- [Snapshot implementation](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/Packages/ChatComputerKit/Sources/VMKit/SnapshotStore.swift)
- [Current upstream status and limitations](https://github.com/chatcomputer/chatcomputer/blob/c774a4ceadc7dc17a589a1de8f5a40fe36c2a649/docs/STATUS.md)
