# iOS 17 Calculator selected-flow rebuild

This is a newly authored UIKit project for the iPhone 14 / iOS 17.3.1 [Calculator report](../../docs/ios17-calculator-fresh-from-report.md). It uses Bundle ID `dev.copyapp.calculator.ios17fresh` and targets iOS 17.0 or later. Its verified scope is the report's fresh-launch `7 + 8 = 15` flow; the keypad also implements basic decimal entry and four operations, but those extra paths are not part of this project's formal delivery.

Generate the Xcode project with `xcodegen generate --spec project.yml`, then build the `CopyAppCalculatorIOS17Fresh` scheme for a generic iOS device. Sign the App with your own Apple Development identity and a provisioning profile covering the Bundle ID. Installation, the exact final result and two screenshot pairs were checked on the named iPhone 14; the signed IPA and device evidence stay in ignored local `cases/`.

This source does not reuse the earlier `CalculatorFreshProbe` implementation. The [English validation note](../../docs/ios17-calculator-fresh-from-report.md) and [Chinese note](../../docs/ios17-calculator-fresh-from-report.zh-CN.md) give the exact evidence and limits.
