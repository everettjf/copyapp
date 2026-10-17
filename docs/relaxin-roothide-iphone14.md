# Relaxin / RootHide on iPhone 14 (iOS 17.3.1)

This is a **partial, real-device validation** dated 2026-10-17. The exact USB
device was an iPhone 14 (`iPhone14,7`, iOS 17.3.1, arm64e) running Relaxin
0.5.5 with a RootHide bootstrap. These results do not establish full Copy APP
support on iOS 17 or on other RootHide configurations.

## Verified on the phone

| Capability | Observation |
| --- | --- |
| USB identity and developer services | The requested UDID matched the connected phone. Native RSD launched Calculator and captured a screenshot; the USB accessibility survey returned 33 elements. The survey and bundle-index cases passed `copyapp verify`. |
| iCTRL | The development-signed Copy APP runner installed, its XCTest session started, and encrypted pairing completed. A new original/clone `7 + 8 = 15` nine-step playbook completed on both sides; `compare-playbooks` and `copyapp verify` passed. The first clone attempt returned a malformed HTTP response at the equals tap, so it was retained and a fresh case was run rather than repeating an uncertain tap. Transport stability remains open. |
| OpenSSH | RootHide's `openssh-server`, `openssh-client` and `openssh-sftp-server` 9.2p1 installed. A dedicated, pinned `mobile` public-key login worked over a USB-only port forward. No password is stored in the repository. |
| App acquisition | Over SSH, Copy APP copied the installed Calculator bundle (15 files), made a 472 KB analysis snapshot, and generated a static Mach-O/Objective-C report with 17 indexed classes. The main executable has no encryption load command. The static case passed `copyapp verify`; the repacked snapshot is not asserted to be an installable Apple IPA. |
| Encrypted package recovery | Remoboard's installed main executable and keyboard extension both had `cryptid=1`; its bundled framework had `cryptid=0`. The RootHide mobile SSH helper path recovered both encrypted executables. A standalone `decrypt-package` case and a full `analyze --decrypt` case each passed `copyapp verify`: three Mach-O headers are decrypted, and the two encrypted binaries changed only in their declared encrypted ranges and `cryptid` fields. The output is an analysis IPA with invalid original signatures. The phone-side temporary helper and archive were removed. |
| Sandbox | A bounded SSH index captured 20 entries and seven files in Calculator's data container. This is an index, not an atomic copy of live app data. |
| Frida | RootHide's `re.frida.server` 16.1.4 runs. A matching Mac client enumerated processes. Direct attach and a formal two-second `copyapp trace` succeeded on the **foreground clone**; a background clone attach timed out. Freshly foregrounded original Calculator still failed direct attach with `ProcessNotRespondingError / unexpected early end-of-stream`. Original-App runtime tracing is **not** verified. The main Mac environment's Frida 17.23.3 is version-mismatched with the phone server. |
| Copy APP iOS MCP | Official RootHide ElleKit 1.2-1 and corrected `com.copyapp.mcp` 0.1.4-5 are installed. After a SpringBoard restart, a USB-forwarded `/health` response, UI tool inventory, foreground identity, accessibility elements and screenshot passed. A `copyapp survey --ui-backend ios-mcp --launch` case confirmed original Calculator as foreground. |
| Rebuilt App | Direct USB installation rejected unsigned and ad hoc signed attempts. An Apple Development signed Calculator clone installed through USB InstallationProxy; `copyapp install --transport usb` verified exact UDID, IPA hash, version/build and `ProfileValidated=true`. Native RSD launched it. Both original and clone then completed the same nine-step `7 + 8 = 15` iOS MCP playbook after fresh launches. The paired comparison case passed hash verification; visual review found the same result and keypad layout, with small display and system chrome differences. This verifies one selected flow, not the whole App. |

The local evidence lives in Git-ignored `cases/iphone14-*20261017/`, especially
`iphone14-after-roothide-openssh`, `iphone14-calculator-acquire-attempt`,
`iphone14-calculator-ictrl-playbook-v4`, `iphone14-calculator-sandbox`,
`iphone14-frida-crashes`, `iphone14-calculator-usb-install`,
`iphone14-after-ellekit-matched-frida-20261017`,
`iphone14-calculator-integrated-analyze-20261017`, and
`iphone14-calculator-basic-native-compare-20261017`. The second UI backend has
`iphone14-calculator-basic-ictrl-compare-20261017`. The encrypted-App cases are
`iphone14-remotekb-roothide-decrypt-20261017` and
`iphone14-remotekb-full-analyze-20261017`. The integrated Calculator `analyze`
case passed `copyapp verify` after a CLI repair made iOS MCP surveys open their
own exact-device USB forward. Its survey screenshot was correctly attributed
to the clone, which happened to be foreground; a separate original survey
confirmed the original App's foreground identity.

## RootHide tweak dependency and next validation

RootHide uses a randomized jailbreak root. The device service uses the
[RootHide Theos fork](https://github.com/roothide/theos),
`THEOS_PACKAGE_SCHEME=roothide`, arm64e, and the real `roothide.h` path API:

```sh
THEOS=/path/to/roothide-theos make -C device/ios-mcp THEOS_PACKAGE_SCHEME=roothide package
```

The first package required `mobilesubstrate`, which this phone lacked. A
temporary build incorrectly allowed the `roothide` core package to satisfy
that dependency; it installed but its service did not start. The corrected
0.1.4-5 package again requires `mobilesubstrate`. The official RootHide
`ellekit` 1.2-1 package declares `Provides: mobilesubstrate (= 99)` and is the
standard loader. Its repository archive was downloaded and matched the package
index SHA-256 `50f1b2d60e029592238d80737b32ccc019e74ce9611390c30ffebba75097b41c`.
The corrected Copy APP package SHA-256 is
`69b38f19c0d85fa7f8b124a27f9d6a4a5f1324bf9cbb479e77832f69a72aab48`.
Both archives were staged over pinned USB SSH, installed through the phone's
package UI, and verified with `dpkg -l`. The configured APT source did not
authenticate ElleKit, so the package-index source and recorded hashes remain
explicit in this test record. The service started after restarting SpringBoard.

For iOS 17, fresh App launches now use native RSD with `--kill-existing`;
the older lockdown DVT route failed before this fix. Both sides of the final
Calculator playbook used the repaired route. The next device work is to make
original Calculator Frida attach work with a matching 16.1.4 host client, then run
more selected flows and deliver a deep report. The declared `trace` extra now
allows the phone's Frida 16.1.4, while the current main virtual environment
still has Frida 17.23.3; use a matching isolated client for device tracing. A successful
Frida process inventory or a clone attach does not establish system-App attach
support. The installed server wrapper sets `CRYPTEX_MOUNT_PATH` to the RootHide
root; its launch plist requests root, but this observation does not explain the
Calculator-specific failure. iOS 26 is still untested.

RootHide's mobile SSH shell sees the shared device Media directory at
`/rootfs/var/mobile/Media`, while the helper itself writes to
`/var/mobile/Media`. Copy APP now maps these paths and runs the pinned helper
as the paired mobile user with a 120-second device timeout. The ordinary
rootless route continues to use Frida for its bounded root command. The
generic `root-run` command has **not** passed on this RootHide phone: a no-op
shell process spawned through Frida but produced no completion marker. This
does not block the verified RootHide package recovery route. App Store
encryption and protection schemes can vary, so this Remoboard result is one
package-level compatibility test.

Sources: [Relaxin](https://github.com/owngoal-dev/Relaxin),
[RootHide developer instructions](https://github.com/roothide/Developer),
[RootHide package index](https://github.com/roothide/roothide.github.io/blob/main/Packages),
[RootHide Bootstrap injection model](https://github.com/roothide/Bootstrap).
