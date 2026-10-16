# Calculator XR 补充运算验证

设备为 iPhone XR / iOS 16.1.1，原版 `com.apple.calculator` 1.0.0 (1.0)，独立复刻版 `dev.copyapp.calculator` 0.1.6 (7)。本次沿用此前五流程的同一已安装复刻版，没有修改源码或重新打包。

四组原版和复刻版 playbook 先分别执行，随后用 [补充规格](calculator-feature-spec-v7.json) 运行 `copyapp rebuild-check`，在每次末端截图后直接采集 UIKit 视图树，并要求显示区域恰有一个可见 `UILabel` 与预期文字相同。完整原始数据及哈希清单位于本地 [`cases/calculator-edge-rebuild-check-v1-20261015/`](../cases/calculator-edge-rebuild-check-v1-20261015/report.md)，`copyapp verify` 通过。

| 流程 | 输入 | 原版终态 | 复刻版终态 | 视图树断言 |
| --- | --- | --- | --- | --- |
| 除零 | `8 ÷ 0 =` | `Error` | `Error` | 两边通过 |
| 小数加法 | `0.1 + 0.2 =` | `0.3` | `0.3` | 两边通过 |
| 正负号加法 | `5 → +/− → + 8 =` | `3` | `3` | 两边通过 |
| 乘法 | `9 × 7 =` | `63` | `63` | 两边通过 |

原版与复刻版的末端结果均由同一台 XR 上的 UIKit `UILabel.text` 直接确认。Mac Vision OCR 对除零、小数加法和乘法的两边末端截图也识别出相同文字；正负号加法原版 OCR 为 `3`，复刻版 OCR 未检出，因此该流程以两边已保存的 UIKit 视图树为依据。一次早期小数流程因显示区和数字键同时暴露 `0` 标签而在点击前停下；四流程首轮用零键坐标完成，失败案例仍保留。

随后给 `tap_label` 增加可选 `region_points`。小数流程的 [原版](../playbooks/calculator-decimal-addition-original-region.json)和[复刻版](../playbooks/calculator-decimal-addition-rebuilt-region.json)脚本均把两个 `0` 键限定于 `[0,700,210,830]`，由当前界面元素的中心位置选择，而非直接写死点击点。[iOS MCP 单流程重测](../cases/calculator-decimal-region-rebuild-check-v1-20261015/report.md)在原版和复刻版的两次零键动作中均记录 `(108,779.5)`，终态 `0.3` 的 UIKit 断言和哈希校验通过。比较器要求配对脚本标签及区域一致。

[iCTRL 同脚本重测](../cases/calculator-decimal-region-ictrl-rebuild-check-v1-20261015/report.md)也已在 XR 完成：四次零键动作分别取得 `el_19`、`el_23`、`el_27`、`el_31` 引用，引用中心均为 `(108,779.5)`；原版及复刻版的终态 UIKit `0.3` 断言通过。iCTRL 路径先用当前 App 的可见元素树找出区域内唯一可操作的标签与元素类型，再以精确 Bundle ID 和类型查询引用；查询结果若不对应刚读到的元素，会在触控前停止。首轮点击脚本成功，但 `flow-capture` 为视图扫描重开 iCTRL 隧道，runner 把 Calculator 切到后台，导致视图扫描失败。修复为一次流程共享同一隧道后，以 `--resume` 完成验收，首次失败证据保留在案例内。

## 原版按钮分支追踪与正式报告

四条原版流程又分别执行了带 Frida 逐点击记录的 `flow-capture`，并在同次流程末端采集 UIKit 树。主程序 SHA-256 为 `8d4e059834d4c3df36f2b5ba473863b55230cb21c7eeeee7919cafdb0dc7ff3c`；当前 IMP 与主程序静态入口同时受测。受测下游偏移按数字 `0xeb5c`、运算符 `0x1136c`、等号 `0x1266c`、正负号/小数点等 `0xf09c`、清除 `0x14840` 的顺序计数。

| 流程 | 新按钮参数与本次命中 | 证据 |
| --- | --- | --- |
| `9 × 7 = 63` | `× → 6 → 0x1136c` | [原版追踪](../cases/calculator-multiplication-traced-20261015/trace/trace.json) |
| `-5 + 8 = 3` | `+/− → 3 → 0xf09c` | [原版追踪](../cases/calculator-sign-addition-traced-20261015/trace/trace.json) |
| `0.1 + 0.2 = 0.3` | 两次 `.` 均为 `10 → 0xf09c` | [原版追踪](../cases/calculator-decimal-addition-traced-20261015/trace/trace.json) |
| `8 ÷ 0 = Error` | `÷ → 5 → 0x1136c` | [原版追踪](../cases/calculator-division-zero-traced-20261015/trace/trace.json) |

数字键和等号在这些窗口也分别命中 `0xeb5c`、`0x1266c`；每个原版案例的脚本、轨迹、末端截图和视图树均通过哈希校验。[Calculator 深度报告 v21](../cases/calculator-xr-deep-report-v21-20261015/report.md)把四组轨迹与此前静态 switch 伪代码、沙盒及界面证据合并为 56 组可核验来源，并将机器可读规格扩为九条流程。分支入口和输出可证，Calculate.framework 内部算法、完整精度策略以及除零后状态仍未知。

自动生成的[九流程计划](../cases/calculator-rebuild-plan-v5-20261015/runbook.md)与 [Agent 任务](../cases/calculator-agent-task-v3-20261015/TASK.md)均有 9/9 原版脚本且无来源缺口。[统一 XR 对照](../cases/calculator-nine-flow-rebuild-check-v1-20261015/report.md)的九条末端 UIKit 断言全部通过；[交付核验](../cases/calculator-agent-delivery-v4-20261015/report.md)绑定同一已安装复刻版、源码树和 IPA 哈希。它不包含独立 Agent CLI 生成源码的运行记录。[18 对截图诊断](../cases/calculator-nine-flow-visual-audit-v1-20261015/report.md)沿用此前阈值且均在阈值内，显式视觉检查仍未审阅。

[截图区域审计](../cases/calculator-edge-visual-audit-v1-20261015/report.md)检查 9 对截图的 `[0,80,414,820]` 区域，最大归一化平均 RGB 差为 0.01364，最大差异像素比例为 2.469%。审计沿用此前五流程的阈值，且是在本次截图取得后执行，属于诊断。人工查看的末端画面显示键盘布局和结果位置接近，但字形粗细、`+/−` 图形以及状态栏返回标签可见差异。四组比较的显式视觉状态仍是 `unreviewed`。

这些结果只证明列出的路径在该设备上的末端行为及受测按钮分支。中间状态、长数字格式、科学计算横屏、其它操作顺序及完整 App 等价仍未验证。
