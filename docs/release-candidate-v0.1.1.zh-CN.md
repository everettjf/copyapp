# Copy APP 下一补丁版 · 发布说明草稿

[English](release-candidate-v0.1.1.md) · [简体中文](release-candidate-v0.1.1.zh-CN.md)

**仅为草稿。**目前正式发布版本仍是 `v0.1.0`；使用本说明发布前请先核对[验收记录](release-readiness-v0.1.1.zh-CN.md)。

## 相对 v0.1.0 的变化

- iOS MCP 脚本会识别 App 区域近乎全黑的截图，保留被拒绝图片的来源和哈希信息，并在 Instruments 启动后进行有界的返回主屏／重启 App 恢复。最终截图为黑图时脚本不能通过。iOS 26 Calculator 和 Clock 已在真机上触发并验证恢复。
- 精确设备 SSH 配置只在身份验证成功后写入本地。后续 `doctor`、`onboard` 和分析命令可分别复用每台手机的端口、密钥及固定的主机密钥文件；显式参数仍可覆盖。
- 复刻计划现在能识别缺少稳定截图和就绪文本的原版流程，在成对对照前明确要求重新采集。
- 第二款 iOS 26 App——Clock——完成选定流程审阅报告及独立开发签名的秒表复刻版。Start → Stop → Reset 的成对行为检查通过；四组截图均有轻微差异。工程改造自较早的独立 Clock 源码。
- 新增全新托管 macOS 安装测试：安装 CLI 与可选跟踪工具、运行单元测试、构建 wheel 并隔离安装检查。中英安装说明区分主机端安装与手机端配置。
- 同一台实体 Mac 的新检出在两台已测手机上完成新 SSH 身份信任，并在 iOS 26 完成源码构建、开发签名、USB 安装与选定流程重放。RootHide 引导现在会等固定版本 Frida 侧车配置完成后才宣告深度分析就绪。

## 已测范围和边界

当前代码在 iPhone XR/iOS 16.1.1 与 iPhone 11/iOS 26.0.1 上通过设备诊断、包／沙盒采集和同一份原版 Clock Start → Stop 界面脚本。XR 夹具 Counter `1 → 2` 原版／复刻版新对照，以及基线归零后的 iOS 26 Clock Start → Stop → Reset 原版／复刻版新对照均通过；新六组截图逐张审阅为轻微差异。[iPhone 14/iOS 17.3.1 当前代码重放](ios17-current-code-validation.zh-CN.md)通过重新采集 Calculator 以及四条 iOS MCP 原版／独立 App 运算流程，五组截图审阅为轻微差异。额外的 iCTRL 复刻版重放在等号处遇到格式错误的 HTTP 响应，该后端限制仍待解决。XR 的可选 DVT 文件列表仍返回 `ConnectionTerminatedError`，SSH 包与沙盒采集可用。iOS 26 的 Instruments 启动后仍偶发黑帧，已观察到的几次均经有界恢复成功。另一台实体 Mac 的手机配置尚未实测，本轮暂缓。选定流程通过和轻微视觉差异不能证明整 App 等价、任意 App 自动复刻或重启后的长期稳定。见[iOS 16／26 证据](ios16-ios26-current-code-validation.md)。

原始 IPA、截图、沙盒内容和设备密钥保存在被 Git 忽略的本地 `cases/`，不作为发布资源。
