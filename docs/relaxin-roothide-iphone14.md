# Relaxin / RootHide on iPhone 14 (iOS 17.3.1)

This is a **partial, real-device validation** dated 2026-10-17. The exact USB
device was an iPhone 14 (`iPhone14,7`, iOS 17.3.1, arm64e) running Relaxin
0.5.5 with a RootHide bootstrap. These results do not establish full Copy APP
support on iOS 17 or on other RootHide configurations.

## Verified on the phone

| Capability | Observation |
| --- | --- |
| USB identity and developer services | The requested UDID matched the connected phone. Native RSD launched Calculator and captured a screenshot; the USB accessibility survey returned 33 elements. The survey and bundle-index cases passed `copyapp verify`. |
| iCTRL | The development-signed Copy APP runner installed, its XCTest session started, encrypted pairing completed, and UI observation and taps worked. A Calculator `7 + 5 = 12` playbook passed its first seven steps, including the result assertion. Its final screenshot step returned an empty HTTP response; a separate screenshot call worked. UI transport stability remains open. |
| OpenSSH | RootHide's `openssh-server`, `openssh-client` and `openssh-sftp-server` 9.2p1 installed. A dedicated, pinned `mobile` public-key login worked over a USB-only port forward. No password is stored in the repository. |
| App acquisition | Over SSH, Copy APP copied the installed Calculator bundle (15 files), made a 472 KB analysis snapshot, and generated a static Mach-O/Objective-C report with 17 indexed classes. The main executable has no encryption load command. The static case passed `copyapp verify`; the repacked snapshot is not asserted to be an installable Apple IPA. |
| Sandbox | A bounded SSH index captured 20 entries and seven files in Calculator's data container. This is an index, not an atomic copy of live app data. |
| Frida | RootHide's `re.frida.server` 16.1.4 runs. A same-version isolated Mac client enumerated processes and apps, but attaching to Calculator and Fila failed with `ProcessNotRespondingError` and produced `EXC_GUARD / GUARD_TYPE_MACH_PORT` app crashes at `task_swap_exception_ports`. Runtime tracing is **not** verified. The main Mac environment's Frida 17.23.3 is also version-mismatched with the phone server. |
| Copy APP iOS MCP | The arm64e RootHide package built and installed as `com.copyapp.mcp` 0.1.4-4. Its dylib and SpringBoard filter are present, and SpringBoard restarted, but port 8090 did not become reachable. No ElleKit or MobileSubstrate package is installed. Whether SpringBoard loaded this dylib is unverified; the missing standard tweak loader is the leading explanation, not yet a proven cause. |
| Rebuilt App | Direct USB installation rejected unsigned and ad hoc signed attempts. An Apple Development signed Calculator clone then built with a profile containing this device and installed through USB InstallationProxy. The `copyapp install --transport usb` case verified exact UDID, IPA hash, version/build and `ProfileValidated=true`. Launch and paired original/clone comparison remain unverified while the phone is locked. |

The local evidence lives in Git-ignored `cases/iphone14-*20261017/`, especially
`iphone14-after-roothide-openssh`, `iphone14-calculator-acquire-attempt`,
`iphone14-calculator-ictrl-playbook-v4`, `iphone14-calculator-sandbox`,
`iphone14-frida-crashes`, `iphone14-calculator-usb-install`, and
`iphone14-after-respring`. The phone was locked
at the end of this session, so no further app UI installation was attempted.

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
Both archives were staged in the phone's Media directory over pinned USB SSH;
neither ElleKit nor the corrected Copy APP package has been installed yet.
The configured APT source did not authenticate ElleKit, so the source and
recorded hash remain explicit in this test record.

After the phone is unlocked, the remaining device check is to install the
verified ElleKit archive and corrected Copy APP package through the normal
phone package UI, restart SpringBoard, then verify the loopback health
endpoint and bounded UI tools. Keep iCTRL as the already working UI backend
until that succeeds. Frida attach needs a compatible RootHide server/client
combination validated against this exact iOS build; process enumeration alone
does not count. The signed clone is installed, but its launch, selected behavior
and same-device comparison still need verification. Do not infer those results
from the iOS 16 XR pilot.

Sources: [Relaxin](https://github.com/owngoal-dev/Relaxin),
[RootHide developer instructions](https://github.com/roothide/Developer),
[RootHide package index](https://github.com/roothide/roothide.github.io/blob/main/Packages),
[RootHide Bootstrap injection model](https://github.com/roothide/Bootstrap).
