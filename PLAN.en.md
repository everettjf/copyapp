# Copy APP implementation plan

**Language:** English | [简体中文](PLAN.md)

The [Chinese plan](PLAN.md) contains the original full architecture, acceptance criteria and chronological experiment log. This English plan describes the current product contract and remaining work. For exact commands and handoffs, read the [workflow guide](docs/copy-workflow.md).

## Product contract

Copy APP has two consecutive jobs:

1. **Analyze:** On a specified jailbroken iPhone, acquire and verify an installed app's package, selected sandbox/UI/runtime evidence and relevant native code. Deliver a readable, cited report and a machine-readable `feature-spec.json`.
2. **Rebuild:** Implement selected behavior in an independent, runnable iOS app. Install it on the specified real device, replay paired flows and deliver explicit behavior and visual differences.

A passing case proves only the selected, observed flows. It cannot recover the original source code, unseen server implementation or arbitrary untested app behavior. The first-version acceptance target is a three-flow analysis-to-rebuild loop for one real app, followed by reuse on a second technology stack. The original plan also specifies iOS 16/17/26 validation; the user has deferred the latter two devices for now.

## Architecture

- **Device:** Jailbroken iPhone with a bounded UI service, package/sandbox acquisition helper, Frida runtime connection and an interchangeable package recovery path.
- **Mac:** Versioned `copyapp` CLI for device selection, iOS MCP/iCTRL routing, evidence cases, Mach-O/Objective-C indexing, direct Ghidra analysis when selected, reporting, Xcode builds and paired real-device checks.
- **Agent:** Codex or Claude Code follows repository skills. In an active session, `--agent-provider current` writes tasks and pauses without launching a nested Agent. In an independent terminal, `codex` or `claude` can be launched by the workflow, but that autonomous end-to-end path is not yet validated.
- **Evidence:** Every case records the exact device, app, version when available, script bytes, timestamps, raw observations and source hashes. Reports label direct observations, interpretations and unknowns separately.

REA is optional. The default path uses Copy APP's own bounded analysis and device tools; `ghidra-direct` uses an external Ghidra installation and JDK for function pseudocode.

## Milestones and current evidence

| Milestone | Acceptance gate | Current state |
| --- | --- | --- |
| M0 Device baseline | Inventory and capability checks on all target phones | XR verified; iOS 17/26 deferred |
| M1 Device control | Repeatable bounded UI flows, one active touch backend, recoverable failures | XR iOS MCP and selected iCTRL paths verified; cross-version work deferred |
| M2 Evidence acquisition | Package and encrypted Mach-O status, sandbox/runtime evidence with source checks | XR Kimi and DeepSeek full-package recovery, several app pilots and known-source fixture verified; broader protection strategies pending |
| M3 Analysis report | Major selected-flow claims linked to UI, code and data evidence or marked unknown | Reviewed XR reports and direct Ghidra path available; arbitrary-app semantic interpretation remains Agent work |
| M4 Real-app pilot | Reviewable deep report and executable feature specification | XR Compass, Calculator, DeepSeek and Clock selected-flow pilots exist; coverage varies by app |
| M5 Rebuild loop | Independent app on real phone, paired behavior and screenshot review | XR Clock current-agent three-flow parent complete; 3/3 assertions and 10 reviewed image pairs with minor differences |
| M6 Product entry | Reliable one-request flow, recovery and reuse on a second stack | Current-agent discovery handoff now reaches XR analysis review; autonomous external-Agent zero-shot creation and whole-app generality remain unverified |

The real XR `--auto-discover --agent-provider current` trial at [its parent case](cases/clock-current-auto-workflow-20261016/manifest.json) replayed three previously authored Clock flows and reached `analysis_agent_needs_review`. This validates the handoff and device evidence chain, not model-authored discovery. A separate [completed Clock parent](cases/clock-current-workflow-live-20261016/manifest.json) proves the downstream report, rebuild, install and selected-flow delivery, using existing independent source as a starting point. The two trials together do not establish zero-shot cloning.

## Next engineering gates

1. Have the active agent author discovery scripts from a new app's real UI, without relying on previously saved scripts; retain failed attempts and verify safe resumption.
2. Produce a formal report and independent source from a fresh target under the single parent workflow, then compare and repair selected flows on XR.
3. Exercise an independent terminal run with a real Codex or Claude CLI and record its output and delivery gates.
4. Extend app coverage across different UI technologies and protection states; quantify discovery coverage and failures.
5. When the user resumes those devices, test iOS 17 and 26 independently. Do not extrapolate from XR.

Keep credentials, IPA snapshots, screenshots and raw sandbox data in ignored local `cases/`. A hash proves consistency of saved bytes, not the correctness of an interpretation.
