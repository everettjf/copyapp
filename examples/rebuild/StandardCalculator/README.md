# Standard-mode acceptance calculator

This independent UIKit example adapts
[CalculatorIOS17Fresh](../CalculatorIOS17Fresh/README.md). It preserves the two
Swift sources, unsigned XcodeGen configuration and paired playbooks from the
October 23, 2026 standard-mode acceptance job. The source and scripts are copied
without changes; the original ignored job and its evidence remain in place.
No Apple executable, extracted artwork, account data or signing credentials are
included. The independent Bundle ID is `dev.copyapp.standardcalculator`.

The named iPhone 11 / iOS 26.0.1 acceptance covered clear then `7 + 8 = 15`, with
two screenshot pairs reviewed as minor differences. The phone had an inactive
jailbreak; this is not a pristine-device or arbitrary-device compatibility claim.
History and mode controls in the header are decorative. Other arithmetic,
layouts and whole-App parity are unverified. See the
[acceptance ledger](../../../docs/ios-device-support-acceptance.md).

## Build

Install Xcode and XcodeGen, then run from this directory:

```sh
xcodegen generate --spec project.yml
xcodebuild -project CopyAppStandardCalculator.xcodeproj \
  -scheme CopyAppStandardCalculator -configuration Debug \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```

This builds a simulator App; it does not install or test it. For a real phone,
configure your own development team and compatible provisioning profile, build
and package a signed IPA, then follow the
[standard-mode guide](../../../docs/ios-standard-mode.md). No personal signing
configuration is stored in this example.

`playbooks/addition.original.json` and `playbooks/addition.rebuilt.json` preserve
the saved iOS 26 labels and assertions. Replay requires the exact requested USB
device, a ready standard-mode backend, and a fresh output case. A new build or
replay does not inherit the historical acceptance result automatically.
