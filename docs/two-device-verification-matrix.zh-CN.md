# iOS 16 与 17 双机验证矩阵

[English](two-device-verification-matrix.md) · [简体中文](two-device-verification-matrix.zh-CN.md)

此表区分“通道可用”和“App 有可见结果”。设备为 iPhone XR / iOS 16.1.1 / Dopamine rootless，以及 iPhone 14 / iOS 17.3.1 / Relaxin RootHide。本地 `cases/` 证据被 Git 忽略，需在测试 Mac 上用 `copyapp verify <CASE>` 核验；提交的脚本不含手机私有数据。

| 能力 | XR / iOS 16 | iPhone 14 / iOS 17 | 边界 |
| --- | --- | --- | --- |
| USB、截图、开发者文件系统、固定主机密钥的 mobile SSH、Frida、iOS MCP、已配对 iCTRL | `cases/ios16-v016-doctor-20261017/` 全部可用 | `cases/ios17-v016-doctor-20261017/` 全部可用 | 各代表一台手机的当前配置；能力探针通过不等于 App 行为通过。 |
| 包、静态与有界沙盒证据 | Calculator 当前 Agent 父案例 `cases/calculator-current-auto-workflow-20261016/` 完成 | Calculator 父案例 `cases/ios17-calculator-current-parent-20261017/` 完成 | 只覆盖该构建及选定路径，未取得整个实时数据容器的一致性快照。 |
| 加密 App 分析 | XR 发布记录中的 DeepSeek/Kimi 整包恢复 | [iPhone 14 记录](relaxin-roothide-iphone14.md)中的 Remoboard 主 App 与键盘扩展恢复 | 分析 IPA 不保留原签名；其他保护手段未覆盖。 |
| 选定报告 → 独立 App → 同机对照 | Calculator 父案例 3/3 结果、三对截图审阅 | Calculator 父案例 4/4 结果、五对截图审阅 | 两份独立源码均早于所引用的父案例；未证明整 App 等价或零样本生成。 |
| 可选 Hopper 直连反编译 | `cases/fixture-counter-hopper-investigation-v2-20261016/` 将夹具 UI、Frida、候选与 Hopper 调查贯通并导入报告 | `cases/ios17-hopper-current-parent-20261017/` 完成 `--analysis-provider hopper-direct` 的 Calculator `copy` 父案例，包含一条原版跟踪、Hopper 伪代码、审阅报告、签名独立复刻版、一条通过的成对结果及两对截图审阅 | 仅一条入口和流程。源码早于父案例；伪代码不是原始源码或完整算法。 |
| 两种界面后端：左滑删位 | **同一提交脚本** `playbooks/ios17-calculator-delete-digit.json` 在 iOS MCP 与 iCTRL 均显示 `98 → 9`：`cases/ios16-calculator-gesture-{iosmcp,ictrl}-v016-20261017/` | 同脚本、同结果：`cases/ios17-calculator-gesture-{iosmcp,ictrl}-20261017/` | 仅一条竖屏左滑和一组数字；前后截图与末端 UIKit 文字验证了可见效果。 |
| 两种界面后端：合成文本输入 | **同一提交脚本** `playbooks/ios17-safari-synthetic-address-input.json` 在 Safari 地址栏通过两个后端显示 `copyapp-fixture-hello`：`cases/ios16-safari-text-{iosmcp,ictrl}-20261017/` | 同脚本、同可见文字：`cases/ios17-safari-text-{iosmcp,ictrl}-20261017/` | 未提交搜索；不能推断所有 App 和输入框都接受文本。XR Translate 的 iOS MCP 失败案例仍然保留。 |
| 已知源码夹具分享扩展 | [v0.1.5](releases/v0.1.5.zh-CN.md)中的固定文本接收与 Counter/Notes/Catalog 回归 | 相同 | 仅一种纯文本输入；其他内容类型和无关扩展未验证。 |

Safari 结果缩小了 XR Translate 旧结论：**XR 的 iOS MCP 文本输入并非整体不可用**。Translate 输入框没有显示 `hello` 的失败仍未解决；该流程暂用已验证的 iCTRL 路径。iOS 17 上尝试由 iOS MCP 启动 `com.apple.Translate` 返回启动失败，保留在 `cases/ios17-translate-entry-survey-20261017/`；Safari 测试不能替代 Translate 功能验证。

仍需解决的产品级门槛包括：陌生 App 的自主发现和全新源码生成、独立 Claude CLI 运行、更广的 App 状态与服务端行为及完整沙盒解释。这些不能由绿色设备探针、选定流程通过或发布标签推出。iOS 26 不在此双机矩阵内。
