# Copy APP device UI service

This directory contains selected MIT-licensed sources from
[`witchan/ios-mcp`](https://github.com/witchan/ios-mcp) at commit
`62c4464f688c8f269419924b1a19c996de75f175`. The upstream `LICENSE`
and `NOTICE` are included. The package is built independently as
`com.copyapp.mcp`; it does not package upstream AppSync, root helpers,
package installers, Settings bundle, OCR worker, or third-party models.

Local changes:

- Build only a rootless SpringBoard tweak for arm64 and arm64e.
- Bind its HTTP listener to `127.0.0.1:8090` for USB port forwarding.
- Advertise and accept only UI observation, gesture, text input, and App launch tools.
- Return 404 for `/upload_file` and `/download_file`.
- Use a separate Copy APP preferences domain and package identity.
- Provide a rootless compatibility header for upstream `jbroot` path calls.
- Refuse in-process Vision OCR inside SpringBoard. On XR/iOS 16.1.1 the
  detector crashed SpringBoard twice, including with `usesCPUOnly`; the Mac
  adapter now runs Vision against a USB screenshot instead.

Build with a complete Xcode installation, Theos, its iPhoneOS16.5 SDK, and
`ldid` on the Mac:

```sh
THEOS=/path/to/theos CLANG_MODULE_CACHE_PATH=/private/tmp/copyapp-clang-modules make package
```

The resulting `.deb` is under `packages/`. Before deploying a new build,
inspect its archive paths and confirm that it contains only the tweak,
filter plist, and copyright notices. The selected build was installed on an
iPhone XR running iOS 16.1.1 via Filza. After `sbreload`, the USB-forwarded
service passed identity and health checks. Screenshot, frontmost App
observation, launch, and tap were exercised on original Compass and an
independent rebuild. The first 0.1.2 reload did not load the tweak because
ElleKit had entered Safe Mode after the OCR crashes. After preserving its
marker, clearing it and using the standard `ldrestart` command, the 0.1.2
service recovered. Version 0.1.3 now removes direct OCR from its exposed UI
tools and rejects OCR requests inside `describe_screen`; these guards passed
live XR checks. The screenshot-to-Mac OCR route passed on Compass. See
`docs/xr-ocr-validation.md`. Other device/OS combinations remain untested.
