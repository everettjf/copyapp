# Copy APP

**Language:** English | [简体中文](README.zh-CN.md)

Copy APP is a local, evidence-gated workflow for analyzing an installed iOS app on a jailbroken iPhone and rebuilding selected behavior as an independent, runnable iOS app. It acquires package and sandbox evidence, inspects native code, captures UI and runtime behavior, produces a cited report and feature specification, then builds and compares a clone on the same device.

The workflow verifies evidence identity and selected UI flows. It does **not** claim complete equivalence to an arbitrary app. The iPhone XR running iOS 16.1.1 is the tested device; iOS 17 and 26 testing is deferred at the user's request.

A [standalone Codex CLI trial on the XR](docs/external-codex-xr-trial.md) completed a source-linked Calculator report, independent build and installation, and three paired behavior checks. It reused verified discovery scripts and earlier clone source; see the trial note for the exact scope.

## Install and run your first survey

Copy APP is a **Mac command-line project plus services on your own jailbroken iPhone**. Start with the Mac CLI and one USB survey; that first result needs no phone-side Copy APP tweak, SSH, Frida, iCTRL or decompiler. Add those components only for deep analysis and rebuilding. The Mac bootstrap script below handles Python and CLI installation, but USB trust, phone permissions and jailbreak packages still need setup on the device. A full Xcode installation is needed for device developer services and building a rebuilt app. The files under `cases/` contain local device evidence and are Git-ignored, so the example case links later in this README exist only in the original test workspace.

If Codex or Claude Code is open in this repository, you can ask it: **“Set up Copy APP and run a first USB survey of the App on my connected iPhone.”** The agent can run the Mac commands and identify the exact device and Bundle ID; you still approve USB trust on the phone. A first survey is an initial observation, not the full reverse-engineering report.

| Goal | Set up now |
| --- | --- |
| First survey | Mac bootstrap, USB cable and phone trust. |
| Detailed analysis | Add phone OpenSSH and Frida, plus UI control. The documented XR path uses iOS MCP; iCTRL is optional. Ghidra and Hopper are optional. |
| Runnable rebuild | Add Xcode signing and a working install path such as TrollStore. |

### 1. Install the Mac CLI

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
```

The script creates or reuses `.venv/`, installs Copy APP and prints the guided setup command. It requires macOS and Python 3.9 or newer. When you reach runtime tracing or encrypted App recovery, rerun `sh scripts/bootstrap-macos.sh --trace` to install host Frida 17.x. Check `xcode-select -p` if you plan to use Xcode device services or build a clone; select a **full Xcode**, rather than only Command Line Tools. Keep `.venv/` and `cases/` on the Mac; neither is committed.

### 2. Connect and check one phone

On the phone, activate its compatible jailbreak, unlock it, connect it by USB, and accept **Trust This Computer**. Run the guided check:

```sh
.venv/bin/copyapp onboard
```

It selects the only USB device, creates a dedicated local SSH key if needed, checks Mac and phone channels, and saves an actionable report under `cases/onboard-.../report.md`. It opens a temporary USB SSH forward for its check, so no tunnel terminal is needed yet. It never installs phone packages or trusts an unverified SSH host key. The default `--stage survey` shows only first-survey repairs; rerun with `--stage analyze` or `--stage rebuild` for those goals. If several devices are connected, it prints their IDs and requires `--udid <UDID>`. Once the report says the first survey is ready, list Apps:

```sh
.venv/bin/copyapp apps --udid <UDID> --all
```

Replace `<UDID>` with the exact ID printed by `onboard`; never use a displayed phone name as the selector. `apps` lists user apps by default, while `--all` includes system apps. Resolve the target's exact Bundle ID before collecting anything. If no device appears, fix USB trust, unlocking and the cable first. On iOS 16, if screenshots or Instruments need developer services, enable Developer Mode and run `.venv/bin/pymobiledevice3 mounter auto-mount --udid <UDID>`; the report identifies unavailable observations.

### 3. Make a first USB-only case

Open the target App on the phone and leave it on the screen you want to inspect. This first survey needs no jailbreak-side Copy APP tweak, SSH or Frida:

```sh
.venv/bin/copyapp survey --udid <UDID> --bundle <BUNDLE_ID> \
  --ui-backend usb --out cases/first-survey
.venv/bin/copyapp verify cases/first-survey
```

Read `cases/first-survey/report.md` and its screenshot. This is an installation and device smoke test, not the deep analysis report. Use a new `--out` directory for each run; Copy APP preserves existing evidence rather than overwriting it.

You can stop here for a first impression. The remaining setup is for full package recovery, runtime evidence, richer UI control and real-device rebuild checks.

### 4. Add phone services for full analysis

First install host Frida if you have not already: `sh scripts/bootstrap-macos.sh --trace`. The phone-side steps below are one-time per device. `copyapp doctor` reports which channels are ready once they are configured.

The full pipeline needs the following channels on the **same UDID**:

| Component | Setup | Used for |
| --- | --- | --- |
| OpenSSH on the jailbroken phone | Install a rootless-compatible OpenSSH server; keep it reachable through the USB port forward below. | Read-only App bundle and sandbox acquisition. |
| Frida server on the phone | Install and start a root-capable Frida server compatible with the host's Frida 17.x. | Runtime method tracing and the optional full-package decrypt helper. |
| Copy APP iOS MCP tweak | Build and install [`device/ios-mcp`](device/ios-mcp/README.md), then reload SpringBoard. | Foreground identity, UI tree, screenshots and gestures over a USB-forwarded localhost service. |
| iCTRL runner and paired Mac client | Run `copyapp setup ictrl --udid <UDID> --out cases/ictrl-setup` after SSH and Xcode setup, then approve the phone's pairing prompt. | Optional UI backend and fallback for an Instruments fresh-launch failure. |

For the tweak, the source build requires a complete Xcode, Theos, the iPhoneOS 16.5 SDK and `ldid`; the SDK and Theos are **not** vendored here. From the repository root, after installing those tools, run `THEOS=/path/to/theos CLANG_MODULE_CACHE_PATH=/private/tmp/copyapp-clang-modules make -C device/ios-mcp package`. Install the resulting `.deb` from `device/ios-mcp/packages/` with the phone's package manager or Filza, then reload SpringBoard. The XR/iOS 16 package is tested; do not assume that build works unchanged on iOS 17 or 26. The optional iCTRL source is pinned in [`vendor/ictrl`](vendor/ictrl/UPSTREAM.md) with its Apache 2.0 license and NOTICE; generated signing files, large build dependencies and pairing keys stay local.

Copy APP expects a dedicated `mobile` SSH key at `cases/ssh/id_ed25519` (created by `onboard` if absent), a pinned host-key file at `cases/ssh-known-hosts`, and an SSH USB forward from Mac port `22222` to phone port `22`. In a separate terminal, one Copy APP command keeps both the SSH and iOS MCP forwards running:

```sh
.venv/bin/copyapp tunnel --udid <UDID>
```

Use `--ssh-only` before installing the iOS MCP tweak if preferred. In the repository terminal, collect the phone's host key; run `ssh-keygen` only if you used `onboard --no-keygen`:

```sh
mkdir -p cases/ssh
ssh-keygen -t ed25519 -f cases/ssh/id_ed25519 -C copyapp
ssh-keyscan -p 22222 127.0.0.1 > cases/ssh-known-hosts
ssh-keygen -lf cases/ssh-known-hosts
```

Compare that fingerprint with the iPhone's SSH host-key fingerprint **before** accepting it; repeat this check for another phone. Add `cases/ssh/id_ed25519.pub` to the phone's `mobile` account `~/.ssh/authorized_keys` in the phone terminal, or use one initial password-authenticated SSH session after the fingerprint check:

```sh
cat cases/ssh/id_ed25519.pub | ssh -p 22222 \
  -o UserKnownHostsFile=cases/ssh-known-hosts \
  -o StrictHostKeyChecking=yes -o PubkeyAuthentication=no \
  mobile@127.0.0.1 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
```

Enter the `mobile` password only at that prompt. Keep the private key on the Mac and do not put a phone password in a command or chat. If you chose a passphrase for the key, load it into `ssh-agent`: Copy APP uses noninteractive SSH authentication. Confirm the connection prints the same `<UDID>`:

```sh
ssh -p 22222 -i cases/ssh/id_ed25519 \
  -o UserKnownHostsFile=cases/ssh-known-hosts \
  -o StrictHostKeyChecking=yes mobile@127.0.0.1 'deviceinfo uniqueid'
```

To add the optional iCTRL UI backend, install `xcodegen` (`brew install xcodegen`) and configure an Apple Development signing team in Xcode. The iCTRL runner is installed through the phone's existing TrollStore, using the SSH key above. `setup` builds the vendored Mac client and signed XCTest runner, applies the tested Xcode 27/iOS 16 outer-runner minimum-version adjustment before signing, installs it, opens a temporary USB tunnel and pairs it. The first build downloads iCTRL's pinned IDevice framework (about 215 MB). Approve the matching pairing fingerprint on the phone. It does not save the pairing token in `cases/`:

```sh
.venv/bin/copyapp setup ictrl --udid <UDID> --out cases/first-ictrl-setup
.venv/bin/copyapp verify cases/first-ictrl-setup
.venv/bin/copyapp doctor --udid <UDID> --out cases/doctor-with-ictrl
```

If a compatible runner is already installed, `setup` reuses it and verifies the existing pairing. An already signed runner IPA can be supplied with `--runner-ipa <IPA>`; setup checks its Bundle ID and minimum iOS version before installation. Add `--reinstall` to replace an existing runner with that IPA. Use a new `--out` directory for retries. The vendored Xcode 27 build, `com.copyapp` migration and first pairing passed on XR/iOS 16.1.1; iOS 17/26 remain untested. See [the iCTRL notes](docs/ictrl-xr-validation.md).

Copy APP's iCTRL builds use team-scoped IDs: `com.copyapp.<team-id>.ictrl` for the optional settings app and `com.copyapp.<team-id>.ictrl.uitests.xctrunner` for the runner. The generated, ignored `vendor/ictrl/Config/Local.xcconfig` overrides the default; if upgrading an earlier upstream build, change its `ICTRL_BUNDLE_PREFIX` to `com.copyapp.<team-id>` or delete the file to regenerate it, then reinstall the runner. A new Bundle ID is a new app, so iOS may ask for notification permission and iCTRL pairing again. Approve the matching fingerprint and rerun `setup` with a new output directory if its first attempt times out. The old runner can be removed after the new ID passes authenticated health.

The vendored runtime's URL registration names, pairing-file type, dispatch queue labels and Keychain service also use `com.copyapp`. Current pairings persist in the sandbox file and survived the XR runner update; legacy pairings stored only in the old Keychain service need pairing again. The `ictrl://` and `ictrl-app://` URL schemes and the RPC protocol remain the same. Upstream identity and old device observations remain in the license/provenance and validation notes.

Then record a capability baseline:

```sh
.venv/bin/copyapp doctor --udid <UDID> --out cases/first-doctor
.venv/bin/copyapp verify cases/first-doctor
```

Read `cases/first-doctor/report.md`. Before a full analysis, `usb_lockdown`, `ssh_mobile`, `frida_usb` and `ios_mcp` should be `available`. `ictrl` is optional until selected as a backend. `doctor` can exit successfully when USB works even if another probe is unavailable; inspect its individual rows and ordered **Next steps**. `doctor` opens a temporary SSH forward when port `22222` is not running. The single `copyapp tunnel` terminal above supplies both fixed ports for `analyze` and the full `copy` workflow; playbook replay opens its own short-lived UI tunnel. Rerun `onboard --udid <UDID> --stage analyze` into a new dated case after each setup stage.

### 5. Run analysis, then choose decompilation and rebuild

For a first package/UI/sandbox analysis, open the target App or let the command launch it:

```sh
.venv/bin/copyapp analyze --udid <UDID> --bundle <BUNDLE_ID> \
  --launch --ui-backend ios-mcp --out cases/first-analysis
.venv/bin/copyapp verify cases/first-analysis
```

Read `cases/first-analysis/analysis.md`. It is a collection index, so a detailed functional report still needs controlled UI flows, function review and `copyapp report`. For an App Store binary with encrypted Mach-O files, prepare the pinned helper with `sh scripts/prepare-ipadecrypt-helper.sh` and add `--decrypt` to `analyze` or use the default full `copy` path; the helper is downloaded outside this repository under `../toolchains/`. Decrypted output is an **analysis IPA**, not an installable signed App. An App you compiled locally may already have `cryptid=0` and need no decryption. See [full-package recovery](docs/full-package-decryption.md).

Direct Ghidra or Hopper pseudocode is optional and requires a separately installed tool. Choose `--analysis-provider ghidra-direct --ghidra-dir <DIR> --java-home <JDK_HOME>` or `--analysis-provider hopper-direct` in the full workflow. Hopper also needs a licensed GUI session. For the rebuilt App, Xcode and a working signing/install path are required; the tested XR path uses an existing TrollStore installation. Start the staged `copy` job below only after the required `doctor` channels work. The [workflow guide](docs/copy-workflow.md) explains every pause, report and device check.

| If setup stops here | Check |
| --- | --- |
| `devices` lists nothing | Unlock the phone, accept USB trust, change the cable or USB port, and rerun `devices`. |
| Screenshot or DVT is unavailable | Check Developer Mode, full Xcode selection and the device's Developer Disk Image; rerun `doctor` into a new directory. |
| `ssh_mobile` is unavailable | Keep the `22222 → 22` forward alive, check the pinned host key and `mobile` key login, then compare `deviceinfo uniqueid` with the chosen UDID. |
| `ios_mcp` is unavailable | Check that the rootless tweak loaded after SpringBoard reload. For `analyze`, also keep the separate `22223 → 8090` forward alive. |
| `frida_usb` is unavailable | Check that Frida server is running on that phone and its version is compatible with the installed host Frida 17.x. |
| Fresh UI launch fails when Instruments is unavailable | Run `setup ictrl`, then check `doctor`'s `ictrl` row; on XR with Xcode 27, see the [iOS 16 compatibility trial](docs/ictrl-xr-validation.md). |

If a case fails, inspect its manifest and stage logs before retrying. `analyze` and the staged `copy` workflow accept `--resume` with their original arguments; a failed UI action may have changed App state, so check the screen before replaying it.

## Run the full Analyze → Rebuild workflow

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
| Native analysis | Mach-O and Objective-C indexing, Frida method/branch observations, bounded ARM64 inspection, direct Ghidra or Hopper pseudocode | XR Compass, Calculator, Clock, DeepSeek and a known-source fixture; integrated Hopper investigation verified on the fixture |
| Report | Verified investigation cases, reviewed semantic report, feature specification, source-linked delivery | Selected, observed flows; function interpretations still require human or agent review |
| Rebuild | Independent Xcode project, real-device installation, paired flow replay, UIKit assertions, visual review and delivery | XR pilots with recorded minor visual differences |

The REA command and provider bridge has been removed. Choose `--analysis-provider ghidra-direct --ghidra-dir <DIR> --java-home <DIR>` or `--analysis-provider hopper-direct` for pseudocode. Hopper can be selected in `investigate-flow`, `investigate-app`, `prepare-analysis`, `prepare-app`, and `copy`; `--hopper-app <Hopper.app>` overrides the installed app location. Its `hopper-function` and `hopper-queue` commands also work independently. Hopper needs an installed, licensed GUI app in a normal macOS user session; a sandboxed launcher may fail its Spotlight lookup. On the iOS 16.1.1 XR, [one integrated Hopper investigation](cases/fixture-counter-hopper-investigation-v2-20261016/manifest.json) completed UI replay, Frida tracing, static candidate binding and decompilation; its evidence was imported into a [source-checked report](cases/fixture-counter-hopper-integrated-report-20261016/report.md). The bounded fresh launch falls back from Instruments to iCTRL lifecycle commands when Instruments fails. A full `copy --analysis-provider hopper-direct` analysis-to-rebuild device run has not yet been verified. See [the standalone analysis boundary](docs/rea-independence.md) and [Hopper integration guide](docs/rea-hopper-integration.md).

A complete current-agent, three-flow Clock case is saved at [the XR workflow manifest](cases/clock-current-workflow-live-20261016/manifest.json). Its [reviewed report](cases/clock-current-workflow-live-20261016/analysis-agent/reviewed-report/report.md), [independent source](rebuild/ClockCurrentProbe) and [device delivery](cases/clock-current-workflow-live-20261016/rebuild-agent/agent-delivery/report.md) cover world-city selection, an unsaved alarm edit and stopwatch start/stop/reset. A second [XR auto-discovery parent](cases/clock-current-auto-workflow-20261016/manifest.json) now joins discovery, [formal report](cases/clock-current-auto-workflow-20261016/analysis-agent/reviewed-report/report.md), [independent source](rebuild/ClockCurrentAutoProbe) and [device delivery](cases/clock-current-auto-workflow-20261016/rebuild-agent/agent-delivery/report.md) in one verified case: 3/3 selected behavior and final-view checks passed; all 10 screenshot pairs were reviewed with minor differences and no major difference. This second run reused previously authored discovery scripts and adapted the earlier independent Clock implementation. It validates orchestration and selected-flow delivery, not autonomous script authoring, zero-shot source generation or whole-app equivalence.

A fresh [Calculator auto-discovery parent](cases/calculator-current-auto-workflow-20261016/manifest.json) now tests those missing current-agent handoffs on the XR. The current agent observed the real Calculator UI, wrote three new playbooks, retained failed discovery attempts, produced a [source-linked report](cases/calculator-current-auto-workflow-20261016/analysis-agent/reviewed-report/report.md), and wrote a new [UIKit clone](rebuild/CalculatorFreshProbe) from an empty project. The installed clone passed 3/3 paired behavior and terminal UIKit assertions for decimal addition (`0.3`), negative addition (`−7`) and percent (`0.5`). All three [screenshot pairs](cases/calculator-current-auto-workflow-20261016/rebuild-agent/visual-review-v2/report.md) were reviewed as minor differences, with none major; the [delivery](cases/calculator-current-auto-workflow-20261016/rebuild-agent/agent-delivery/report.md) and parent both verify. This is one selected-flow, current-agent result; it does not establish general discovery, external CLI autonomy or complete Calculator behavior.

An unfamiliar-app [Translate XR workflow](docs/translate-xr-workflow.md) ([中文](docs/translate-xr-workflow.zh-CN.md)) now completes the same current-agent chain without REA: three newly discovered flows, a reviewed [binary/UI/data report](cases/translate-current-workflow-20261016/analysis-agent/reviewed-report/report.md), a new [UIKit clone](rebuild/TranslateFreshProbe), installation and 3/3 paired real-device replays. Six screenshots were reviewed with minor differences, mainly icons and spacing. The tested behavior is text entry without translation submission, Favorites empty state and Conversation idle navigation; translation output, speech and camera behavior remain outside this result.

Other local XR pilots include [Compass](docs/compass-xr-analysis.md), [Calculator](docs/calculator-button-dispatch-xr.md), [DeepSeek](docs/deepseek-three-flow-xr-verification.md) and [Clock](cases/clock-six-flow-no-rea-reviewed-report-v8-20261015/report.md), plus a known-source fixture. The current roadmap is in [the English plan](PLAN.en.md); the full historical experiment log is in [the Chinese plan](PLAN.md).

## Verification and limits

```sh
.venv/bin/copyapp devices
.venv/bin/copyapp apps --udid <DEVICE_UDID> --all
.venv/bin/copyapp verify cases/<CASE>
.venv/bin/python -m unittest discover -s tests
```

`apps` lists user-installed apps by default. `--all` also lists system apps, including Calculator, Compass and Clock on the tested XR, so a target named by its display name can be resolved to an exact Bundle ID.

Playbooks now support bounded swipes, long presses and double taps through both iOS MCP and iCTRL. The [gesture guide](docs/ui-gesture-playbooks.md) ([中文](docs/ui-gesture-playbooks.zh-CN.md)) gives the syntax, backend differences and XR evidence. iOS MCP 0.1.4 is installed on the XR and advertises all three actions. Calculator's observed `98→9` display swipe now passes on the independent clone too; the three earlier arithmetic flows passed again on the updated clone. Long press and double tap were verified as callable without claiming a specific app response.

Playbooks also support bounded [text entry](docs/ui-text-playbooks.md) ([中文](docs/ui-text-playbooks.zh-CN.md)). The XR [Translate discovery case](cases/translate-xr-discovery-20261016/manifest.json) accepted three iCTRL flows, including synthetic `hello` input. iOS MCP reported text events but Translate did not display them, so this device's verified text flow uses iCTRL and checks the visible result.

Formal reports now render a bounded Assets.car name list and a metadata-only sandbox summary when those indexes exist. A [deeper Calculator report](cases/calculator-ui-deep-report-20261016/report.md) and its [source-linked analysis delivery](cases/calculator-ui-deep-analysis-delivery-20261016/report.md) verify these appendices and add direct Ghidra evidence for the root view, keypad frame layout and result-view gesture setup. Resource names and storage-looking filenames are investigation leads, not evidence of runtime use; the three arithmetic flows did not exercise the display gestures.

`copyapp verify` checks recorded source links and file hashes. For a standalone `install.json` directory, it also rechecks the saved IPA hash, Bundle ID and version; that does not prove the App is still installed now. A matching hash does not prove that a decompiler interpretation is correct or that an app is functionally equivalent. Store raw IPA files, screenshots, sandbox snapshots, traces and credentials only in ignored local `cases/`. Reports should distinguish direct observations, inferences and unknown behavior.

The current gaps are general discovery and independent implementation across unfamiliar apps, a real external Codex/Claude CLI end-to-end run, broader app behavior and backend semantics, full sandbox and network interpretation, and cross-version validation. iOS 17 and 26 devices have not been run through this workflow.

## Documentation

- [End-to-end workflow](docs/copy-workflow.md) · [中文](docs/copy-workflow.zh-CN.md)
- [UI gesture playbooks](docs/ui-gesture-playbooks.md) · [中文](docs/ui-gesture-playbooks.zh-CN.md)
- [UI text entry](docs/ui-text-playbooks.md) · [中文](docs/ui-text-playbooks.zh-CN.md)
- [Translate XR full workflow](docs/translate-xr-workflow.md) · [中文](docs/translate-xr-workflow.zh-CN.md)
- [Implementation plan](PLAN.en.md) · [中文及详细试验记录](PLAN.md)
- [REA independence](docs/rea-independence.md)
- [Copy APP agent skill](skills/copyapp-copy/SKILL.md)
- [Repository agent instructions](AGENTS.md)
- [Full Chinese README and historical evidence links](README.zh-CN.md)

## Acknowledgements

Copy APP builds on the work of these projects. Thank you to their maintainers and contributors.

**Source included or adapted in this repository:**

- [witchan/ios-mcp](https://github.com/witchan/ios-mcp) provides the basis for the adapted, rootless [iOS MCP tweak](device/ios-mcp/README.md). Its MIT license and NOTICE are retained.
- [OpenMinis/iCTRL](https://github.com/OpenMinis/iCTRL) provides the vendored XCUITest runner, companion app and encrypted client. The [pinned source and modifications](vendor/ictrl/UPSTREAM.md) retain its Apache-2.0 license and NOTICE.
- [morluto/rea](https://github.com/morluto/rea) informed the direct Ghidra scripts. Its [MIT license](docs/third-party/REA-LICENSE.txt) is retained; the current workflow does not require REA to run.

**Tools and components used by the workflow or the XR trials:**

- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) and [OpenSSH](https://www.openssh.com/) provide USB device services, port forwarding and authenticated file transfer.
- [londek/ipadecrypt](https://github.com/londek/ipadecrypt) supplies the pinned full-package decryption helper, fetched outside this repository. [Frida](https://frida.re/) supplies runtime tracing and device-side instrumentation.
- [Ghidra](https://github.com/NationalSecurityAgency/ghidra) and [Hopper](https://www.hopperapp.com/) provide optional, separately installed decompilers; Hopper requires a license.
- [Theos](https://github.com/theos/theos), [ldid](https://github.com/ProcursusTeam/ldid), [XcodeGen](https://github.com/yonaskolb/XcodeGen) and [Apple Xcode/XCTest](https://developer.apple.com/xcode/) support tweak, runner and rebuilt-app builds. [jkcoxson/idevice](https://github.com/jkcoxson/idevice) is fetched for iCTRL's device-image component.
- [TrollStore](https://github.com/opa334/TrollStore) installs the tested runner and rebuilt IPAs; the tested XR uses the [Dopamine](https://github.com/opa334/Dopamine) jailbreak. [Pillow](https://github.com/python-pillow/Pillow) supports image processing and visual comparisons.
