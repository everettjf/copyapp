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
| P0 | Pin ChatComputer; ready desktop, input lease, screenshots, coordinates; file exchange; exact identity; snapshot recovery | Live probe cases, including failures; restart must not accept stale results | In progress |
| P1 | `copyapp mac` CLI; target/environment identity; versioned cases and validators; old iOS compatibility | Positive cases and negative tampering/cross-platform tests; baseline and final iOS suite | In progress |
| P2 | Guest collector; app/package/data acquisition; AX/window observations; bounded playbooks | Same-name app rejection, ambiguous element rejection, output and persistence assertions | In progress |
| P3 | Discovery, reviewed report/specification, coverage plan, agent task, host build, guest install, paired check, visual review, delivery | End-to-end source-linked cases with explicit scope and remaining differences | In progress |
| P4 | Control takeover, interrupted action, reconnect, snapshot restore, time and data resets | No blind action retries; new run/session identity; rejected old results | In progress |
| P5 | Agent-first bilingual docs, wheel resources, examples and clean installation | Installed-wheel checks; two sample applications and one physical Mac recheck | In progress |
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
  PNG hashes); 26 exact unique screenshots have been inspected so far. This indexed
  subset is not a complete fixture visual review or delivery. No full acceptance
  is claimed. Selected Unicode editor, reopened second document, both inspectors
  and wrapping Off/relaunch/Reset screens agree in the inspected first-round
  states. Native save panels retain default-directory, extension-display and
  transient focus/button-state differences. App names, run-scoped paths and the
  desktop clock also differ; no masks were declared. Preserve these differences
  and review every remaining full pair before attempting delivery. Stocks retains
  its complete adverse 195-pair review, independently of this partial fixture review.

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
