# First-run task for a coding agent

[English](first-run-agent.md) · [简体中文](first-run-agent.zh-CN.md)

Open Codex or Claude Code **in the Copy APP checkout** with your jailbroken iPhone connected to the Mac. Replace `<APP NAME OR BUNDLE ID>` in the following request and send it to the agent. You can name an App even if you do not know its Bundle ID.

> Analyze `<APP NAME OR BUNDLE ID>` on my connected jailbroken iPhone with Copy APP. Work in this repository and follow `AGENTS.md` and `skills/copyapp-analyze/SKILL.md`. Install the Mac CLI with `sh scripts/bootstrap-macos.sh` if needed; invoke it as `.venv/bin/copyapp`. Identify the exact USB UDID and Bundle ID; if more than one phone or matching App is present, show me the choices. Run `.venv/bin/copyapp onboard --stage survey`, ask me to open the target App on the phone, then run a USB `survey` without `--launch`; verify the case and show me its report and screenshot. Continue to `onboard --stage analyze` and its ordered repairs for the deep report. Configure Mac-side tools you can configure, and tell me only the exact phone-side trust, package or permission action that needs my participation. When the required channels are ready, collect package, sandbox, UI and runtime evidence; investigate representative flows and relevant classes/functions; produce a cited, reviewed deep report and `feature-spec.json`; verify the report case. Distinguish observed facts, code interpretation and unknown behavior. Do not treat `survey` or `analyze/analysis.md` as the finished deep report. Keep IPA, screenshots, sandbox data and credentials under ignored local `cases/`. Do not rebuild the App in this task.

For a **USB-only first check**, replace the final part with: “Stop after the verified survey and explain what it captured.” Ask the user to open the target App on the phone before this survey; the optional USB `--launch` path depends on developer services that may be unavailable. This path needs no phone-side Copy APP tweak, OpenSSH or Frida.

## What you should receive

- An exact device and App identity, plus the verified survey case and screenshot.
- For a deep run, a source-linked report that describes the observed UI, package and libraries, selected implementation paths, data/storage and runtime evidence, with explicit gaps and a feature specification. The [analysis skill](../skills/copyapp-analyze/SKILL.md) defines the handoff and evidence checks.
- A clear statement of what still needs device setup or observation if the deep run cannot complete. The agent should finish all Mac-side work it can perform before reporting a phone-side blocker.

When you later want a runnable independent App, use the [Analyze → Rebuild workflow](copy-workflow.md) and [coverage-target method](coverage-targets.md). That is a separate, larger task and requires Xcode signing and same-device comparison.
