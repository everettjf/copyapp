# Copy APP

English · [简体中文](README.zh-CN.md) · [繁體中文](docs/readme/README_zh-TW.md) · [日本語](docs/readme/README_ja.md) · [한국어](docs/readme/README_ko.md) · [Türkçe](docs/readme/README_tr.md) · [Русский](docs/readme/README_ru.md) · [Tiếng Việt](docs/readme/README_vi.md) · [ไทย](docs/readme/README_th.md) · [Deutsch](docs/readme/README_de.md) · [Español](docs/readme/README_es.md) · [Français](docs/readme/README_fr.md) · [Українська](docs/readme/README_uk.md) · [Polski](docs/readme/README_pl.md) · [Português (Brasil)](docs/readme/README_pt-BR.md) · [العربية](docs/readme/README_ar.md) · [فارسی](docs/readme/README_fa.md) · [Bahasa Indonesia](docs/readme/README_id.md) · [Italiano](docs/readme/README_it.md) · [Ελληνικά](docs/readme/README_el.md)

[Project website](https://xnu.app/copyapp/) · [Illustrated overview (简体中文)](docs/articles/copyapp-overview.zh-CN.md) · [Documentation](docs/README.md) · [Reverse-engineering tools](docs/reverse-engineering-tools.md) · [Latest release](docs/releases/v0.2.0.md) · [Contributing](CONTRIBUTING.md) · [Apache-2.0 license](LICENSE)

Copy APP helps Codex or Claude Code **analyze installed apps and build independent, runnable implementations of selected behavior** on **non-jailbroken iOS, jailbroken iOS and macOS**. Conclusions, source and comparisons stay linked to inspectable evidence. The three routes are available in the latest `main` checkout. The latest tagged release is **v0.2.0**, which predates the standard iPhone route. [v0.1.2](docs/releases/v0.1.2.md) is the previous iOS-only release.

**First time?** [Choose one of three routes and copy the agent task](#start-here). The agent checks dependencies and installs the local tools; you complete the required device/system confirmations.

**Choose the access your task needs:** standard mode works from visible UI; enhanced mode adds evidence available on a supported jailbroken phone; Mac apps use a separate ChatComputer workflow.

| Route | What it provides | Requirements / guide |
| --- | --- | --- |
| **Non-jailbroken iOS · standard** | UI flows, accessibility observations, USB screenshots, reviewed behavior reports and independently signed rebuilds | Mac, USB iPhone, Xcode / Developer Mode and development signing; [standard mode](docs/ios-standard-mode.md) |
| **Jailbroken iOS · enhanced** | UI workflows plus package/sandbox acquisition, optional Frida tracing and supported device decryption | Exact-device SSH and compatible device services; [iOS setup](docs/setup.md) |
| **Mac apps** | App-package / AX evidence, UI replay, independent `.app` builds and selected-flow comparisons | Apple Silicon Mac and a dedicated ChatComputer virtual Mac; [Mac setup](docs/macos-support.md) |

Standard mode needs no original IPA, FairPlay credential, SSH or Frida. Its named iOS 26 test used an inactive jailbreak; iOS 17 also passed an explicit standard-mode regression. A never-jailbroken-device test was waived, so that separate compatibility result is not claimed. See the [iOS acceptance ledger](docs/ios-device-support-acceptance.md).

Optional [IPA download and offline recovery](docs/ios-standard-mode.md#standard-iphone-mode) are separate from phone UI collection. First [credential preparation](docs/ios-fairplay-credentials.md) uses a supported jailbroken phone and a license matching the IPA account; once retained locally, the matching credential permits offline recovery without a connected phone. Real Remoboard main/extension recovery and matching-device code comparison passed.

Mac behavior reports do not imply deep native function analysis or arbitrary-Mac compatibility. See [Mac setup and AI task](docs/macos-support.md) and the [acceptance ledger](docs/macos-implementation-plan.md).

Source examples: [Stocks AppKit demo](examples/macos/Stocks/) (illustrative offline data), [independent editor](examples/macos/IndependentEditor/), [owned fixture](examples/macos/BehaviorFixture/) and [iOS examples](examples/rebuild/).

## Architecture at a glance

![Copy APP architecture: agent, local toolkit, standard iPhone, jailbroken iPhone and macOS routes, and reviewed deliverables](docs/assets/readme-architecture.svg)

One Mac coordinates the coding agent, evidence and build. Choose standard UI collection on a USB iPhone, enhanced collection on a supported jailbroken iPhone, or a dedicated virtual Mac through ChatComputer. Each route keeps its own prerequisites and verified identity. See the [detailed architecture and evidence model](docs/architecture.md).

<a id="start-here"></a>

## Quick start: choose a route and paste one task

1. Open **Codex or Claude Code with local command execution on your Mac**.
2. Choose your target below and replace **APP NAME** in its task.
3. Paste the task. The agent checks dependencies, installs the repository CLI and follows the matching skill. You handle the device trust and system permissions it identifies.

Keep a source checkout: it includes the skills, device components and examples as well as the CLI. **No provider-specific extension is required.**

| Target | You prepare | The agent sets up and checks |
| --- | --- | --- |
| Non-jailbroken iOS | A Mac with Xcode, an unlocked USB iPhone with the target App installed, Developer Mode and development signing | Python 3.9+, CLI, exact phone/App identity, development-signed iCTRL / XCTest and USB installation |
| Jailbroken iOS | A Mac, an unlocked jailbroken iPhone connected by USB, and the target App on that phone | Python 3.9+, repository CLI, exact phone/App identity, then the required SSH/UI/runtime tools and signing route |
| macOS | A host meeting ChatComputer's requirements; initialize its virtual Mac and approve required permissions; make the target App available in that guest | Python 3.9+, repository CLI, Swift/macOS SDK, ChatComputer, guest collector and exact environment/App identity |

### Non-jailbroken iOS

Use standard mode for visible behavior and an independent signed implementation. Copy:

```text
Use https://github.com/everettjf/copyapp to observe and independently rebuild selected behavior of “APP NAME” on my USB-connected non-jailbroken iPhone.
Use the latest main checkout. Read AGENTS.md, skills/copyapp-start/SKILL.md and docs/ios-standard-mode.md first. Prepare the CLI with sh scripts/bootstrap-macos.sh if needed.
Identify the exact USB phone and App. Use --mode standard; check Xcode, Developer Mode, device trust and development signing. Prepare the signed iCTRL XCTest runner and install over USB.
Discover representative UI flows, review screenshots and accessibility evidence, and deliver a reviewed UI behavior report. Standard collection needs no IPA or FairPlay credential. Implement an independent App with its own Bundle ID, sign and install it over USB, then compare the same flows and review every screenshot pair in the current agent session.
Use a unique output/ job with project/ and evidence/. Follow docs/fidelity.md: default grade 80/100, at most three implementation/check cycles including the first. Deliver source, runnable artifacts, verified scope and remaining differences. Keep native function and private sandbox claims outside the UI-only report.
```

For setup only, append **“Stop after a verified standard-mode capability check; list signing or runner setup still needed.”** For analysis only, append **“Deliver the reviewed UI behavior report; do not rebuild.”** See [standard-mode setup and commands](docs/ios-standard-mode.md).

### Jailbroken iOS

Connect and unlock the phone. Its Bundle ID can be discovered by the agent. Copy:

```text
Use https://github.com/everettjf/copyapp to analyze and independently rebuild selected behavior of “APP NAME” on my USB-connected jailbroken iPhone.
Clone into a new directory if needed, or reuse my existing checkout. Read AGENTS.md and skills/copyapp-start/SKILL.md first.
Check Python 3.9+ and run sh scripts/bootstrap-macos.sh if the repository CLI is missing. Identify the exact phone and App; complete the initial USB check, then configure only the analysis/rebuild prerequisites this device needs. Use --mode enhanced for UI-first collection with enhancement, and the explicit investigation/report commands for deeper function reasoning.
Work in the current agent session through a reviewed report, independent implementation, installation and same-device comparison. Ask me for the specific device-side trust, permission or signing action when needed.
Use a unique output/ job with project/ and evidence/. Follow docs/fidelity.md: default grade 80/100, at most three implementation/check cycles including the first. Stop at the target or cycle limit and deliver source, runnable artifacts, verified scope and remaining differences.
```

For a setup check only, append **“Stop after a verified USB survey, identify the phone and App, and list remaining prerequisites; do not analyze or rebuild yet.”** For analysis only, append **“Deliver the reviewed report; do not rebuild.”**

First-use actions can include **Trust This Computer**, the documented SSH fingerprint check, phone permissions and signing access. Installing the host CLI does not jailbreak the phone or install its services. See [iOS setup](docs/setup.md).

### macOS with ChatComputer

As checked on **2026-10-22**, [ChatComputer's official requirements](https://github.com/chatcomputer/chatcomputer#install) are **Apple Silicon, macOS 27, 16 GB or more RAM and about 70 GB of free disk space**. Python 3.9+ and a working Swift/macOS SDK are needed for Copy APP; Xcode-project builds need full Xcode. The agent checks these before proceeding.

ChatComputer can be installed with `brew install --cask chatcomputer/tap/chatcomputer`, or by moving the official release's `ChatComputer.app` into Applications. The [Mac installation guide](docs/macos-support.md#install-and-first-use) covers both paths, CLI availability and guest permissions. You can let the agent carry out the installation:

```text
Use https://github.com/everettjf/copyapp and ChatComputer to analyze and independently rebuild selected behavior of the macOS App “APP NAME”.
Clone into a new directory if needed, or reuse my existing checkout. Read AGENTS.md, skills/copyapp-mac/SKILL.md and docs/macos-support.md first.
Check the host against ChatComputer's current requirements, Python 3.9+ and the Swift/macOS SDK. If needed, prepare the repository CLI with sh scripts/bootstrap-macos.sh and install ChatComputer from its official distribution.
Guide me through guest initialization and required system permissions. Use .venv/bin/copyapp mac doctor, deploy the bounded collector and register the exact guest. Confirm the target App is installed inside that virtual Mac; identify its exact build before analysis.
Use the current agent session for flow discovery, report review and implementation. Install the independent App separately, compare the same flows and review every screenshot. Preserve iOS support; do not start another agent or ChatComputer's model loop.
Use a unique output/ job with project/ and evidence/. Follow docs/fidelity.md: default grade 80/100, at most three implementation/check cycles including the first. Stop at the target or cycle limit and deliver source, runnable artifacts, verified scope and remaining differences.
```

**The target App must be available inside the virtual Mac.** The first run includes guest initialization and screen-recording/accessibility permissions for ChatComputer and the collector. A working current agent supplies the model; this workflow does not require starting ChatComputer's built-in chat model.

For a setup check only, append **“Stop after verified environment registration and one target-App screenshot/AX observation; do not analyze or rebuild yet.”** For analysis only, append **“Deliver the reviewed behavior report; do not rebuild.”** A passing doctor checks transport and screenshots, not complete setup or App acceptance.

[Detailed Mac setup](docs/macos-support.md) · [iOS first-run tasks](docs/first-run-agent.md) · [Example source](examples/README.md)

### Shared defaults

Agent-led default: **80/100 reviewed fidelity grade, three cycles**. Ask for 70
for a quick prototype or 90 for finer detail. Core selected behavior must pass;
remaining visual differences stay explicit. This grade is separate from objective
image similarity and known-capability coverage. The [bounded workflow](docs/fidelity.md)
uses `fidelity-plan --fidelity 80 --max-iterations 3`; historical strict delivery
and standalone parent workflows retain their existing rules.

## Reverse-engineering tools

**Ghidra and Hopper are directly integrated decompilers.** They are optional; the default analysis provider is `none`.

| Tool | Used for | Entry / prerequisite |
| --- | --- | --- |
| **Ghidra** | Selected-function pseudocode and bounded call/reference facts | `ghidra-function`, `ghidra-queue`, `ghidra-indirect` / `ghidra-direct`; external Ghidra + matching JDK |
| **Hopper** | Selected-function pseudocode and candidate queues | `hopper-function`, `hopper-queue` / `hopper-direct`; licensed local app + macOS GUI session |
| **Frida** | Runtime method hits and bounded register observations | `trace`, `experiment`, `flow-capture --method`; compatible host/device services |
| **LLVM / Xcode** | Bounded ARM64 disassembly and direct-call followers | `native-disasm`, `native-queue`; `llvm-objdump` |
| **Built-in Mach-O / Objective-C** | Packages, load commands, classes, selectors and method addresses | `ipa`, `objc`; Mac package index via `mac inspect` / `mac acquire` |
| **ipadecrypt / recovery** | Recover encrypted analysis binaries on verified iOS routes | `decrypt-package`, `analyze --decrypt`; device-specific setup |

The native investigation/report integration primarily serves the existing **iOS workflow**. macOS currently uses App-package, AX and UI evidence; an equivalent Mac native-function chain is not implemented. **REA is not required.** IDA Pro, Binary Ninja and radare2 do not currently have direct adapters.

[Tool setup, provider choices and agent prompts](docs/reverse-engineering-tools.md) · [Direct Hopper](docs/rea-hopper-integration.md)

## What the workflow delivers

1. **Analyze:** identify the exact target environment and app build; inspect its package and supported data evidence, then observe selected flows. iOS adds optional native/runtime investigation; macOS uses bounded App/AX observations. Review a cited report with implementation hypotheses and explicit unknowns.
2. **Rebuild:** choose a milestone from a known-capability inventory; implement an independent iOS or macOS app; build and install its IPA or `.app`; compare the same selected flows in the pinned phone or virtual Mac and review every screenshot pair. Report measured coverage and gaps.

A small app may justify a broad first milestone. A complex app needs a named slice of behavior; a percentage is meaningful only with an explicit known-capability denominator. A passing selected-flow check does not establish whole-app equivalence. See [coverage targets](docs/coverage-targets.md).

The Mac runs orchestration and builds. OpenSSH acquires files, iOS MCP provides jailbroken UI observation and control, iCTRL / XCTest provides standard-mode UI control and is also available to enhanced workflows, and Frida provides bounded runtime evidence. Ghidra and Hopper are optional native-analysis tools. **REA is not required.** The [architecture guide](docs/architecture.md) explains the trust and evidence boundaries.

The [example projects](examples/README.md) live under `examples/rebuild/` (iOS) and `examples/macos/` (Mac). New jobs default to `output/`; the legacy `rebuild/<NEW_PROJECT>` workspace remains supported.

### A running macOS example

![Actual independent AppKit Stocks example on macOS, showing a local watchlist, AAPL detail and an offline chart](docs/assets/macos/stocks-demo.jpg)

The [Stocks source example](examples/macos/Stocks/) implements symbol search, chart-period selection and local watchlists. This is an actual window capture of the independently built app on the host Mac, with illustrative offline values; it is not Apple's Stocks or a live market feed. Build instructions are included with the source. Recorded guest comparisons and remaining visual/behavior gaps are separate in the [acceptance ledger](docs/macos-implementation-plan.md).

### Evidence, comparison and deliverables

![Package, sandbox, UI and runtime evidence feed a cited analysis report; the Hopper excerpt is a diagram of saved evidence](docs/assets/social/02-evidence.png)

![Original Calculator and an independent rebuild showing the selected 7 + 8 = 15 flow on the same iPhone 14](docs/assets/social/03-calculator-comparison.png)

![The two deliverables: a cited analysis report and an independent runnable iOS app with explicit coverage and gaps](docs/assets/social/04-deliverables.png)

These are workflow illustrations and selected public observations. The Calculator comparison covers one named flow and still has visible differences; the Hopper excerpt depicts saved evidence, not recovered source code. See the [device evidence and limits](docs/current-status.md).

## Tested iOS support

These are named-device, selected-flow results, not a compatibility promise for every iOS device or app. The [new standard/enhanced acceptance ledger](docs/ios-device-support-acceptance.md) adds inactive-jailbreak iOS 26 standard UI delivery, an iOS 17 standard regression, enhanced RootHide recovery and offline FairPlay checks. [Current evidence and limitations](docs/current-status.md) records the v0.1.2 scope and remaining gaps.

| Phone | Jailbreak and verified scope | Open limits |
| --- | --- | --- |
| iPhone XR · iOS 16.1.1 | Dopamine rootless; SSH, Frida, iOS MCP and iCTRL; selected Notes, Calculator, Translate and Clock analysis/rebuild paths | Optional developer file listing can return `ConnectionTerminatedError`; the SSH package/sandbox route works. |
| iPhone 14 · iOS 17.3.1 | Relaxin/RootHide; original Calculator acquisition, Frida trace and four original/independent-app arithmetic checks through iOS MCP | v0.1.2 fixes the v0.1.1 iCTRL session-lifetime fault; two runs of four paired flows passed. Reboot durability and the changed cleanup on other devices remain untested. |
| iPhone 11 · iOS 26.0.1 | Relaxin/RootHide; original Calculator and Clock analysis, signed independent apps and selected paired arithmetic/Stopwatch checks | iOS MCP can return a black frame after fresh launch; bounded Home/relaunch recovery passed observed runs. |

Current limitations include incomplete app coverage, modest visual differences, unverified reboot/rejailbreak durability, and no end-to-end onboarding test on a second physical Mac. Raw IPAs, complete case screenshots, sandbox contents and credentials stay in Git-ignored local `cases/` or job `output/` (credentials keep their existing local stores) and are never release assets; the few Calculator images in the docs were selected separately for publication.

## Manual installation and first survey

These commands are for readers using the CLI directly; an agent executes them for you. The first USB survey needs Python 3.9+, an unlocked USB-connected iPhone, and **Trust This Computer** accepted. This stage needs no phone tweak, SSH, Frida or Xcode signing.

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
.venv/bin/copyapp apps --udid <UDID> --all
```

Open the target app on the phone, confirm its exact Bundle ID, then collect and verify:

```sh
.venv/bin/copyapp survey --udid <UDID> --bundle <BUNDLE_ID> \
  --ui-backend usb --out cases/first-survey
.venv/bin/copyapp verify cases/first-survey
```

Read `cases/first-survey/report.md` and use a new output directory for each retry. Deep analysis also needs OpenSSH, an exact-device SSH route, the Copy APP iOS MCP tweak and a compatible Frida service; add iCTRL as needed. Standard UI collection and rebuilding require Xcode, a signed XCTest runner and development signing; start with `onboard --mode standard` and the [standard guide](docs/ios-standard-mode.md). Enhanced rebuilding uses the verified signing or TrollStore route. Use `onboard --stage analyze` and `doctor --udid <UDID>` to check readiness, then follow the [full setup guide](docs/setup.md) and [Analyze → Rebuild workflow](docs/copy-workflow.md).

## Run the full Analyze → Rebuild workflow

From an active Codex or Claude Code session, use `standard` for a non-jailbroken phone, `enhanced` for supported jailbreak collection, or `auto` to select from probed capabilities:

```sh
.venv/bin/copyapp copy --mode standard \
  --udid <UDID> --bundle <ORIGINAL_BUNDLE_ID> \
  --auto-discover --agent-provider current \
  --rebuilt-bundle <NEW_BUNDLE_ID>
```

New jobs default to `output/<bundle>-<UTC>-<unique-id>/` in the workspace, with
`project/` for independent source and `evidence/` for reports, captures and checks.
Use `--output-dir output/my-job` to choose a job directory. The existing explicit
`--project <SOURCE> --out <CASE>` form remains supported. Paths must stay inside
the selected workspace (`--workspace <DIR>`); the root `output/` is Git-ignored.
Existing examples and cases stay in place. On resume, pin the printed
`--output-dir` (or legacy `--out` and `--project`) and retain all other settings;
`--resume` never guesses the latest job.

The command pauses for reviewed discovery scripts, a reviewed UI behavior report, and an independent implementation. Enhanced function investigation remains explicit; this UI report does not certify native functions. Resume with the printed output path and the same settings plus `--resume` after each verified handoff. `current` uses the agent already in this session; it does not launch a nested agent. The explicit-mode workflow uses `--agent-provider current`. Historical unflagged strict workflows retain their separate `codex` / `claude` CLI providers. Existing flows can be supplied with `--discovery <CASE>` or repeated `--script <FILE>` instead of `--auto-discover`. The [workflow guide](docs/copy-workflow.md) documents the gates and commands.

## Philosophy and contribution

Keep raw observations separate from interpretation. Tie material claims to a device, app build and verifiable source. Record failed attempts and uncertainty. Compare original and rebuilt apps from equivalent states, and report the behavior actually checked. Keep upstream credits and licenses with vendored components. Contributions that improve setup, bounded analysis, reproducible device checks, accessibility, or translations are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Copy APP's project-owned code and documentation are licensed under the [Apache License 2.0](LICENSE). Vendored and adapted third-party material retains its own license and attribution: [iOS MCP](device/ios-mcp/LICENSE) is MIT-licensed, [iCTRL](vendor/ictrl/LICENSE) is Apache-2.0, and the retained [REA license](docs/third-party/REA-LICENSE.txt) is MIT. The project license does not replace those notices.

## Acknowledgements

Copy APP uses or draws on [ChatComputer](https://github.com/chatcomputer/chatcomputer), [witchan/ios-mcp](https://github.com/witchan/ios-mcp), [OpenMinis/iCTRL](https://github.com/OpenMinis/iCTRL), [Frida](https://frida.re/), [pymobiledevice3](https://github.com/doronz88/pymobiledevice3), [londek/ipadecrypt](https://github.com/londek/ipadecrypt), [Ghidra](https://github.com/NationalSecurityAgency/ghidra), and optional [Hopper](https://www.hopperapp.com/). Its optional direct Hopper interface was informed by MIT-licensed REA code; the license is retained in [docs/third-party/REA-LICENSE.txt](docs/third-party/REA-LICENSE.txt). See the vendored iCTRL [source record](vendor/ictrl/UPSTREAM.md), license and notice for the precise attribution and local changes.
