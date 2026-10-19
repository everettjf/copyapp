# Set up a Mac and jailbroken iPhone

[English](setup.md) · [简体中文](setup.zh-CN.md) · [Documentation](README.md)

## Choose a setup level

| Goal | Required components |
| --- | --- |
| First USB survey | macOS, Python 3.9+, USB trust, unlocked phone, Copy APP CLI. |
| Deep analysis | Compatible jailbreak, mobile OpenSSH and pinned SSH key, iOS MCP UI service, Frida; full Xcode for developer services. Ghidra/Hopper only when requested. |
| Runnable rebuild | Deep-analysis setup plus full Xcode, signing or TrollStore, and a verified install route. iCTRL is optional. |

These instructions describe the v0.1.2 checkout. The release wheel contains the Mac CLI but does not contain Theos, the phone tweak, signing assets, or private credentials. If using the wheel for optional source-built components, also keep a checkout and set `COPYAPP_SOURCE_ROOT=/absolute/path/to/copyapp`.

## 1. Install the Mac CLI and identify the phone

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
.venv/bin/copyapp apps --udid <UDID> --all
```

`onboard` prints the exact UDID; supply `--udid` when more than one phone is connected. Unlock the phone and accept USB trust. For developer services, select a full Xcode with `xcode-select -p`, enable Developer Mode if prompted, and use the compatible developer image. On iOS 26, the tested iCTRL route uses a personalized developer image and a userspace XCTest tunnel. Read the saved `onboard` report before installing more components.

For a first case, open the target app on the phone and run:

```sh
.venv/bin/copyapp survey --udid <UDID> --bundle <BUNDLE_ID> \
  --ui-backend usb --out cases/first-survey
.venv/bin/copyapp verify cases/first-survey
```

This is an initial screen and device check. Use a new `--out` directory for a retry.

## 2. Establish mobile SSH over the exact USB phone

Install a jailbreak-compatible OpenSSH server on the phone. Run `.venv/bin/copyapp onboard --udid <UDID> --stage analyze` to create a dedicated Mac key and list the remaining repairs. For first-time host-key verification, keep the USB forward open in another terminal:

```sh
.venv/bin/copyapp tunnel --udid <UDID> --ssh-only
```

The default local SSH port is `22222`. With multiple phones, use distinct `--ssh-port` and `--ssh-known-hosts` values per device. Compare the forwarded SSH host-key fingerprint with the fingerprint shown on the selected phone before saving it. Add the Mac public key `cases/ssh/id_ed25519.pub` to the phone's `mobile` account `~/.ssh/authorized_keys`, using the phone terminal or one verified password-authenticated SSH session. Never put a phone password in a command, repository file or chat. Keep the private key in ignored `cases/`.

In the repository terminal, while the SSH forward runs, inspect the forwarded key:

```sh
ssh-keyscan -p 22222 127.0.0.1 > cases/ssh-known-hosts
ssh-keygen -lf cases/ssh-known-hosts
```

On the selected phone, use its terminal to run `ssh-keygen -lf <PHONE_SSH_HOST_PUBLIC_KEY>` for the OpenSSH host public key and compare the fingerprint. The package may place that key under `/etc/ssh/` or a jailbreak-specific prefix. Only after the values match, authorize the Mac public key. If password login is enabled, this one-time command keeps the password at the interactive prompt:

```sh
cat cases/ssh/id_ed25519.pub | ssh -p 22222 \
  -o UserKnownHostsFile=cases/ssh-known-hosts \
  -o StrictHostKeyChecking=yes -o PubkeyAuthentication=no \
  mobile@127.0.0.1 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
ssh -p 22222 -i cases/ssh/id_ed25519 \
  -o UserKnownHostsFile=cases/ssh-known-hosts \
  -o StrictHostKeyChecking=yes mobile@127.0.0.1 'deviceinfo uniqueid'
```

The last command must return the selected UDID. Then run:

```sh
.venv/bin/copyapp doctor --udid <UDID> --out cases/first-doctor
.venv/bin/copyapp verify cases/first-doctor
```

After successful authentication, `onboard`/`doctor` records the exact-device port and key paths in ignored `cases/ssh/profiles.json`; later commands reuse them. Do not replace a pinned host key merely because it differs. The XR/iOS 16 developer file-listing probe can fail with `ConnectionTerminatedError`; SSH package and sandbox acquisition are the verified alternative.

## 3. Add UI control and Frida

**iOS MCP:** build [`device/ios-mcp`](../device/ios-mcp/README.md) with full Xcode, Theos, iPhoneOS 16.5 SDK and `ldid`, install the matching rootless or RootHide package, and reload SpringBoard. Theos and the SDK are external prerequisites. RootHide needs its Theos fork, `THEOS_PACKAGE_SCHEME=roothide`, and a tweak loader such as ElleKit. Run `doctor` again and check the `ios_mcp` row.

**Frida:** install host tracing support with `sh scripts/bootstrap-macos.sh --trace` and a compatible device server. On the tested iOS 17/26 RootHide devices, pin host `frida==17.23.3`, then configure the isolated sidecar:

```sh
.venv/bin/python -m pip install 'frida==17.23.3'
.venv/bin/copyapp setup frida-roothide --udid <UDID> \
  --out cases/frida-roothide-setup
```

RootHide's older packaged Frida server did not attach to the tested original Calculator; process enumeration alone does not prove attachment. On ordinary rootless iOS, use a server matching the host Frida version. The RootHide package-recovery helper uses authenticated mobile SSH; the ordinary rootless helper route uses a verified root Frida process.

**Optional iCTRL:** install `xcodegen` (`brew install xcodegen`), configure Apple Development signing in Xcode, or supply an already signed compatible runner IPA. Then run:

```sh
.venv/bin/copyapp setup ictrl --udid <UDID> --out cases/ictrl-setup
.venv/bin/copyapp verify cases/ictrl-setup
```

The first source build downloads the pinned iCTRL framework. Approve device-side XCTest, notification and pairing prompts for the matching fingerprint. On iOS 17+, `--auto-approve-first-pair` can approve one local USB request in a development runner. The app and runner use team-scoped `com.copyapp.<team-id>` IDs. See [`vendor/ictrl/UPSTREAM.md`](../vendor/ictrl/UPSTREAM.md) for provenance. A current iOS 17 multi-step clone replay still has an iCTRL transport failure; use iOS MCP for the verified four-flow Calculator path and inspect [current status](current-status.md) before relying on iCTRL for acceptance.

## 4. Analyze and install a rebuild

```sh
.venv/bin/copyapp analyze --udid <UDID> --bundle <BUNDLE_ID> \
  --launch --ui-backend ios-mcp --out cases/first-analysis
.venv/bin/copyapp verify cases/first-analysis
```

`analysis.md` is a collection index, not a semantic reverse-engineering report. Encrypted App Store binaries may need `sh scripts/prepare-ipadecrypt-helper.sh` and `analyze --decrypt`; the output is an **analysis IPA**, not a signed installable app. See [package recovery](full-package-decryption.md). A full report needs reviewed UI flows, function evidence and `copyapp report`; follow the [workflow guide](copy-workflow.md).

Build and sign the independent Xcode app. On a development-signed route:

```sh
.venv/bin/copyapp install --transport usb --udid <UDID> \
  --ipa <SIGNED_IPA> --out cases/clone-install
.venv/bin/copyapp verify cases/clone-install
```

A successful install does not prove launch or equivalence. Replay selected original and clone flows, check final behavior, inspect every screenshot pair and report gaps. The XR TrollStore path remains available for compatible packages. Keep all IPAs, screenshots, sandbox data, SSH keys and pairing material in ignored `cases/`.
