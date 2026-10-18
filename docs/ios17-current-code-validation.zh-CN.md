# iOS 17 当前代码真机复核 · 2026-10-18

[English](ios17-current-code-validation.md) · [简体中文](ios17-current-code-validation.zh-CN.md)

通过精确 UDID `00008110-001650202E81401E` 选中 USB 连接的 iPhone 14（`iPhone14,7`，iOS 17.3.1，Relaxin/RootHide）。当前 `main` 的 `cases/ios17-return-current-doctor-20261018` 验证 USB 配对与截图、DVT 文件列表、RootHide SSH 命名空间、mobile SSH、Frida 侧车、iOS MCP 和 iCTRL 可用。`cases/ios17-return-current-calculator-analysis-20261018` 重新采集原版 Calculator 安装包、静态索引和 SSH 沙盒元数据，截图时确认原版 App 位于前台。两个案例均通过 `copyapp verify`。

原版 Calculator 与独立签名的 `dev.copyapp.calculator.ios17fresh` 0.1.1 (2) 经 iOS MCP 在 `cases/ios17-return-current-calculator-four-flow-20261018` 中重放。四条选定流程的末端 UIKit 文本断言全部通过：`7 + 8 = 15`、小数结果 `0.3`、负数结果 `−7`、百分比结果 `0.5`。五组截图均已打开审阅，并在 `cases/ios17-return-current-calculator-visual-review-20261018` 中记录为字形或系统返回标签的轻微差异。对照和审阅案例均通过 `copyapp verify`。

额外的原版 `7 + 8 = 15` 流程 `cases/ios17-return-current-calculator-traced-flow-20261018` 通过 RootHide Frida 侧车附加，依据本次采集的 Calculator 二进制绑定 `_TtC10Calculator15CalculatorModel::buttonPressed:`，五次点击各记录一次方法调用；流程和跟踪案例通过 `copyapp verify`。这只证明该选定序列的运行时路径，不代表 Calculator 完整实现原理。

iOS MCP 验收后还尝试了 iCTRL 成对重放。原版通过，复刻版在等号点击处收到 `ictrl: malformed HTTP response`（`cases/ios17-return-current-calculator-ictrl-20261018`）。单独实验确认坐标点击能改变复刻版画面，但第二次成对尝试仍在等号处收到相同传输错误（`cases/ios17-return-current-calculator-ictrl-coordinate-20261018`）。两个失败案例均保留；点击消息和随后看到的 `15` 不能证明最后一次 iCTRL 响应正常完成。之后的 doctor 再次显示通道可用。坐标点击实验代码因未解决故障而已撤回；iCTRL 对复刻版的多步操作稳定性仍待修复。

案例保存在 Git 忽略的本地目录。本次只验证指定手机、App 构建和选定流程，不证明整 App 等价、任意 App 自主复刻、iCTRL 稳定性或重启／重新越狱后的持续可用性。
