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
apps, plus explicitly identified arm64 Mac Catalyst packages for the requested
Stocks sample; Catalyst UI acceptance still needs live evidence. Universal bundles
retain full-file and selected-slice hashes. Begin with
independent `.app`, ZIP and DMG distribution. No initial promise for Intel/Rosetta,
encrypted store packages, drivers, system extensions, hardware-dependent or
account/payment workflows. Electron behavior compatibility is a later named test.

UI/static/file evidence produces a **behavior analysis** report, never an
unsupported deep function report. Optional Frida/Ghidra/Hopper evidence is a
separate capability and cannot be invented to satisfy a gate.

## Work and evidence ledger

| Stage | Required work | Acceptance evidence | State |
| --- | --- | --- | --- |
| P0 | Pin ChatComputer; ready desktop, input lease, screenshots, coordinates; file exchange; exact identity; snapshot recovery | Live probe cases, including failures; restart must not accept stale results | Named guest ready; snapshot App-state preservation failed |
| P1 | `copyapp mac` CLI; target/environment identity; versioned cases and validators; old iOS compatibility | Positive cases and negative tampering/cross-platform tests; baseline and final iOS suite | Implemented; 410-test regression and isolated wheel passed |
| P2 | Guest collector; app/package/data acquisition; AX/window observations; bounded playbooks | Same-name app rejection, ambiguous element rejection, output and persistence assertions | Selected guest/UI and one preference-file evidence verified; broader data limits remain explicit |
| P3 | Discovery, reviewed report/specification, coverage plan, agent task, host build, guest install, paired check, visual review, delivery | End-to-end source-linked cases with explicit scope and remaining differences | Owned-fixture selected delivery verified; Stocks bounded 80-grade milestone met, strict delivery deferred |
| P4 | Control takeover, interrupted action, reconnect, snapshot restore, time and data resets | No blind action retries; new run/session identity; rejected old results | Controlled reply-loss/reconnect and real takeover refusal verified; manual hand-back recovery pending and App-state recovery unresolved |
| P5 | Agent-first bilingual docs, wheel resources, examples and clean installation | Installed-wheel checks; two sample applications and one physical Mac recheck | Docs/wheel/two guest samples ready; named same-binary physical selected-flow recheck passed |
| M2 | Optional runtime/native function investigation | Debug fixture first, then named third-party build; report actual entitlement limits | Pending |

First-stage effort estimate is 13–20 developer days, revised after P0. This is not
a deadline or a reason to reduce scope. No tag/release until acceptance completes.

The branch remains unmerged at the user's request. Open an issue and a draft PR
for review while development and acceptance continue. The requested real-app
sample is now Apple Stocks (`com.apple.stocks`), alongside the owned fixture.
The host has Stocks 8.0 (2028); acquire the actual guest build before choosing
flows. Discover and review at least three representative flows, freeze their
known-capability inventory, then implement the independent selected behavior under
`examples/macos/Stocks/` with a separate Bundle ID. Search, watchlist changes,
chart ranges and persistence are candidates for observation, not accepted flows.
Retain market-data/network dependencies and remaining differences explicitly;
captured prices do not establish a live data service or complete App parity.
Earlier TextEdit static distribution probes remain separate evidence.

## Snapshot diagnostics and bounded collector polling (2026-10-21)

- The user clicked the live ChatComputer virtual desktop during a held neutral
  pointer lease and confirmed taking over. Raw status changed to user control;
  the next single neutral pointer request returned an explicit takeover error.
  The client stopped, with no retry or programmatic hand-back. Host UI separately
  displayed the real-click takeover notice. The local manual review is
  `output/macos-human-takeover-live-20261021/attempt-3/manual-review.json`.
  The earlier two waits timed out and remain unsuccessful attempts. Manual
  hand-back and subsequent fresh-session recovery are still pending.
- A bounded review of the original failure window found Security error `-25308`
  in the host Virtualization service. It does not establish the exact host lock
  state or a root cause. Raw diagnostics stay local under
  `output/macos-snapshot-error-diagnostic-20261021/`.
- A fresh experiment after host unlock retained the synthetic unsaved editor text
  and wrapping preference in the post-take screenshot. The snapshot RPC succeeded,
  but subsequent collector health timed out and Finder could not reopen the
  bridge. Therefore `output/macos-snapshot-unlocked-20261021/snapshot-take-1`
  remains failed; no restore was submitted. After observed cleanup and a normal
  guest restart, the unchanged old collector recovered. Failed evidence and the
  snapshot remain preserved.
- A new optional `quiesce` acknowledgment pauses only the collector's shared-file
  polling for 30 guest-clock seconds before take/restore. It binds the exact
  session, instance and executable; it does not pause other guest filesystem I/O
  or prove App-state recovery. Historical collectors and cases keep their prior
  validation semantics. Live snapshot verification with the upgraded collector
  remains pending its guest Accessibility grant. See [recovery](macos-recovery.md).
- Native protocol checks pass, including pause/resume and tampering rejection.
  Full regression: **410 tests in 57.299s**; isolated installed wheel passed,
  SHA-256 `e92b6c52187e14bbb8d63fa066ca5b9c8f096ba77666882632c3639d5aa85c94`.
  Logs: `/tmp/copyapp-quiesce-regression-20261021.log` and
  `/tmp/copyapp-quiesce-wheel-20261021.log`. These local checks do not certify
  the live mitigation or a new iPhone run. A timed-out wait is not takeover
  evidence.

## Output defaults and unlocked-host follow-up (2026-10-21)

- New `copyapp copy` jobs default to ignored `output/<bundle>-<UTC>-<unique-id>/`,
  with sibling `project/` and `evidence/` directories. `--output-dir` chooses the
  job root; explicit `--project` plus `--out` preserves the legacy contract. Resume
  pins the printed previous path, never the latest job. Mac agent-led jobs use the
  same layout explicitly; low-level Mac commands still require `--out`. Existing
  examples and historical cases were not moved.
- Five new output-path tests cover isolated jobs, overrides, workspace boundaries,
  explicit resume and a current-agent discovery handoff that never contacts a
  device. Full regression: **409 tests passed in 65.349s**. Installed wheel passed,
  SHA-256 `5b1321629ba65f1e84b312c70c78264fca6000d54f62588df301a3523f936f6c`.
  Logs: `/tmp/copyapp-output-regression-20261021.log` and
  `/tmp/copyapp-output-wheel-final-20261021.log`. A real CLI smoke run using a dummy
  target paused at the printed default discovery task without device operations.
- After the user unlocked the host, native CUA opened the owned fixture host build
  and the exact guest-tested independent editor binary on the physical Apple
  Silicon Mac (macOS 27.0 / 26A428). One manual round per App checked Unicode
  save/open, quit/relaunch wrapping preference, distinct document statistics and
  JSON export. Both saved files and summaries match; full screenshots were viewed.
  The 37 hashed artifacts and review are retained locally under
  `output/physical-mac-recheck-20261021/`. This is a manual review, not a new
  `copyapp verify` case or complete physical-host CLI acceptance.
- The original host fixture binary matches its own local build record
  (`c0e39153…`), but differs from the guest-acquired fixture (`4e25dd26…`). The
  independent editor matches the guest-tested saved binary (`673de8ce…`). The
  original required closing a disposable second document to expose the first;
  the editor used its Window menu. These adapted routes are not an exact canonical
  paired physical replay. Host appearance/geometry also differ; no pixel parity
  or additional guest capability coverage is claimed. Both Apps were normally
  quit with wrapping On. Human takeover and snapshot App-state preservation
  remain open. Earlier locked-host evidence stays intact.

## Same-binary physical follow-up and remaining recovery gate (2026-10-21)

- The acquired guest original (`4e25dd26…`) was then launched on the physical
  macOS 27.0 / 26A428 arm64 host, after verifying its acquisition case. Its exact
  path, running PID and executable hash were recorded. One manual round of all
  three selected behaviors passed: Unicode file save/open; wrapping Off after
  quit/relaunch; two independent document/inspector counts and first-document
  JSON export, using Window menu selection with the second document retained.
- The original and the already physically checked guest-tested independent editor
  (`673de8ce…`) saved identical 18-byte UTF-8 text and JSON summaries. Full AX trees
  and screenshots support the exact-original follow-up; both Apps exited with
  wrapping On. This closes the named physical **selected-behavior recheck** in
  release item 7. A physical CLI transport was not required by that item and was
  not added. It does not establish whole-App equivalence, arbitrary-Mac support
  or pixel parity, and does not alter guest delivery/coverage.
- Evidence: `output/physical-mac-recheck-20261021/same-binary-review.json` and
  `same-binary-report.md`, with 26 hash references. The earlier different-host-build
  review is preserved. Initial captures 02/03 show an Open panel whose first Open
  action was ineffective; after current-state inspection, confirmed captures
  04/05 establish document readback and Wrapping Off. The intermediate observations
  are diagnostics, not successful behavior evidence.
- A new read-only human-takeover preparation rechecked the pinned VM/environment,
  collector health, status and full screenshot. The desktop is ready and control
  is free. No input or snapshot was submitted. Actual human participation remains
  pending; a programmatic click is not being reported as a human test. Local
  preparation: `output/macos-human-takeover-20261021/`.
- Public upstream release metadata was rechecked: the newest listed release is
  v0.9.11, and its tag points to the already reviewed revision
  `c774a4ceadc7dc17a589a1de8f5a40fe36c2a649`. Its VM factory uses the saved machine
  and hardware identifiers and saved network MAC; no random identity cause was
  found in that source. The current main still contains the silent cold-boot
  fallback after saved-state restore/resume failure. This supports a diagnostic
  hypothesis, not the cause of the installed build's observed failure. No new
  snapshot, restore or runtime patch was submitted.
- Sources: [release](https://github.com/chatcomputer/chatcomputer/releases/tag/v0.9.11),
  [VM factory](https://github.com/chatcomputer/chatcomputer/blob/v0.9.11/Packages/ChatComputerKit/Sources/VMKit/VMConfigurationFactory.swift),
  [VM controller](https://github.com/chatcomputer/chatcomputer/blob/main/Packages/ChatComputerKit/Sources/VMKit/VirtualMachineController.swift).
  The failed unsaved-App-state preservation gate and real human takeover remain
  open; the full first-stage goal is not complete.

## Required evidence model

### Development evidence recorded on 2026-10-21

- Branch: `codex/macos-chatcomputer-support`.
- Existing iOS baseline: 346 tests passed before modifications.
- Separate `copyapp mac` commands now cover doctor, inspect, build/prepare-collector,
  connect, observe, acquire, playbook, report, rebuild-plan, build-app, install,
  check-plan, rebuild-check, visual-review, delivery, share-probe,
  share-probe-check, import-app, discover-check, data-file, data-schema,
  snapshot-inspect, snapshot-take, snapshot-restore and probe-collector, with versioned
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
- An [owned original AppKit sample](../examples/macos/BehaviorFixture/README.md)
  now supplies native panels, editor/counts, wrapping persistence, multiple
  document/inspector windows and JSON export. The failed first compilation is
  retained. Build-2 (1.0/1) received a manual host original-only smoke check:
  32-byte UTF-8 save/open, asserted summary fields, inspector counts and setting
  quit/relaunch persistence. Build-3 (1.0/2) adds a native Window menu; actual host
  UI listed two documents and switched exactly between them. Both static package
  indexes verified; test processes were quit and exact-path absence checked.
  Files: `cases/macos-owned-fixture-20261021/`, including the explicitly manual
  `manual-smoke-1/notes.json`. No screenshots were archived into a flow case.
  These observations from different builds are not merged into one acceptance,
  do not certify guest replay, and do not satisfy paired reconstruction or the
  required physical-Mac reconstruction recheck. The current original needs its
  own guest acquisition, reviewed flows and independent rebuild before comparison.
- Snapshot development now records bounded public metadata, creates a uniquely
  named ChatComputer snapshot and restores a pinned take case only with
  `save_current: true`. It retains the exclusive collector lock while switching
  protocol epoch and MCP transport, preserving old shared replies. Unknown action
  outcomes are not retried. A preflight input lease detects an existing human
  takeover; the upstream snapshot API has no atomic expected-lease condition, so
  a later takeover race remains an explicit limitation. Metadata/reconnect cases
  do not verify restored App behavior, saved disk/memory bytes or shared-data reset.
  See [recovery](macos-recovery.md).
- The actual VM's read-only snapshot inventory verified at
  `cases/macos-p0-20261021/snapshot-inventory-1`: stage `agentInstalled`, zero
  snapshots, no current ID or restore in progress. No snapshot mutation or
  permission grant was made. The source contract was checked at the pinned
  upstream revision and retained under ignored
  `cases/macos-recovery-upstream-20261021/` without credentials.
- Snapshot regression: 388 tests passed, including existing iOS tests and the
  simulated snapshot controller with a real local collector. Tests reject old
  session replies, altered metadata/requests, missing safety snapshots, changed
  targets, interrupted journals and incompatible argument schemas. Lost take/
  restore replies and a post-commit readiness error retain evidence with one
  action submission; human takeover blocks before snapshot submission. No actual
  VM disk/memory was restored in these tests. The installed wheel passed;
  development SHA-256:
  `5e34680164ba45059ae831c48c967d558e0636a3f5ee077753eef64d3f8bfc2c`.
  Logs: `/tmp/copyapp-dual-platform-snapshots-20261021.log` and
  `/tmp/copyapp-macos-snapshots-wheel-20261021.log`.
- A no-prompt collector deployment was verified, published only into the VM's
  existing read-only inbox and opened once through the visible guest Finder.
  `probe-collector` then received two distinct, source-bound health replies from
  the actual guest and its case verified:
  `cases/macos-p0-20261021/collector-identity-probe-1`.
  Collector SHA-256:
  `4e2f81c07646c06ec4cf06b7f05b7efa50ce175fef68d9d948f3c9ef22f5559f`.
  The guest reports macOS **27.0.1 (26A434)** and Accessibility **false**; this is
  more specific than the earlier macOS 27 planning assumption and differs from
  the host's build. The public stage remains `agentInstalled`, GUI step 4. No
  capture/Accessibility grant or permission request was made. Exact launcher
  content is now checked against its build and permission-request flag, including
  rejection of a rehashed no-prompt-to-prompt change. The source deployment and
  published copy both verified. The observed guest identity is first bound to
  this shared root, not a substitute for complete environment registration.
- Collector-probe regression: 388 tests passed with expanded actual-local-collector
  probe and launcher checks, alongside existing iOS tests. Probe completion cannot
  assert desktop control, transport readiness or full environment acceptance. The
  installed wheel passed; development SHA-256:
  `59ec07db7c7b686aec387577208e2f5013936df8918fac0fc217f2eb8f1b70f2`.
  Logs: `/tmp/copyapp-dual-platform-collector-probe-20261021.log` and
  `/tmp/copyapp-macos-collector-probe-wheel-20261021.log`.
- Interrupted-input development now preserves the failed MCP transport/server,
  exact request and last response separately from cleanup failures in a replay
  case. The pinned upstream wraps pre-dispatch refusals and post-dispatch failures
  in the same unstructured error channel. Input/file/VM mutation error replies
  therefore remain unknown outcomes, close that transport and are not retried;
  read-only errors remain distinct. Actual stdio-process error tests and simulated
  replay interruption check one action submission and retained raw failure
  evidence. This is protocol recovery evidence, not a live guest interruption.
- Interrupted-input regression: 390 tests passed, including the unchanged iOS
  suite. The installed wheel passed; development SHA-256:
  `77c884b28ecd9836f0c2a5cd9637bddd3cbd2b270fff331d408980c1d9b27e17`.
  Logs: `/tmp/copyapp-dual-platform-input-failure-20261021.log` and
  `/tmp/copyapp-macos-input-failure-wheel-20261021.log`. Guest permission consent
  remains pending; no guest or host security permission was granted in this work.
- The repository Mac skill and bilingual entry prompts route Mac targets directly
  to this development workflow. Existing iOS skills and historical v1 validation
  retain their scope. Live sandbox capture,
  live discovery acceptance, live guest install/launch,
  live paired delivery and actual sample/physical-Mac evidence remain unfinished.
- After explicit guest-permission authorization, ChatComputer onboarding saved its
  initial snapshot. Normal quit/reopen enabled external MCP without a configured
  built-in model. `transport-ready-attempt-1` and `environment-1` under
  `cases/macos-p0-20261021/` verified. Collector authorization then completed;
  the earlier `collector-after-authorization-1` retains a false permission
  observation, while `collector-authorized-1` records true. The actual guest's
  `settings-ax-1` verified exact foreground System Settings identity, a screenshot
  and 323 untruncated AX nodes on macOS 27.0.1 (26A434). This is live environment
  and AX collection evidence, not a completed sample reconstruction or P0/P4 gate.
- Registration now retains the raw MCP initialization envelope and self-reported
  server identity independently of App version; reconnect and snapshot validation
  use that pinned server identity. The actual CLI-alias doctor reported server
  version `0`; resolved-App registration reported `0.9.11`. Simulated snapshot
  tests now deliberately use server `0` with App `0.9.11`, reject a rehashed
  substitution and reject a changed server on reconnect. Full regression: 390
  tests passed; installed-wheel SHA-256:
  `76a882ce9457d6e73d69aac76aac4315832346a89be903b9d36b621508a36e9b`.
  Logs: `/tmp/copyapp-dual-platform-live-registration-20261021.log` and
  `/tmp/copyapp-macos-live-registration-wheel-20261021.log`. The first Mac-only
  recheck failed on a test import-order mistake; the retained log is
  `/tmp/copyapp-macos-live-server-20261021.log`; its corrected recheck passed.
- The first actual guest Stocks acquisition exported 124 package entries and
  identified Stocks 8.0 (2028), but the host index rejected its Mach-O platform
  **6 (Mac Catalyst)**. The failed attempt remains at
  `cases/macos-stocks-20261021/acquisition-1`. Add explicit Mac Catalyst package
  facts and rejection tests for iOS/simulator inputs before a new acquisition;
  do not relabel the failed case as accepted or infer UI compatibility from it.
- Mac package inspection now accepts platform 6 exclusively as Mac Catalyst,
  records its runtime separately and rejects iOS, simulator and conflicting platform
  declarations. Native platform-1 index facts retain their historical shape.
  A rehashed Catalyst-to-native fact substitution is rejected. Fresh guest Stocks
  acquisition `cases/macos-stocks-20261021/acquisition-2` verified; its first
  launch/observation cases show the welcome sheet, not a completed behavior flow.
  Full regression: 392 tests passed in 46.490s; installed wheel passed, SHA-256
  `49a08be256f8a702c97ead1d56265ff19ab133a26c3b44a28b11e64b1a9e4894`.
  Logs: `/tmp/copyapp-dual-platform-catalyst-20261021.log` and
  `/tmp/copyapp-macos-catalyst-wheel-20261021.log`.
- Live Stocks exposes many visible labels as AX descriptions rather than titles.
  Mac replay selectors now accept exact `description` alongside the existing fields;
  missing, partial and duplicate matches remain rejected. The actual guest showed
  its news/watchlist interface and AAPL chart. These exploration cases do not yet
  supply the three reviewed representative flows. Full regression: 393 tests
  passed in 42.127s; installed wheel passed, SHA-256
  `d067e0cebc6752e1bd962d2bef5437ea031f353fbebcc2b14172e754c442924d`.
  Logs: `/tmp/copyapp-dual-platform-description-selector-20261021.log` and
  `/tmp/copyapp-macos-description-selector-wheel-20261021.log`.
- A live new-watchlist click changed the focused window during the immediate AX
  observation. Its failed case is preserved; a fresh read confirmed the dialog
  before further input. Replay now waits 350 ms after a successful input reply
  before strict post-input capture, without retrying the input or relaxing
  identity/focus checks. Subsequent save/manage sheet exploration succeeded.
  The original Stocks search flow and chart-range/quit/reselect flow have now
  replayed with assertions; discovery review and reconstruction are still pending.
  Full regression: 393 tests passed in 52.830s; installed wheel passed, SHA-256
  `e9dc83a80208441dad3aeb6f1b3c1c6ca8d67bbd8a58e1a109c77e063bcbff75`.
  Logs: `/tmp/copyapp-dual-platform-ui-settle-20261021.log` and
  `/tmp/copyapp-macos-ui-settle-wheel-20261021.log`.
- Stocks now has three verified original assertion-bearing replays:
  `search-flow-1`, `chart-range-flow-2` and `watchlist-flow-1` under
  `cases/macos-stocks-20261021/`. Their `discovery-1`, `report-1` and rebuild
  plans verified. The known inventory freezes 11 capabilities; the reconstruction
  targets 3/11 (27.27%), not whole-App parity or verified coverage. Range persistence
  requires reselecting AAPL after relaunch; the initial unsupported assumption
  remains in failed `chart-range-flow-1`.
- `examples/macos/Stocks/` supplies independent AppKit source, illustrative offline
  data, generated curves, local search/watchlists/period preferences, original
  playbooks and a standalone builder. No original binary, artwork, article or
  account data is included. The first source-linked guest build/install/acquisition
  verified and all three frozen clone scripts replayed with assertions. Those
  single runs are not the required three-round paired check or visual acceptance.
  The example visibly differs in catalog, curves, metrics, modal rendering and
  overview content; preserve these differences in review. `build-2` adds normal
  startup overview behavior and an independently drawn dock icon. Its install and
  paired checks remain pending; all earlier build/run cases remain separate.
- Actual snapshot testing exposed stale shared-directory observations after memory
  resume. `snapshot-take-live-1` saved a snapshot but timed out on collector health;
  `snapshot-take-live-2` retained another failure. A fresh Finder directory read
  restored health with the same collector; rotating sessions alone was insufficient.
  The collector now enumerates the bridge directory before reading the active
  epoch. Its request IDs, mutation start markers and no-retry rules remain intact.
  New collector SHA-256:
  `c0f5274ba212847062cd586d5ba7a82e78cc7246c2d9fce3808865cda07b24de`;
  source build/deployment/probe/registration are under
  `cases/macos-snapshot-collector-20261021/`. Its AX permission must be checked
  separately after this ad-hoc build change.
- The new collector passed actual take and restore in
  `cases/macos-p0-20261021/snapshot-take-directory-refresh-1` and
  `snapshot-restore-directory-refresh-1`, including fresh sessions and a retained
  safety snapshot. These cases verify metadata/reconnect only; App restoration,
  live input interruption/takeover and complete P0/P4 acceptance remain open.
  Serialized full regression: 393 tests passed in 51.696s; installed wheel passed,
  SHA-256 `060a9201a1eb7496ab99a4826a61fa41e21e910f25888687efeb85cabe00832a`.
  Logs: `/tmp/copyapp-dual-platform-directory-refresh-20261021.log` and
  `/tmp/copyapp-macos-directory-refresh-wheel-20261021.log`. Earlier concurrent
  runs had short MCP startup-deadline failures; their retained logs are
  `/tmp/copyapp-dual-platform-post-snapshot-health-20261021.log` and
  `/tmp/copyapp-macos-post-snapshot-health-20261021.log`.


- The updated collector's permission row still selected the earlier ad-hoc build.
  An authorized, guest-only per-bundle permission reset and exact-path regrant
  restored AX access. Fresh registration is
  `cases/macos-snapshot-collector-20261021/environment-2`; old false-health probes
  remain unchanged. The existing VM and its official credential store were kept.
- The actual guest reports 34 ordered preferred languages. The bounded UI validator
  now accepts up to 128 without truncation; equality and order remain pinned.
  Regression tests reject reordered, truncated, oversized and non-string lists.
  Full regression: 394 tests passed in 68.498s; installed wheel passed, SHA-256
  `2c9d03a99a4d02c2b3a70299bc2e6139b7be336c52b6e26be247a4d0b3ce421c`.
  Logs: `/tmp/copyapp-dual-platform-language-bound-20261021.log` and
  `/tmp/copyapp-macos-language-bound-wheel-20261021.log`.
- Fresh Stocks evidence under `cases/macos-stocks-recheck-20261021/` uses that new
  registration. Original acquisition, three replay flows, discovery, report and
  rebuild planning verified. `check-1` completed all nine original/rebuild behavior
  comparisons across three rounds (100% selected-flow pass rate, not whole-App
  coverage). An early full-image inspection found a chart-seed collision: the
  sample's 1-day and 1-year trajectories were identical. The 195-pair review was
  stopped after this concrete defect; this build has no accepted visual review or
  delivery. Its evidence and partial review index remain local.
- The independent Stocks example now uses an explicit period index for distinct
  generated curves, with improved local search rows, axes, volume and preview
  layout. Build 4 compiled/signed and was installed under another fresh guest path;
  renewed paired acceptance is pending. Offline quotes, generated curves, limited
  catalog, independent overview cards and native control differences remain explicit.
- A physical-host recheck attempt was blocked before App launch because the host
  was locked and the computer-use tool could not unlock it. The diagnostic is saved
  in `physical-host-recheck-1` under the fresh Stocks folder. It establishes no
  physical-Mac behavior. Guest work continues independently; this gate stays open.


- Build-4 `check-2` completed five original/rebuild pairs, then stopped during the
  second-round original watchlist flow: the quit reply succeeded, but 22 retained
  exact-identity polls still reported the inactive process during the five-second
  wait. `inspect-after-check2-quit-1` later verified that original process was absent.
  This does not establish its exact exit time. `cleanup-after-check2-1` deliberately
  removed only the leftover test list after that inspection; no uncertain input was
  blindly repeated. The failed parent and partial visual review remain preserved.
- `expect_stopped` now waits at most 30 seconds for exact process termination,
  retaining read-only polls. Inactive processes still fail the assertion, and a
  timeout sends no additional input or force quit. The new tests cover shutdown
  beyond five seconds and a still-running timeout. Full regression: 396 tests
  passed in 54.761s; isolated wheel passed, SHA-256
  `afec2f3077f359214cfd9fcac311c47e6c85efe4b9067ebe1f1542e6bb71542e`.
  Logs: `/tmp/copyapp-dual-platform-graceful-quit-20261021.log` and
  `/tmp/copyapp-macos-graceful-quit-wheel-20261021.log`. A fresh paired attempt is
  required; neither previous behavior success nor this timing change accepts a
  failed check or completes the remaining visual/physical gates.

### Continued live acceptance on 2026-10-21

- The repaired VM remains usable; no deletion/recreation or password change was
  needed. Credentials remain only in ChatComputer's official local storage.
- Fresh Stocks build-4 `check-3` completed and verified all nine behavior
  comparisons (three flows × three rounds). The exact check is under
  `cases/macos-stocks-recheck-20261021/`; `visual-review-3` also verifies.
  All 195 required full pairs were reviewed (390 occurrences, 299 exact unique
  complete PNG hashes; no content/mask deduplication). Every pair retains a major
  full-screen difference. Missing live news/market services, incomplete menus,
  absent hover feedback and different delete-dialog stacking prevent accepted
  delivery. Initial task states agree in all nine pairs; that does not make the
  substituted data/content visually equivalent. The frozen target remains 3/11
  known capabilities; 9/9 is the selected-flow behavior rate, not verified coverage.
- The owned fixture's guest package matches the local original build exactly.
  `cases/macos-owned-fixture-20261021/` now contains verified
  `file-roundtrip-original-2`, `wrap-persistence-original-1` and
  `multiwindow-summary-original-1`, followed by `discovery-1`, `report-1` and
  `rebuild-plan-1`. The selected Unicode text roundtrips as 18 UTF-8 bytes with
  14 characters/four words. Two documents keep distinct text; Window-menu selection,
  two inspectors and exported JSON agree. Wrapping Off survives an asserted process
  exit/relaunch; Reset returns On. This empty-document persistence flow does not
  establish long-text line breaking. The earlier default-filename mismatch and
  compilation failure remain preserved.
- The fixture reconstruction target freezes seven of nine reviewed known
  capabilities before implementation. `examples/macos/IndependentEditor/` is an
  independent source-available acceptance example, with separate Bundle ID and
  preferences, not a blind-source benchmark. `rebuilt-build-2` and
  `rebuilt-install-1` verify its build and non-overwriting guest installation;
  `check-plan-1` freezes three rounds. Paired checking is in progress and has no
  accepted visual review/delivery yet. Current full CLI regression remains the
  396-test/wheel run above; the new example additionally passed native compilation.
- The physical-host lock, live takeover/input-interruption and restored-App
  behavior gates remain unresolved. The branch and draft PR remain unmerged;
  neither sample is described as whole-App parity or native function analysis.
- Fixture `check-1` stopped before rebuilt input because its initial frame was
  720×508 at (204,88), versus the declared original 720×512 at (204,84). The saved
  screen and AX were inspected, then `cleanup-after-check1-1` quit the blank clone
  once and verified exit. A local compiler experiment found direct swiftc stamped
  SDK 14.0, while xcrun/the same explicit SDKROOT stamped the actual SDK 27.0.
  New builds preserve the versioned SDK spelling and export/record that SDKROOT;
  historical build cases still verify with their original log shape. The native
  regression now checks LC_BUILD_VERSION and rejects a rehashed SDKROOT log change.
  `rebuilt-build-3` records SDK 27.0; `rebuilt-install-2`, `check-plan-2` and fresh
  `check-2` retain the new non-overwriting path. The live rebuilt frame now matches
  the original. Original/rebuilt file roundtrip has passed in its first round;
  the remaining pairs are running, without accepted visual delivery.
- SDKROOT regression: seven native/bridge tests passed. Full regression passed
  **396 tests in 53.867s** (`/tmp/copyapp-dual-platform-sdk-root-final-20261021.log`);
  isolated wheel passed, SHA-256
  `5fd0de74bb0ce956c0fceeb9b5bbd0a4128839de1b866b9fa3197759940e379f`
  (`/tmp/copyapp-macos-sdk-root-wheel-20261021.log`). The earlier full attempt
  retained two simulated-server initialization timeouts under concurrent build
  load. The action-timeout test now applies its 0.3s bound after initialization;
  its lost/late-input/no-retry assertions are unchanged. No iOS device execution
  code changed and no fresh physical-iPhone regression is claimed.
- Fixture `check-2` subsequently completed and verified all three rounds: nine of nine selected
  behavior comparisons passed, with 18 complete original/rebuilt playbooks. The
  rebuilt executable is
  `6bc8fa8be0f6d08294b2e81af820b5e4bd545dabc8565be5fff81f822b681bdc`.
  Together with Stocks this supplies 18 selected behavior comparisons across the
  two samples, not accepted sample delivery or verified capability coverage.
  The fixture check contains 285 full screenshot pairs (457 exact unique complete
  PNG hashes). All 457 exact unique full images have now been opened, and
  `visual-review-2` verifies all 285 explicit pair judgments and nine equivalent
  declared starting states. Six pairs are major differences: each round's Window
  menu (`09/after`, `10/before`) omits the original's disabled Enter Full Screen
  and six tab rows. The remaining 279 retain minor differences in App identity,
  clock, pointer/caret, Dock state, native-panel history/extension/focus and
  adaptive Go To geometry. Later panel geometry converges; menu omissions repeat
  in all three rounds. Text, counts, inspector geometry and saved wrapping state
  agree within the selected strings/empty-document scope. Rebuilt relaunch
  sometimes briefly omits the menu title before later rendering. No masks were
  declared and that historical attempt has no accepted delivery. `rebuild-plan-3` and
  `rebuilt-build-4` preserve a separate fresh-path attempt that attaches the
  complete menu before activation. `rebuilt-install-3`, `rebuilt-acquisition-3`
  and `menu-recheck-build2-1` verify the new build at `CopyAppEditor3.app`;
  executable SHA-256 is
  `673de8ce4127dc51a4c1b200899817d140abedbd17f5a0228a440c5f0e0b17f6`.
  The targeted 15-step guest replay passes blank/Unicode editing, two documents,
  both inspectors, Window selection and normal exit. The opened full menu screen
  restores the missing rows; all 27 direct AX menu rows (including alternates)
  match the original's titles, selectors, enabled states and frames. This is a
  targeted regression result, not replacement acceptance. `check-plan-3` freezes
  the same measured conditions without masks. Fresh `check-3` completed and
  verified all nine selected behavior comparisons and 18 complete playbooks.
  All 459 exact unique full unmasked PNGs were opened for its 285 pairs;
  `visual-review-3` verifies zero major differences, 285 minor differences and
  nine equivalent declared starting states. The complete standard Window rows
  and App menu title are present in the new rounds. Minor independent identity,
  clock/caret/Dock phase, native-panel path/history and focus differences remain.
  `capability-review-check3.json` reviews all nine frozen capability units in
  order; `delivery-1` passes verification with seven verified known capabilities
  out of nine (77.78%), the same seven-of-nine target, and a separate 9/9 selected
  comparison pass rate. Undo/clipboard and general window-management actions
  remain deferred. Arbitrary Unicode, long-line wrapping, file errors/cancel/
  overwrite, native semantics and physical-Mac behavior remain unknown.
  This source-available fixture is a workflow acceptance example, not a blind
  reconstruction benchmark or whole-App parity. Stocks independently retains
  its complete adverse 195-pair review and has no accepted delivery.
- Stocks build 5 fixes the custom Delete confirmation stack: the selected Manage
  Watchlists table remains underneath, with a bordered table, grouped add/remove
  controls, blue Cancel and red destructive styling. The new executable is
  `a53b23aafe349d4f2312f1ddbb06be4a36630e93feda1581fc2c0ae412b5c25c`.
  `cases/macos-stocks-recheck-20261021/rebuild-plan-4`, `build-4`, `install-5` and
  `rebuilt-acquisition-3` verify a separate `CopyAppStocks5.app` installation.
  Initial `install-4` refused the still-running bundle and remains failed with
  unknown-completion evidence. Exact old identity and missing new target were
  inspected before `build4-normal-exit-1` stopped the old build normally and the
  separate install attempt proceeded. No uncertain install was automatically
  repeated. `modal-cancel-delete-build5-1` verifies 28 steps and nine assertions,
  including test-list persistence, Cancel retaining the list, subsequent Delete,
  return to AAPL and normal process exit. Six full images were opened; untruncated
  AX snapshots retain the list after Cancel and omit it/disable remove after
  Delete. Only active custom confirmation controls remain exposed while it is
  shown. See `modal-build5-findings.json`. This is a targeted regression, not a
  new complete paired review or capability delivery. Independent market/news
  content, toolbar/menus, hover and native modal semantics remain unresolved.
- Stocks build 6 separates the newly-created-list search page from the persisted
  empty-list page after cold launch. The latter now shows Business News, the list
  label, No Symbols and Add Symbol; Add Symbol focuses search and opens its empty
  prompt. `rebuild-plan-5`, `build-5`, `install-6` and `rebuilt-acquisition-4` in
  the same Stocks case root verify `CopyAppStocks6.app`, executable
  `69421969027231451726578e4fe84f34e5da352a86a31c762a3775b0652ebee7`.
  `empty-list-and-modal-build6-2` verifies 31 steps and 11 behavior assertions;
  six full screenshots were opened. It includes cold-list restoration, Add Symbol,
  Cancel retaining the list, subsequent Delete, return to AAPL and normal exit.
  The earlier `empty-list-and-modal-build6-1` is retained as failed: its added
  diagnostic step requested Business News after entering a search page where
  that element is absent, so it stopped before dispatch. The screenshot was
  inspected before the separate verified `build6-inspected-cleanup-1` removed
  the test list and quit; only then was the reviewed script run in a new case.
  See `empty-list-build6-findings.json`. This is still a targeted regression,
  not a complete new paired delivery; content/menu/hover differences, list-header
  menu behavior and actual symbol membership remain unresolved.
- Controlled real-guest reply-loss evidence is retained at
  `cases/macos-live-response-loss-20261021/`. A local diagnostic harness withholds
  one matching genuine successful `type` reply at the client receive boundary
  and terminates that MCP process. Production `interrupted-playbook-1` retains
  its exact request, null response, unknown completion, inspection requirement
  and no retry; `verify` rejects the incomplete case. The withheld real envelope
  remains separate. A new collector session's verified
  `post-loss-readonly-observation-1` shows exactly one probe string; its full
  screenshot was opened. After inspection, `observed-normal-exit-1` verifies the
  observed text and normal process exit. This is controlled fault injection
  against the real guest, not a simulated desktop or an unplanned network failure.
  No production transport code changed. Human takeover, other interruption
  timings, snapshot App-state restoration and physical-Mac acceptance remain open.
- A subsequent real-guest App-state probe failed and remains preserved at
  `cases/macos-fixture-snapshot-behavior-20261021/`. Verified `baseline-1` shows
  unsaved Unicode text and Wrapping Off. `snapshot-take-1` returned an agent-
  disconnected error after creating manual snapshot
  `3BF59B3B-6B33-451E-883B-282BCD5B9303`. A separate verified inventory matches
  the uniquely requested label, addition, current ID and ancestry; the original
  take stays failed with unknown completion and no retry. No restore was issued.
  After the desktop became ready, the hash-pinned collector needed explicit
  relaunch through its verified deployment. `post-relaunch-collector-probe-1`
  and `cases/macos-snapshot-collector-20261021/environment-3` verify the same VM,
  guest OS and retained Accessibility grant. Verified editor acquisition/identity
  and `post-take-ui-inspection-1` show the unchanged executable with a new PID
  (4806 before, 364 after), blank text and Wrapping Off. Full before/after images
  were opened. The unsaved document was not preserved; the behavior is consistent
  with a cold restart, but the exact saved-state failure is unconfirmed.
  `post-take-observed-cleanup-1` verifies the observed blank Off state, Reset On
  and normal exit. See `snapshot-app-state-findings.json`. This is an adverse
  App-state result, not successful memory restoration or a completed take case.
  The environment is ready again. Further snapshot experiments require saved or
  discardable test state; resolving take/resume behavior remains a release gate.


- The later Stocks `check-4` stopped in round one's original search: after clearing
  MSFT, the visible AAPL row was temporarily missing from the AX tree, so no
  return click was sent. A fresh read-only observation found the row. All 37 exact
  unique full PNGs from this partial attempt were opened; this is not a complete
  paired comparison or visual-review case. Further diagnostic attempts retain
  intermittent row-center misses and unsuccessful keyboard navigation rather than
  claiming universal AX timing or keyboard behavior.
- `search-original-point-1` and `search-rebuilt-point-1` separately verified a revised
  16-step search flow with six assertions. The script asserts a unique result,
  waits for settling, clicks reviewed ticker-text points and returns to AAPL.
  Its explicit geometry is a 1080×670 window at (100,56) on a 1280×800 screenshot.
  `discovery-2` and `report-2` retain the original 11-capability inventory and three
  targets, reuse verified chart/watchlist evidence, and disclose different
  observation times. `rebuild-plan-6`, `build-6`, `install-7` and
  `rebuilt-acquisition-5` verify the version-7 example at `CopyAppStocks7.app`,
  executable SHA-256 `026f3621cbbf7c91aed44e29e2b04c3bb7c70332819fd8abef7d5224f6bfce17`.
  The first refreshed check-plan request was rejected before case creation/input
  because old clock masks referenced removed captures. `conditions-2.json`
  regenerates the same clock-only masks from the frozen script; full images still
  require review. No new Stocks delivery is claimed by these preparation stages.
- Version 7 subsequently completed `check-plan-6` and three-round `check-5`:
  **9/9 selected behavior comparisons passed**, including the revised search flow.
  Every one of its 207 full screenshot pairs was reviewed (414 occurrences,
  **320 exact unique full PNG hashes**). All referenced image bytes were rehashed
  against the comparison and review index before producing `visual-review-5`;
  both cases verify. Nine declared task starting states are equivalent and all
  1280×800 image dimensions match, but **207 major differences remain**. The
  retained Manage sheet beneath Delete and the cold No Symbols/Add Symbol state
  are now visible. Offline prices/curves, replaced news, incomplete menus/toolbar,
  missing hover feedback, styles and AAPL-like example MSFT statistics differ.
  Round-three original search briefly captures a blank chart before its heading
  assertion; this does not invalidate that heading assertion or prove chart
  readiness. See `visual-judgments-check5.json`,
  `full-screen-review-build7-check5-index.json` and `check5-reviewed-findings.json`
  in the same ignored case root. Historical failed/partial runs and build-4's
  adverse 195-pair review remain preserved. This supplies a refreshed paired
  review, not an accepted Stocks delivery or verified capability coverage.
- A live selected-data check now uses the owned original fixture acquisition:
  `preferences-data-1` captures exactly
  `/Users/agent/Library/Preferences/dev.copyapp.fixture.Behavior.plist` through
  a fresh pinned collector session. Its 1,246 bytes hash to
  `f7d8c3299c3b80684cab64e2d8f2ca13c87ee9998ba311fc0162934e11742225`.
  `preferences-structure-1` verifies a non-truncated dictionary with boolean
  `/fixture.wrap` and native panel metadata key/types, omitting scalar values.
  `report-with-preferences-1` imports the structure with an explicit reviewed
  citation and separately verifies. These cases are under
  `cases/macos-owned-fixture-20261021/`. The known inventory remains nine units;
  the original selected-behavior delivery retains its original report. This later
  data observation is not simultaneous with the UI evidence, does not identify
  every key's writer and establishes neither complete App data nor SQLite/WAL
  consistency. Raw bytes remain in ignored local child cases.

- The later user request bounds prototype fidelity instead of indefinite visual
  polishing. New cross-platform `fidelity-plan`, `fidelity-template` and
  `fidelity-check` commands freeze a default reviewed grade of **80/100** and
  **three implementation/check cycles including the first**. Behavior/layout/detail
  weights are 40/40/20; core selected behavior and full image review remain required.
  Every difference retains its verdict plus an explicit blocking impact. Results
  distinguish `target_met`, `continue` and `iteration_limit` (CLI exits 0/2/3);
  supported failed attempts consume cycles without gaining behavior/visual points.
  The retained predecessor chain enforces the submitted budget and stop decision,
  rather than claiming a global process/time limiter. Historical iOS/Mac strict
  delivery validators and standalone parent completion semantics are unchanged.
  See [the bounded workflow](fidelity.md), updated AI entry prompts and skills.
- Stocks `fidelity-plan-1` and `fidelity-check-1` under the same recheck case root
  verify the user-requested selected offline-prototype milestone: behavior 100,
  layout 80 and details 45 yield **81/100**, meeting target 80. This explicitly
  reuses version-7 `visual-review-5` after the new target request; it is not a
  threshold predeclared before that original run or a fresh guest test. All
  **207 major visual judgments remain unchanged** and are acknowledged with
  reasons. Further cosmetic polishing stops at this milestone. It certifies no
  objective similarity percentage, known-capability coverage, strict Stocks
  delivery or release gate. `fidelity-policy-timing-1.json` records these limits.
- `cases/macos-fidelity-contract-20261021/limit-check-1` verifies a diagnostic
  one-cycle plan against retained failed `check-4`: the CLI exits 3 with
  `iteration_limit`, zero points and no target achievement. No guest action was
  submitted. Unit tests also cover 80/90/100 boundaries, core/starting-state
  blockers, complete difference acknowledgment, fabricated scores/citations,
  predecessor budgets and rehashed result tampering. Mac integration accepts an
  explicitly non-blocking major difference at an 80 milestone while the old strict
  delivery still rejects it. Current full regression: **404 tests in 107.954s**
  (`/tmp/copyapp-dual-platform-fidelity-20261021.log`); final report formatting was
  separately covered by the eight fidelity tests. The isolated installed wheel
  includes the new commands/options and passed with SHA-256
  `8a981dbf2f1ca60af31d5ec8c469d40fd36fd68122d8ab6d1920366403c79b07`
  (`/tmp/copyapp-fidelity-wheel-final-20261021.log`). The three revised skills pass
  their frontmatter/reference review. No new iPhone or physical-Mac result is claimed.

- A subsequent completion audit at HEAD `dc310dd` leaves the full first-stage goal
  and release acceptance incomplete. `cases/macos-goal-audit-20261021/` retains
  the 14-item manual `completion-audit.json`, copied regression/wheel logs and a
  fresh verified `guest-observation-1`. The opened full screenshot and pinned
  process identity confirm version-7 Stocks remains running at its reviewed AAPL
  demo state; no new App input or snapshot was submitted. A read-only CoreGraphics
  session probe still reports the physical host locked. Real human takeover and
  physical-Mac selected-flow validation need human participation/unlock. Running
  App-state snapshot preservation remains an adverse result with unconfirmed
  resume cause; a local upstream-report draft records evidence and source
  hypotheses without posting raw data or claiming a fix. Optional M2 native
  analysis is still unverified. Stocks polishing remains stopped at its bounded
  milestone; these environment gates do not turn that milestone into whole-App,
  strict-delivery or release acceptance.

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
