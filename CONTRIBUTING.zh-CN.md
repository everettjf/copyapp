# 为 Copy APP 贡献

**语言：** [English](CONTRIBUTING.md) | 简体中文

Copy APP 将手机观测、原生代码分析、审阅报告和独立构建的 App 连接起来。贡献应改善其中一个环节，并让结论仍能追溯到证据。

## 适合开始的任务

- 修复可复现的安装、USB 转发或界面后端问题。
- 添加有界的界面脚本，或用合成夹具补充解析器测试。
- 针对实际失败改善报错与引导步骤。
- 翻译 README 概览或修正现有译文。
- 增加可选分析器，同时保持默认流程无需安装它。

## 开发流程

1. 阅读 [README](README.zh-CN.md)、[流程指南](docs/copy-workflow.zh-CN.md)及 [AGENTS.md](AGENTS.md)。若设计变动影响案例格式或设备权限，先用聚焦的 issue 讨论。
2. 用明确命令和新的输出案例复现问题，记录设备型号、iOS、越狱、Xcode 与相关工具版本。无需真机时使用合成夹具。
3. 保持改动聚焦，保留案例来源关系及已有校验门槛的语义；可选工具不应变成默认必需项。
4. 运行 `PYTHONPYCACHEPREFIX=/tmp/copyapp-pycache .venv/bin/python -m unittest discover -s tests`。生成案例后运行 `.venv/bin/copyapp verify <CASE>`。设备控制改动需写明实测手机、流程及尚未测试的版本。
5. PR 说明行为变化、证据、测试和限制。Agent 正常退出、编译成功或哈希相符，单独都不能证明功能等价。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `copyapp/` | Mac CLI、采集、分析、编排与校验。 |
| `device/ios-mcp/` | 手机端 rootless 界面服务。 |
| `vendor/ictrl/` | 保留来源和署名的可选 iCTRL 源码。 |
| `skills/` | Coding Agent 流程与交接。 |
| `examples/rebuild/` | 独立实现的示例工程和实验探针。 |
| `rebuild/` | 新复刻工程建议使用的本地输出路径；不代表已审阅示例。 |
| `tests/` 和 `fixture/` | 自动测试与源码已知夹具。 |
| `examples/report-inputs/` | 历史试点 JSON 输入，不是当前设备报告。 |
| `docs/` | 当前安装、架构、工作流、支持边界、正式发布说明与 README 翻译。 |
| `cases/` | 本地证据与凭据，Git 默认忽略。 |

不要提交原始 IPA、设备截图、沙盒导出、配对记录、密钥或账号数据。评审时使用合成夹具或去敏摘要。改造上游源码时保留许可证、NOTICE 和来源记录。

英文 `README.md` 和简体中文 `README.zh-CN.md` 概述安装并链接完整指南。其余语言 README 应准确描述 iOS 16、17、26 指定设备上的选定流程结果，保留当前安装和贡献指南链接，避免泛化到所有设备或整 App 等价。纯翻译改动无需连接手机，但要检查链接、命令及技术名词。
