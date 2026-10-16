# Encrypted App pilot on iPhone XR

Target for the decryption path only: `com.moonshot.kimichat` 3.0.9 on the jailbroken iPhone XR, iOS 16.1.1. The selected Compass analysis target is a system app with no Mach-O encryption command, so it cannot validate a real FairPlay recovery path. The first pilot recovered only the main executable; the later autonomous package path recovered all three extensions too. It does not collect account or sandbox data. Local artifacts under `cases/` are ignored by Git.

## Evidence

| Evidence | Observation |
| --- | --- |
| `cases/kimi-main-decrypt-confirmed-20261015/decryption.json` | Installed main executable `Kimi` had `cryptid=1`, `cryptoff=466944`, `cryptsize=4096`. The first 4096 bytes of the runtime module matched the disk header byte for byte. The encrypted disk region and runtime region have distinct SHA-256 values, with 4079 changed bytes. The analysis copy has `cryptid=0`, the same Mach-O UUID, and the recovered bytes at exactly the encrypted range. |
| REA `inspect_macho` evidence `ev_846edf22fcacb06120fe13bfa260eadad564da6052f8c267ec806331bd472e06` | Independently parsed the recovered executable as arm64 Mach-O, UUID `0D17CB36-07BF-3643-B05E-E8444588171D`, `LC_ENCRYPTION_INFO_64` with the same offset and size and `cryptid=0`. |
| `cases/kimi-acquired-20261015/static/ipa-index.json` | Read-only installed bundle snapshot: 530 files, 13 Frameworks, 3 extensions, 17 Mach-O binaries. Frameworks have `cryptid=0`; the main executable and all three extension executables have nonzero `cryptid` in the installed snapshot. |
| `cases/kimi-analysis-ipa-20261015/assembly.json` and `decryption-check.json` | The analysis IPA replaces only the exact matching main executable. Package-wide verification fails on the three remaining encrypted extension executables and names each one. |
| `cases/kimi-package-automated-20261015/decryption.json`, `check/decryption-check.json` and `device-run/output.txt` | Later full-bundle recovery succeeded: 17 Mach-O checked; main plus all 3 encrypted extensions recovered; zero remaining encryption failures. Every original encrypted binary retained its size and UUID, and changes were confined to the encrypted range and `cryptid` field. |
| `cases/kimi-unfair-root-diagnostic-20261015/result.json` and `output.txt` | A bounded 25-second device trial of a locally patched `unfair` build found all four encrypted executables. It reached `mremap_encrypted` for Kimi's non-16-KB-aligned encrypted range, then stopped while reading the resulting page. Exit status 124 is a timeout, not a successful decryption. |

The encrypted file SHA-256 is `1b8f1a1c932caaf20bae84e5b73cddf763c5b9b900db850363cabb81ffcf7329`; the recovered main executable SHA-256 is `9fe5eeb2558fdea1141a1b0e558b32c103c4aa74ea8fe8c9f26dd0da714d8a06`. The assembled analysis IPA SHA-256 is `6d5acd06afced85390fc7041046c7575b5cfaf6ed2334a0c99b6d8730456dcfa`.

## Alternate extractor trial

The upstream [`unfair` project](https://github.com/lbr77/unfair) uses an iOS FairPlay page-remapping path. Its source was tested at commit `a754437649b1428e07918c0315a678ed7fc57dec`. The initial on-device run required an explicit writable working directory, then rejected Kimi's `cryptoff=0x72000`, `cryptsize=0x1000` because the device reports 16-KB pages. A local diagnostic patch aligned the file mapping down to the page boundary while copying only the 4096 encrypted bytes. Eleven upstream tests passed, and the iOS 16 build ran on XR, but the real extraction stalled after `mremap_encrypted` returned. The process was stopped after 25 seconds and its temporary package removed. This patch is not merged into Copy APP, and the extractor is not a validated fallback for this device.

The verified Mac-controlled root channel now uses the already running Frida server to start a one-shot process on the exact USB UDID. Its output and status are read through key-authenticated mobile SSH after checking `deviceinfo uniqueid` matches the Frida UDID. `copyapp root-run` proved `uid=0` on XR and removed the failed half-configured trial package. This requires no phone terminal input and adds no root SSH key or new network listener.

## Reproduction

```sh
.venv/bin/copyapp decrypt-main --udid <XR_UDID> --bundle com.moonshot.kimichat --out cases/<new-decryption-case>
.venv/bin/copyapp acquire --udid <XR_UDID> --bundle com.moonshot.kimichat --transport ssh --out cases/<new-acquisition-case>
.venv/bin/copyapp assemble-ipa --snapshot cases/<new-acquisition-case>/bundle-snapshot.ipa --recovered cases/<new-decryption-case> --out cases/<new-assembly-case>
```

`decrypt-main` requires the already installed iOS MCP service, Frida service and key-authenticated USB SSH on the selected device. It opens its own device-specific MCP USB tunnel. It only supports a thin arm64 main Mach-O whose encrypted range falls within the mapped module, and it refuses output reuse or a runtime/disk header mismatch. The first attempt was interrupted by first-launch system privacy prompts; the agent handled them on the device without asking the user to type. The command now tolerates a system permission alert owning the foreground if the target process is already running.

## Boundary

The original `decrypt-main` and `assemble-ipa` cases remain a verified **main-only** recovery with three explicit extension failures. The newer `decrypt-package` case is a fully header-verified **analysis IPA** covering all four encrypted executables; see [full-package verification](full-package-decryption.md). Replacing signed code bytes invalidates the original code signature, so no installation claim is made. `cryptid=0` alone does not prove code correctness: the new pipeline also confirms byte differences inside each encrypted range, zero changes elsewhere in each executable, matching Mach-O UUIDs, and identical Kimi main executable bytes from the independent Frida recovery. The extension bytes are supported by the helper's `mach_vm_read` trace and the package audit, without a separate Frida read from those extension processes.
