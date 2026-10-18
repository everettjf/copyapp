# Encrypted package recovery for analysis

[English](full-package-decryption.md) · [简体中文](full-package-decryption.zh-CN.md) · [Setup](setup.md)

An App Store bundle may contain encrypted Mach-O executables in the main app and extensions. Copy APP can produce an **analysis IPA** whose indexed executables have `cryptid=0`, then audit exactly which bytes changed. It does not recover the developer's original source or produce a signed installable IPA.

## Path and checks

1. `copyapp acquire` reads the installed bundle over authenticated mobile SSH on the exact USB device and saves a hash-bound snapshot.
2. `scripts/prepare-ipadecrypt-helper.sh` fetches the pinned `londek/ipadecrypt` helper into an external `../toolchains/` directory; it is not vendored in this repository.
3. `copyapp decrypt-package` verifies device, app and snapshot identity. On tested ordinary rootless iOS it starts a bounded root process via Frida; on tested RootHide devices it uses authenticated mobile SSH in the RootHide namespace.
4. The helper uses suspended spawning and `mach_vm_read` to recover each encrypted executable. Copy APP checks length and UUID, audits changes against only the declared encrypted ranges and `cryptid` fields, verifies all unchanged ZIP members, and writes canonical package metadata.
5. The command indexes the recovered IPA and records per-file results. `copyapp verify <DECRYPT_CASE>` rechecks saved identities, hashes, changed-byte audit and package encryption headers.

```sh
sh scripts/prepare-ipadecrypt-helper.sh
.venv/bin/copyapp acquire --udid <UDID> --bundle <BUNDLE_ID> \
  --out cases/<ACQUIRE>
.venv/bin/copyapp decrypt-package --udid <UDID> --bundle <BUNDLE_ID> \
  --snapshot cases/<ACQUIRE>/bundle-snapshot.ipa \
  --out cases/<DECRYPT>
.venv/bin/copyapp verify cases/<DECRYPT>
```

`copyapp analyze --decrypt` composes the recovery with UI survey, bundle acquisition and bounded sandbox indexing. It writes `analysis.md`, which is a collection index; a semantic report still needs reviewed UI/runtime evidence and `copyapp report`.

## Tested scope and limits

Full-package recovery was verified on XR/iOS 16.1.1 for encrypted DeepSeek and Kimi main executables and extensions, and on iPhone 14/iOS 17.3.1 RootHide for the Remoboard main app and keyboard extension. These are specific package builds, not a guarantee for every App or iOS version. Some binaries are already unencrypted; the workflow records an unchanged source snapshot rather than claiming a decrypt operation. The RootHide helper does not require root SSH login. Analysis output, helper logs and extracted data remain in Git-ignored local `cases/`; they are not release assets. Inspect the exact case before reporting recovery success, and keep separate any UI, function or behavioral conclusions.
