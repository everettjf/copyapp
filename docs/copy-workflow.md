# Analyze → Rebuild workflow

[English](copy-workflow.md) · [简体中文](copy-workflow.zh-CN.md) · [Documentation](README.md)

Copy APP runs a resumable, evidence-gated job for one exact device and installed App build. Begin with [setup](setup.md) and `copyapp doctor`. Use `--agent-provider current` from an active Codex or Claude Code session; it pauses for the current agent's work without starting another agent process. `codex` and `claude` select external CLI processes when that is intended.

## 1. Discover representative behavior

```sh
.venv/bin/copyapp copy --udid <UDID> --bundle <ORIGINAL_BUNDLE> \
  --auto-discover --agent-provider current \
  --project rebuild/<NEW_PROJECT> --rebuilt-bundle <NEW_BUNDLE> \
  --out cases/<WORKFLOW>
```

The first pause writes `discovery-agent/TASK.md`. Observe the real App and author 3–12 distinct bounded UI playbooks. Each should identify its starting page, contain a meaningful action, assert an observable final state where possible, and save a stable screenshot. Run `copyapp discover-check` as directed by the task, verify its case, and resume the **same** `copy` command with `--resume`. Existing selected scripts may be supplied through repeated `--script <FILE>`; a verified discovery case may be passed with `--discovery <CASE>`. These alternatives replace `--auto-discover`.

Use one UI backend per playbook. When comparing original and clone, use the same backend and aligned starting state. Read the [gesture](ui-gesture-playbooks.md) and [text-entry](ui-text-playbooks.md) guides for action bounds. A successful action RPC is not a result assertion. Preserve failed or uncertain attempts; inspect the current screen before another tap.

## 2. Collect and interpret evidence

After discovery verifies, `copy` runs package, sandbox, UI and requested runtime collection. It pauses at `analysis-agent/TASK.md`. Read the acquired binary indexes, UI evidence, trace and any optional Ghidra/Hopper pseudocode. Write a reviewed `findings.json` and `feature-spec.json`, then create and verify the formal `copyapp report` and `analysis-delivery` specified by the task. `analysis.md` from `analyze` is only a collection index. Every substantive functional claim needs a source case and a stated observation or inference; unknown server or native behavior remains unknown.

Encrypted binaries may require [analysis IPA recovery](full-package-decryption.md). If the installed Mach-O is already unencrypted, a source snapshot is recorded; do not describe that as a decryption. Ghidra and Hopper are optional; [direct Hopper](rea-hopper-integration.md) does not require REA. A static function candidate and a nearby Frida hit are different kinds of evidence.

Before implementation, inventory known user-visible capabilities and set a [reviewed coverage target](coverage-targets.md). Use `coverage-plan` to freeze the target, selected flows, weights and deferred/blocked items. An uncertain inventory should produce a named target without a percentage.

## 3. Build, install and compare

Resume the parent. `prepare-rebuild` writes `rebuild-agent/TASK.md`. Implement an independent Xcode project at the selected path and give it a different Bundle ID. Build, sign and install it on the exact phone. For a development-signed IPA:

```sh
.venv/bin/copyapp install --transport usb --udid <UDID> \
  --ipa <SIGNED_IPA> --out cases/<INSTALL>
.venv/bin/copyapp verify cases/<INSTALL>
```

Use the compatible TrollStore path where appropriate. An install case does not establish launch or equivalence. Run the task's original/rebuilt paired checks, inspect all screenshot pairs, save an explicit `visual-review`, and bind source, install and check cases with `agent-delivery`. For data-changing flows, compare relevant bounded sandbox contents before and after; a matching UI count cannot prove matching persistence. Mark simulated backend behavior as simulated.

Resume `copy` again after every child verifies. A completed parent proves that the selected evidence gates were met; `copyapp verify cases/<WORKFLOW>` rechecks saved hashes and source links, not semantic correctness or behavior outside the selected flows. Finish with `coverage-delivery` and a reviewer decision for each known capability. Report target coverage, milestone completion and verified known coverage separately, with a defensible denominator and explicit unknowns.

See [current status](current-status.md) for named-device results and unresolved limitations. Raw case folders stay local and Git-ignored.
