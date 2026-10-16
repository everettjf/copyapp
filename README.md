# Copy APP

**Language:** English | [简体中文](README.zh-CN.md)

Copy APP is a local, evidence-gated workflow for analyzing an installed iOS app on a jailbroken iPhone and rebuilding selected behavior as an independent, runnable iOS app. It acquires package and sandbox evidence, inspects native code, captures UI and runtime behavior, produces a cited report and feature specification, then builds and compares a clone on the same device.

The workflow verifies evidence identity and selected UI flows. It does **not** claim complete equivalence to an arbitrary app. The iPhone XR running iOS 16.1.1 is the tested device; iOS 17 and 26 testing is deferred at the user's request.

## Start here

From an active Codex or Claude Code session, use the current agent as the worker:

```sh
.venv/bin/copyapp copy \
  --udid <DEVICE_UDID> --bundle <ORIGINAL_BUNDLE_ID> \
  --auto-discover --agent-provider current \
  --project rebuild/<NEW_PROJECT> --rebuilt-bundle <NEW_BUNDLE_ID> \
  --out cases/<NEW_WORKFLOW_CASE>
```

The command first writes `<CASE>/discovery-agent/TASK.md` and pauses. The current agent observes the real app, writes 3–12 bounded UI playbooks, and runs `copyapp discover-check` against the specified device. Resume the same `copyapp copy` command with `--resume` after its discovery case verifies. Preparation then collects package, sandbox, UI, runtime and optional network evidence. The workflow pauses again for a formal analysis report and `analysis-delivery`, and once more for independent app implementation, installation, paired real-device comparison, screenshot review and `agent-delivery`. Each phase resumes only after its evidence passes verification. This mode never starts a nested coding-agent process.

If representative flows already exist, replace `--auto-discover` with repeated `--script <PLAYBOOK>` or `--discovery <VERIFIED_DISCOVERY_CASE>`. These options are mutually exclusive. An independent terminal may instead choose `--agent-provider codex` or `claude` for external CLI execution; the external model's end-to-end autonomous run has not yet been validated. Agent process exit alone is never accepted as a finished report or clone.

See [the workflow guide](docs/copy-workflow.md) for the exact handoffs, commands and evidence gates, or [its Chinese version](docs/copy-workflow.zh-CN.md). Agents working in this repository should follow [the Copy APP skill](skills/copyapp-copy/SKILL.md) and [repository guidance](AGENTS.md).

## Capabilities and evidence

| Stage | Available capability | Verified scope |
| --- | --- | --- |
| Device and UI | Exact USB device selection, screenshot, foreground identity, accessibility tree, bounded taps, stable screenshots | iPhone XR; iOS MCP and selected iCTRL paths |
| Acquisition | App package and sandbox metadata collection, full-package Mach-O recovery, source hashes | XR; encrypted Kimi and DeepSeek main apps and extensions |
| Native analysis | Mach-O and Objective-C indexing, Frida method/branch observations, bounded ARM64 inspection, direct Ghidra pseudocode | XR Compass, Calculator, Clock, DeepSeek and a known-source fixture |
| Report | Verified investigation cases, reviewed semantic report, feature specification, source-linked delivery | Selected, observed flows; function interpretations still require human or agent review |
| Rebuild | Independent Xcode project, real-device installation, paired flow replay, UIKit assertions, visual review and delivery | XR pilots with recorded minor visual differences |

REA is optional. The default path runs without it; direct Ghidra can be enabled with `--analysis-provider ghidra-direct --ghidra-dir <DIR> --java-home <DIR>`. Ghidra and the JDK remain external tools for that option. See [REA independence](docs/rea-independence.md) for the integration boundary.

A complete current-agent, three-flow Clock case is saved at [the XR workflow manifest](cases/clock-current-workflow-live-20261016/manifest.json). Its [reviewed report](cases/clock-current-workflow-live-20261016/analysis-agent/reviewed-report/report.md), [independent source](rebuild/ClockCurrentProbe) and [device delivery](cases/clock-current-workflow-live-20261016/rebuild-agent/agent-delivery/report.md) cover world-city selection, an unsaved alarm edit and stopwatch start/stop/reset. A second [XR auto-discovery parent](cases/clock-current-auto-workflow-20261016/manifest.json) now joins discovery, [formal report](cases/clock-current-auto-workflow-20261016/analysis-agent/reviewed-report/report.md), [independent source](rebuild/ClockCurrentAutoProbe) and [device delivery](cases/clock-current-auto-workflow-20261016/rebuild-agent/agent-delivery/report.md) in one verified case: 3/3 selected behavior and final-view checks passed; all 10 screenshot pairs were reviewed with minor differences and no major difference. This second run reused previously authored discovery scripts and adapted the earlier independent Clock implementation. It validates orchestration and selected-flow delivery, not autonomous script authoring, zero-shot source generation or whole-app equivalence.

A fresh [Calculator auto-discovery parent](cases/calculator-current-auto-workflow-20261016/manifest.json) now tests those missing current-agent handoffs on the XR. The current agent observed the real Calculator UI, wrote three new playbooks, retained failed discovery attempts, produced a [source-linked report](cases/calculator-current-auto-workflow-20261016/analysis-agent/reviewed-report/report.md), and wrote a new [UIKit clone](rebuild/CalculatorFreshProbe) from an empty project. The installed clone passed 3/3 paired behavior and terminal UIKit assertions for decimal addition (`0.3`), negative addition (`−7`) and percent (`0.5`). All three [screenshot pairs](cases/calculator-current-auto-workflow-20261016/rebuild-agent/visual-review-v2/report.md) were reviewed as minor differences, with none major; the [delivery](cases/calculator-current-auto-workflow-20261016/rebuild-agent/agent-delivery/report.md) and parent both verify. This is one selected-flow, current-agent result; it does not establish general discovery, external CLI autonomy or complete Calculator behavior.

Other local XR pilots include [Compass](docs/compass-xr-analysis.md), [Calculator](docs/calculator-button-dispatch-xr.md), [DeepSeek](docs/deepseek-three-flow-xr-verification.md) and [Clock](cases/clock-six-flow-no-rea-reviewed-report-v8-20261015/report.md), plus a known-source fixture. The current roadmap is in [the English plan](PLAN.en.md); the full historical experiment log is in [the Chinese plan](PLAN.md).

## Verification and limits

```sh
.venv/bin/copyapp devices
.venv/bin/copyapp apps --udid <DEVICE_UDID> --all
.venv/bin/copyapp verify cases/<CASE>
.venv/bin/python -m unittest discover -s tests
```

`apps` lists user-installed apps by default. `--all` also lists system apps, including Calculator, Compass and Clock on the tested XR, so a target named by its display name can be resolved to an exact Bundle ID.

Formal reports now render a bounded Assets.car name list and a metadata-only sandbox summary when those indexes exist. A [deeper Calculator report](cases/calculator-ui-deep-report-20261016/report.md) and its [source-linked analysis delivery](cases/calculator-ui-deep-analysis-delivery-20261016/report.md) verify these appendices and add direct Ghidra evidence for the root view, keypad frame layout and result-view gesture setup. Resource names and storage-looking filenames are investigation leads, not evidence of runtime use; the three arithmetic flows did not exercise the display gestures.

`copyapp verify` checks recorded source links and file hashes. A matching hash does not prove that a decompiler interpretation is correct or that an app is functionally equivalent. Store raw IPA files, screenshots, sandbox snapshots, traces and credentials only in ignored local `cases/`. Reports should distinguish direct observations, inferences and unknown behavior.

The current gaps are general discovery and independent implementation across unfamiliar apps, a real external Codex/Claude CLI end-to-end run, broader app behavior and backend semantics, full sandbox and network interpretation, and cross-version validation. iOS 17 and 26 devices have not been run through this workflow.

## Documentation

- [End-to-end workflow](docs/copy-workflow.md) · [中文](docs/copy-workflow.zh-CN.md)
- [Implementation plan](PLAN.en.md) · [中文及详细试验记录](PLAN.md)
- [REA independence](docs/rea-independence.md)
- [Copy APP agent skill](skills/copyapp-copy/SKILL.md)
- [Repository agent instructions](AGENTS.md)
- [Full Chinese README and historical evidence links](README.zh-CN.md)
