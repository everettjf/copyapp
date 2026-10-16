# Full analysis IPA recovery on iPhone XR

Device: iPhone XR, iOS 16.1.1, Dopamine rootless. This note covers two installed App Store apps only. All case data is under Git-ignored `cases/`; it may contain proprietary code and should be kept local.

## Verified results

| App | Installed version | Mach-O checked | Encrypted executables recovered | Package result |
| --- | --- | ---: | ---: | --- |
| DeepSeek `com.deepseek.chat` | 2.4.4 | 32 | Main and one share extension | `cases/deepseek-package-automated-20261015/decryption.json`: all headers decrypted, zero failures |
| Kimi `com.moonshot.kimichat` | 3.0.9 | 17 | Main, push, share and widget extensions | `cases/kimi-package-automated-20261015/decryption.json`: all headers decrypted, zero failures |

For every originally encrypted executable, Copy APP compared the installed-bundle snapshot with the recovered IPA. File length and Mach-O UUID stayed identical. Only the declared encrypted byte range and four-byte `cryptid` field changed. Every encrypted range had thousands of changed bytes, and the package-wide check found no remaining encrypted Mach-O. DeepSeek and Kimi main executable bytes also exactly match the independent Frida runtime recovery done earlier. Older repeat DeepSeek runs produced identical main and extension binary SHA-256 values but different IPA ZIP hashes because the device helper stamped the recovered entries with the current time. Copy APP now rebuilds the analysis IPA with source ZIP metadata after checking that all other members are unchanged. It accepts only the helper's omission of `SC_Info` receipts.

The command now automatically writes `static/ipa-index.json`, `static/ipa-report.md`, `static/objc-index.json`, and `static/objc-report.md` after the package checks pass. A fresh DeepSeek run produced 1,212 locally defined Objective-C classes and 13,099 methods from the recovered main executable. These are metadata names and addresses, not decompiled implementations.

Kimi's verified analysis IPA SHA-256 is `04da194d939a83350ae5cab27b2ee6b99baf2cdaa281253ff5ffdcc7bc39ff4f`. DeepSeek's automated analysis IPA SHA-256 is `08d590c4736af407427f4d338d73b407885908d33e5db407ea1d4c9b67c34f0c`. These hashes identify local evidence, not downloadable packages.

## How the autonomous path works

1. `copyapp acquire` reads the installed `.app` bundle over key-authenticated USB SSH and records file hashes.
2. `scripts/prepare-ipadecrypt-helper.sh` pins [`londek/ipadecrypt`](https://github.com/londek/ipadecrypt) at `2fa69244cc6e580cd05f781db57912c79a4c3197` and checks the reviewed iOS helper SHA-256 `8fe2ace941132c29d19480adba554ebd71d2a1ea27a2c7c6ee1eb648a504151b`. The helper stays outside this repository under `../toolchains/`.
3. `copyapp decrypt-package` verifies snapshot identity and the exact connected UDID, stages that helper, and starts it as a bounded root process using the existing USB Frida server. It retrieves only status/logs via mobile SSH; no root SSH login is configured.
4. The helper uses suspended process spawning and `mach_vm_read` to recover the main executable and each extension, then packages an analysis IPA. Copy APP transfers the output over USB SSH, checks its transfer hash, inspects every Mach-O and audits every changed byte against the original snapshot. It then validates the ZIP member list and all unchanged members, restores original ZIP metadata, and records both the device archive hash and canonical analysis archive hash.
5. Device-side temporary helper and IPA files are removed when the command ends. Local evidence stays in the requested case directory.

`decrypt-package` now writes a standalone `manifest.json`. `copyapp verify <DECRYPT_CASE>` checks the saved files and re-runs the source-to-output byte audit: App/version identity, every recovered encrypted range, all unchanged members, canonical ZIP layout, package-wide encryption headers, static index and device-run identity. The [new XR standalone case](../cases/deepseek-verifiable-decrypt-live-20261015/manifest.json) was produced by the command itself and passed that verifier: 32 Mach-O files checked, two encrypted executables recovered, and canonical IPA SHA-256 `9d4610e4e3587b8ca500aa3d7a08a8eabb498113e9589700a7bc099a09d46185`. A new `analyze` or `prepare-app` case also checks this child manifest when present. The archived device IPA bytes are not retained after canonicalization, so its saved transfer hash is a run-time observation rather than independently rechecked bytes.

`copyapp analyze --decrypt` composes the same recovery with USB UI survey, bundle acquisition, and sandbox metadata indexing into one case. It writes `analysis.md` with links to the recovered IPA index and class report. Individual steps retain errors and evidence if one collector fails.

On the XR, `cases/deepseek-onepass-decrypt-fixed-20261015/` passed all four stages and `copyapp verify`. The iOS MCP foreground check returned `verified_frontmost`; the screenshot visibly shows DeepSeek's sign-in screen. This establishes only that entry screen, since no account session or in-app pages were observed. The resulting case report is `analysis.md`, with a full-package manifest and recovered static indexes in `decrypted/`.

The later [canonical DeepSeek preparation case](../cases/deepseek-canonical-prepare-app-network-live-20261015/manifest.json) ran `prepare-app --decrypt --network` on the XR and passed parent case verification. Its canonical IPA hash is `9d4610e4e3587b8ca500aa3d7a08a8eabb498113e9589700a7bc099a09d46185`, identical to Mac-side normalization of two earlier independent DeepSeek recoveries from the same source snapshot. The three device archive hashes differ. This demonstrates deterministic packaging for this package and helper; it does not establish that every App can be decrypted.

The direct Frida attach path works for regular app processes on this XR, but attach to the system-hosted DeepSeek and Kimi share extension processes timed out after about 25 seconds. A separate `unfair`/`mremap_encrypted` trial stalled while reading a remapped page. The suspended-spawn helper succeeded for those same extension binaries. The earlier unsuccessful methods are retained as diagnostic evidence; the validated full-package command uses the successful method.

## Reproduction

```sh
sh scripts/prepare-ipadecrypt-helper.sh
.venv/bin/copyapp acquire --udid <UDID> --bundle <BUNDLE_ID> --out cases/<ACQUIRE_CASE>
.venv/bin/copyapp decrypt-package --udid <UDID> --bundle <BUNDLE_ID> \
  --snapshot cases/<ACQUIRE_CASE>/bundle-snapshot.ipa --out cases/<DECRYPT_CASE>
```

The device needs Dopamine or another compatible jailbreak, a running root Frida server, OpenSSH reachable through a USB port forward, and the existing mobile SSH key. The command has a 120-second device timeout and 140-second host timeout. It does not install, launch through the UI, or sign the recovered app. The output is an **analysis IPA**; modified code signatures make installability a separate task. Package header checks and changed-byte auditing provide strong evidence of recovery, while full behavioral equivalence still requires runtime analysis and testing.
