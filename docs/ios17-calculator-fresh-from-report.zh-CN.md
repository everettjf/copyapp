# iOS 17 Calculator：从审阅报告重新编写源码

[English](ios17-calculator-fresh-from-report.md) · [简体中文](ios17-calculator-fresh-from-report.zh-CN.md)

[iPhone 14 Calculator 报告](../cases/iphone14-calculator-frida17-deep-report-v3-20261017/report.md)选定了一条竖屏 `7 + 8 = 15` 流程，并把可见结果、UIKit 视图树、按键分发及主二进制身份绑定到已校验证据。此前的 iOS 17 交付复用了既有复刻版。这次以 `dev.copyapp.calculator.ios17fresh` 为 Bundle ID，独立编写了新的 [UIKit 工程](../rebuild/CalculatorIOS17Fresh)，没有沿用旧复刻版源码。实现依据报告中的选定行为和布局，不代表恢复了 Apple 原始源码或私有 Calculate 框架算法。

工程面向 iOS 17 构建、使用 Apple Development 签名，并安装到报告对应的 iPhone 14 / iOS 17.3.1。使用 iOS MCP 后端复核，本地 IPA 的 SHA-256 为 `d3ae127dbad0576b0552859a70a716b01528eda19fa83f81d388df73770b884b`。[安装](../cases/ios17-calculator-fresh-install-20261017/install.json)与首次[复刻版脚本](../cases/ios17-calculator-fresh-basic-ui-20261017/manifest.json)通过 `copyapp verify`；末端无障碍观察包含精确文本 `15`。

正式成对验收使用报告的一流程功能规格的本地副本，仅把 `rebuilt_bundle_id` 改为新 Bundle ID。这是明确标注的派生规格，并不声称原报告本来指向新 App。[成对案例](../cases/ios17-calculator-fresh-rebuild-check-20261017/report.md)在原版和新 App 上重放同一条 `all clear → 7 → add → 8 → equals` 脚本，保存两组截图，并在两端通过最终 UIKit 文本断言。[逐图审阅](../cases/ios17-calculator-fresh-visual-review-20261017/report.md)将两组判为轻微差异：数字结果和键盘排布一致，结果字形及系统返回应用名称不同。两个案例均通过 `copyapp verify`。

因此，iOS 17 Calculator 的这一条流程完成了**审阅报告 → 全新源码 → 已签名 App → 同机对照**。小数、其他运算、历史、精度边界、横屏科学模式、无障碍变体与整 App 等价仍未验收。编写时已有参考截图和选定报告，这不等于陌生 App 的零样本自主复刻。`cases/` 下的证据仅保存在本地、被 Git 忽略；源码工程纳入版本控制。
