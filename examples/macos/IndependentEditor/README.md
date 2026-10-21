# Independent selected-behavior editor

This native AppKit example implements the reviewed behavior of the owned
`BehaviorFixture` sample under a separate Bundle ID (`dev.copyapp.examples.Editor`).
It provides plain text documents, UTF-8 Save/Open, per-document inspectors, JSON
summary export and a saved wrapping preference. The compatibility document titles
and AX identifiers allow the same bounded playbooks to run on both applications.

The reviewed target and verified selected delivery both cover seven of nine named
known capabilities (77.78%). Three rounds passed 9/9 selected behavior comparisons;
all 285 full screenshot pairs were reviewed, with zero major and 285 minor
differences. Independent App identity, clock/caret/Dock phases and native-panel
directory history/focus remain recorded. Clipboard/Undo behavior and general window management are
deferred. Arbitrary Unicode, long text, error paths, other OS builds and physical
Mac behavior are unverified. The original fixture source was available to the
author; this is a workflow acceptance example, not a blind reconstruction benchmark.

Local evidence begins at `cases/macos-owned-fixture-20261021/report-1` and the frozen
`rebuild-plan-3`; the accepted historical chain is `rebuilt-build-4`,
`rebuilt-install-3`, `check-plan-3`, `check-3`, `visual-review-3` and `delivery-1`.
Raw evidence remains ignored and local. Older failed/adverse attempts are retained.
Build with `copyapp mac build-app --plan <PLAN> --swift-source
Sources/Main.swift --info-plist Info.plist --out <NEW_BUILD_CASE>`. Install and
compare through the Mac skill; a successful build is not acceptance.
