# Copy APP 当前计划

[English](PLAN.en.md) · 简体中文 · [当前状态](docs/current-status.zh-CN.md)

## 产品约定

Copy APP 在越狱 iPhone 上完成两项工作：先**分析**已安装 App，产出审阅过、带来源引用的报告和功能规格；再把选定行为**复刻**为独立可运行的 iOS App，在同一手机上与原版对照。Coding Agent 负责解释与实现，CLI 负责采集和校验证据、控制设备、记录缺口。具体操作见[工作流](docs/copy-workflow.zh-CN.md)、[架构](docs/architecture.zh-CN.md)与[覆盖目标](docs/coverage-targets.zh-CN.md)。

报告应覆盖 App 身份、权限、安装包与动态库、界面及导航、资源、沙盒与数据模型、网络及系统集成、原生类和函数证据、选定运行行为、实现推断与未知项。重要结论引用设备、App 构建和来源案例。反编译伪代码不等于原作者源码；不能仅从客户端推断服务端内部逻辑。

复刻目标在盘点已知能力后选定。简单 App 可以覆盖全部已知能力；复杂 App 应先交付有用的一部分，并列明延期、阻塞与未知行为。选定流程的通过数不能当成整 App 覆盖率。

## 当前基线

- **正式发布：**v0.1.2 纳入 iOS 17 会话修复和面向 Coding Agent 的首次入口；指定设备的历史与新增证据分开记录。v0.1.0 保留首次发布档案。
- **iOS 16：**iPhone XR/Dopamine rootless 已通过选定报告到复刻路径。可选 DVT 文件列表失败时，SSH 采集可用。
- **iOS 17：**iPhone 14/Relaxin RootHide 通过当前代码的 Calculator 采集、四条原版／独立 App iOS MCP 对照、五组截图审阅和原版五次 Frida 方法命中。v0.1.1 的 iCTRL 会话问题已在 v0.1.2 修复，两轮各四条原版／复刻版 iCTRL 末端断言与退出清理通过。
- **iOS 26：**iPhone 11/Relaxin RootHide 完成选定 Calculator 与 Clock 交付。iOS MCP 的黑帧拒绝和有界恢复在已观察案例中通过。
- **Mac：**v0.1.2 的 346 项本地测试及隔离 wheel 安装检查通过；提交 `1499222` 保留先前 GitHub 全新 macOS 安装与测试记录。第二台实体 Mac 的首次手机配置暂缓。
- **图文说明：**[项目介绍](docs/articles/copyapp-overview.zh-CN.md)已按三台真机现状更新；[架构图](docs/assets/architecture-overview.svg)区分 Mac 与越狱手机的组件和 USB 证据流，另有基于真实案例的 Hopper 与沙盒证据图示。

这些只是在指定设备上的选定流程结果，边界见[当前状态](docs/current-status.zh-CN.md)。原始案例留在被 Git 忽略的本地目录，不作为发布资源。

## 后续门槛

新增双平台工作见 [macOS 实施与验收计划](docs/macos-implementation-plan.md)。在保留现有
iOS 命令、设备链路和历史 case 的前提下，使用 ChatComputer 增加 macOS Computer Use、
行为分析与独立重建。当前为开发分支工作；不代表 v0.1.2 已支持 Mac App。

1. **继续验证可靠性：**保留 iOS 17 会话修复的指定设备回归证据，并在其他指定手机复验本次会话清理改动。结果不明的操作仍须先检查设备状态，再决定是否重放。
2. **保留可选路径记录：**XR 的 DVT 文件列表故障曾重复出现；只有新设备或开发者服务变化确实需要此路径时再调查。SSH 采集仍可用。
3. **做长期验收：**检查重启／重新越狱后的持续可用性，以及更长时间的界面与后端稳定性。
4. **复核新用户体验：**恢复第二台实体 Mac 的工作时，按安装指南从首次 USB 信任、SSH 指纹固定、界面控制、包采集一直验证到签名或 TrollStore 复刻安装。
5. **集中发布：**在下一次发布前扩大指定 App 和设备的证据范围，审阅实现 diff 和双语文档，在发布提交上运行测试；仅为已完成的范围创建一个标签和 GitHub Release。

长期工作包括扩大陌生 App 的自主探索、更完整的功能、数据持久化及后端边界、视觉还原程度。在证据足够之前，不承诺任意 App 的完整复刻。
