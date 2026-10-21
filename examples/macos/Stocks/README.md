# Stocks selected-behavior example

An independent AppKit example based on observed Apple Stocks 8.0 (2028) behavior
in a named ChatComputer macOS 27.0.1 guest. Bundle ID:
`dev.copyapp.examples.Stocks`. Original Apple binaries, artwork, news articles and
account data are not included. Curves are generated; prices are **illustrative
offline data**, labelled inside the App. This example has no live market service.

Ask the current Codex or Claude Code agent:

```text
Read AGENTS.md and skills/copyapp-mac/SKILL.md. Work on examples/macos/Stocks.
Use ChatComputer and the bounded collector to identify the exact guest and Stocks
build. Review and replay its three example playbooks from an inspected AAPL detail
with a blank search field. Preserve failures and freeze the reviewed known scope
before changing this independent example. Build, install at a separate guest path,
compare the selected flows and disclose visual/data differences. Keep iOS support
intact. Do not merge the development branch.
```

The current selected scope is symbol search/detail navigation, chart-period
selection with quit/relaunch persistence, and creation/management of local named
watchlists. The reviewed original inventory has 11 known capabilities; these three
are a target of 3/11 (27.27%) of that inventory. This is a target, not verified
coverage or a whole-App completeness estimate.

The original scripts in `playbooks/` target `/System/Applications/Stocks.app`.
Use them only after acquiring the actual original and inspecting its state. They
search MSFT, switch the AAPL chart period, and create then remove the test-only
`CopyAPP Test` watchlist. An unexpected dialog, duplicate test name or failed input
requires inspection. Generated rebuild plans change only App identity/path; do not
edit a frozen plan's scripts to make a clone pass.

The search script uses reviewed ticker-text click points after unique AX assertions
and bounded settling waits. It requires the observed 1080×670 window at (100, 56)
on the 1280×800 screenshot display. Inspect that frame before a standalone run;
paired checks freeze and validate it. If the frame or interface changes, prepare
a new reviewed script and evidence chain instead of editing a frozen case.

To build a local demo without the evidence workflow:

```sh
.venv/bin/python examples/macos/Stocks/build.py --out cases/stocks-demo-build
```

This compiles/signs a fresh `.app` and retains source/build diagnostics. Open the
resulting App normally. Its menu supports New Watchlist and Manage Watchlists;
search matches the small bundled symbol catalog. It stores periods and watchlist
names in its own UserDefaults domain. It does not change Apple's Stocks data.

For a source-linked guest build, use the reviewed `mac rebuild-plan` and:

```sh
.venv/bin/copyapp mac build-app --plan <PLAN_CASE> \
  --swift-source Sources/Main.swift --info-plist Info.plist --out <NEW_BUILD_CASE>
.venv/bin/copyapp verify <NEW_BUILD_CASE>
.venv/bin/copyapp mac install --build <NEW_BUILD_CASE> --out <NEW_INSTALL_CASE>
.venv/bin/copyapp verify <NEW_INSTALL_CASE>
```

Then follow `docs/macos-checks.md` for paired runs and full screenshot review.
Compilation, installation or isolated text assertions cannot establish acceptance.

Remaining differences include the restricted local symbol catalog, generated
charts, illustrative metrics, independent overview cards, simplified modal UI,
and unimplemented symbol membership/reordering, article reading, sharing, calendar,
additional viewer windows and iCloud sync. Native function semantics and a
physical-Mac reconstruction recheck are not established. Keep the parent PR in draft.
