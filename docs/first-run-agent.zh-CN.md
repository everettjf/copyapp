# 交给 Coding Agent 的首次运行任务

[English](first-run-agent.md) · [简体中文](first-run-agent.zh-CN.md)

在 Mac 上打开能执行本地命令的 Codex 或 Claude Code，连接并解锁已越狱的 iPhone。无需先手动安装 Copy APP：把任务交给 Agent，它可以检出仓库、配置 Mac 环境并调用 CLI。已有检出时，在该目录打开 Agent 即可。仓库内的[首次使用 Skill](../skills/copyapp-start/SKILL.md)通过提示词明确读取，无需先配置扩展或斜杠命令。

## 分析并复刻

把 `<App 名称或 Bundle ID>` 换成目标后，复制到 Agent 对话中：

```text
请使用 https://github.com/everettjf/copyapp，分析并复刻 USB 连接的越狱 iPhone 上的 <App 名称或 Bundle ID>。
如未检出项目，克隆到一个新目录；已有检出就复用。先阅读 AGENTS.md 和 skills/copyapp-start/SKILL.md。
检查和配置环境，识别准确设备与 App，自主发现代表性流程，完成带来源的深度报告、明确的复刻目标、独立工程、真机安装和原版／复刻版对照。
能执行的步骤请直接完成，只在确需手机操作或目标不明确时告诉我具体需要。最终给我报告、工程、实测范围和剩余差异。
```

Agent 应继续完成当前任务中的发现、报告审阅和实现交接；CLI 显示等待 Agent 或生成 `TASK.md` 时，仍需它继续工作。它在当前会话中执行，不再启动嵌套的 Codex／Claude CLI。

## 只做分析

```text
请使用 https://github.com/everettjf/copyapp，分析 USB 连接的越狱 iPhone 上的 <App 名称或 Bundle ID>，这次先不复刻。
如未检出项目，克隆到新目录。先阅读 AGENTS.md 和 skills/copyapp-start/SKILL.md，完成环境检查、设备与 App 身份确认、证据采集及相关类／函数调查。
交付经过审阅、有来源引用的深度报告和 feature-spec.json，并校验案例。区分观测、推断与未知；不要在 survey 或 analyze/analysis.md 生成后就结束。
```

只想验证连接时，将交付要求改为“完成并校验首次 USB survey 后停止，给我报告、截图和仍缺少的配置”。这条路径需要 USB 信任和前台 App，不需要手机端 Copy APP tweak、OpenSSH 或 Frida。深度分析和复刻的额外条件见[安装指南](setup.zh-CN.md)。

## 你会得到什么

- 精确设备与 App 身份，以及通过校验的证据案例。
- 分析任务：带来源引用的深度报告和功能规格，而非只有采集索引。
- 复刻任务：独立工程、构建／安装结果、同机成对检查、逐张截图审阅与实际覆盖和差异。
- 缺少手机侧条件时：已完成的 Mac 工作，以及需要你参与的具体操作。解锁、信任、首次 SSH 指纹核对、权限或签名条件可能需要你确认。

原始 IPA、截图、沙盒数据和凭据保留在忽略的本地 `cases/`。选定流程通过不表示整 App 等价；已知能力清单与目标见[覆盖方法](coverage-targets.zh-CN.md)，实测设备边界见[当前状态](current-status.zh-CN.md)。
