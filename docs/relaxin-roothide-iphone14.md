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
- The Copy APP iOS MCP tweak and the optional iCTRL runner were not reachable.
  The tweak has not been built or installed for RootHide.
- The standard DVT filesystem service was unavailable through lockdown, and
  ordinary developer services did not expose the package or sandbox. The
  preliminary survey therefore has no IPA, decrypted binary or native-code
  analysis.
- The current root command bridge still assumes `/var/jb/bin/sh`, and the
  deep acquisition path needs a validated RootHide path and process launch.

These are explicit blockers to the detailed analysis and rebuild stages. A
passing USB survey does **not** establish full Copy APP support for Relaxin.

## RootHide package preparation

RootHide uses a randomized jailbreak root rather than a fixed `/var/jb` path.
Its tweak builds require the RootHide Theos fork, `THEOS_PACKAGE_SCHEME=roothide`
and the real `roothide.h` path API. Copy APP's iOS MCP source now accepts that
build scheme, chooses arm64e, links the RootHide library and excludes its old
rootless-only header. The generic `iphoneos-arm` control field lets the selected
Theos package scheme set the package architecture. This is source preparation,
**not a validated `.deb`**: the Mac
currently has no Theos installation, and no RootHide package has been deployed.

For a future build, the intended command is:

```sh
THEOS=/path/to/roothide-theos make -C device/ios-mcp THEOS_PACKAGE_SCHEME=roothide package
```

Inspect the package architecture and archive paths before installing it. The
RootHide OpenSSH and Frida packages must also match this jailbreak; a normal
rootless `.deb` is not a substitute. Then rerun `copyapp onboard --stage analyze`
and validate privileged file access, Frida attach, iOS MCP health and UI tools,
and an actual App acquisition before claiming deep support.

Sources: [Relaxin](https://github.com/owngoal-dev/Relaxin),
[RootHide developer instructions](https://github.com/roothide/Developer),
[RootHide path model](https://github.com/roothide/Developer/blob/main/roothide.md),
[RootHide package index](https://github.com/roothide/roothide.github.io/blob/main/Packages).
