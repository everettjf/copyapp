# Copy APP workflow

**Language:** English | [简体中文](copy-workflow.zh-CN.md)

Copy APP treats “analyze” and “rebuild” as one resumable, evidence-gated job for selected behavior on a specified jailbroken iPhone. Its current-device mode is intended for a Codex or Claude Code session already working in this repository. The standalone mode can launch a separate coding-agent CLI; it has not yet completed a real autonomous end-to-end run.

For a new Mac and phone, run `sh scripts/bootstrap-macos.sh`, then `.venv/bin/copyapp onboard --stage rebuild` (add `--udid` when several devices are connected). It saves a device and Mac capability report with ordered repairs. Once the required phone services are installed, keep `.venv/bin/copyapp tunnel --udid <UDID>` open in one terminal for the SSH and iOS MCP ports used by the full workflow. SSH host-key fingerprint comparison and phone pairing prompts remain explicit one-time steps.

## 1. Discover representative behavior

```sh
.venv/bin/copyapp copy --udid <UDID> --bundle <ORIGINAL_BUNDLE> \
  --auto-discover --agent-provider current \
  --project rebuild/<NEW_PROJECT> --rebuilt-bundle <NEW_BUNDLE> \
  --out cases/<WORKFLOW>
```

The initial command writes `discovery-agent/TASK.md` and pauses before touching the phone. The current agent observes the actual app, creates 3–12 distinct bounded playbooks under `discovery-agent/candidates/`, and submits them to `copyapp discover-check` using the exact device, Bundle ID and UI backend. That command statically checks identity and action bounds before replay, then saves a verified case at `discovery-agent/discovery/`. Keep failed attempts for diagnosis; inspect phone state before a new attempt. The accepted case pins script bytes, device identity and replay evidence. It establishes only the observed paths, not whole-app coverage.

Each playbook may use bounded taps, swipes, long presses and double taps. Include a post-action state assertion when available; a successful gesture call does not prove the intended UI effect. See the [gesture guide](ui-gesture-playbooks.md) ([中文](ui-gesture-playbooks.zh-CN.md)) for parameters and backend differences.

For input-heavy apps, use [bounded text entry](ui-text-playbooks.md) ([中文](ui-text-playbooks.zh-CN.md)) after focusing an empty field. Check the resulting UI: an input RPC can succeed without visible text reaching the app.

The [Translate XR case](translate-xr-workflow.md) ([中文](translate-xr-workflow.zh-CN.md)) is a concrete three-flow run using iCTRL for visible text input. It reaches a reviewed report, an independently built UIKit app, paired replay and a screenshot-by-screenshot visual review without REA. The example documents the exact behavior covered and the remaining differences.

If a verified discovery case already exists, use `--discovery <CASE>` instead; if scripts were chosen explicitly, use repeated `--script <FILE>`. The three inputs are mutually exclusive.

## 2. Prepare and interpret

Resume the identical `copyapp copy` invocation with `--resume`. The parent verifies discovery and calls `prepare-app`: package and sandbox collection, requested Mach-O recovery, UI/runtime investigation and a semantic review draft. On `analysis_agent_needs_review`, read `analysis-agent/TASK.md` and all linked evidence. Produce a formal report and `feature-spec.json` under `analysis-agent/reviewed-report/`, then run `copyapp analysis-delivery` into `analysis-agent/analysis-delivery/`. The delivery gate checks exact source identity and every selected flow's evidence link. An agent must still judge the meaning of the decompiled functions and state unknown behavior explicitly.

By default the native path needs no REA. For direct decompilation, choose `--analysis-provider ghidra-direct --ghidra-dir <DIR> --java-home <JDK_HOME>` or `--analysis-provider hopper-direct` (optionally `--hopper-app <Hopper.app>`). Ghidra needs a JDK; Hopper needs its licensed GUI app in a normal macOS user session. An integrated `investigate-flow --provider hopper-direct` run on the iOS 16.1.1 XR completed UI replay, Frida tracing and Hopper decompilation, and the result was imported into a verified report. A complete Hopper-backed `copy` analysis-to-rebuild run remains untested. Runtime method hits and static pseudocode are separate evidence; neither alone proves a full implementation.

## 3. Build and compare

Resume the same command again. `prepare-rebuild` creates a source-linked task and the workflow pauses at `rebuild-agent/TASK.md`. Implement an independent Xcode project at the specified `--project`; install it on the pinned device and save installation evidence. For a development-signed IPA, use `copyapp install --transport usb --udid <UDID> --ipa <IPA> --out <CASE>`; the existing TrollStore path remains the default. Verify the install case, then run `rebuild-task-check` for the selected original and clone playbooks on the same UI backend. Inspect every screenshot pair, save `visual-review`, and run `agent-delivery` **without** `--run` in current-device mode. The completed parent requires behavior or final-view assertions for every selected flow, a review of all captured pairs and no major visual difference. Minor differences must be recorded.

A final `--resume` marks the parent complete only if all child cases and source links verify. `copyapp verify cases/<WORKFLOW>` rechecks recorded hashes; it does not certify semantic correctness or behavior outside the selected flows. Do not launch `copyapp agent-run` or another Codex/Claude process from an active coding-agent session.

## Current validation boundary

The iPhone XR on iOS 16.1.1 has completed a three-flow Clock current-agent parent workflow, including report, independent app source, install, 3/3 behavior and terminal-view assertions, and 10 reviewed screenshot pairs with minor differences. A separate [Clock auto-discovery parent](../cases/clock-current-auto-workflow-20261016/manifest.json) completes those gates after replaying three previously authored scripts and adapting prior independent source. The [fresh Calculator parent](../cases/calculator-current-auto-workflow-20261016/manifest.json) adds agent-authored scripts from the current XR UI and a new UIKit project. Its three selected arithmetic flows passed paired behavior and terminal-view assertions, with three image pairs reviewed as minor differences and none major; the parent and delivery verify. An external-process discovery trial used fixed scripts. General discovery across unfamiliar apps, a real autonomous external CLI run and whole-app equivalence remain unverified. The iPhone 14/iOS 17.3.1 has completed USB, iCTRL, SSH acquisition, iOS MCP UI capture, a verified development-signed clone installation, one paired arithmetic flow using native fresh launches, and one encrypted App plus extension recovery. Frida tracing passes on the foreground clone but fails on system Calculator; iOS 26 is untested.

See [the README](../README.md), [the Chinese README](../README.zh-CN.md), and [the detailed experiment log](../PLAN.md).
