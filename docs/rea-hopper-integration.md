# Direct Hopper integration

**Language:** English | [简体中文](rea-hopper-integration.zh-CN.md)

Copy APP now calls Hopper directly. REA is not required at runtime. The old `rea-function`, `rea-queue` and `rea-bridge` commands are removed; archived REA evidence remains readable by the report verifier.

## How it works

1. The acquired or decrypted Mach-O is pinned by its original SHA-256. For a fat binary, Copy APP selects the ARM64 slice and records that slice's hash separately. Encrypted binaries are rejected.
2. `hopper-function` launches the installed Hopper app with `--loader Mach-O --aarch64 --analysis -Y <script> --executable <private-copy>`. The temporary script uses Hopper's Python `Document` and `Procedure` APIs to resolve the exact function entry and request pseudocode.
3. Copy APP saves the script, launcher log, result, pseudocode, source identity and evidence hashes. The report validator checks the original binary, selected slice, requested address and saved files. Pseudocode is an interpretation, not original source or evidence that a UI action executed the function.
4. `hopper-queue` selects a bounded set of addresses from a verified runtime/static candidate case. `--provider hopper-direct` plugs the queue into UI investigations and their report and coding-agent handoff. The top-level `copy` command uses `--analysis-provider hopper-direct`.

The API selection was informed by REA's MIT-licensed Hopper adapter (`21eff3bae10f58711a35ad44f86e9f96f9bb4790`); Copy APP's script, queue and evidence verifier are its own implementation. The license is saved in [REA-LICENSE.txt](third-party/REA-LICENSE.txt). No REA process, package or MCP session is started.

## Commands

```sh
.venv/bin/copyapp hopper-function --file <MACHO> --sha256 <ORIGINAL_SHA256> --address 0xADDRESS --out cases/<FUNCTION>
.venv/bin/copyapp hopper-queue --candidates cases/<CANDIDATES> --limit 4 --out cases/<QUEUE>
.venv/bin/copyapp investigate-flow --udid <UDID> --analysis cases/<ANALYSIS> --script playbooks/<FLOW>.json --provider hopper-direct --out cases/<INVESTIGATION>
.venv/bin/copyapp copy --udid <UDID> --bundle <BUNDLE_ID> --script playbooks/<FLOW>.json --project rebuild/<PROJECT> --rebuilt-bundle <NEW_BUNDLE_ID> --analysis-provider hopper-direct --out cases/<WORKFLOW>
```

Add `--hopper-app '/Applications/Hopper Disassembler.app'` to select an installation; `HOPPER_APP` can also set the default. Hopper is a separate licensed macOS GUI application. It must be ready in the logged-in user's normal GUI session. Its launcher uses Spotlight to find the app, so a restricted shell may exit with `Cannot launch Hopper!` even when the same command works in the normal session. `--timeout` defaults to 600 seconds for a direct function or queue target. The integrated investigation raises a shorter configured timeout to at least 60 seconds per target.

## Verification and limits

The XR-exported FixtureShare `viewDidLoad` at `0x100004000` was decompiled without REA. A verified one-function queue on the XR-exported fixture main binary decompiled `FixtureHomeViewController::showCounter` at `0x1000056ec`; Hopper's pseudocode shows the SwiftUI hosting controller being pushed on the navigation controller. See `cases/fixture-counter-hopper-queue-v2-20261016/` and its [source-checked report](../cases/fixture-counter-hopper-report-20261016/report.md). That was a static code observation using an earlier UI/Frida candidate.

The initial fresh `investigate-flow --provider hopper-direct` attempt on the connected XR stalled while launching the fixture app through Instruments; the interrupted partial case is `cases/fixture-counter-hopper-investigation-20261016/`. Copy APP now runs that launch in a child process with a 20-second limit. If it fails, it opens the paired iCTRL channel, terminates the exact target App and launches it again. The playbook manifest records the chosen backend and primary failure.

The subsequent [integrated XR investigation](../cases/fixture-counter-hopper-investigation-v2-20261016/manifest.json) completed all seven UI steps. Its counter observation changed from 12 to 13; Frida recorded one `FixtureHomeViewController::showCounter` call during the navigation tap; native candidate binding selected `0x1000056ec`; Hopper 6.6.0 returned pseudocode for that address. The flow, Hopper queue and [formal report](../cases/fixture-counter-hopper-integrated-report-20261016/report.md) passed `copyapp verify`. Instruments failed on this run, and the manifest records `ictrl_lifecycle_fallback`. This verifies the integrated investigation and report import on one XR/iOS 16.1.1 fixture flow. The XR case alone does not verify a full `copy` delivery or another device.

On the iPhone 14/iOS 17.3.1, a later [direct Hopper queue](../cases/ios17-calculator-hopper-queue-20261017/manifest.json) used the already verified Calculator original-App Frida/static candidate at `0x10000fca0`. Hopper 6.6.0 produced bounded pseudocode that retains `self` and passes the button argument to local `sub_10000fb4c`; the candidate binary SHA-256 matches the acquired App. A separate [source-linked supplemental report](../cases/ios17-calculator-hopper-supplement-20261017/report/report.md) imports that queue and four-flow runtime evidence. Both cases pass `copyapp verify`.

The [one-flow iOS 17 Hopper-provider parent](../cases/ios17-hopper-current-parent-20261017/manifest.json) subsequently completed that full `copy` handoff with the current Agent: original Calculator acquisition and Frida trace, direct Hopper decompilation, reviewed report, signed existing independent clone, same-device `15` assertion, two manually reviewed screenshot pairs and verified delivery. During this test, the `app_preparation` verifier initially rejected the supported provider string `hopper-direct`; Copy APP now accepts it and has a regression test. The workflow reused source written before this parent and covers only one selected arithmetic flow.

Hopper currently runs one analysis import per selected function and returns pseudocode and signature. Direct Ghidra also provides bounded caller/callee and instruction facts and can follow selected direct and observed indirect targets. For those deeper edges, choose Ghidra or combine separate, source-verified cases in a report. A failed Hopper launch leaves a failed case and log for inspection.

Earlier REA/Hopper results remain historical evidence, including the Compass and fixture investigations. Their saved evidence may be cited with its original provider and time; new cases should use `hopper-direct`.
