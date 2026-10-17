# iOS 17 Calculator：从审阅报告重新编写源码

[English](ios17-calculator-fresh-from-report.md) · [简体中文](ios17-calculator-fresh-from-report.zh-CN.md)

[iPhone 14 Calculator 报告](../cases/iphone14-calculator-frida17-deep-report-v3-20261017/report.md)选定了一条竖屏 `7 + 8 = 15` 流程，并把可见结果、UIKit 视图树、按键分发及主二进制身份绑定到已校验证据。此前的 iOS 17 交付复用了既有复刻版。这次以 `dev.copyapp.calculator.ios17fresh` 为 Bundle ID，独立编写了新的 [UIKit 工程](../rebuild/CalculatorIOS17Fresh)，没有沿用旧复刻版源码。实现依据报告中的选定行为和布局，不代表恢复了 Apple 原始源码或私有 Calculate 框架算法。

工程面向 iOS 17 构建、使用 Apple Development 签名，并安装到报告对应的 iPhone 14 / iOS 17.3.1。第一版通过一流程成对验收；新增的原版观察又覆盖小数加法、负数加法及百分比，并发现可见差异：原版显示数学负号 `−7`，第一版复刻显示连字符 `-7`。修复后重新安装 0.1.1（build 2）；新版本地 IPA 的 SHA-256 为 `a7d58fd85b3c8b78927dbd6153a33fe01d2d7b707203a05ac734bd2420fc1aab`，[安装案例](../cases/ios17-calculator-fresh-v2-install-20261017/install.json)通过 `copyapp verify`。

工程内的[四流程规格](../rebuild/CalculatorIOS17Fresh/feature-spec.json)明确派生自报告的一流程规格：复刻版 Bundle ID 改为新工程，并加入三条由本轮真机界面观察支持的流程；新增流程不继承报告中的静态或 Frida 结论。[正式成对案例](../cases/ios17-calculator-fresh-four-flow-check-20261017/report.md)在同一手机上重放四组原版／复刻版脚本，末端 UIKit 文本断言在两端分别通过 `15`、`0.3`、`−7`、`0.5`。[逐图审阅](../cases/ios17-calculator-fresh-four-flow-visual-review-20261017/report.md)覆盖全部五组截图，均为轻微差异：键盘布局和选定结果一致，结果字体与系统返回应用名称不同。成对和审阅案例均通过 `copyapp verify`。

因此，iOS 17 Calculator 报告中的一条流程完成了**审阅报告 → 全新源码 → 已签名 App → 同机对照**，另三条经真机观察的流程也完成了同机对照。其他运算、历史、精度边界、横屏科学模式、无障碍变体与整 App 等价仍未验收。编写时已有参考截图和选定报告，这不等于陌生 App 的零样本自主复刻。`cases/` 下的证据仅保存在本地、被 Git 忽略；源码与脚本纳入版本控制。
