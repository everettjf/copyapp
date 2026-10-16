# Translate XR workflow: analysis to runnable clone

**Language:** English | [简体中文](translate-xr-workflow.zh-CN.md)

This is a verified Copy APP v1 case on a jailbroken iPhone XR running iOS 16.1.1. The target was Apple's Translate 1.0 (216.4), `com.apple.Translate`. The independent probe is `com.copyapp.translate.freshprobe`. The [parent workflow](../cases/translate-current-workflow-20261016/manifest.json) finished with `complete` status without REA. Xcode 27 built the clone with an iOS 16.0 deployment target; the phone performed installation and UI replay.

## Covered behavior

| Flow | Original and clone result | Boundary |
| --- | --- | --- |
| Text input | Open input card, enter synthetic `hello`, verify visible text, close to Translation | Does not submit or translate text |
| Favorites empty state | Open Favorites, verify empty message, return to Translation | No saved favorite was tested |
| Conversation idle | Open Conversation, verify idle prompt, return to Translation | No microphone or speech action was tested |

The [paired XR check](../cases/translate-current-workflow-20261016/rebuild-agent/rebuild-check-v4/report.md) completed all three flows with two saved screenshot pairs per flow. The [six-image review](../cases/translate-current-workflow-20261016/rebuild-agent/visual-review/report.md) found only minor visual differences in this selected scope: icons, small text offsets and language-card details. This is selected behavior verification, not complete Translate equivalence.

## Analysis evidence

- The [reviewed report](../cases/translate-current-workflow-20261016/analysis-agent/reviewed-report/report.md) links package, Objective-C metadata, sandbox, UI screenshots, Frida traces and bounded ARM64 assembly. It distinguishes observations from unresolved implementation details.
- The main executable and CacheDelete extension were already unencrypted in the acquired package; the decryption helper recovered no code bytes. The acquisition and header checks remain in the parent case.
- The main binary links UIKit, SwiftUI, AVFoundation, Vision/VisionKit, CoreData and Apple's private Translation framework. A linked framework is an investigation lead, not proof of the path taken by a tested interaction.
- On the input-card close tap, the indexed `TranslateInputCard::closeButtonPressed` static entry at offset `0x1abf1c` had one Frida hit, versus zero on focus and typing. Opening Favorites gave one hit at `FavoritesViewController::viewDidLoad`, offset `0xd0544`, versus zero on return. These are bounded code-to-UI observations, not recovered original source.
- The sandbox inventory found `Library/Application Support/Translate.sqlite`. A schema-only read found `ZTRANSLATION` and related Core Data tables, including favorite-date, source-input and target-result columns. No rows were read. The three bounded URLSession resume observers recorded zero events; that does not establish offline operation.

## Delivery and reproducibility

The clone source is in [TranslateFreshProbe](../rebuild/TranslateFreshProbe). [Installation evidence](../cases/translate-current-workflow-20261016/rebuild-agent/install-v4/install.json), [agent delivery](../cases/translate-current-workflow-20261016/rebuild-agent/agent-delivery/report.md) and the parent manifest bind the installed IPA, device and report to the selected scripts. The delivered IPA SHA-256 is `008a2e18b5758b4c096712b96592bfebbce111180d8bc03080e24624710bab1c`.

From this repository, `sh rebuild/TranslateFreshProbe/package.sh` rebuilds the independent project using Xcode, XcodeGen and `ldid`. Run `.venv/bin/copyapp verify cases/translate-current-workflow-20261016` to recheck the saved parent evidence. Device replay requires the paired, jailbroken XR and the existing USB services.

The iCTRL backend supplied verified text input. On the same XR, iOS MCP reported successful text events without visible text in Translate; the failed probes are retained under local `cases/`. A playbook checks the screen after typing and stops if the text is absent. The runner also reuses an already active iCTRL service and has bounded startup; fresh iCTRL replay terminates and relaunches the target through XCTest when Instruments is unavailable.

## Remaining work

Submitting text, actual translation output, language selection and downloads, camera OCR, speech permissions and recognition, audio playback, populated favorites, persistence mutations, broader sandbox interpretation and an external autonomous Codex/Claude CLI run remain unverified. The iOS 17 and 26 phones were deliberately left out of this test round.
