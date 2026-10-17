# Copy APP implementation plan

**Language:** English | [简体中文](PLAN.md)

The [Chinese plan](PLAN.md) contains the original full architecture, acceptance criteria and chronological experiment log. This English plan describes the current product contract and remaining work. For exact commands and handoffs, read the [workflow guide](docs/copy-workflow.md).

**Latest XR milestone:** An [independent Codex CLI trial](docs/external-codex-xr-trial.md) completed the Calculator analyze → rebuild chain on iOS 16.1.1. Three selected behavior assertions passed and three screenshot pairs were reviewed with minor differences. Previously verified discovery scripts and an earlier independent clone were reused, so autonomous discovery and unfamiliar-app implementation remain open. The [Translate workflow](docs/translate-xr-workflow.md) separately exercises a second UI stack.

## Product contract

Copy APP has two consecutive jobs:

1. **Analyze:** On a specified jailbroken iPhone, acquire and verify an installed app's package, selected sandbox/UI/runtime evidence and relevant native code. Deliver a readable, cited report and a machine-readable `feature-spec.json`.
2. **Rebuild:** Implement selected behavior in an independent, runnable iOS app. Install it on the specified real device, replay paired flows and deliver explicit behavior and visual differences.

A passing case proves only the selected, observed flows. It cannot recover the original source code, unseen server implementation or arbitrary untested app behavior. The first-version acceptance target is a three-flow analysis-to-rebuild loop for one real app, followed by reuse on a second technology stack. The original plan also specifies iOS 16/17/26 validation. The [v0.1.1 two-device run](docs/releases/v0.1.1.md) verifies selected paths on iOS 16 and 17; iOS 26 remains untested.

## Architecture

- **Device:** Jailbroken iPhone with a bounded UI service, package/sandbox acquisition helper, Frida runtime connection and an interchangeable package recovery path.
- **Mac:** Versioned `copyapp` CLI for device selection, iOS MCP/iCTRL routing, evidence cases, Mach-O/Objective-C indexing, direct Ghidra or Hopper analysis when selected, reporting, Xcode builds and paired real-device checks.
- **Agent:** Codex or Claude Code follows repository skills. In an active session, `--agent-provider current` writes tasks and pauses without launching a nested Agent. A standalone Codex CLI has completed the selected Calculator report, build, installation and comparison gates on the XR; the equivalent Claude CLI run remains untested.
- **Evidence:** Every case records the exact device, app, version when available, script bytes, timestamps, raw observations and source hashes. Reports label direct observations, interpretations and unknowns separately.

The REA command and provider bridge has been removed. Copy APP uses its own bounded analysis and device tools; `ghidra-direct` uses an external Ghidra installation and JDK; `hopper-direct` uses an external, licensed Hopper GUI installation in a normal macOS session. The selected-flow `copy` analysis-to-rebuild device workflow has been verified on the XR. Archived REA evidence remains readable for historical case verification.

## Milestones and current evidence

| Milestone | Acceptance gate | Current state |
| --- | --- | --- |
| M0 Device baseline | Inventory and capability checks on all target phones | XR/iOS 16 and iPhone 14/iOS 17 verified; iOS 26 untested |
| M1 Device control | Repeatable bounded UI flows, one active touch backend, recoverable failures | Three fixture flows passed both backends on iOS 17 and a formal iCTRL paired check on XR; iOS 26 untested |
| M2 Evidence acquisition | Package and encrypted Mach-O status, sandbox/runtime evidence with source checks | XR Kimi and DeepSeek full-package recovery, several app pilots and known-source fixture verified; broader protection strategies pending |
| M3 Analysis report | Major selected-flow claims linked to UI, code and data evidence or marked unknown | Reviewed XR reports and direct Ghidra path available; arbitrary-app semantic interpretation remains Agent work |
| M4 Real-app pilot | Reviewable deep report and executable feature specification | XR Compass, Calculator, DeepSeek and Clock selected-flow pilots exist; coverage varies by app |
| M5 Rebuild loop | Independent app on real phone, paired behavior and screenshot review | XR Clock and fresh Calculator current-agent parents complete; Calculator 3/3 assertions and 3 reviewed image pairs with minor differences |
| M6 Product entry | Reliable one-request flow, recovery and reuse on a second stack | Guided onboarding and a standalone Codex CLI selected-flow XR run verified; unfamiliar-app autonomy and whole-app generality remain unverified |

The real XR `--auto-discover --agent-provider current` trial at [its parent case](cases/clock-current-auto-workflow-20261016/manifest.json) replayed three previously authored Clock flows, produced a source-linked report, built and installed a distinct clone, and passed 3/3 selected behavior and final-view assertions. Ten screenshot pairs were reviewed with minor differences and no major difference; 517 parent evidence files verified. The clone adapted previously authored independent source. A separate [completed Clock parent](cases/clock-current-workflow-live-20261016/manifest.json) also verifies the downstream handoffs. Neither case establishes model-authored discovery or zero-shot cloning.

The [Calculator parent](cases/calculator-current-auto-workflow-20261016/manifest.json) closes that narrow evidence gap: the active agent authored three scripts from the XR's current UI and implemented [new UIKit source](rebuild/CalculatorFreshProbe) without reusing an earlier clone. A failed ambiguous clear-label replay and a later visual-layout repair are retained in the local case. The [formal report](cases/calculator-current-auto-workflow-20261016/analysis-agent/reviewed-report/report.md) combines current package/UI/Frida evidence with matching-hash direct Ghidra function cases, with the earlier collection times disclosed. On the same XR, 3/3 paired behavior and terminal view assertions passed; [three image pairs](cases/calculator-current-auto-workflow-20261016/rebuild-agent/visual-review-v2/report.md) show minor differences, none major. The [delivery](cases/calculator-current-auto-workflow-20261016/rebuild-agent/agent-delivery/report.md) and parent verify. The implementation covers only decimal addition, negative addition and percent, so it is not a complete Calculator clone.

The device-name entry now supports `copyapp apps --udid <UDID> --all` for system apps; the XR returned 182 installed entries, including Calculator, Compass and Clock. The report renderer adds bounded resource names and read-only sandbox metadata to the readable appendix. A [new Calculator report](cases/calculator-rich-inventory-report-20261016/report.md) and [analysis delivery](cases/calculator-rich-inventory-analysis-delivery-20261016/report.md) verify the new output against the same saved evidence. These entries do not prove runtime resource or file access.

The [latest Calculator analysis](cases/calculator-ui-deep-report-20261016/report.md) adds seven source-verified direct Ghidra function cases from the same 361,440-byte binary. It follows `CalculatorController.loadView` into the root-view builder, `CalculatorKeypadView.layoutSubviews` into the button-frame loop, and `DisplayViewController.loadView` into its lazy display view and gesture setup. The [analysis delivery](cases/calculator-ui-deep-analysis-delivery-20261016/report.md) still binds the same three observed XR scripts. Static UI construction is better explained. Later [gesture playbook tests](docs/ui-gesture-playbooks.md) observed a Calculator display swipe, while the private Calculate framework algorithm remains untested.

Gestures now pass through discovery, replay, bounded Frida/network windows, original/rebuild comparison and the delivery assertion gate. iOS MCP 0.1.4 exposes swipe, long press and double tap on the XR. A Calculator display swipe changed the result from `9` to `0` in an iCTRL accessibility assertion and was visually observed after an iOS MCP replay. Both backends completed bounded long-press and double-tap calls without a verified feature-specific outcome. iCTRL approximates requested swipe duration through velocity tiers and does not accept a caller-selected double-tap interval.

The original Calculator's `98→9` left-swipe deletion and the updated independent clone passed the same [paired XR script](cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-comparison/report.md). The new clone build 0.1.1 (3) also passed the [three existing arithmetic comparisons](cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-check/manifest.json); [three screenshot pairs](cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-visual-review/report.md) were reviewed as minor differences. This is selected-state behavior evidence, not a whole-app gesture or Calculator implementation claim.

The XR [Translate discovery case](cases/translate-xr-discovery-20261016/manifest.json) adds an unfamiliar app and a text-entry action: synthetic `hello` input, Favorites empty state and Conversation idle view all passed bounded iCTRL replay. The same iOS MCP text-input request reported dispatch but failed the visible-text assertion on Translate, so that path is not validated on this device. The [text guide](docs/ui-text-playbooks.md) records the backend evidence and limits. The later [Translate workflow](docs/translate-xr-workflow.md) completed a report and independent rebuild for these selected flows; actual translation submission remains untested.

## Next engineering gates

1. Exercise independent CLI discovery and implementation on an unfamiliar app without reusing prior scripts or clone source; optionally repeat with Claude CLI.
2. Extend fresh discovery and implementation to an unfamiliar app and different UI stack or protection state; quantify coverage and failures.
3. Expand selected-flow implementations into more of each app's behavior, including persistence and backend boundaries, with new paired checks.
4. Test iOS 26 independently if its jailbreak and device services are available. Do not extrapolate from XR or iOS 17.

Keep credentials, IPA snapshots, screenshots and raw sandbox data in ignored local `cases/`. A hash proves consistency of saved bytes, not the correctness of an interpretation.
