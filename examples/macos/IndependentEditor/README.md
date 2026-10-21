# Independent selected-behavior editor

This native AppKit example implements the reviewed behavior of the owned
`BehaviorFixture` sample under a separate Bundle ID (`dev.copyapp.examples.Editor`).
It provides plain text documents, UTF-8 Save/Open, per-document inspectors, JSON
summary export and a saved wrapping preference. The compatibility document titles
and AX identifiers allow the same bounded playbooks to run on both applications.

The reviewed target is seven of nine named known capabilities (77.78% target,
not verified coverage). Clipboard/Undo behavior and general window management are
deferred. Arbitrary Unicode, long text, error paths, other OS builds and physical
Mac behavior are unverified. The original fixture source was available to the
author; this is a workflow acceptance example, not a blind reconstruction benchmark.

Local evidence begins at `cases/macos-owned-fixture-20261021/report-1` and the frozen
`rebuild-plan-1`. Build with `copyapp mac build-app --plan <PLAN> --swift-source
Sources/Main.swift --info-plist Info.plist --out <NEW_BUILD_CASE>`. Install and
compare through the Mac skill; a successful build is not acceptance.
