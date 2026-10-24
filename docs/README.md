# Copy APP documentation

[English](README.md) · [简体中文](README.zh-CN.md) · [Project README](../README.md)

Copy APP supports jailbroken iOS and macOS in **v0.2.0**. **v0.1.2** is the previous iOS-only release. Begin with the [agent-led first task](first-run-agent.md) or [manual setup guide](setup.md), then use the guides below for the task at hand. Historical development checkpoints and superseded experiment documents have been removed from the working tree; Git history retains their original commits. Raw device evidence remains local under ignored `cases/`.

| Topic | Read this |
| --- | --- |
| New Mac and phone | [Setup and first survey](setup.md) |
| macOS App preview support | [ChatComputer integration](macos-support.md) · [Acceptance ledger](macos-implementation-plan.md) |
| How the parts fit | [Architecture and evidence model](architecture.md) |
| Illustrated project story | [Copy APP overview (简体中文)](articles/copyapp-overview.zh-CN.md) |
| Tested phones and open limits | [Current status](current-status.md) |
| Standard and enhanced iPhone development | [Usage and limits](ios-standard-mode.md) · [Acceptance ledger](ios-device-support-acceptance.md) · [Implementation plan (简体中文)](ios-device-support-plan.zh-CN.md) |
| Deferred follow-up work | [TODO](../TODO.md) |
| End-to-end analyze and rebuild | [Workflow](copy-workflow.md) |
| Choosing a realistic clone goal | [Coverage targets](coverage-targets.md) |
| Give a coding agent a first task | [First-run agent task](first-run-agent.md) |
| UI playbooks | [Gestures](ui-gesture-playbooks.md) · [Text entry](ui-text-playbooks.md) |
| Decompilers and reverse-engineering tools | [Tool matrix, setup and agent tasks](reverse-engineering-tools.md) |
| Native and package analysis | [Encrypted-package recovery](full-package-decryption.md) · [Direct Hopper integration](rea-hopper-integration.md) · [REA independence](rea-independence.md) |
| Published version | [v0.2.0 release notes](releases/v0.2.0.md) / [v0.1.2 archive](releases/v0.1.2.md) · [v0.1.1 archive](releases/v0.1.1.md) · [v0.1.0 archive](releases/v0.1.0.md) |
| Source examples | [iOS and macOS examples](../examples/README.md) · [Report input formats](../examples/report-inputs/README.md) |

The six JSON files in [`examples/report-inputs/`](../examples/report-inputs/README.md) are **historical, target-specific examples** used by pilot composition scripts and the analysis skill. They are not current device reports. Re-evaluate every claim for a new target app.
