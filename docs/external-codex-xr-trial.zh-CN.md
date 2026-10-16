# iPhone XR 上的独立 Codex CLI 实测

**语言：** [English](external-codex-xr-trial.md) | 简体中文

2026-10-16，独立运行的 `codex exec` 在已越狱 iPhone XR（iOS 16.1.1）上完成了 Copy APP 的分析与复刻两段任务。本地案例位于 `cases/calculator-external-codex-20261016/`；`cases/` 不提交到 Git，新克隆不会包含这些真机证据。

分析阶段生成有来源引用的报告并通过 `analysis-delivery`。复刻阶段生成 `rebuild/CalculatorExternalAgent`，构建 IPA，在 XR 上安装并启动。原版与复刻版的小数加法、负数加法、百分比三条成对流程的脚本断言全部通过；三对截图均审阅为轻微差异，没有重大差异。绑定 CLI 运行记录的交付包及顶层 `copyapp copy --resume` 案例均通过校验。

本次只验证选定流程。CLI 使用此前已验证的发现脚本，复刻实现改自既有独立 Calculator 工程；报告引用了同一二进制此前采集的 Ghidra 证据，并注明采集时间。因此它证明独立 CLI 编排和真机交付，不证明自主发现、对陌生 App 从零实现或完整 Calculator 等价。iOS 17、26 不在本次范围。

实测发现一个交付衔接问题：CLI 先创建了未绑定运行记录的 `agent-delivery` 草稿，而 Copy APP 应在 CLI 退出后创建正式交付包。草稿已保留在 `rebuild-agent/agent-delivery-agent-draft`，随后生成并校验正式交付包。提示词和收尾代码现已处理这种情况。
