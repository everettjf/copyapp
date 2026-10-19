---
name: copyapp-start
description: Set up Copy APP for first use with a local coding agent on a Mac, identify the connected USB iPhone and target app, and continue into the requested survey, analysis or rebuild workflow. Use for getting started with this repository; use its focused skills for an already configured investigation or implementation.
---

# Start Copy APP with a coding agent

Help the user run Copy APP from their request through the requested deliverable. Work in the Copy APP checkout and read [AGENTS.md](../../AGENTS.md). This skill is a repository instruction file: the agent reads it directly, so the user does not need to install a provider-specific extension or type every CLI command.

## Prepare the Mac and identify the target

If the repository has not been checked out, clone `https://github.com/everettjf/copyapp` into a new directory and work there. Reuse an existing checkout when the user has selected it; preserve its local changes. Do not overwrite another project to create the checkout.

Use the repository's `.venv/bin/copyapp`. If it is missing, run `sh scripts/bootstrap-macos.sh`. Read [setup](../../docs/setup.md) ([中文](../../docs/setup.zh-CN.md)) for additional prerequisites required by the requested phase. Complete available Mac-side setup yourself; do not hand the user a list of commands the agent can execute.

Run `.venv/bin/copyapp onboard --stage survey` to inventory USB phones and basic readiness. Identify the exact phone, then use `.venv/bin/copyapp apps --udid <UDID> --all` to resolve the user's app name to its Bundle ID. Use an available foreground-app observation to disambiguate when possible. Ask only when the target or device remains ambiguous; do not arbitrarily choose a phone or substitute a sample app.

Follow [the survey skill](../copyapp-survey/SKILL.md) for the initial verified evidence. If only USB capture is available, have the user open the target app when needed and collect `survey --ui-backend usb` without `--launch`; a USB screenshot probe alone does not establish SSH, Frida or UI-control readiness.

Some prerequisites require the user on the phone: unlocking it, trusting the Mac, confirming its SSH fingerprint through the documented first-use process, approving permissions, or supplying signing access. State the concrete missing action and continue independent Mac-side work. Follow the pinned-key checks in the setup guide. Do not claim that installing the Mac CLI installs the phone services or jailbreaks the device.

## Continue to the requested outcome

- **First check only:** deliver the verified survey, device/app identity, screenshot and remaining setup needs. Stop here when the user requested only a connection or installation check.
- **Analyze:** follow [copyapp-analyze](../copyapp-analyze/SKILL.md), using `onboard --stage analyze` and the guide's ordered repairs where necessary. Finish the reviewed, cited deep report and `feature-spec.json`; `analyze/analysis.md` alone is a collection index.
- **Copy / analyze and rebuild:** follow [copyapp-copy](../copyapp-copy/SKILL.md). Discover representative flows when none were supplied, review the analysis, freeze the known-capability target, implement an independent app, then build, install and compare it on the exact phone. Keep deferred, blocked and unknown behavior explicit.
- **Rebuild from an existing report:** follow [copyapp-rebuild](../copyapp-rebuild/SKILL.md), preserving the report's source identity and the user's selected scope.

Inside Codex or Claude Code, do the agent work in the current session. Use `copy --agent-provider current` when that workflow applies and complete its handoff tasks yourself; do not launch a nested coding-agent CLI. Commands that pause at a handoff have not finished the user's task.

Save device evidence and credentials only in ignored local `cases/`, verify every collected or composed case, and show the resulting report paths. Report what was actually observed and tested. A passing selected-flow comparison is not a claim of whole-app equivalence. Read [current status](../../docs/current-status.md) for named-device limits rather than assuming compatibility.
