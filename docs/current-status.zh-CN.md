# 当前支持与真机验证

[English](current-status.md) · 简体中文 · [文档目录](README.zh-CN.md)

**当前正式版：**[v0.2.0](releases/v0.2.0.zh-CN.md) 支持越狱 iOS 和通过 ChatComputer 的实验性 macOS。**上一版仅支持 iOS 的版本：**[v0.1.2](releases/v0.1.2.zh-CN.md)。下方手机记录保留原设备与时间范围，本版不增加新的 iPhone 真机执行声明。

## macOS 预览

指定 ChatComputer 0.9.11／macOS 27.0.1 客体已完成两个样例各三条流程、各三轮（每个 9/9）、完整截图审阅、真人接管／输入拒绝、受控回复丢失和一次暂停轮询后的运行中编辑器快照取回／恢复。自有编辑器完成 7/9 已知能力严格交付，并在指定实体 Mac 以相同二进制手动复验选定行为。Stocks 达到后来要求的 81/100 离线原型目标，207 项明显差异保留，尚无严格交付或已验证能力覆盖。详见 [Mac 支持](macos-support.zh-CN.md)、[实施账本](macos-implementation-plan.md)及 [Stocks 源码](../examples/macos/Stocks/README.md)。

macOS 为实验性支持，不声称任意 Mac 兼容、整 App 等价、深层函数分析、完整数据或实时行情。本版通过 410 项本地测试和隔离 wheel 检查；指定真实记录早于最终版本元数据更新。

## 指定手机的结果

| 设备 | 当前代码结果 | 边界 |
| --- | --- | --- |
| iPhone XR，iOS 16.1.1，Dopamine rootless | SSH 包／沙盒采集、Frida、iOS MCP 与 iCTRL；Notes、Calculator、Translate、Clock 的选定分析／复刻路径。最近一次 Counter 原版／复刻版在状态对齐后通过。 | 这台手机的可选开发者文件列表返回 `ConnectionTerminatedError`；SSH 采集仍可用。 |
| iPhone 14，iOS 17.3.1，Relaxin/RootHide | 当前代码的 `doctor` 和原版 Calculator 采集通过；经 iOS MCP 的四条原版／独立 App 流程通过末端断言（`15`、`0.3`、`−7`、`0.5`），五组截图审阅为轻微差异。原版 Frida 跟踪在五次点击中各记录一次选定按钮方法调用。 | v0.1.1 的 iCTRL 成对重放会因 XCTest 会话过早断开而失败；v0.1.2 修复后四条原版／复刻版 iCTRL 流程通过，退出后 runner PID 为 0。重启／重新越狱及其他设备上的本次改动仍待验证。 |
| iPhone 11，iOS 26.0.1，Relaxin/RootHide | USB／SSH 采集、iCTRL 与 iOS MCP 界面、Frida 附加、Calculator 与 Clock 审阅报告、签名独立 App、选定运算和秒表成对检查。Clock Start → Stop → Reset 对照与逐图审阅通过。 | Instruments 新启动后 iOS MCP 可能截到黑色 App 区域；已保存拒绝的黑帧并在已观察案例中通过有界返回主屏／重启恢复。长期稳定性未知。 |

v0.1.2 本地测试通过 **346 项**，本轮隔离 wheel 安装检查也通过。先前提交 `1499222` 的 [GitHub macOS 全新安装、单元测试与隔离 wheel 检查](https://github.com/everettjf/copyapp/actions/runs/39151891412)也通过。成功和失败的原始案例都保存在被忽略的本地 `cases/`，不进入仓库或发布附件。`copyapp verify` 核对案例内容与来源绑定，不证明逆向解释正确或整 App 等价。

## iOS 17 iCTRL 会话修复（v0.1.2）

旧逻辑会在原版采集结束时断开自建 XCTest 宿主，后续流程又复用仍能短暂响应日志的 runner。本轮重现中，复刻版等号请求收到 0 字节，独立截图却显示 15：点击已执行，不能因响应丢失直接重发。保持同一宿主的受控实验完成两轮四流程检查，支持会话生命周期这一原因判断。

当前 `rebuild-check` 将会话保持到全部成对流程和即时 view-tree 采集完成；自建会话退出前停止 runner，HTTP 断开时明确提示执行结果未知。两轮独立正式命令（本地案例 `cases/ios17-ictrl-session-fixed-four-flow-run1-20261018`、`cases/ios17-ictrl-session-fixed-four-flow-run2-20261018`）每轮四条末端断言均通过，退出后 runner PID 均为 0；十对截图逐张审阅为轻微差异。原始失败、请求时间线、源码快照和实验记录留在本地 `cases/ios17-ictrl-transport-diagnosis-20261018/`。这是指定设备与选定流程的回归修复，不能替代重启和长期验收；v0.1.1 的发布记录保持原样。

## 尚未完成

- **低优先级：**XR 可选的 DVT 开发者文件列表在 10 月 17 日和 18 日多次返回 `ConnectionTerminatedError`。SSH 包和沙盒采集仍可用，不阻塞主流程。
- **保留恢复机制并观察：**iOS 26 的 iOS MCP 在 10 月 18 日多次独立的 Calculator、Clock 新启动流程中得到黑帧。相关流程均拒绝黑帧，并在有界重新激活后完成。只有恢复失败、黑帧被当作有效证据，或新设备／构建缺少可用替代路径时，再深入排查截图通道。
- 重启／重新越狱后的持续可用性，以及较长时间的界面与后端稳定性，还需专门验证。
- **第二台实体 Mac** 的从零手机配置尚未实测，本轮暂缓。同一台 Mac 上的全新检出与 GitHub 托管 Mac 的无手机安装检查覆盖范围更窄。
- 已通过的选定流程不能证明任意 App 的自主发现、整 App 等价、服务端行为或像素级一致。有些独立工程改自已有源码，应与从零新写工程区分。

### 下一轮验收条件

| 尚待验证 | 完成所需证据 |
| --- | --- |
| iCTRL 会话改动的设备边界 | 指定 iPhone 14 上的多步回归已通过；继续做重启／重新越狱检查，并在其他指定设备上复验本次会话清理改动。 |
| XR 的 DVT 文件列表 | 保留可选路径限制。只有开发者服务变化或新设备确实需要此路径时再调查；SSH 采集已获验证。 |
| 重启／重新越狱后的持续可用性 | 在每台已测手机重启并恢复越狱和服务，重新运行 `doctor`、采集小型案例并完成界面检查；若遇到 iOS 26 黑帧，先确认仍能拒绝并恢复，只有恢复失效时才深入排查截图通道。 |
| 第二台实体 Mac | 从全新检出与 USB 信任开始，按公开安装指南走到 SSH 指纹固定、界面采集、包采集，以及签名或 TrollStore 安装的复刻版。 |
| 更广泛的 App 覆盖 | 对陌生 App 审阅能力清单、带来源报告和明确复刻目标，再做成对流程并列明未知项；少量流程通过不能推导整 App 等价。 |

[图文介绍](articles/copyapp-overview.zh-CN.md)和[系统架构图](assets/architecture-overview.svg)展示当前流程及经过筛选的公开证据示例。底层原始案例仍留在本地。

对可比重试后未再出现的单次故障，只保留原始案例，不长期列为待修问题。上述 iCTRL、DVT 和黑帧现象均曾重复出现；iCTRL 的指定设备回归修复已记录，其余问题按是否阻塞主流程和是否已有可用替代路径排序。

## 发布原则

只有打标签并公开发布的版本才编号。[当前计划](../PLAN.md)记录下一阶段的验证工作。原始 IPA、账号数据、沙盒导出与私钥不作为发布资源。
