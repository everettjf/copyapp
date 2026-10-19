---
title: "Copy APP：让越狱 iPhone 成为可验证的 App 分析与复刻实验室"
date: 2026-10-18
tags: [iOS, 越狱, 逆向工程, Coding Agent, 开源]
description: "从真机采集、Mach-O 与运行时分析，到独立 iOS App 的构建、安装和逐项对照。"
---

![Copy APP：观察、理解、重新构建](../assets/article-cover.svg)

在越狱 iPhone 上观察一个 App，远比“拿到 IPA”复杂。包里能看到二进制、资源和依赖；屏幕上能看到界面；运行时能看到某些调用；沙盒里能看到状态。它们各自只回答一部分问题。Copy APP 把这些证据组织成可复查的流程，再让 Coding Agent 据此构建一个**独立的、可运行的 iOS App**。

项目分成两部分：**深度分析**和**按目标复刻**。前者回答“这个 App 在已观察范围内做了什么、证据在哪里”；后者回答“我们实现了哪些能力，以及真机对照结果如何”。“复刻”始终要有明确范围：小 App 可以追求覆盖全部已知功能，复杂 App 则先选一个有价值的阶段目标。

> 项目地址：[github.com/everettjf/copyapp](https://github.com/everettjf/copyapp)。文中的真机结果是针对具体设备和选定流程的证据，不代表任意 App 的完整等价。

## 为什么要把越狱手机接给 Agent

最近 REA 等项目让“用 Agent 辅助逆向”受到更多关注。我也在想：如果 Agent 不只读取一份离线反编译结果，而能直接观察一台真实的越狱 iPhone，它能否自主完成从分析到新 App 真机验收的闭环？Copy APP 就从这个问题开始。它参考了相关工具的交互思路，但默认流程不依赖 REA。

过去，这件事常被拆成许多手工步骤：从手机导出文件，在 Mac 上看 Mach-O，用 Hopper 或 Ghidra 找函数，用 Frida 观察一次操作，再靠截图回忆哪个按钮引起了什么变化。工具各自有用，证据却很容易失去设备、App 版本和操作顺序。Copy APP 的目标是让 Coding Agent 能调用这些能力，同时把**证据与结论之间的关系**留给后来的人复查。

## 一张图看懂系统

![Copy APP 架构：Mac 端 Agent、CLI、证据与构建，经 USB 连接越狱 iPhone，最终进行同机对照](../assets/architecture-overview.svg)

Coding Agent（Codex、Claude Code 或其他 Agent）负责规划、解释证据和编写新实现。Mac 上的 Copy APP CLI 选择**精确的 USB 设备和 Bundle ID**，协调采集、静态分析、构建与验证。越狱手机提供几个相互独立的通道：

| 通道 | 用途 | 它不能单独证明什么 |
| --- | --- | --- |
| OpenSSH | 获取安装包及限定范围的沙盒文件 | 文件快照不等于实时业务语义 |
| iOS MCP / iCTRL | 前台识别、界面树、截图、触控与文本输入 | 一个按键成功不等于整个页面可用 |
| Frida | 观察选定方法调用、参数或运行时路径 | 一次命中不自动证明该方法导致了可见结果 |
| Mach-O / Ghidra / Hopper | 分析类、依赖、汇编与选定函数伪代码 | 反编译结果不是原作者源码 |

## 原理：一条可追溯的证据链

每一步都会留下本地 case：设备身份、输入、时间、哈希、截图、跟踪与校验结果。原始 IPA、完整截图、沙盒数据和凭据留在 Git 忽略的 `cases/`。本文仅选用了已检查的 Calculator 画面和不含原始文件内容的证据图示。

![二进制、沙盒、界面与运行时观察汇入带来源的分析报告](../assets/social/02-evidence.png)

工作流先固定**哪台手机、哪个 App 构建**，再把界面动作与文件、运行时、原生代码证据对齐。Agent 可以提出“这个类可能实现了计算按钮”的假设，但报告必须说明哪些是实际观察、哪些是推断、哪些仍未知。分析结果写成带来源的报告和 `feature-spec.json`；复刻时又把同一组可重放的用户流程变成验收条件。这样，截图、伪代码或一次 Frida 命中都不会被单独当作“完整实现”。

## 第一部分：深度分析

分析从确认设备和 App 开始，再逐步增加证据：

1. **确定目标。** 固定 USB UDID、Bundle ID、版本与构建号，记录当前前台 App。
2. **观察界面。** 找出代表性用户流程，保存每一步的动作、界面结构和截图。
3. **采集包与状态。** 索引 App 包、动态库、扩展、资源和限定范围的沙盒数据；需要时恢复加密 Mach-O 供分析。
4. **验证实现线索。** 结合 Objective-C 元数据、ARM64 指令、可选的 Ghidra/Hopper 伪代码与 Frida 的有界跟踪，定位选定功能的关键路径。
5. **写可追溯报告。** 把观测、推断和未知分开，输出来源链接与 `feature-spec.json`，作为后续实现依据。

拿到包不等于“拿到源码”。例如 `cryptid=0` 只表示对应 Mach-O 载荷未处于 App Store 加密状态；它并不意味着类名完整、算法逻辑明白，也不保证打包结果能重新签名安装。Copy APP 把这些边界明确写进报告。

### 两类容易误读的证据

下面的 Hopper 图示基于已保存的 iOS 17 Calculator 反编译结果：`CalculatorModel.buttonPressed:` 是一个按钮入口，伪代码显示它调用另一段原生函数。**这只能支持一个局部实现线索**；要理解运算规则，还需沿调用路径进一步分析，并用运行时跟踪和实际界面结果交叉检查。Ghidra 可作为同类的可选反编译后端。图是对真实输出的排版摘录，并非 Hopper 应用窗口截图。

![Hopper 证据图示：Calculator 按钮入口、伪代码摘录与解释边界](../assets/hopper-evidence.svg)

沙盒图示取自一次经 USB 转发的只读 SSH 元数据索引。它能说明当时存在 `Documents`、`Library/Preferences`、Saved Application State 等路径，但这次采集**没有复制文件内容**，也不能凭目录名推断业务数据模型。完整索引、设备绑定和时间戳保存在本地 case。

![Calculator 沙盒元数据图示：相对路径、采集范围与解释边界](../assets/sandbox-evidence.svg)

## 第二部分：按目标复刻

分析报告完成后，先列出目前**已知的用户可见能力**，再选择目标：一个简单工具也许能一次覆盖已知功能；大型 App 可能先做 50–60% 的有价值切片，但百分比必须有明确的已知能力分母。未发现的功能仍是未知，不能算进“已完成”。

复刻由浅入深：先搭出独立 Xcode 工程与主要页面，再实现选定状态和交互，接着在真机上安装签名 IPA。原版与复刻版分别重放同一套脚本，检查最终界面文字、状态变化和截图，逐张记录视觉差异。最终交付列出通过、未通过、暂缓与未知项。

![两项交付：有来源的分析报告和标明覆盖范围的独立可运行 App](../assets/social/04-deliverables.png)

下面是 iPhone 14 / iOS 17.3.1 上 Calculator 的一组**有界**结果：原版和独立实现都完成 `7 + 8 = 15` 流程，但截图仍能看到系统状态栏与布局细节差异。它证明这条选定流程通过，并不代表 Calculator 全功能等价。

| 原版 Calculator | 独立复刻版 |
| :---: | :---: |
| ![原版 Calculator 显示 15](../assets/calculator-original.jpg) | ![独立复刻版显示 15](../assets/calculator-rebuilt.jpg) |

## 三台真机，三种验证状态

| 设备 | 系统与越狱 | 当前证据范围 |
| --- | --- | --- |
| iPhone XR | iOS 16.1.1，Dopamine rootless | 已完成 Notes 等选定流程的分析、独立安装与同机对照；部分可选开发者文件服务仍有连接问题，SSH 采集路径可用。 |
| iPhone 14 | iOS 17.3.1，Relaxin / RootHide | 已验证 SSH、iOS MCP、iCTRL、Frida 17 sidecar、加密包恢复及签名独立 App 的选定流程。 |
| iPhone 11 | iOS 26.0.1，Relaxin / RootHide | USB／SSH 采集、iCTRL 与 iOS MCP 界面、Frida 附加、Calculator 与 Clock 审阅报告、签名独立 App，以及选定运算和秒表的同机对照均已完成。iOS MCP 新启动后偶发黑帧；已观察的故障经有界恢复通过，长期稳定性仍未知。 |

以上状态会随新的真机 case 更新。iOS 26 的结论来自 iPhone 11 上独立采集、构建和对照的案例，而不是沿用 iOS 17 的 RootHide 结果。

下面这张 iOS 26 **原版** Calculator 截图来自已校验的 iCTRL 脚本。它证明选定的 `7 + 8 = 15` 流程在这台 iPhone 11 上运行成功；复刻版的同机对照另有独立案例，不能仅凭这张图证明。

![iPhone 11 / iOS 26 原版 Calculator 的 7+8=15 真机结果](../assets/ios26-calculator-15.jpg)

## 从一条命令开始

第一次运行只需要 Mac、USB 线、已解锁且信任电脑的 iPhone。USB 初检不要求手机先安装 Copy APP tweak、OpenSSH 或 Frida：

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

`onboard` 会列出设备和可用通道。随后用精确 UDID 查询 App 的 Bundle ID，再做第一份 USB survey；深度分析与复刻所需的越狱服务按照 [README 安装指南](https://github.com/everettjf/copyapp#start-here)逐步加入。Coding Agent 可以直接阅读仓库的 `AGENTS.md` 和 `skills/`，驱动相同的命令与验收门槛。

## 为什么坚持“有证据的范围”

逆向分析很容易把一张截图、一次方法命中或一段伪代码讲成完整实现。复刻也很容易把“页面看起来像”讲成“App 已复制”。Copy APP 的工作方式是把结论缩回证据能支持的范围：每个已验证行为都对应明确设备、明确 App 构建、明确操作和明确结果；余下的差异同样写出来。

## 下一步：把可用路径变成可靠路径

当前三台手机上的**选定流程**已经覆盖分析到可运行复刻，剩下的工作主要是可靠性和范围，而不是再堆一个版本号：

1. 定位 iOS 17 上 iCTRL 对复刻版进行多步重放时偶发的 `malformed HTTP response`，并重新做同机验收。
2. 调查 XR 的可选开发者文件列表 `ConnectionTerminatedError`；现有 SSH 包与沙盒采集路径可继续使用。
3. 验证重启、重新越狱后的持续可用性和较长时间的后端稳定性。
4. 在第二台实体 Mac 上走一次从 USB 信任到签名安装的全新配置流程。
5. 扩大陌生 App 的自主探索，并把更深的状态、数据持久化和视觉差异纳入明确的覆盖目标。

## 欢迎试用，也欢迎给项目一个 Star

如果你有一台越狱 iPhone，可以从上面的 `onboard` 开始，先做一次 USB 概览，再按 [README](https://github.com/everettjf/copyapp#start-here) 选择一个熟悉的小 App 跑通分析。想尝试复刻时，先给自己定一条可重放的功能流程；把结果和差异都记下来。没有越狱机也欢迎阅读架构、改进文档或提交可复现的问题。

项目仍在持续打磨，当前正式发布版是 **v0.1.1**。如果这条“真机证据 → 可追溯报告 → 独立实现 → 同机对照”的路线对你有帮助，欢迎到 [GitHub 仓库](https://github.com/everettjf/copyapp) **Star**，动手试用，并分享你遇到的设备问题或工作流改进。也可以加入与 [xnu.app 相同的 Discord 社区](https://discord.gg/eGzEaP6TzR)交流。
