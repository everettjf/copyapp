# Copy APP plan

[English](PLAN.en.md) · [简体中文](PLAN.md) · [Current status](docs/current-status.md)

## Product contract

Copy APP has two jobs on a jailbroken iPhone: **Analyze** an installed app into a reviewed, source-linked report and feature specification; then **Rebuild** a selected set of behavior as an independent, runnable iOS app and compare it with the original on the same device. A coding agent performs interpretation and implementation. The CLI collects and verifies evidence, controls the device, and records gaps. The [workflow](docs/copy-workflow.md), [architecture](docs/architecture.md) and [coverage method](docs/coverage-targets.md) are the operational specifications.

A report should cover app identity, permissions, package and embedded libraries, UI/navigation, resources, sandbox/data model, network and system integrations, native class/function evidence, selected runtime behavior, implementation hypotheses and unknowns. Material claims cite the device, app build and source case. Decompiled pseudocode is not original source. Server-only behavior cannot be inferred from client code.

The rebuild milestone is selected after a known-capability inventory. A simple app may target its entire known inventory; a complex app should deliver a useful first slice and report deferred, blocked and unknown behavior. A selected-flow pass count must never be called whole-app coverage.

## Current baseline

- **Published:** v0.1.0 is the only Git tag and GitHub Release. There are no published v0.1.1+ versions.
- **iOS 16:** iPhone XR/Dopamine rootless has selected report-to-rebuild paths. SSH acquisition works despite an optional DVT file-listing failure.
- **iOS 17:** iPhone 14/Relaxin RootHide has current-code Calculator acquisition, four original/independent-app iOS MCP checks, five reviewed image pairs and a five-hit original Frida trace. An extra iCTRL clone replay has an unresolved malformed HTTP response.
- **iOS 26:** iPhone 11/Relaxin RootHide has selected Calculator and Clock deliveries. iOS MCP black-frame rejection and bounded recovery passed observed runs.
- **Host:** 342 local tests and a fresh GitHub macOS bootstrap, test and isolated-wheel check passed at `1499222`. A second physical Mac's first phone onboarding is deferred.

These are named-device, selected-flow results. See [current status](docs/current-status.md) for limits. Raw cases remain ignored local evidence, not release assets.

## Next gates

1. Diagnose and fix or explicitly scope the iOS 17 iCTRL multi-step transport failure. Do not replay an uncertain action without checking device state.
2. Investigate XR's optional DVT file-listing failure while keeping the working SSH acquisition route.
3. Check reboot/rejailbreak durability and longer-running backend reliability on the supported devices.
4. When work on a second physical Mac resumes, follow the setup guide from first USB trust through SSH pinning, UI control, acquisition and a signed or TrollStore rebuild.
5. Review the final implementation diff and bilingual docs, run tests on the release commit, set the next package version once, create one tag and publish one GitHub Release. State the selected flows and remaining limits in those notes.

Future work after that release includes unfamiliar-app autonomous discovery, more complete selected-app behavior, persistence/backend boundaries and stronger visual fidelity. Do not promise an arbitrary complete clone before those checks exist.
