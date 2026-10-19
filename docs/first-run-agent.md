# First-run tasks for a coding agent

[English](first-run-agent.md) · [简体中文](first-run-agent.zh-CN.md)

Open Codex or Claude Code with local command execution on your Mac, then connect and unlock your jailbroken iPhone. You do not need to install Copy APP manually first: the agent can clone the repository, configure the Mac and invoke the CLI. If you already have a checkout, open the agent there. The prompt explicitly reads the repository's [first-use skill](../skills/copyapp-start/SKILL.md); no extension or slash-command configuration is required.

## Analyze and rebuild

Replace `<APP NAME OR BUNDLE ID>` and paste this into the agent conversation:

```text
Use https://github.com/everettjf/copyapp to analyze and rebuild <APP NAME OR BUNDLE ID> on my USB-connected jailbroken iPhone.
Clone into a new directory if needed, or reuse its existing checkout. Read AGENTS.md and skills/copyapp-start/SKILL.md first.
Check and configure the environment, identify the exact phone and app, discover representative flows, and complete a cited deep report, a named rebuild target, an independent project, device installation and original/rebuilt comparisons.
Execute the steps you can perform yourself. Tell me the specific action only when you need phone-side participation or missing target information. Deliver the report, project, tested scope and remaining differences.
```

The agent should complete discovery, semantic review and implementation handoffs within this task. A CLI message waiting for an agent or a generated `TASK.md` still requires it to continue. It works in the current session without starting nested Codex or Claude CLIs.

## Analyze only

```text
Use https://github.com/everettjf/copyapp to analyze <APP NAME OR BUNDLE ID> on my USB-connected jailbroken iPhone. Do not rebuild it in this task.
Clone into a new directory if needed. Read AGENTS.md and skills/copyapp-start/SKILL.md first, then check the environment, identify the phone and app, collect evidence and investigate relevant classes/functions.
Deliver a reviewed, cited deep report and feature-spec.json, and verify the case. Distinguish observations, inferences and unknowns; do not stop when survey or analyze/analysis.md has been generated.
```

For a connection check only, replace the deliverable with: “Stop after a verified first USB survey and show its report, screenshot and missing setup.” This route needs USB trust and the foreground app, but no phone-side Copy APP tweak, OpenSSH or Frida. Additional analysis and rebuild prerequisites are in [setup](setup.md).

## What you receive

- The exact device/app identity and verified evidence cases.
- For analysis: a cited deep report and feature specification, beyond the collection index.
- For rebuilding: an independent project, build/install results, same-device paired checks, image-by-image review and measured scope with differences.
- If phone-side prerequisites are missing: the completed Mac work and the specific action you need to take. Unlocking, trust, initial SSH fingerprint checks, permissions or signing access may require your participation.

Keep raw IPAs, screenshots, sandbox data and credentials under ignored local `cases/`. Selected-flow success does not establish whole-app parity; see [coverage targets](coverage-targets.md) and the [named-device limits](current-status.md).
