# 当前支持与真机验证

[English](current-status.md) · 简体中文 · [文档目录](README.zh-CN.md)

**正式版本：**[v0.1.1](releases/v0.1.1.zh-CN.md)。本页描述截至 2026-10-18 在指定设备上已测的范围和剩余限制。[v0.1.0 说明](releases/v0.1.0.zh-CN.md)保留当时的原始发布记录。

## 指定手机的结果

| 设备 | 当前代码结果 | 边界 |
| --- | --- | --- |
| iPhone XR，iOS 16.1.1，Dopamine rootless | SSH 包／沙盒采集、Frida、iOS MCP 与 iCTRL；Notes、Calculator、Translate、Clock 的选定分析／复刻路径。最近一次 Counter 原版／复刻版在状态对齐后通过。 | 这台手机的可选开发者文件列表返回 `ConnectionTerminatedError`；SSH 采集仍可用。 |
| iPhone 14，iOS 17.3.1，Relaxin/RootHide | 当前代码的 `doctor` 和原版 Calculator 采集通过；经 iOS MCP 的四条原版／独立 App 流程通过末端断言（`15`、`0.3`、`−7`、`0.5`），五组截图审阅为轻微差异。原版 Frida 跟踪在五次点击中各记录一次选定按钮方法调用。 | 额外的 iCTRL 复刻版成对重放两次在等号步骤报 `ictrl: malformed HTTP response`。随后健康探针恢复，但多步稳定性未获证明。 |
| iPhone 11，iOS 26.0.1，Relaxin/RootHide | USB／SSH 采集、iCTRL 与 iOS MCP 界面、Frida 附加、Calculator 与 Clock 审阅报告、签名独立 App、选定运算和秒表成对检查。Clock Start → Stop → Reset 对照与逐图审阅通过。 | Instruments 新启动后 iOS MCP 可能截到黑色 App 区域；已保存拒绝的黑帧并在已观察案例中通过有界返回主屏／重启恢复。长期稳定性未知。 |

最新本地测试通过 **342 项**；提交 `1499222` 的 [GitHub macOS 全新安装、单元测试与隔离 wheel 检查](https://github.com/everettjf/copyapp/actions/runs/39151891412)也通过。成功和失败的原始案例都保存在被忽略的本地 `cases/`，不进入仓库或发布附件。`copyapp verify` 核对案例内容与来源绑定，不证明逆向解释正确或整 App 等价。

## 尚未完成

- iOS 17 复刻版的 iCTRL 多步传输故障仍需验证修复。v0.1.1 已明确记录这一限制；已测的 iOS MCP 路径可用。
- XR 可选的 DVT 开发者文件列表失败；SSH 采集路径可用。
- 重启／重新越狱后的持续可用性，以及较长时间的界面与后端稳定性，还需专门验证。
- **第二台实体 Mac** 的从零手机配置尚未实测，本轮暂缓。同一台 Mac 上的全新检出与 GitHub 托管 Mac 的无手机安装检查覆盖范围更窄。
- 已通过的选定流程不能证明任意 App 的自主发现、整 App 等价、服务端行为或像素级一致。有些独立工程改自已有源码，应与从零新写工程区分。

### 下一轮验收条件

| 尚待验证 | 完成所需证据 |
| --- | --- |
| iOS 17 iCTRL 多步重放 | 保存失败响应与 runner 状态，修复或隔离传输问题，然后对原版与复刻版重复执行流程，检查末端状态与截图。在此之前，相关选定流程可走已验证的 iOS MCP 路径。 |
| XR 的 DVT 文件列表 | 固定设备与开发者服务状态复现；若仍不可用，就把它保留为可选路径限制。SSH 包与沙盒采集已可用。 |
| 重启／重新越狱后的持续可用性 | 在每台已测手机重启并恢复越狱和服务，重新运行 `doctor`、采集小型案例并完成界面检查；同时覆盖 iOS 26 黑帧恢复和较长时间运行。 |
| 第二台实体 Mac | 从全新检出与 USB 信任开始，按公开安装指南走到 SSH 指纹固定、界面采集、包采集，以及签名或 TrollStore 安装的复刻版。 |
| 更广泛的 App 覆盖 | 对陌生 App 审阅能力清单、带来源报告和明确复刻目标，再做成对流程并列明未知项；少量流程通过不能推导整 App 等价。 |

[图文介绍](articles/copyapp-overview.zh-CN.md)和[系统架构图](assets/architecture-overview.svg)展示当前流程及经过筛选的公开证据示例。底层原始案例仍留在本地。

## 发布原则

只有打标签并公开发布的版本才编号。[当前计划](../PLAN.md)记录下一阶段的验证工作。原始 IPA、账号数据、沙盒导出与私钥不作为发布资源。
