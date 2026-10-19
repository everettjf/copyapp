# Current support and validation

[English](current-status.md) · [简体中文](current-status.zh-CN.md) · [Documentation](README.md)

**Published version:** [v0.1.1](releases/v0.1.1.md). This page describes the named-device scope tested through 2026-10-18 and the remaining limits. The [v0.1.0 notes](releases/v0.1.0.md) retain the original release record.

## Named-device results

| Device | Current-code result | Boundaries |
| --- | --- | --- |
| iPhone XR, iOS 16.1.1, Dopamine rootless | SSH package/sandbox route, Frida, iOS MCP and iCTRL; selected Notes, Calculator, Translate and Clock analysis/rebuild paths. A recent Counter original/clone check passed after aligning state. | Optional developer file listing returns `ConnectionTerminatedError` on this phone. SSH-backed acquisition remains usable. |
| iPhone 14, iOS 17.3.1, Relaxin/RootHide | Current-code `doctor` and original Calculator acquisition verified; four iOS MCP original/independent-app flows passed final assertions (`15`, `0.3`, `−7`, `0.5`), with five image pairs reviewed as minor differences. Original-App Frida tracing hit the selected button method once on each of five taps. | An extra iCTRL rebuilt-app paired replay failed at equals with `ictrl: malformed HTTP response` on two attempts. Runner health later recovered; multi-step reliability is not established. |
| iPhone 11, iOS 26.0.1, Relaxin/RootHide | USB/SSH acquisition, iCTRL and iOS MCP UI, Frida attach, reviewed Calculator and Clock reports, signed independent apps, selected arithmetic and Stopwatch paired checks. A Clock Start → Stop → Reset comparison and visual review passed. | iOS MCP may capture a black app area after Instruments fresh launch. Rejected frames and bounded Home/relaunch recovery are recorded; long-term reliability is unknown. |

The most recent local suite passed **342 tests**; the [macOS bootstrap, unit-test and isolated-wheel run](https://github.com/everettjf/copyapp/actions/runs/39151891412) passed on commit `1499222`. Saved case evidence, including failed attempts, stays under ignored local `cases/` and is not shipped with the repository or release. `copyapp verify` checks case consistency and source binding; it does not prove a reverse-engineering interpretation or whole-app equivalence.

## What is still open

- iCTRL's iOS 17 rebuilt-app multi-step transport failure needs a verified fix. The v0.1.1 release records this limitation; the selected iOS MCP checks remain usable.
- XR's optional DVT developer-file listing fails, although its SSH acquisition route works.
- Reboot/rejailbreak persistence and longer-running UI/backend reliability need dedicated checks.
- A full first-use phone onboarding on a **second physical Mac** has not been tested; that work is deferred for now. A fresh checkout on the same Mac and a clean GitHub-hosted macOS bootstrap passed narrower setup checks.
- Selected-flow deliveries do not demonstrate arbitrary-app discovery, complete app parity, server-side behavior, or pixel-perfect visuals. Some independent app projects adapted existing source; distinguish those from new-source work.

### Next verification pass

| Open item | Evidence needed to close it |
| --- | --- |
| iOS 17 iCTRL multi-step replay | Capture the failing response and runner state, fix or isolate the transport, then replay the original and rebuilt flows repeatedly with final-state and screenshot checks. Until then, use the verified iOS MCP route for those selected checks. |
| XR DVT file listing | Reproduce with a pinned device and developer service state; either demonstrate a working listing or document it as an optional-path limitation. SSH package and sandbox acquisition already work. |
| Reboot / rejailbreak durability | Reboot each tested phone, restore its jailbreak and services, run `doctor`, acquire a small case, and complete a UI check. Include iOS 26 black-frame recovery and longer runs. |
| Second physical Mac | Follow the public setup guide from a fresh checkout and USB trust through SSH key pinning, UI capture, package acquisition and a signed or TrollStore-installed rebuild. |
| Broader app coverage | Test an unfamiliar app with a reviewed capability inventory, source-linked report, named rebuild target, paired flows and documented unknowns. Do not infer full-app parity from a few passing flows. |

The [illustrated overview](articles/copyapp-overview.zh-CN.md) and [system diagram](assets/architecture-overview.svg) show the current workflow and selected public evidence examples. The underlying raw cases remain local.

## Publication rule

Number only tagged, published releases. The [current plan](../PLAN.en.md) tracks the next verification work. Raw IPAs, account data, sandbox exports and private keys are never release assets.
