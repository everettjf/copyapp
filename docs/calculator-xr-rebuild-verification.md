# Calculator 在 iPhone XR 的分析与复刻验收

当前 0.1.10 (11) 的九流程真机对照与字体修复记录见 [字体与显示区真机复核](calculator-typography-xr-review.md)；以下保留早期版本的逐次发现与失败案例。

目标是 XR / iOS 16.1.1 上的 `com.apple.calculator` 1.0.0。最新分析证据在[深度报告 v19](../cases/calculator-xr-deep-report-v19-20261015/report.md)，可执行范围在[复刻规格 v6](calculator-feature-spec-v6.json)。当前验收竖屏首页、`7 + 8 = 15`、`100 + 10% = 110`、`5 + 2 = = 9` 和 `7 + 8 = 15 → C → 0 → = → 8`；iOS 17/26 暂缓。

## 原版取证

- `copyapp analyze` 记录 USB 设备、iOS MCP 前台与截图、安装包、16 个本地类的 112 个 Objective-C 方法，以及 11 个数据容器路径的元数据。Calculator 主程序没有加密加载命令，本次没有脱壳。基础案例 `cases/calculator-xr-analysis-20261015/` 通过 `copyapp verify`。
- 原版 [按键脚本](../playbooks/calculator-basic.json) 从 AC 开始依次按 7、加号、8、等号，结果截图显示 15。macOS Vision 对保存截图的 OCR 给出 `15`；最终脚本案例为 `cases/calculator-basic-addition-ready-20261015/`。
- 一次常规 Frida 方法追踪命中 `buttonPressed:`，但其当前 IMP 在 `Calculator.axbundle`，因此 `copyapp candidates` 正确拒绝把它直接匹配为 App 主程序的静态方法。后续精确模块偏移探针同时挂载可访问性 IMP 和主程序原始入口；四次按键均按可访问性层→主程序的顺序各命中一次，ID 为 18、8、19、9。
- 现已把双入口追踪写进通用 `copyapp experiment --binary ... --objc-index ...`。在 XR 上对数字 7 再测一次，[实验记录](../cases/calculator-static-entry-experiment-20261015/experiment.json)显示辅助功能层当前 IMP 偏移 `0x5300` 与 App 本体入口偏移 `0xeb0c` 各命中 1 次；[候选队列](../cases/calculator-static-entry-candidates-20261015/candidates.json)保留当前 IMP 不匹配事实，同时生成 `buttonPressed:` 的精确哈希 REA 地址。候选案例通过 `copyapp verify`。
- REA/Hopper 与 Ghidra 对主程序入口及按钮分发表的结果，将上述 ID 对应到数字、运算符和等号分支。Hopper 对等号下游函数的反编译显示主程序以 `dlsym` 查找 `CalculatePerformExpression`。同一 XR 上的受控探针观察该私有框架实际收到 `(7)+(8)`，写出 `15` 并返回 1；记录在 `cases/calculator-direct-button-probe-v4-20261015/`，该目录和报告均通过哈希校验。反编译伪代码不是原始源码，未分析私有框架内部算法。

## 独立复刻

- [Copy Calculator 工程](../rebuild/CalculatorClone) 使用 UIKit 自行实现竖屏键盘、显示、清除状态与基础算术，不调用 Apple 私有 Calculate.framework。iOS 部署目标为 16.0。
- Xcode 27 编译、`ldid` 签名后的 IPA SHA-256 为 `26c5826da5db217eeb2fa083448b97d6789f07f756fa48ba0652689d4f710c6b`。`copyapp install` 经 XR 的 TrollStore 安装 `dev.copyapp.calculator` 0.1.2 (3)，[安装记录](../cases/calculator-clone-install-v3-20261015/install.json)显示 `installed`；iOS MCP 随后确认 App 能启动并处于前台。
- 原版与复刻版分别在同一 XR 上，以同一个 iOS MCP 后端执行等价的九步脚本；清除状态和结果状态的截图均满足稳定及就绪检查。[成对对照](../cases/calculator-basic-comparison-v4-20261015/report.md)通过 `copyapp verify`。414×896 截图的平均 RGB 绝对差分别为 0.00829（清除后）和 0.00883（显示 15 后）。复刻版观察树直接给出显示值 `15` 与清除键 `clear`；原版结果由截图和 OCR 证实。
- 增加百分比和重复等号的受控脚本后发现复刻版分别给出 `100.1` 与 `7`，而原版显示 `110` 与 `9`。复刻版现按原版实测状态修改并升级至 0.1.3 (4)，IPA SHA-256 为 `890cc459c09fecce400d379757a6b48b9a47b4646dac6b090bf83ccd156a78b7`；[安装记录](../cases/calculator-clone-install-v4-20261015/install.json)确认 TrollStore 在 XR 上更新成功。
- 更新后，两端 `100 + 10%` 的截图均在百分比后显示 `10`、等号后显示 `110`；[成对对照](../cases/calculator-percent-comparison-v4-20261015/report.md)及各自的脚本案例通过 `copyapp verify`。`copyapp ocr-file` 对四张源截图保存哈希和显示区裁剪信息，Vision 分别读到 `10`/`110`，原版及复刻版的记录见 `cases/calculator-ocr-20261015/`。
- 两端的 `5 + 2 = =` 截图均显示 `7→9`；[成对对照](../cases/calculator-repeat-comparison-v4-20261015/report.md)通过校验。细线字体的 `9` 没有被 Vision 稳定识别，此项由原始截图核读，不能表述为 OCR 自动通过。旧加法路径在新包上再次重跑，[回归对照](../cases/calculator-basic-comparison-v5-20261015/report.md)通过校验，复刻版结果 OCR 为 `15`。
- `copyapp view-tree` 又在同一 XR 的两款 App 中读取当前 UIKit 子视图。原版有 1 个窗口、47 个节点，其中 `Calculator.DisplayView` 的 frame 为 `(0,48,414,293)`，其子 `UILabel` 为结果数字；复刻版有 1 个窗口、43 个节点。重新执行两边的重复等号脚本后，[原版视图树](../cases/calculator-repeat-original-view-tree-20261015/view-tree.json)和[复刻版视图树](../cases/calculator-repeat-clone-view-tree-20261015/view-tree.json)的显示标签都直接给出 `9`，两份扫描及截图通过哈希校验。键盘上的数字 9 是另一子树，按父节点与 frame 排除。
- 现在可用一条 `copyapp flow-capture` 命令依次执行脚本与无重启视图扫描。[原版组合案例](../cases/calculator-repeat-flow-original-20261015/manifest.json)和[复刻版组合案例](../cases/calculator-repeat-flow-clone-20261015/manifest.json)都在同一 XR 完成，末端显示 `UILabel.text` 均为 `9`；子案例及父清单均通过 `copyapp verify`。新的[成对截图对照](../cases/calculator-repeat-flow-comparison-20261015/report.md)也通过哈希校验。报告 v9 直接导入原版组合案例，核对脚本和视图扫描发生在同一 App、设备、后端且相隔不超过 60 秒。
- 增加动态方法追踪后，[原版组合案例](../cases/calculator-repeat-traced-flow-original-20261015/manifest.json)再次在 XR 跑通 `5 + 2 = =`。六个点击步骤各记录一次 Calculator.axbundle 当前 IMP 和一次 Calculator.app 静态 `0xeb0c` 入口命中；完成后的 47 节点视图树显示结果 `9`。原始钩子脚本、每步计数、截图和视图树均有哈希；[报告 v10](../cases/calculator-xr-deep-report-v10-20261015/report.md)导入了这一完整案例。
- 这份组合案例又直接输入 `copyapp candidates --flow`，自动得到[按步骤归属的静态候选](../cases/calculator-traced-flow-candidates-20261015/candidates.json)：六个点击窗口均指向 `buttonPressed:` 的 `0x10000eb0c`，并保留当前 IMP 在辅助功能模块的冲突。`copyapp rea-queue` 对该地址使用 Ghidra 12.1.4 完成[函数证据](../cases/calculator-traced-flow-rea-queue-20261015/targets/01-10000eb0c/summary.json)，候选与队列均通过哈希校验。反编译得到的是 Swift/Objective-C 桥接入口，完整行为仍须沿被调用函数继续解释。
- [深度报告 v12](../cases/calculator-xr-deep-report-v12-20261015/report.md)现导入整条 REA 队列，并校验候选来源、设备、App、二进制、函数地址、provider、Evidence ID 和伪代码一致性。
- 新的 `copyapp investigate-flow` 在 XR 上从已验证的 Calculator 分析案例和原版重复等号脚本一命令重跑：自动选择 `buttonPressed:`，连续完成[操作/方法/视图证据](../cases/calculator-one-command-investigation-20261015/flow/manifest.json)、[静态候选](../cases/calculator-one-command-investigation-20261015/candidates/candidates.json)及[Ghidra 队列](../cases/calculator-one-command-investigation-20261015/rea/queue.json)。[待审摘要](../cases/calculator-one-command-investigation-20261015/review-brief.md)给出六次点击计数、函数地址及解释边界；整案通过哈希校验。
- 随后的[按钮分发真机复核](calculator-button-dispatch-xr.md)在同一 XR 上记录三条流程每次点击的原始按钮值，并对五个 Ghidra 预测的下游函数入口逐步挂钩。清除、数字、加号、百分比和等号在受测点击窗口分别只命中对应的入口；三个新分支案例均通过哈希校验。函数内部状态与调用顺序仍需单独分析。
- [深度报告 v13](../cases/calculator-xr-deep-report-v13-20261015/report.md)把这一整案作为单个证据导入，重新核对其方法选择、原版脚本、设备/App、二进制、流程候选和 REA 队列之间的关系。

## 当前边界

此前将三条选定流程放进同一个 `copyapp rebuild-check` 真机任务，并在每次脚本结束后读取原版和复刻版的 UIKit 视图树。[早期总验收案例](../cases/calculator-xr-rebuild-check-with-view-20261015/report.md)记录原版 1.0.0 (1.0) 与复刻版 0.1.3 (4) 在 XR 上的构建身份；原版与复刻版的末端显示 `UILabel` 分别各自通过 `15`、`110`、`9` 的区域文本断言，六份状态检查、脚本、视图树和成对截图均通过哈希校验。百分比中间值 `10` 与重复等号第一次结果 `7` 由成对截图及此前案例支持；当时的自动断言只检查每条流程的末端值。

这个试点证明四条规格流程能在 XR 上完成，像素差并非全面功能等价证明。运行时视图树只覆盖采集当时已加载的 UIKit 视图。原版的 `C`/`AC` 全状态规则、其他运算符下的百分比与重复等号、长小数、错误处理、横屏科学模式及私有 Calculate.framework 内部算法仍未复核。复刻版的算术用独立实现，其未测路径不应视为与原版一致。两台其他系统手机按用户当前安排不在本轮验收范围。

- `copyapp rea-bridge` 从一命令调查的 Ghidra 队列自动跟踪唯一的本地匿名被调用函数：`0x10000eb0c → 0x10000e9b8`。后者是按钮 ID 的 switch 分发，向下有 10 个候选分支，工具记录歧义后停下；[完整桥接案例](../cases/calculator-bridge-follow-20261015/manifest.json)带原始队列副本、函数证据和每条决策，已通过哈希与语义链校验。[深度报告 v14](../cases/calculator-xr-deep-report-v14-20261015/report.md)已导入该案例。

## 0.1.5 的 C/AC 修正与四流程回归

[原版 C/AC 分支实验](../cases/calculator-clear-states-branch-20261015/manifest.json)证明结果 15 后的 C 按钮值为 1，只命中清除入口和当前显示复位辅助函数；再按 AC 的值为 51，还命中全状态复位辅助函数。Ghidra 对这三个函数的证据已经导入[深度报告 v16](../cases/calculator-xr-deep-report-v16-20261015/report.md)。[原版后续行为](../cases/calculator-clear-repeat-original-20261015/manifest.json)是 `15 → C → 0 → = → 8`，说明受测 C 路径保留了重复运算所需状态。

复刻版此前把按钮创建时的固定标签 `all clear` 用于所有点击处理，所以即使画面显示 C，仍会全清除。[Copy Calculator 0.1.5](../rebuild/CalculatorClone/Sources/CalculatorViewController.swift)改用点击当下的 C/AC 状态分派，C 只清当前输入，AC 清除运算与重复状态。[安装记录](../cases/calculator-clone-install-v6-20261015/install.json)确认 0.1.5 (6) 已在 XR 上更新成功；上一包 0.1.4 (5) 的[失败实测](../cases/calculator-clear-repeat-clone-v5-20261015/manifest.json)留存，修复后的[复测](../cases/calculator-clear-repeat-clone-v6-20261015/manifest.json)末端 UIKit 标签为 8。

[四流程统一验收](../cases/calculator-four-flow-rebuild-check-v6-20261015/report.md)固定了原版 1.0.0 (1.0) 和复刻版 0.1.5 (6) 的安装身份。加法、相对百分比、重复等号、C 后重复等号的双方末端 UIKit 文本分别通过 `15`、`110`、`9`、`8` 断言；八组成对截图、脚本与视图树经 `copyapp verify` 校验。新流程的并排截图在[C 后 0](../cases/calculator-clear-repeat-rebuild-check-v6-20261015/flows/calculator-clear-repeat/comparison/comparison/step-09-side_by_side.png)和[再次等号后 8](../cases/calculator-clear-repeat-rebuild-check-v6-20261015/flows/calculator-clear-repeat/comparison/comparison/step-11-side_by_side.png)显示数值一致，但按钮字形、颜色和间距仍有可见差异；对照器的视觉状态仍为 `unreviewed`，不能当作像素级还原。其他清除前状态、精度、异常输入与横屏仍需继续验证。

## 0.1.6 的末端清除键修正

从[自动生成脚本的首次四流程复核](../cases/calculator-generated-plan-rebuild-check-20261015/report.md)审阅截图时发现：`15 → C → 0 → = → 8` 后，原版清除键是 `AC`，复刻版 0.1.5 (6) 却是 `C`。当时的 `final_view` 只检查数字 `8`，且截图就绪条件 `clear` 同时可匹配 `all clear`，因此未拦下这项差异。[并排截图](../cases/calculator-generated-plan-rebuild-check-20261015/flows/calculator-clear-repeat/comparison/comparison/step-11-side_by_side.png)保存了旧状态。

[复刻规格 v5](calculator-feature-spec-v5.json)为四条流程增加清除键的末端精确文本与区域断言：普通结果为 `C`，C 后再次等号为 `AC`。对旧证据离线重验时，原版的 `8 + AC` 通过，旧复刻版的 `8 + C` 失败。复刻源码现保留等号前的清除键状态，构建为 0.1.6 (7)，IPA SHA-256 `79f959bc077dba6734472f64105ab7d29b2bebb9765b366e579899ffaa220eb2`；[安装记录](../cases/calculator-clone-install-v7-20261015/install.json)确认 TrollStore 更新。

报告 v18 生成的[复刻交接计划](../cases/calculator-rebuild-plan-v2-20261015/runbook.md)在 XR 上实际运行了[新版四流程对照](../cases/calculator-generated-plan-rebuild-check-v7-20261015/report.md)：原版 1.0.0 (1.0) 与复刻版 0.1.6 (7) 的 `15+C`、`110+C`、`9+C`、`8+AC` 末端 UIKit 断言均在双方通过；八组截图和案例哈希通过，末端 `8+AC` 的[并排截图](../cases/calculator-generated-plan-rebuild-check-v7-20261015/flows/calculator-clear-repeat/comparison/comparison/step-11-side_by_side.png)也已核读。图片仍可见顶部返回文案、按钮字形和间距差异；视觉检查状态保持 `unreviewed`，未宣称像素级一致。

## 五流程自动交接与真机验收

新增的[原版首页流程](../cases/calculator-initial-flow-original-20261015/manifest.json)在 XR 完成前台观察、AC 点击、稳定截图和末端 UIKit 扫描，显示区为 `0`、清除键为 `AC`，案例哈希通过。报告 v19 将它作为 `flow.initial` 导入，规格 v6 为首页加上 `0+AC` 精确断言。[复刻交接 v3](../cases/calculator-rebuild-plan-v3-20261015/runbook.md)于是从同一份报告自动生成 5 对脚本，无缺失流程。

[五流程 XR 对照](../cases/calculator-five-flow-rebuild-check-v7-20261015/report.md)固定原版 1.0.0 (1.0) 与复刻版 0.1.6 (7)。双方末端 UIKit 断言分别通过 `0+AC`、`15+C`、`110+C`、`9+C` 和 `8+AC`；9 组成对截图、脚本与视图树通过哈希校验。[首页并排截图](../cases/calculator-five-flow-rebuild-check-v7-20261015/flows/calculator-initial/comparison/comparison/step-03-side_by_side.png)已核读。当前仍是选定竖屏状态覆盖，视觉检查标为 `unreviewed`；顶部返回文案、按钮字形和间距仍与原版有差异。
