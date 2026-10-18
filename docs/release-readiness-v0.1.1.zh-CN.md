# 下一补丁版发布准备 · 草稿

[English](release-readiness-v0.1.1.md) · [简体中文](release-readiness-v0.1.1.zh-CN.md)

这是正式标签 `v0.1.0` 之后单次补丁发布的验收记录，**不是发布公告**。源码对比基线为 `git diff v0.1.0..main`；编号 `v0.1.1`–`v0.1.17` 的[开发记录](development-checkpoints/README.md)从未成为正式标签。

| 门槛 | 当前证据 | 发布判断 |
| --- | --- | --- |
| 1. iOS 26 Calculator 报告到独立 App | 审阅报告、计划、签名 App、`7 + 8 = 15` 同机对照、逐图审阅及已校验交付 `cases/ios26-calculator-source-linked-delivery-20261018` | 一条指定运算流程通过；独立源码沿用并调整已有实现。 |
| 2. iOS MCP 黑帧处理 | iOS 26 上拒绝三张黑帧后经返回主屏／重启 App 恢复；见[设备记录](relaxin-roothide-iphone11-ios26.md)。新一轮 Clock 实测再次触发并恢复。 | 已观察故障的回退通过；启发式和短时观察不能证明长期稳定。 |
| 3. 第二款 App 与已连接设备回归 | iOS 26 Clock 审阅报告、签名独立 App 和四组逐图审阅；[当前代码 iOS 16／26 记录](ios16-ios26-current-code-validation.md)包含两机新诊断及同一 Clock Start → Stop 脚本。 | XR/iOS 16.1.1 与 iPhone 11/iOS 26.0.1 的选定流程通过；iOS 17 未连接，当前代码重放仍待进行。 |
| 4. 全新环境与文档 | [GitHub 全新 macOS 运行](https://github.com/everettjf/copyapp/actions/runs/39139348793)安装 CLI 和跟踪依赖，并完成 338 项测试；本机隔离检出完成安装、首次采集及校验。 | 主机端安装通过；第二台实体 Mac 的手机配对、越狱服务和签名仍未实测。 |
| 5. 单次发布 | main 已包含实现及[英文](release-candidate-v0.1.1.md)／[中文](release-candidate-v0.1.1.zh-CN.md)发布说明草稿；实际只有 `v0.1.0` 标签和正式版本。 | 剩余验收完成前暂不改版本号、打标签或创建 GitHub Release。 |

发布前，用当前代码在 iPhone 14/iOS 17 上重放核心诊断和一条原版／复刻版流程，校验案例并记录设备专属问题。在第二台实体 Mac 按 README 配置，配对一台手机，核验 SSH 信任、UI 控制、包与沙盒采集，以及签名或 TrollStore 安装。重启／重新越狱后的持续可用性仍未经验证；应实测，或在最终说明中明确保留这一边界。随后审阅 `git diff v0.1.0..main`、在最终提交上运行测试、定稿中英说明，仅一次修改包版本、打一次标签并发布一次 GitHub Release。案例校验只能证明文件和来源一致，不能证明语义解释正确或整 App 等价。
