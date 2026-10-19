# 小红书图文笔记

## 标题

越狱 iPhone × Coding Agent

## 正文

最近 REA 让“Agent 辅助逆向”受到更多关注。我一直在想：如果 Coding Agent 能直接使用一台越狱 iPhone，能不能把 App 分析、独立复刻和真机验证串起来？

这就是开源项目 Copy APP 的起点。手工逆向常要在 SSH、Frida、Hopper、截图与 Xcode 之间切换；单张截图或一次方法命中又很容易被误读。Copy APP 把每一步绑定到具体设备、Bundle ID、App 构建和本地证据 case，报告区分“观察到”“推断”和“未知”。

架构上，Mac 运行 Codex / Claude Code 与 Copy APP CLI；越狱 iPhone 经 USB/SSH 提供包和沙盒，iOS MCP / iCTRL 采集界面，Frida 观察选定运行路径；Ghidra / Hopper 可选做原生分析。Agent 据此写报告和功能规格，再构建独立 iOS App，回到同一台手机重放选定流程、逐张对照。

第一阶段是深度分析；第二阶段按 App 复杂度定复刻目标。简单 App 可以覆盖更广，复杂 App 先选有用的功能切片，差异和未验证项都要写清楚。iOS 16、17、26 的三台手机已跑过选定流程，这不等于任意 App 都能“一键完整复制”。

想试试：GitHub 搜索 everettjf/copyapp。欢迎 Star，先按 README 跑 onboard / survey；也欢迎分享可复现的真机问题和改进建议。

#iOS开发 #逆向工程 #开源项目 #CodingAgent

## 配图顺序

1. `publish/01-cover.png`
2. `publish/02-architecture.png`
3. `publish/03-evidence.png`
4. `publish/04-workflow.png`
5. `publish/05-comparison.png`
6. `publish/06-github.png`
