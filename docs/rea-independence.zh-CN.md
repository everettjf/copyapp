# 不依赖 REA 的运行路径

[English](rea-independence.md) · 简体中文 · [架构](architecture.zh-CN.md)

Copy APP 的正式分析到复刻流程不需要 REA 进程、软件包或 MCP 服务。默认原生分析会索引 Mach-O 元数据及有界汇编；可选的直连 Ghidra 与[直连 Hopper](rea-hopper-integration.zh-CN.md)提供与二进制哈希绑定的伪代码。Frida 负责运行时跟踪。旧 REA 桥接命令已不再属于 CLI。

`--provider none` 可以采集 UI、静态索引和运行观察，但不会生成新的伪代码。需要函数级伪代码时选择 `ghidra-direct` 或 `hopper-direct`，再把校验过的结果导入 `copyapp report`。反编译结果仍需由人或 Coding Agent 解释，并关联已观察的流程及未知项。

Hopper 直连设计参考了 MIT 许可的 REA 代码并保留[许可证](third-party/REA-LICENSE.txt)，这不使 REA 成为运行依赖。其他外部前提取决于任务所选手机服务和 Mac 工具链。见[安装指南](setup.zh-CN.md)及[当前状态](current-status.zh-CN.md)。
