# Relaxin / RootHide on iPhone 14 (iOS 17.3.1)

This is a **partial, real-device validation** dated 2026-10-17. The connected
device was an iPhone 14 (`iPhone14,7`, iOS 17.3.1, arm64e). The user identified
its active jailbreak as Relaxin with RootHide. Copy APP has not independently
verified the jailbreak installation or obtained privileged access on this phone.

## What ran

| Capability | Observation |
| --- | --- |
| Exact-device USB lockdown | Available; the requested UDID matched the connected phone. |
| Installed App listing | Available; Calculator resolved to `com.apple.calculator`. |
| Developer Disk Image | Mounted successfully with `pymobiledevice3 mounter auto-mount`. |
| App launch | Calculator launched through `pymobiledevice3 developer dvt launch --native`. |
| Screenshot | Native RSD screenshot captured; the earlier lockdown screenshot service returned `InvalidService`. |
| Accessibility survey | 33 elements returned after launch; the screenshot was visually reviewed as Calculator. |
| Case integrity | `copyapp verify` passed for the Calculator USB survey. |
| App bundle index | Native RSD listed 56 Calculator bundle paths; the updated survey case passed `copyapp verify`. This is a directory index, not file export. |
| iCTRL package | The existing development-signed Copy APP iCTRL XCTest IPA installed through USB InstallationProxy. The test process started after the phone's one-time XCTest passcode approval. Its control server was not yet reachable during this run. |
| RootHide tweak build | RootHide Theos produced a `com.copyapp.mcp` `iphoneos-arm64e` package. USB AFC staged it under `/var/mobile/Media/`; the read-back SHA-256 matched. It was not installed. |
| Rebuilt Calculator IPA | The independent clone built for arm64. Direct USB installation rejected the original IPA for missing an app bundle signature and a fully ad hoc signed variant for an invalid signature. No clone was installed. |

Copy APP now selects the native RSD route for macOS/iOS 17+ screenshot and App
launch, while retaining the validated lockdown route for iOS 16. The local
survey case is under `cases/iphone14-relaxin-calculator-survey-20261017/` and
is Git-ignored because it contains device evidence. Its screenshot and UI
elements do not have a verified foreground Bundle ID; the report says so.

## What is still missing

- The USB-forwarded SSH connection closed before login. No package or sandbox
  acquisition through SSH has been validated on this phone.
- Frida could enumerate processes, but its actual access mode was `jailed`.
  Attaching to an App failed. Copy APP's doctor now requires `full` Frida access
  before marking runtime tracing available. RootHide's own package index lists
  a `re.frida.server` `iphoneos-arm64e` package at 16.1.4; that older listing
  does not establish compatibility with this iOS build or host Frida 17.
- The Copy APP iOS MCP tweak has been built and staged but not installed. The
  iCTRL runner installed and XCTest began, but the control server was not
  reachable during the run. UI control and pairing remain unverified.
- The standard DVT filesystem service was unavailable through lockdown. Native
  RSD can index bundle paths but cannot export the package or sandbox. The
  survey therefore has no IPA, decrypted binary or native-code analysis.
- The current root command bridge still assumes `/var/jb/bin/sh`, and the
  deep acquisition path needs a validated RootHide path and process launch.

These are explicit blockers to the detailed analysis and rebuild stages. A
passing USB survey does **not** establish full Copy APP support for Relaxin.

## RootHide package preparation

RootHide uses a randomized jailbreak root rather than a fixed `/var/jb` path.
Its tweak builds require the RootHide Theos fork, `THEOS_PACKAGE_SCHEME=roothide`
and the real `roothide.h` path API. Copy APP's iOS MCP source accepts that build
scheme, chooses arm64e, links the RootHide library and excludes its old
rootless-only header. The generic `iphoneos-arm` control field lets the selected
Theos package scheme set the package architecture. The build completed with the
RootHide Theos fork and iPhoneOS 16.5 SDK. The resulting package contains the
MobileSubstrate dylib and filter plist, and its archive architecture is
`iphoneos-arm64e`. Package creation and byte transfer do not prove that the
tweak loads correctly on this phone.

The build command was:

```sh
THEOS=/path/to/roothide-theos make -C device/ios-mcp THEOS_PACKAGE_SCHEME=roothide package
```

The built package SHA-256 is
`1cda335795ef7785b50c6bd8070f601d92bce7d55ca9445ece09e3d3bf991686`.
The RootHide OpenSSH and Frida packages must also match this jailbreak; a
normal rootless `.deb` is not a substitute. After installing the tweak, rerun
`copyapp onboard --stage analyze` and validate privileged file access, Frida
attach, iOS MCP health and UI tools, and an actual App acquisition before
claiming deep support.

Sources: [Relaxin](https://github.com/owngoal-dev/Relaxin),
[RootHide developer instructions](https://github.com/roothide/Developer),
[RootHide path model](https://github.com/roothide/Developer/blob/main/roothide.md),
[RootHide package index](https://github.com/roothide/roothide.github.io/blob/main/Packages).
