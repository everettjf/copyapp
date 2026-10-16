# Copy APP 与 REA 的边界

Copy APP 的正式分析与复刻链路不要求安装 REA。手机端采集、整包恢复、Mach-O/Objective-C 与 Assets.car 资源索引、UI 和 Frida 实验、原生汇编、直接 Ghidra 反编译、证据报告、Agent 任务和真机对照都由本仓库的命令串联。需要函数伪代码时选 `--provider ghidra-direct`；这个选项调用本仓库的 `CopyAppDecompile.java`，不调用 REA CLI、MCP 或桥接服务。外部 Ghidra、JDK、Frida、macOS `assetutil` 和手机端组件仍需按所选能力安装。

`rea-function`、`rea-queue`、`rea-bridge` 及显式 `--provider ghidra|hopper` 是兼容旧案例的可选入口。它们不会在 `--provider none` 或 `ghidra-direct` 时执行。旧报告可继续验证其已保存的 REA 证据，但新案例优先使用直接 Ghidra 证据。

## 选择性移植

本机 REA 源码位于 `<REA_CHECKOUT>`，核对的提交为 `21eff3bae10f58711a35ad44f86e9f96f9bb4790`。REA 以 MIT 许可证发布，文本保存在本仓库的 [`REA-LICENSE.txt`](third-party/REA-LICENSE.txt)。直接复制实质代码时，须在对应文件标明原文件、提交和修改，并附带原许可。`CopyAppAnalysisOptions.java` 参考了 REA 的分析选项机制；`CopyAppDecompile.java` 借鉴了 REA 函数资料中的调用者/被调用者观察，改写成有限的单次 Ghidra JSON 输出。它不包含 REA 的会话桥接，Copy APP 自己负责证据格式、来源校验和队列。

| REA 中有价值的能力 | Copy APP 当前实现 | 后续判断 |
| --- | --- | --- |
| Ghidra 函数伪代码与分析器配置 | `ghidra-function`、`ghidra-queue`、`ghidra-indirect` 和 `--provider ghidra-direct` 已独立实现并在 XR 案例验证 | 保持直接实现，无需复制整个 REA 桥接层 |
| 函数调用关系、交叉引用、字符串引用、基本块 | `function-facts.json` v2 输出有界调用者、被调用者、签名、静态基本块和指令引用；可识别的字符串值只保留短预览。已在 XR 导出的 FixtureShare 二进制上由真实 Ghidra 运行并验证；原生汇编队列另提供有界直接调用跟随 | 针对具体 App 继续补动态分支验证；静态引用不能证明运行时命中 |
| Hopper 函数资料 | 旧入口依赖 REA/Hopper | 如需不安装 REA 仍用 Hopper，单独实现 Hopper adapter；主流程先以直接 Ghidra 覆盖 |
| 通用 MCP 会话、其他平台反编译器、跨平台进程管理 | Copy APP 没有这些通用需求 | 不整体搬入，避免把 REA 的通用产品复杂度带进 iOS 专用流程 |

移植的验收标准是：干净环境不安装 REA，也能从越狱机采集目标、生成经校验的分析报告和复刻任务、构建独立 App，并在同一设备执行对照。已有 Calculator 与 DeepSeek 的限定流程完成过该链路；这不代表任意 App 的所有页面和逻辑都已自动复刻。报告中的代码仍是反编译推断，运行时分支和 UI 结果需单独取证。

XR 上的 DeepSeek 三流程 `prepare-analysis --provider none` 案例已经生成待审任务，再由 Copy APP 把实机 UI/Frida、原生汇编和此前直接 Ghidra 证据汇成[来源绑定的报告](../cases/deepseek-no-rea-three-flow-prepared-report-v9-20261015/report.md)及[分析交付](../cases/deepseek-no-rea-three-flow-analysis-delivery-v9-20261015/report.md)。`none` 路径自身不生成新的伪代码；需要新函数伪代码时明确使用 `ghidra-direct`。代码可以按 MIT 条款选择性参考或移植，但现有正式路径没有必须从 REA 再复制的模块。Copy APP 仍依赖设备端组件及相应外部工具链，独立的含义是运行时不依赖 REA。

新函数资料的真实运行案例在 `cases/fixture-share-direct-facts-20261015/`：Ghidra 给出了 `viewDidLoad` 的签名、一个调用者，以及包括 `addSubview:`、`activateConstraints:` 在内的静态被调用函数。其[独立报告](../cases/fixture-share-direct-facts-report-20261015/report.md)已导入函数资料；两个案例均通过 `copyapp verify`。外部函数地址是 Ghidra 分析地址，不能按主程序偏移解释。

新版函数资料的[真实 Ghidra 案例](../cases/fixture-share-direct-topology-v3-20261015/function-facts.json)保存了同一 `viewDidLoad` 的 11 个基本块、73 条指令引用及静态 `viewDidLoad` 字符串线索；[报告导入案例](../cases/fixture-share-direct-topology-report-20261015/report.md)也已通过来源校验。v1 案例继续可验证。首两次尝试分别因缺 JDK 设置、受限执行环境不能写 Ghidra 用户配置而失败，保留在 `cases/fixture-share-direct-topology-20261015/` 与 `cases/fixture-share-direct-topology-v2-20261015/`。
