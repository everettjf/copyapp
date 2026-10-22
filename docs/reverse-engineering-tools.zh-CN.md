# 反编译与逆向工具支持

[English](reverse-engineering-tools.md) · [项目首页](../README.zh-CN.md) · [文档目录](README.zh-CN.md)

Copy APP 当前直接接入 **Ghidra 与 Hopper 两种反编译器**，并组合 Frida 动态跟踪、LLVM 反汇编、内置 Mach-O／Objective-C 索引和选定设备上的安装包恢复。工具在 Mac 上运行，生成带二进制哈希、地址与原始日志的证据；当前 Agent 负责解释。

## 工具支持表

| 工具 | 用途 | Copy APP 入口 | 需要准备 |
| --- | --- | --- | --- |
| **Ghidra** | 指定原生函数伪代码；有界调用者／被调用者、基本块和指令引用 | `ghidra-function`、`ghidra-queue`、`ghidra-indirect`；`--provider ghidra-direct` | 单独安装的 Ghidra、与所选版本匹配的 JDK；提供 Ghidra 与 JDK 路径 |
| **Hopper Disassembler** | 指定函数伪代码与有界候选队列 | `hopper-function`、`hopper-queue`；`--provider hopper-direct` | 本机 Hopper、可用许可、正常登录的 macOS 图形会话 |
| **LLVM / Xcode llvm-objdump** | 有界 ARM64 汇编、唯一局部直接调用／分支跟随 | `native-disasm`、`native-queue` | `xcrun --find llvm-objdump` 能定位的工具链；输出是汇编，不是伪代码 |
| **Frida** | 指定 Objective-C 方法命中、选定原始入口及间接调用寄存器等运行观察 | `trace`、`experiment`、`flow-capture --method`；调查流程按需组合 | 宿主 Frida 与兼容的越狱手机服务、明确设备身份；需要时用 bootstrap 的 `--trace` |
| **内置 Mach-O／Objective-C 解析** | 安装包、加载命令、加密标记、类／selector／方法地址索引 | `ipa`、`objc`；Mac 包另用 `mac inspect`／`mac acquire` | 采集到的对应文件；不依赖 Ghidra 或 Hopper，也不恢复 Swift 原始源码 |
| **ipadecrypt helper 与 Copy APP 恢复流程** | 在已验证设备路径上恢复加密 Mach-O 分析副本 | `decrypt-package`、`analyze --decrypt`；主程序另有 `decrypt-main` | 明确手机／App／包快照，准备并校验 helper；SSH／Frida 路线按设备选择 |

前两项是反编译器；其余分别提供汇编、动态观察、静态索引与包恢复。ChatComputer、iOS MCP 和 iCTRL 提供界面观察／控制，不是反编译器。

## iOS 和 macOS 的范围分别是什么？

**iOS：**现有原生分析流程把 UI 重放、Frida 命中、Objective-C 地址候选、有界汇编与可选伪代码绑定到同一采集二进制。Agent 审阅证据后，才能写入正式报告。设备、版本及加密包恢复范围见[当前状态](current-status.zh-CN.md)与[包恢复指南](full-package-decryption.zh-CN.md)。

**macOS：**当前独立工作流主要是 App 包、AX 辅助功能树、截图和行为对照。它没有接成与 iOS 等价的原生函数调查／报告链。底层函数命令可处理满足其约束的本地 Mach-O，但这不构成 Mac 深层函数分析或任意 Mac App 的验收结论。见 [Mac 支持](macos-support.zh-CN.md)。

## 默认不启动反编译器

`investigate-flow`、`investigate-app`、`prepare-analysis` 与 `prepare-app` 的默认参数是 `--provider none`。这条路径仍可采集 UI、静态索引、运行观察和可用的有界汇编，但不会生成新的反编译伪代码。

需要伪代码时显式选 `--provider ghidra-direct` 或 `--provider hopper-direct`。父工作流 `copy` 对应的选项名是 `--analysis-provider`。不要把这些 iOS 调查参数直接加到 `copyapp mac` 命令上。

Copy APP 的 bootstrap 不会同时安装 Ghidra、JDK 或 Hopper。Ghidra 按[官方安装说明](https://github.com/NationalSecurityAgency/ghidra#install)准备匹配的 JDK；Hopper 从[官网](https://www.hopperapp.com/)安装并准备许可。所选工具无法启动、超时或输入仍加密时，保留失败证据，不把部分伪代码写成完成结果。

## 交给 Agent 怎么说

在已有的 **iOS 分析任务**后补充：

```text
本次需要函数级伪代码。请检查可用的 Ghidra/JDK 或 Hopper，使用 ghidra-direct 或 hopper-direct，并在报告中记录实际选择。
先核对采集二进制、SHA-256、ARM64 切片与候选函数地址，再对与选定流程相关的有限函数运行反编译。
把 Frida 实际命中、静态引用、反编译结果和你的语义推断分别写清楚，引用校验过的证据；不要把伪代码称为原始源码。
在当前 Agent 会话里完成审阅，不启动嵌套 Agent。若当前目标是 Mac，只按已实现的 Mac 范围处理，明确原生函数链尚未接入。
```

已指定工具时，直接指定所需 provider，并提供安装路径。Agent 可以检查已有环境；Hopper 许可与正常图形会话不能由 Python 包安装替代。

## 手动调用一个已选定函数

以下 SHA-256 与地址必须来自同一份已验证的分析二进制。加密输入先按设备验证过的恢复流程处理。每次用新的案例目录。

Ghidra：

```sh
.venv/bin/copyapp ghidra-function --file <MACHO> \
  --sha256 <SHA256> --address <0xFUNCTION_ENTRY> \
  --ghidra-dir <GHIDRA_DIR> --java-home <JDK_HOME> --out <NEW_CASE>
.venv/bin/copyapp verify <NEW_CASE>
```

Hopper：

```sh
.venv/bin/copyapp hopper-function --file <MACHO> \
  --sha256 <SHA256> --address <0xFUNCTION_ENTRY> \
  --hopper-app '/Applications/Hopper Disassembler.app' --out <NEW_CASE>
.venv/bin/copyapp verify <NEW_CASE>
```

已有候选队列用 `ghidra-queue`／`hopper-queue`。Ghidra 还支持在已验证的原生队列上进行有界直接跟随，以及配合 Frida 的选定间接调用调查；具体要求见仓库 `AGENTS.md` 和对应命令的 `--help`。[Hopper 直连说明](rea-hopper-integration.zh-CN.md)记录图形会话、超时与失败诊断。

## 尚未接入的工具与解释边界

当前没有 IDA Pro、Binary Ninja、radare2 的直接 provider 或对应的自动证据接入链。工具自身支持某个平台，不代表 Copy APP 已自动集成该能力。

**REA 不是运行依赖。** 旧 `rea-function`、`rea-queue`、`rea-bridge` 命令已经移除；保留的 REA 许可证属于历史参考／改造代码的署名。[不依赖 REA 的路径](rea-independence.zh-CN.md)说明当前替代方式。Hopper 本身提供的其他接口，也不等于这里已接入；本项目当前直连使用其 Python 脚本接口。

伪代码是工具生成的解释，不是原作者源码。Frida 在某个操作窗口内命中一个函数，不足以单独证明该函数导致了可见 UI 变化。`copyapp verify` 校验文件、来源与绑定关系，函数语义仍需要 Agent 或人工审阅。

## 实现依据

- CLI 选项与命令：[`copyapp/cli.py`](../copyapp/cli.py)
- 反编译适配：[`ghidra_direct.py`](../copyapp/ghidra_direct.py)、[`ghidra_queue.py`](../copyapp/ghidra_queue.py)、[`hopper_direct.py`](../copyapp/hopper_direct.py)、[`hopper_queue.py`](../copyapp/hopper_queue.py)
- 有界反汇编与静态索引：[`native_disasm.py`](../copyapp/native_disasm.py)、[`objc.py`](../copyapp/objc.py)
- 上游信息核对：2026-10-22；支持范围以本仓库实际适配和案例为准。
