# Owned macOS behavior fixture

This is an **original test application**, not an independently rebuilt delivery.
It supplies deterministic, offline native AppKit behavior for the macOS acceptance
plan. The published iOS examples and workflows are unchanged.

Build on an Apple Silicon Mac with Xcode command-line tools. Choose a fresh output
directory; failed builds and source/log snapshots remain in that directory:

```sh
.venv/bin/python examples/macos/BehaviorFixture/build.py \
  --out cases/mac-fixture-build
.venv/bin/copyapp mac inspect \
  --app cases/mac-fixture-build/BehaviorFixture.app --out cases/mac-fixture-index
.venv/bin/copyapp verify cases/mac-fixture-index
```

The builder saves its inputs, compiler/signing diagnostics and binary hash. It
signs the original fixture ad-hoc, verifies the signature and does not launch or
install it. `build.json` is a development build log, not a Copy APP delivery case.
`mac inspect` proves the static package inventory only.

The Bundle ID is `dev.copyapp.fixture.Behavior`, version 1.0, build 2. Use the
registered guest's actual App path after copying the reviewed original there;
collect it with `mac acquire` and compare its full package hash to the static
index. Do not use `mac install` for an original: that command is for a reviewed
independent rebuild. Keep host/guest and each original/rebuilt build separate.

## Behavior to observe before freezing flows

| Surface | Intended behavior | Evidence to capture |
| --- | --- | --- |
| Editor | Plain UTF-8 text; character, whitespace-separated word and UTF-8 byte counts | AX text plus actual saved bytes |
| File → Save As / Open | Native panels; saving retains exact UTF-8 bytes; opening creates another document | Panel/AX captures, saved output, reopened text |
| File → New | A new numbered window, Command-N | Two distinct document windows and precise Window-menu selection |
| Tools → Show Inspector | A separate window with the current document's counts | Window identity and count text |
| File → Export Summary | JSON with text, characters, words, utf8_bytes and wrapping | Full expected JSON assertion |
| Tools → Toggle Wrapping | Global fixture setting, Command-Shift-W, persisted across normal quit/relaunch | Before/after status plus a stopped-process check and fresh launch |
| Tools → Reset Fixture Settings | Set fixture wrapping to On; touches only this App's preference key | Assert the restored status before another run |
| Window menu | Switch/close/minimize native windows | Exact titles/identifiers; OS-injected commands require separate scope review |

An empty document has zero characters and words. Character count uses Swift
String grapheme clusters; UTF-8 bytes are counted separately. Documents are not
autosaved and close/quit without an unsaved-change prompt. Open panels accept
plain text; summary export uses JSON. No network, account or payment is involved.
The setting key is `fixture.wrap` in this Bundle ID's UserDefaults. This describes
the fixture's intended behavior; actual replay and comparison remain required.

Use scoped selectors: `fixture.editor` and `fixture.status` repeat across document
windows. Document titles are `Fixture Document N`; inspectors are `Fixture
Inspector N`. An ambiguous selector must fail rather than picking the first node.

Prepare at least three distinct **observed** flow cases, covering edit/save/reopen,
setting quit/relaunch persistence, and multiple windows/inspector/summary export.
Use fresh run-scoped output paths and no replacement of existing files. Observe
the real guest panels and AX before authoring replay selectors; do not substitute
host coordinates or treat this checklist as accepted playbooks. Freeze the reviewed
known inventory/target before independently implementing the rebuild under another
Bundle ID. Then compare every selected flow for three rounds, with full image and
output review. An original-only smoke test cannot satisfy any paired-delivery gate.

## Recorded development scope

On 2026-10-21, the host's build-1 compilation failure was retained, and build-2
(version 1.0/build 1) was opened through the computer-use UI. Editing, native save
and open panels, an inspector, JSON output and wrapping across quit/relaunch were
observed. The saved test text was exactly 32 UTF-8 bytes, and its summary contained
the asserted six words and 32 characters/bytes. This was a host original-only
smoke test, with manually recorded observations, not a verified reconstruction.

Build-3 (version 1.0/build 2) adds the native Window menu. It compiled/signed and
passed its static index verifier. Its actual UI showed two listed documents and
switched from Document 2 back to Document 1 through that menu. The fixture was
then quit and its process absence checked. Earlier observations from another
binary are not merged into this build's acceptance. Logs and output files remain
under ignored `cases/macos-owned-fixture-20261021/`.

Guest replay, independent reconstruction, three paired rounds and physical-Mac
reconstruction recheck are still outstanding. Follow
[the implementation ledger](../../../docs/macos-implementation-plan.md),
[Mac skill](../../../skills/copyapp-mac/SKILL.md) and
[paired check contract](../../../docs/macos-checks.md).
