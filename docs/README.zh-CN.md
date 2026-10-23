# Copy APP 文档

[English](README.md) · 简体中文 · [项目首页](../README.zh-CN.md)

Copy APP 的 **v0.2.0** 正式版支持越狱 iOS 与macOS；**v0.1.2** 为上一版仅支持 iOS 的版本。新用户从 README 的[双平台 AI 任务](../README.zh-CN.md#从这里开始)或[手动 iOS 安装指南](setup.zh-CN.md)开始，再按任务查阅下表。历史检查点保留在 Git 历史，原始设备证据仅留本地忽略目录。

| 主题 | 文档 |
| --- | --- |
| 新 Mac 与手机 | [安装及首次概览](setup.zh-CN.md) |
| macOS App 预览支持 | [ChatComputer 集成](macos-support.zh-CN.md) · [实施与验收清单](macos-implementation-plan.md) |
| 系统怎样协作 | [架构与证据模型](architecture.zh-CN.md) |
| 带图的项目介绍 | [Copy APP：分析与复刻实验室](articles/copyapp-overview.zh-CN.md) |
| 已测手机与限制 | [当前状态](current-status.zh-CN.md) |
| 普通手机基础路径与越狱增强 | [开发版用法与边界](ios-standard-mode.zh-CN.md) · [验收账本](ios-device-support-acceptance.md) · [实施与验收方案](ios-device-support-plan.zh-CN.md) |
| 分析到复刻 | [工作流](copy-workflow.zh-CN.md) |
| 确定可实现的目标 | [覆盖目标](coverage-targets.zh-CN.md) |
| 给 Coding Agent 的首次任务 | [首次运行任务](first-run-agent.zh-CN.md) |
| 界面脚本 | [手势](ui-gesture-playbooks.zh-CN.md) · [文字输入](ui-text-playbooks.zh-CN.md) |
| 反编译与逆向工具支持 | [工具矩阵、安装条件与 Agent 任务](reverse-engineering-tools.zh-CN.md) |
| 原生代码与安装包 | [加密包恢复](full-package-decryption.md) · [Hopper 直连](rea-hopper-integration.zh-CN.md) · [不依赖 REA](rea-independence.zh-CN.md) |
| 已发布版本 | [v0.2.0 发布说明](releases/v0.2.0.zh-CN.md) · [v0.1.2 归档](releases/v0.1.2.zh-CN.md) · [v0.1.1 归档](releases/v0.1.1.zh-CN.md) |
| 源码示例 | [iOS／macOS 独立 App](../examples/README.md) · [报告输入格式](../examples/report-inputs/README.md) |

[`examples/report-inputs/`](../examples/report-inputs/README.md) 中的六份 JSON 是试点合成脚本及分析 Skill 使用的**历史目标专属示例**，不是当前设备报告。分析新目标 App 时，必须重新审阅每条结论。
