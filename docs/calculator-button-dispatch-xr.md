# Calculator 按钮 ID 与静态分支：XR 实测

目标为 `com.apple.calculator` 1.0.0、iPhone XR / iOS 16.1.1。三个新案例分别是[加法](../cases/calculator-arg2-addition-20261015/manifest.json)、[百分比](../cases/calculator-arg2-percent-20261015/manifest.json)、[重复等号](../cases/calculator-arg2-repeat-20261015/manifest.json)；各案例的脚本、截图、Frida 钩子、逐步轨迹和末端 UIKit 视图树均通过 `copyapp verify`。它们使用同一份 SHA-256 为 `8d4e059834d4c3df36f2b5ba473863b55230cb21c7eeeee7919cafdb0dc7ff3c` 的 Calculator 主程序静态索引。

## 运行时观察

Frida 同时钩住 `CalculatorModel::buttonPressed:` 的当前 Objective-C IMP 和主程序本体偏移 `0xeb0c`。前者位于系统 `Calculator.axbundle`；每次记录的两个入口各命中一次，原始第 3 个参数低 32 位相同。以下数字是原始参数值，作为按钮 ID 的解释还依赖先前[受控探针](../cases/calculator-direct-button-probe-v4-20261015/probe.json)与按键标签的一致性。

| 原版流程 | 点击标签与观测值 |
| --- | --- |
| `7 + 8 =` | `AC→51`、`7→18`、`add→8`、`8→19`、`equals→9` |
| `100 + 10% =` | 清除坐标→51、`1→12`、`0→11`、`0→11`、`add→8`、`1→12`、`0→11`、`percent→4`、`equals→9` |
| `5 + 2 = =` | 清除坐标→51、`5→16`、`add→8`、`2→13`、`equals→9`、`equals→9` |

对应的逐步原始记录在[加法轨迹](../cases/calculator-arg2-addition-20261015/trace/trace.json)、[百分比轨迹](../cases/calculator-arg2-percent-20261015/trace/trace.json)和[重复等号轨迹](../cases/calculator-arg2-repeat-20261015/trace/trace.json)。每条轨迹包含点击步骤索引、入口类型和参数值；没有保存任意对象内容或返回值。

## 静态分支预测

[Ghidra 分发函数伪代码](../cases/calculator-bridge-follow-20261015/targets/01-10000e9b8/pseudocode.txt)显示入口 `0x10000eb0c` 调用 `FUN_10000e9b8`，后者以参数值做 switch。将上面的观测值代入该伪代码，可得到下列**静态预测**：

| 原始值 | 已见按钮 | Ghidra 伪代码的目标 |
| ---: | --- | --- |
| 11、12、13、16、18、19 | 数字 0、1、2、5、7、8 | `FUN_10000eb5c` |
| 8 | add | `FUN_10001136c` |
| 9 | equals | `FUN_10001266c` |
| 4 | percent | `FUN_10000f09c` |
| 1、51 (`0x33`) | C、AC | `FUN_100014840`（switch 默认分支） |

## 下游入口的真机复核

`flow-capture --branch-offset` 在同一主程序镜像上按偏移挂钩上述五个函数入口。新的[加法案例](../cases/calculator-branch-addition-20261015/manifest.json)、[百分比案例](../cases/calculator-branch-percent-20261015/manifest.json)、[重复等号案例](../cases/calculator-branch-repeat-20261015/manifest.json)均在 XR 完成，并通过 `copyapp verify`。五个偏移按 `0xeb5c / 0x1136c / 0x1266c / 0xf09c / 0x14840` 的固定顺序记录。

| 按钮值与可见动作 | 同一点击窗口内实际命中的下游入口 | 三流程观测次数 |
| --- | --- | ---: |
| 11、12、13、16、18、19；数字 | `0xeb5c` | 9 |
| 8；add | `0x1136c` | 3 |
| 9；equals | `0x1266c` | 4 |
| 4；percent | `0xf09c` | 1 |
| 51；清除 | `0x14840` | 3 |

逐步计数见[加法轨迹](../cases/calculator-branch-addition-20261015/trace/trace.json)、[百分比轨迹](../cases/calculator-branch-percent-20261015/trace/trace.json)及[重复等号轨迹](../cases/calculator-branch-repeat-20261015/trace/trace.json)。每个受测点击窗口中，当前 IMP、主程序 `buttonPressed:` 和表中相应下游入口各命中一次；另外四个受测入口为零。这把静态预测提升为**选定流程中的运行时入口证据**。计数仍不证明函数调用顺序，也不解释函数内部状态或私有 Calculate.framework 的算法；模块路径和偏移不能单独证明内存字节与采集文件完全一致。三条流程的末端显示及复刻对照见[Calculator 验收记录](calculator-xr-rebuild-verification.md)。

另一次[C/AC 连续真机实验](../cases/calculator-clear-states-branch-20261015/trace/trace.json)记录：结果 15 后按 C 的原始值为 1，命中 `0x14840 → 0x12cac`；随后按 AC 的值为 51，命中 `0x14840 → 0x12db8`，而 `0x12db8` 同一窗口还调用 `0x12cac`。这里的箭头表示反编译调用关系与同一点击窗口命中，不表示 Frida 已保存严格时序。状态复位函数的 Ghidra 证据及 `C → 0 → = → 8` 的可见结果已进入[深度报告 v16](../cases/calculator-xr-deep-report-v16-20261015/report.md)。

## 四流程自动汇总

`copyapp branch-map` 对上述三条流程和 C/AC 流程逐一重验后，产出[分支观测映射](../cases/calculator-button-branch-map-20261015/report.md)与[逐步 JSON](../cases/calculator-button-branch-map-20261015/branch-map.json)。27 个点击窗口中，原始值 4、8、9、11、12、13、16、18 分别只观测到所列单一候选入口；值 1、19、51 有额外的辅助入口同时命中，保留为多分支观测。第四条流程只挂钩清除相关的三个函数，因此未挂钩的入口按未知处理，不计为零命中。该自动映射可复用到其他 App，但仍不能替代对分发代码、状态条件和可见行为的审阅。

映射已经作为 `branch.buttons` 导入[深度报告 v17](../cases/calculator-xr-deep-report-v17-20261015/report.md)。报告保留四份来源流程和主程序副本；从这些副本重跑后，27 条逐步观察及汇总映射与原案例相同。[来源索引](../cases/calculator-xr-deep-report-v17-20261015/evidence/branch.buttons/replay-sources.json)列出相对路径和哈希。
