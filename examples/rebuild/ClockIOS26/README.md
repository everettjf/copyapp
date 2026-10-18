# ClockIOS26 selected-flow rebuild

This independent UIKit app adapts the earlier `ClockCurrentProbe` source for the observed iOS 26 Clock Stopwatch screen. The verified scope is Start → Stop → Reset on one iPhone 11 running iOS 26.0.1. Other tabs are navigable scaffolding; alarms, timers, notifications and long-running behavior have not been matched to the system app. See [current status](../../../docs/current-status.md) for the named-device result and limits. Raw report, trace and visual-review cases remain local.

The source is an XcodeGen project. From this directory, run `xcodegen generate --spec project.yml` and open `CopyAppClockIOS26.xcodeproj` in Xcode. Set an Apple Development team and a provisioning profile that covers `dev.copyapp.clock.ios26` and the exact target device, then build and archive for iPhone. Package the signed `.app` under `Payload/` in an IPA and install it with `copyapp install --transport usb --udid <UDID> --ipa <SIGNED_IPA> --out <CASE>`. The signed IPA used in the device record was created this way; its private profile and certificate are not part of this repository.

`./package.sh` is a separate ad hoc `ldid` packaging route for a compatible TrollStore setup. An ad hoc IPA from that script is **not** the development-signed IPA validated on iOS 26 through USB InstallationProxy. Keep build products and signing material outside Git.
