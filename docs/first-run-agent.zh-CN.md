# 交给 Coding Agent 的首次运行任务

[English](first-run-agent.md) · [简体中文](first-run-agent.zh-CN.md)

在 **Copy APP 仓库目录**打开 Codex 或 Claude Code，把越狱 iPhone 用 USB 连接到 Mac。将下文的 `<App 名称或 Bundle ID>` 换成目标后直接发送给 Agent；不知道 Bundle ID 时填 App 名称即可。

> 用 Copy APP 分析已连接越狱 iPhone 上的 `<App 名称或 Bundle ID>`。在本仓库工作，遵循 `AGENTS.md` 和 `skills/copyapp-analyze/SKILL.md`。如未安装 Mac 命令行，先运行 `sh scripts/bootstrap-macos.sh`，之后用 `.venv/bin/copyapp` 调用。确认准确 USB UDID 和 Bundle ID；若有多台手机或多个同名 App，列出选项让我选择。先运行 `.venv/bin/copyapp onboard --stage survey`，请我在手机上打开目标 App，再执行不加 `--launch` 的纯 USB `survey`、案例校验，并给我报告和截图。然后运行 `onboard --stage analyze`，按它列出的顺序配置深度分析通道。Mac 端能自主完成的配置请直接完成；只把确需我在手机上操作的信任、安装或授权步骤明确告诉我。通道就绪后，采集 App 包、沙盒、界面和运行时证据，调查代表性流程及相关类/函数，产出有证据引用且经过审阅的深度报告和 `feature-spec.json`，最后校验报告案例。区分观测事实、代码解释与未知行为；不要把 `survey` 或 `analyze/analysis.md` 当成最终深度报告。IPA、截图、沙盒数据和凭据保存在被 Git 忽略的本地 `cases/`。这次先不复刻 App。

如果只想验证 USB 首次采集，把末尾要求改为：“完成并校验 `survey` 后停止，说明采集到了什么。”采集前请用户在手机上打开目标 App；可选的 USB `--launch` 会依赖可能不可用的开发者服务。这一条路径不需要手机端 Copy APP tweak、OpenSSH 或 Frida。

## 预期交付

- 精确的设备与 App 身份、可校验的首次采集案例和截图。
- 深度分析时，得到有来源引用的报告：已观察的界面、包与动态库、选定功能实现路径、数据与存储、运行时证据、尚未确认之处，以及功能规格。具体证据门槛见[分析 Skill](../skills/copyapp-analyze/SKILL.md)。
- 如果手机端条件暂时不齐，明确列出缺少什么以及已完成哪些 Mac 端工作。

之后要生成可运行的独立 App，再使用[分析到复刻工作流](copy-workflow.zh-CN.md)和[动态覆盖方法](coverage-targets.zh-CN.md)。那是更大的任务，需要 Xcode 签名和同机对照。
