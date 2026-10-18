# Copy APP 当前计划

[English](PLAN.en.md) · 简体中文 · [当前状态](docs/current-status.zh-CN.md)

## 产品约定

Copy APP 在越狱 iPhone 上完成两项工作：先**分析**已安装 App，产出审阅过、带来源引用的报告和功能规格；再把选定行为**复刻**为独立可运行的 iOS App，在同一手机上与原版对照。Coding Agent 负责解释与实现，CLI 负责采集和校验证据、控制设备、记录缺口。具体操作见[工作流](docs/copy-workflow.zh-CN.md)、[架构](docs/architecture.zh-CN.md)与[覆盖目标](docs/coverage-targets.zh-CN.md)。

报告应覆盖 App 身份、权限、安装包与动态库、界面及导航、资源、沙盒与数据模型、网络及系统集成、原生类和函数证据、选定运行行为、实现推断与未知项。重要结论引用设备、App 构建和来源案例。反编译伪代码不等于原作者源码；不能仅从客户端推断服务端内部逻辑。

复刻目标在盘点已知能力后选定。简单 App 可以覆盖全部已知能力；复杂 App 应先交付有用的一部分，并列明延期、阻塞与未知行为。选定流程的通过数不能当成整 App 覆盖率。

## 当前基线

- **正式发布：**v0.1.0 是唯一的 Git 标签与 GitHub Release，尚无正式 v0.1.1+。
- **iOS 16：**iPhone XR/Dopamine rootless 已通过选定报告到复刻路径。可选 DVT 文件列表失败时，SSH 采集可用。
- **iOS 17：**iPhone 14/Relaxin RootHide 通过当前代码的 Calculator 采集、四条原版／独立 App iOS MCP 对照、五组截图审阅和原版五次 Frida 方法命中。额外的 iCTRL 复刻版重放仍有格式错误的 HTTP 响应。
- **iOS 26：**iPhone 11/Relaxin RootHide 完成选定 Calculator 与 Clock 交付。iOS MCP 的黑帧拒绝和有界恢复在已观察案例中通过。
- **Mac：**本地 342 项测试及提交 `1499222` 的 GitHub 全新 macOS 安装、测试、隔离 wheel 检查通过。第二台实体 Mac 的首次手机配置暂缓。
- **图文说明：**[项目介绍](docs/articles/copyapp-overview.zh-CN.md)已按三台真机现状更新；[架构图](docs/assets/architecture-overview.svg)区分 Mac 与越狱手机的组件和 USB 证据流，另有基于真实案例的 Hopper 与沙盒证据图示。

这些只是在指定设备上的选定流程结果，边界见[当前状态](docs/current-status.zh-CN.md)。原始案例留在被 Git 忽略的本地目录，不作为发布资源。

## 后续门槛

1. **优先修可靠性：**定位并修复 iOS 17 iCTRL 多步传输故障，或在下一版中明确限制。结果不明的操作须先检查设备状态，再决定是否重放。
2. **补齐可选路径：**调查 XR 的 DVT 文件列表失败；保留已可用的 SSH 采集路径。
3. **做长期验收：**检查重启／重新越狱后的持续可用性，以及更长时间的界面与后端稳定性。
4. **复核新用户体验：**恢复第二台实体 Mac 的工作时，按安装指南从首次 USB 信任、SSH 指纹固定、界面控制、包采集一直验证到签名或 TrollStore 复刻安装。
5. **集中发布：**审阅最终实现 diff 和双语文档，在发布提交上运行测试；只改一次包版本、创建一个标签并发布一次 GitHub Release。发布说明列出选定流程和剩余限制。

之后再扩大陌生 App 的自主探索、更完整的功能、数据持久化及后端边界、视觉还原程度。在证据足够之前，不承诺任意 App 的完整复刻。
