# iOS 17 Calculator selected-flow rebuild

This is a newly authored UIKit project for the iPhone 14 / iOS 17.3.1 [Calculator report](../../docs/ios17-calculator-fresh-from-report.md). It uses Bundle ID `dev.copyapp.calculator.ios17fresh` and targets iOS 17.0 or later. The original report covers fresh-launch `7 + 8 = 15`; three additional flows were observed on that phone and added to the tracked [selected-flow specification](feature-spec.json). They cover decimal addition (`0.3`), negative addition (`−7`) and percentage (`0.5`). This does not establish the original Calculator's full arithmetic state machine.

Generate the Xcode project with `xcodegen generate --spec project.yml`, then build the `CopyAppCalculatorIOS17Fresh` scheme for a generic iOS device. Sign the App with your own Apple Development identity and a provisioning profile covering the Bundle ID. Installation, all four exact final results and five screenshot pairs were checked on the named iPhone 14; the signed IPA and device evidence stay in ignored local `cases/`.

From the repository root, after installing the signed App on the exact iPhone, run:

```sh
.venv/bin/copyapp rebuild-check --udid <IPHONE_14_UDID> \
  --feature-spec rebuild/CalculatorIOS17Fresh/feature-spec.json --backend ios-mcp \
  --pair calculator-basic-addition rebuild/CalculatorIOS17Fresh/playbooks/basic-addition.original.json rebuild/CalculatorIOS17Fresh/playbooks/basic-addition.rebuilt.json \
  --pair decimal-addition rebuild/CalculatorIOS17Fresh/playbooks/decimal-addition.original.json rebuild/CalculatorIOS17Fresh/playbooks/decimal-addition.rebuilt.json \
  --pair negative-addition rebuild/CalculatorIOS17Fresh/playbooks/negative-addition.original.json rebuild/CalculatorIOS17Fresh/playbooks/negative-addition.rebuilt.json \
  --pair percent-of-fifty rebuild/CalculatorIOS17Fresh/playbooks/percent-of-fifty.original.json rebuild/CalculatorIOS17Fresh/playbooks/percent-of-fifty.rebuilt.json \
  --out cases/calculator-ios17fresh-recheck
```

The source does not reuse the earlier `CalculatorFreshProbe` implementation. The [English validation note](../../docs/ios17-calculator-fresh-from-report.md) and [Chinese note](../../docs/ios17-calculator-fresh-from-report.zh-CN.md) give the exact evidence and limits.
