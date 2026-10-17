# Relaxin / RootHide on iPhone 14 (iOS 17.3.1)

This is a **supported, real-device configuration for the first-release selected-flow workflow**, validated on 2026-10-17. The exact USB device was an iPhone 14 (`iPhone14,7`, iOS 17.3.1, arm64e) running Relaxin 0.5.5 with a RootHide bootstrap. The report, installation and paired behavior gates passed for the selected Calculator flow. This status does not extend to every iOS 17 device, RootHide build or App feature.

After this baseline, [first-use setup](ios17-first-use-gates.md) let original Translate and Clock enter their own foreground processes. Their selected text-input and Stopwatch flows then passed through both UI backends; see the [two-device matrix](two-device-verification-matrix.md). These additional original-App checks do not add clone equivalence for either App on iOS 17.

## Verified on the phone

| Capability | Observation |
| --- | --- |
| USB identity and developer services | The requested UDID matched the connected phone. Native RSD launched Calculator and captured a screenshot; the USB accessibility survey returned 33 elements. The survey and bundle-index cases passed `copyapp verify`. |
| iCTRL | The development-signed Copy APP runner installed, its XCTest session started, and encrypted pairing completed. A new original/clone `7 + 8 = 15` nine-step playbook completed on both sides; `compare-playbooks` and `copyapp verify` passed. The first clone attempt returned a malformed HTTP response at the equals tap, so it was retained and a fresh case was run rather than repeating an uncertain tap. Transport stability remains open. |
| OpenSSH | RootHide's `openssh-server`, `openssh-client` and `openssh-sftp-server` 9.2p1 installed. A dedicated, pinned `mobile` public-key login worked over a USB-only port forward. No password is stored in the repository. |
| App acquisition | Over SSH, Copy APP copied the installed Calculator bundle (15 files), made a 472 KB analysis snapshot, and generated a static Mach-O/Objective-C report with 17 indexed classes. The main executable has no encryption load command. The static case passed `copyapp verify`; the repacked snapshot is not asserted to be an installable Apple IPA. |
| Encrypted package recovery | Remoboard's installed main executable and keyboard extension both had `cryptid=1`; its bundled framework had `cryptid=0`. The RootHide mobile SSH helper path recovered both encrypted executables. A standalone `decrypt-package` case and a full `analyze --decrypt` case each passed `copyapp verify`: three Mach-O headers are decrypted, and the two encrypted binaries changed only in their declared encrypted ranges and `cryptid` fields. The output is an analysis IPA with invalid original signatures. The phone-side temporary helper and archive were removed. |
| Sandbox | A bounded SSH index captured 20 entries and seven files in Calculator's data container. This is an index, not an atomic copy of live app data. |
| Frida | RootHide's packaged 16.1.4 server still fails to attach to original Calculator, including with `--ignore-crashes`; the saved crash shows `EXC_GUARD` inside `task_swap_exception_ports`. An isolated, official Frida 17.23.3 server and matching Mac client, started with `-C` on a separate USB-forwarded port, attached to original Calculator and completed `copyapp trace`. A `flow-capture` run recorded one `CalculatorModel::buttonPressed:` hit for each of five selected taps; its trace and view-tree cases passed `copyapp verify`. This verifies that selected original-App runtime path on this phone, not general system-App support. |
| Copy APP iOS MCP | Official RootHide ElleKit 1.2-1 and corrected `com.copyapp.mcp` 0.1.4-5 are installed. After a SpringBoard restart, a USB-forwarded `/health` response, UI tool inventory, foreground identity, accessibility elements and screenshot passed. A `copyapp survey --ui-backend ios-mcp --launch` case confirmed original Calculator as foreground. |
| Rebuilt App | Direct USB installation rejected unsigned and ad hoc signed attempts. An Apple Development signed Calculator clone installed through USB InstallationProxy; `copyapp install --transport usb` verified exact UDID, IPA hash, version/build and `ProfileValidated=true`. Native RSD launched it. Both original and clone completed the same nine-step `7 + 8 = 15` flow through iOS MCP and iCTRL. A later report-derived iOS MCP rebuild check asserted the exact final UIKit text `15` on both apps; two screenshot pairs received explicit minor-difference judgments. Its final `agent-delivery` case passed `copyapp verify` with status `selected_behavior_verified_visual_reviewed_with_differences`. This verifies one selected flow, not the whole App. |

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
The Frida 17 cases are `iphone14-frida17-sidecar-setup-v3-20261017`,
`iphone14-calculator-frida17-viewtree-20261017`, and
`iphone14-calculator-frida17-flow-capture-20261017`. The sidecar was stopped and
automatically restarted before another successful original Calculator trace.
The subsequent `iphone14-frida17-doctor-v2-20261017` baseline passed
`copyapp verify` and reported USB, DVT filesystem, RootHide namespace, pinned
mobile SSH, Frida 17 sidecar, iOS MCP, and paired iCTRL available.
`iphone14-calculator-frida17-prepare-app-20261017` then resumed a failed
attempt caused by a missing fixed SSH forward. Copy APP now opens or checks an
exact-device SSH forward for each acquisition stage; survey, bundle, and
sandbox collection all completed, and the selected flow investigation chose
`CalculatorModel::buttonPressed:`. The parent passed `copyapp verify` with
status `needs_semantic_review`. A separately reviewed, source-linked
`iphone14-calculator-frida17-deep-report-v3-20261017` and
`iphone14-calculator-frida17-analysis-delivery-v2-20261017` then passed
verification. The report explains the selected method's bounded assembly and
records unknown branches rather than treating the generated draft as a report.
The report-derived `iphone14-calculator-frida17-rebuild-check-v2-20261017`
passed exact result checks on both apps. Two screenshots were reviewed in
`iphone14-calculator-frida17-visual-review-20261017`; the final
`iphone14-calculator-frida17-agent-delivery-20261017` passed verification with
minor visual differences. The reused clone source and installed IPA existed
before this report was written; the delivery proves the saved source and IPA
identities and this selected behavior, not that the new report generated the
clone from scratch.

## Reproduce the RootHide Frida path

Install host `frida==17.23.3` in `.venv`, then use the exact USB device and
previously pinned mobile SSH key:

```sh
.venv/bin/python -m pip install 'frida==17.23.3'
.venv/bin/copyapp setup frida-roothide \
  --udid <UDID> --out cases/frida-roothide-setup \
  --ssh-identity cases/ssh/id_ed25519 \
  --ssh-known-hosts cases/ssh-known-hosts
.venv/bin/copyapp verify cases/frida-roothide-setup
```

Setup downloads the official Rootless Frida 17.23.3 package and checks its
pinned SHA-256 before extracting only the server and agent. It stages both in
the phone's Media directory, runs them as `mobile` on a loopback-only port,
and keeps the existing RootHide package intact. Its per-device configuration
and the SSH paths stay in ignored `toolchains/`; Copy APP forwards the sidecar
through the exact USB UDID, starts it again after a service restart, and uses
it automatically for Frida-backed commands. The installed RootHide 16.1.4
server remains available separately. Running setup again atomically replaces
the staged binaries. This path requires the phone's OpenSSH service and a
pinned mobile key; it was tested on this iPhone 14, not on every RootHide build.

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

The v0.1.0 [two-device release run](releases/v0.1.0.md) adds an independent,
known-source fixture on this phone. The original App (SwiftUI counter,
UIKit/SQLite notes, framework-backed catalog and a packaged share extension)
was development-signed and acquired with a static and sandbox index. iOS 17
initially rejected its share extension because `CFBundleDisplayName` was
missing; after that repair, the missing main-App `UILaunchScreen` exposed a
letterboxed UI and offset tap coordinates. Both metadata entries are now in
the source. The corrected original and a separately signed clone installed
through USB. All three original flows passed both iOS MCP and iCTRL; the clone
passed iOS MCP, and a formal three-flow paired check passed after existing
counter and notes test data were aligned. Five screenshot pairs were reviewed
as minor differences in system return-to-app labels. This is fixture coverage,
not evidence that a new unknown App can be cloned automatically.

The signed original's first in-place update stalled while the App was running;
after iCTRL terminated it, the same IPA installed and its install case passed
verification. The interrupted case is retained.

For iOS 17, fresh App launches now use native RSD with `--kill-existing`;
the older lockdown DVT route failed before this fix. Both sides of the final
Calculator playbook used the repaired route. A selected-flow deep report and
delivery now verify as recorded above. The fixture adds three flows and a
second technology stack, while unfamiliar-App coverage and iCTRL transport
stability remain open. Generic
RootHide `root-run` is unavailable with the installed mobile-privilege Frida
server, as established below. The 16.1.4 server crash is retained
as evidence; the working 17.23.3 sidecar is isolated from that package.
iOS 26 is still untested.

RootHide's mobile SSH shell sees the shared device Media directory at
`/rootfs/var/mobile/Media`, while the helper itself writes to
`/var/mobile/Media`. Copy APP now maps these paths and runs the pinned helper
as the paired mobile user with a 120-second device timeout. The ordinary
rootless route continues to use Frida for its bounded root command. The
generic `root-run` command is **not available** through the installed RootHide
Frida server: an instrumented, suspended shell child reported effective UID
`501` (`mobile`). Copy APP now checks the child's effective UID before resuming
it and rejects this case promptly rather than waiting for a completion marker
or claiming root execution. Its CLI also owns the exact-device SSH forward.
This does not block the verified RootHide package recovery route. App Store
encryption and protection schemes can vary, so this Remoboard result is one
package-level compatibility test.

The updated known-source fixture 0.1.2 (3) passed a real system share-sheet invocation of its packaged `FixtureShare.appex` on this iPhone 14 and displayed the exact synthetic text received from the host App. Its extension UI and prior original Counter, Notes and Catalog regressions were observed through iOS MCP; see the [two-device share-extension record](fixture-share-extension-two-device.md). This validates one fixture text path, not generic third-party extension behavior.

Sources: [Relaxin](https://github.com/owngoal-dev/Relaxin),
[RootHide developer instructions](https://github.com/roothide/Developer),
[RootHide package index](https://github.com/roothide/roothide.github.io/blob/main/Packages),
[RootHide Bootstrap injection model](https://github.com/roothide/Bootstrap).

## New-source Calculator comparison

A separate [UIKit Calculator project](../rebuild/CalculatorIOS17Fresh) was written after the reviewed report. Its first arithmetic flow derives from that report; three additional flows derive from current-device UI observations. After a Unicode minus display correction, the signed build 0.1.1 (2) passed four paired final-view assertions (`15`, `0.3`, `−7`, `0.5`) through iOS MCP on this phone. All five saved screenshot pairs were manually reviewed with minor font and system-label differences. See the [bilingual pilot record](ios17-calculator-fresh-from-report.md) for provenance and limits; this check does not establish full Calculator equivalence.

A later [current-agent `copyapp copy` parent](../cases/ios17-calculator-current-parent-20261017/manifest.json) joined acquisition, a newly reviewed four-flow report, the already authored signed project, fresh 4/4 paired assertions and five manual screenshot judgments into one completed verified case. The [v0.1.6 record](releases/v0.1.6.md) also lists the new live doctor checks on both connected phones and the remaining scope limits.
