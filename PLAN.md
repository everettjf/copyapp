# Copy APP 产品与实施计划

**语言：** [English](PLAN.en.md) | 简体中文

状态：已进入实施。本文确定产品范围、架构、验收标准和实施顺序；当前可运行原型与实机结果见 `README.md` 和本地 `cases/`。

2026-10-16 更新：`copyapp copy --auto-discover --agent-provider current` 现先生成发现任务并暂停，当前会话将 3–12 条脚本提交 `discover-check` 后以 `--resume` 续跑，不嵌套启动 Agent。XR 上的 `cases/clock-current-auto-workflow-20261016/` 使用三条先前编写的 Clock 脚本完成真机重放、正式报告、独立复刻工程、安装和三流程对照。3/3 行为及末端视图断言通过，10 对截图逐张审阅为轻微差异，父案例 517 项证据文件通过校验。它验证了完整编排，不证明模型自主发现或从零生成；复刻源码改自既有独立实现。另一个 `cases/clock-current-workflow-live-20261016/` 也完成报告、复刻、安装和三流程对照。英文默认入口为 `README.md`、`PLAN.en.md` 和 `docs/copy-workflow.md`；对应中文版本可从页面顶部切换。

## 1. 产品目标与第一版边界

Copy APP 提供两项连续功能：

1. **Analyze**：指定一台越狱 iPhone 上已安装的 App，采集包、沙盒、界面和运行行为，生成可追溯证据的全面逆向报告，并输出机器可读的功能规格。
2. **Rebuild**：从报告中选择功能流程，独立实现一个可运行的 iOS App；在真机上与目标 App 对照，持续修正差异。

第一版只支持越狱真机，目标系统为 iOS 16、17、26。Mac 负责流程编排、二进制分析、报告生成和新 App 构建；手机负责观察和采集。第一版的成功标准是**一个 App 的三条代表性功能流程形成“采集 → 解释 → 实现 → 真机对照”的闭环**。功能范围由任务显式选定，不能把报告的页数或类名数量当作完成标准。

第一版不承诺还原原作者源码、获取不可见的服务端实现，或自动复刻任意 App 的所有功能。关键方法以可恢复的符号、元数据、反编译伪代码和运行证据表达。复刻 App 使用独立实现，第三方资源和账号数据不默认并入新工程。

## 2. 当前仓库与外部基础

本仓库 `everettjf/copyapp` 的 `main` 在克隆时为初始提交 `4ee0a7bd675951df050e1be0934f0d8e9d72e861`，仅有 Apache-2.0 `LICENSE`，没有现成模块需要迁移。计划采用一个独立仓库容纳设备端、Mac 端、Skills、格式定义与测试夹具。

越狱采集以 [witchan/ios-mcp](https://github.com/witchan/ios-mcp) 为代码来源，**不要求先在 GitHub 创建 fork**。实施时记录引入的上游提交和许可证、保留署名，挑选需要的模块纳入本仓库并维护本地修改。上游自有代码声明为 MIT；其构建文件还打包其他许可证的组件，因此引入范围和再分发文件必须逐项确认。第一版不直接复制整个安装包及所有辅助组件。[来源与打包清单](https://github.com/witchan/ios-mcp/blob/main/Makefile)

界面操作同时接入 [OpenMinis/iCTRL](https://github.com/OpenMinis/iCTRL) 的现有 JSON-RPC 服务。第一版先写 Mac 端适配器，让 iCTRL 与 iOS MCP 在手机上并存，不把 XCUITest runner 源码合并进 SpringBoard tweak。若实测表明必须修改 iCTRL，再单独引入所需源码和上游版本记录。iCTRL 当前以独立签名的测试 runner 和 DDI 工作，与 iOS MCP 的越狱 tweak 生命周期不同。[iCTRL 运行与安装说明](https://github.com/OpenMinis/iCTRL)

## 3. 目标架构

```text
Codex / Claude Code / 后续自有 Agent
             │  Copy APP Skills：规定步骤、证据和停止条件
             ▼
Mac 端 Copy APP：任务编排、双 UI 适配器、证据库、分析器、报告器、复刻验证器
             │  受控 USB/本地连接，版本化协议
             ▼
越狱设备：iOS MCP UI/采集入口 + iCTRL UI runner + 独立采集 helper
          + Frida 服务 + 可替换 IPA 获取器
             │
             └── 目标 App、容器、系统日志与运行轨迹
```

### 3.1 设备端

- **双 UI 后端**：iCTRL 和 iOS MCP 都可完成触控、截图、无障碍树/OCR 和 App 启动。iCTRL 提供元素引用、可见区域快照与配对访问；iOS MCP 在需要越狱上下文或 iCTRL runner 不可用时承担 UI。一次流程只允许一个后端发送触控/输入，切换时先记录前台 App 与屏幕状态，避免两个 agent 同时操作。两者原始结果均保留，不假设元素 ID 或坐标语义完全一致。[iCTRL 能力](https://github.com/OpenMinis/iCTRL)、[iOS MCP 能力](https://github.com/witchan/ios-mcp)
- **轻量越狱服务**：复用 iOS MCP 的设备与文件能力；保持 SpringBoard 中的常驻部分轻量，避免执行大文件复制或反编译。
- **采集 helper**：独立进程负责目标 App 的包路径、数据容器、App Groups、文件元数据、沙盒前后差异、批量打包及传输。权限按实际越狱环境确定，路径通过系统信息发现，不写死 rootless 前缀。
- **运行时适配器**：Mac 调度 Frida；设备端只需提供连接状态和任务标识。Frida 脚本按问题启用，记录调用、加载模块、文件与网络事件；默认不采集令牌或正文等敏感值。
- **IPA 获取器**：以插件接口封装不同方案；每种方案都要验证主程序、扩展和内嵌动态库的解密状态与文件哈希。`copyapp check-ipa` 完成包内 Mach-O 检查，`decrypt-main` 完成独立的主程序运行时恢复，`decrypt-package` 已在 XR 上对 DeepSeek 和 Kimi 的主程序及扩展完成自动整包恢复，逐个验证代码差异只发生在加密区和 `cryptid` 字段。iOS 17/26 上仍需实测兼容性；`unfair` 的重映射路径在 XR 上超时，作为诊断材料保留。[ipadecrypt](https://github.com/londek/ipadecrypt)、[bagbak 说明](https://github.com/ChiChou/bagbak)、[iOS 上的 unfair 实现](https://github.com/lbr77/unfair)
- **连接安全**：上游 iOS MCP 声明没有内置认证，服务源码绑定 `INADDR_ANY`。Copy APP 设备服务默认只接受受控连接，远程开放需单独启用；危险操作通过目标范围和能力白名单约束。[上游安全说明](https://github.com/witchan/ios-mcp)、[监听实现](https://github.com/witchan/ios-mcp/blob/main/MCPServer.m)

### 3.2 Mac 端

- **流程引擎**保存任务状态、断点、设备能力、步骤结果和重试记录；每一步可单独重跑，不覆盖已有原始证据。
- **UI 后端路由器**同时探测 iCTRL 与 iOS MCP 的健康状态、截图、元素覆盖率、动作成功率和延迟；按当前设备与 App 选择主后端，另一后端只用于交叉观察或故障切换。它将两套接口归一为 `observe`、`tap`、`swipe`、`type`、`launch`、`foreground`，并记录实际执行者。
- **静态分析器**先解析 IPA、Mach-O、Info.plist、entitlements、依赖库、资源、ObjC/Swift 元数据；默认以本机 `llvm-objdump` 获取有界 ARM64 汇编并结合运行时分支观测。显式选择 `ghidra-direct` 时，Copy APP 自身直接调用本机 Ghidra Headless 反编译哈希固定的关键函数；`ghidra-indirect` 还可从已验证调查自动找出有限 `blr` 位点，在真机重放后分析实际回调目标。REA/Ghidra 与 REA/Hopper 仍是显式选择的历史路径，不是独立流程的运行依赖。无 REA 的 XR 真机报告、复刻任务和对照见 `docs/no-rea-analysis.md`；可选 REA 的运行边界见 `docs/rea-hopper-integration.md`。[Ghidra headless 说明](https://github.com/NationalSecurityAgency/ghidra/blob/master/Ghidra/RuntimeScripts/support/analyzeHeadlessREADME.md)
- **关联分析器**把一次 UI 动作与截图、沙盒变化、Frida 事件、网络端点和候选方法连接起来，产出“功能证据图”。
- **报告器**从证据图生成可阅读报告和机器可读的复刻规格；缺失证据标为未知，不由模型补写。
- **复刻验证器**编译、安装并操作新 App，比较页面、导航、状态和功能输出，生成差异任务供 coding agent 修复。

### 3.3 Agent 与 Skills

第一版依附 Codex 或 Claude Code，不开发新的通用 coding agent。设备操作、采集和分析逻辑实现为稳定工具；Skills 仅定义工作流、输入输出、证据质量和失败处理。计划的 Skills 为：`device-check`、`app-survey`、`acquire`、`static-analysis`、`runtime-investigation`、`report-review`、`rebuild-feature`、`compare-on-device`。所有 Skills 调用同一版本化工具协议，因此后续 API agent 可以接管编排，不需重写设备代码。

## 4. 三系统兼容策略

| 系统 | 初始路径 | 必须实测的风险与替代路径 |
| --- | --- | --- |
| iOS 16 | iOS MCP 与 iCTRL 分别验收 UI，越狱 helper 采集包/沙盒，Frida 采集运行时 | Xcode 27 的设备调试支持从 iOS 17 起；iCTRL 文档另有在手机上签名与挂载 DDI 的路径，必须在这台 iOS 16 实机验证，不能仅凭 Xcode 限制判定其不可用。 |
| iOS 17 | 双 UI 后端和同一采集协议 | 验证具体越狱方式下的注入、容器权限、OCR、Frida、脱壳，以及 iCTRL runner 的签名与 DDI 恢复。 |
| iOS 26 | iCTRL 和 iOS MCP 分别做兼容性试验，再启用完整流水线 | 上游 iOS MCP 的公开支持范围止于 iOS 18，不能视作现成可用；iCTRL 声明支持 iOS 16 及以后，但在目标 iOS 26 上仍须验证 runner 与 DDI。即使 UI 交给 iCTRL，包、沙盒和运行时仍由越狱采集路径负责。 |

三台手机共享**协议、报告格式和 Mac 端主流程**，设备端按能力探测选择实现，避免复制三套工程。已确认测试设备为 iPhone XR（iOS 16.1.1）、iPhone 14（iOS 17.3.1）和 iPhone 11（iOS 26.0.1）；每台设备保留越狱工具、bootstrap/rootless 类型、架构和工具版本记录。上游 iOS MCP 列出的 rootless/roothide 支持范围为 iOS 15–18；Frida 曾宣布对 iOS 26 的初步支持，这些资料都不能代替三台实机验收。[iOS MCP 支持表](https://github.com/witchan/ios-mcp)、[iCTRL 安装与系统要求](https://github.com/OpenMinis/iCTRL)、[Frida 发布说明](https://frida.re/news/2025/07/02/frida-17-2-9-released/)、[Apple Xcode 支持表](https://developer.apple.com/xcode/system-requirements)

## 5. Analyze 工作流与报告

### 5.1 采集顺序

1. **建档**：固定目标 bundle ID、App 版本、设备、测试状态和关注的功能；检查已有证据与前次任务是否可复用。
2. **界面地图**：按入口和业务任务探索页面；每步保存动作、截图、无障碍树/OCR、前台 App、时间戳和状态变化，形成可重放的屏幕图。
3. **包与沙盒**：取得 IPA 和签名/加密状态；索引 App、Framework、扩展、资源；获取允许范围内的容器清单，并为关键动作做前后差异。
4. **静态索引**：识别依赖、技术栈候选、类与协议、Swift 符号、调用图和关键字符串；为候选函数保留二进制哈希、地址、分析工具版本。
5. **定向动态实验**：依据 UI 流程和静态候选设计 Frida 观察点，追踪方法调用、模块加载、文件与网络事件；重复实验以排除噪声。
6. **深入解释**：每个主要功能回答“界面怎样组织、入口在哪里、数据怎样流动、核心逻辑在哪里、哪些部分仍不可见”。
7. **审稿与输出**：审查结论和证据，生成报告、索引和复刻规格。

### 5.2 报告内容

报告按照目标 App 组织，不设固定章节数量，至少覆盖：身份和权限、包与动态库、技术栈、屏幕与导航、UI 组件与资源、交互状态机、沙盒与数据模型、网络与后端边界、系统集成、ObjC/Swift 类与方法、关键函数伪代码、按功能串联的静态和动态证据、无法确认的部分及复刻优先级。附录提供完整文件/库/类/资源索引，正文聚焦有解释价值的实现。

每项实质性结论都带证据 ID、来源路径或截图、设备与 App 版本、采集条件及可信度：**直接观察 / 多证据推断 / 待验证**。报告中的“关键代码”指反编译伪代码、方法关系和算法解释，不冒充原作者源码。服务端逻辑仅描述客户端能观察到的契约。

### 5.3 案例目录与格式

```text
cases/<case-id>/
  manifest.json          # 目标、设备、工具版本、采集范围
  evidence/              # 原始截图、UI 树、IPA、沙盒快照、日志和轨迹
  indexes/               # 文件、动态库、类、方法、资源与页面索引
  findings.json          # 带证据引用和可信度的结构化结论
  feature-spec.json      # Rebuild 可读取的功能规格与测试场景
  report.md              # 面向人的报告
  comparison/            # 后续复刻对照结果
```

原始证据采用内容哈希和只追加保存；报告可重生成。案例目录默认本地保存，凭据、账号数据和网络负载在进入模型上下文前做脱敏。

## 6. Rebuild 工作流

1. **范围冻结**：从 `feature-spec.json` 选择三条代表性流程，明确页面、状态、输入输出、离线/在线依赖和验收场景。
2. **实现计划**：由 coding agent 选定 UIKit/SwiftUI 或混合方案，建立独立代码结构、组件、状态和服务接口；不可见的后端能力使用可替换的模拟服务，并在差异报告中标识。
3. **逐流程交付**：每完成一个纵向流程，就构建并在真机上走完整路径，避免最后才发现系统版本或签名问题。
4. **对照验证**：相同设备、账号状态和操作脚本下，比较原 App 与新 App 的截图、页面跳转、交互反馈、数据持久化和异常行为；动态内容区域单独处理。
5. **迭代与交付**：差异转成可追踪任务，完成后重测；交付源码、可安装构建、覆盖范围和未复刻行为清单。

新 App 第一版设定最低部署目标为 iOS 16；在 iOS 16、17、26 三台真机上验证选定流程。Xcode 27 可以设置 iOS 16 部署目标，但其官方真机安装与调试支持从 iOS 17 开始；iOS 16 的安装和日志走越狱路径，界面验证使用实测可用的 iCTRL 或 iOS MCP 后端。[Apple 支持表](https://developer.apple.com/xcode/system-requirements)、[iCTRL 安装方式](https://github.com/OpenMinis/iCTRL)

## 7. 实施里程碑与关卡

| 里程碑 | 工作内容 | 通过条件 |
| --- | --- | --- |
| M0 设备基线 | 登记三台设备，确定连接、越狱类型、架构、重启后的恢复步骤 | 三台设备可被流程引擎识别；能力探测给出可用/不可用原因。 |
| M1 设备控制 | 接入 iCTRL API，引入必要的 iOS MCP 源码，完成双 UI 适配、单后端触控仲裁、受控连接、目标会话和独立采集 helper | 三台设备分别测两套 UI 后端；每台至少有一个可重复执行固定脚本的主后端，失败切换能保留证据；iOS 26 的越狱采集能力逐项验收。 |
| M2 证据采集 | IPA 获取器、加密校验、沙盒差异、Frida 轨迹与传输 | 测试夹具 App 的主程序、内嵌库和扩展均能被索引；采集失败有明确原因且可重跑。 |
| M3 分析报告 | 静态索引、功能关联、证据审查与报告模板 | 对测试夹具的三条流程能从 UI 动作追到代码和数据变化；报告重大结论都有证据或明确标为未知。 |
| M4 真实 App 试点 | 对一款选定 App 完成主要界面、沙盒、静态和动态分析 | 交付可审阅的深入报告、证据包和可执行的复刻规格。 |
| M5 复刻闭环 | 独立实现试点 App 的三条代表性流程并真机对照 | 新 App 可在三台设备运行；流程测试通过，视觉与行为差异有记录和复测结果。 |
| M6 产品化 | 失败恢复、升级兼容、批量任务和 agent 一句话入口 | 第二款不同技术栈 App 可复用流程，主要步骤不依赖人工临时命令。 |

M0 和 iOS 26 的 M1 兼容性试验必须先于大规模移植。若 iOS 26 的某项底层能力暂不可用，保留统一接口与明确状态，先继续其他系统和独立模块的工作，同时针对该能力选择替代实现；不把未经验证的支持写入发布承诺。

`copyapp doctor --udid` 已提供 M0 的可重复能力基线，XR 上逐项探测和证据哈希校验通过；iOS 17、26 两台设备仍需连接后分别运行，不能以 XR 结果代替。当前 SSH 基线使用已存在的本地 USB 转发；换设备时必须配置该设备的转发和固定主机密钥。

## 8. 验证方法与验收指标

先开发一款**已知源码的测试夹具 App**：同时包含 UIKit/SwiftUI 页面、Framework、扩展、模拟接口、SQLite/UserDefaults 写入和可重复的三条操作流程。它用来检验类识别、页面图、沙盒差异、运行轨迹和报告推断是否准确。其后再选择一款实际目标 App 作盲测；避免只凭无法核实的商业 App 判断工具正确性。

第一版的验收指标：

- 三台设备分别通过连接、截图、界面读取、触控、沙盒读取、Frida attach、IPA 获取的能力测试，失败项有可复现记录；iCTRL 和 iOS MCP 的 UI 结果分开计量。
- 同一套测试夹具脚本分别用两个 UI 后端运行，记录元素覆盖率、动作成功率、耗时、runner/DDI 重启恢复和 SpringBoard 稳定性，再选各设备的默认后端。
- 测试夹具上，每条选定流程可重复采集；包中的主程序、Framework 和扩展都有明确的加密与分析状态。
- 报告正文的关键实现判断均能回溯到至少一份原始证据；推断和未知项与直接观察分开。
- 实际目标 App 的三条流程均有屏幕图、实现解释、数据/网络边界及复刻规格。
- 复刻 App 在三台系统上能安装、启动并完成这三条流程；对照测试记录视觉、行为和状态差异，不用单一截图分数代替人工判断。
- 每个阶段可以从保存的任务状态重试，失败不破坏已采集证据。

## 9. 主要工程风险与处理

| 风险 | 处理 |
| --- | --- |
| iOS 26 未在上游 iOS MCP 支持范围内 | M1 优先做逐项实机兼容性试验；UI 服务、helper 和传输分别判断，不把单项失败扩散到整个流程。 |
| iCTRL 的签名、DDI 和测试 runner 生命周期不同于越狱 tweak | 将其作为独立服务接入；设备重启后先检查 runner/DDI，再决定是否切回 iOS MCP。 |
| 两套 UI 后端同时操作导致状态错乱 | 每个任务只设一个写入后端；另一后端可只读观察，切换必须保存前台 App、截图和任务时间线。 |
| 不同越狱环境的权限与路径不同 | 设备能力探测和路径发现，按 rootless/roothide 等环境封装适配器。 |
| 脱壳方案受 App 保护或系统版本影响 | 可替换工具接口、完整性验证、按失败原因切换方案；不将导出一个 IPA 等同于可分析。 |
| Swift、裁剪符号和自绘界面降低可见度 | 结合无障碍/OCR、资源、静态分析和定向运行时实验；保留可信度与未知项。 |
| 高权限工具影响手机稳定性 | UI 服务保持轻量，耗时工作移到 helper；记录崩溃/重启，提供停止与恢复路径。 |
| 不可见的服务端行为影响复刻 | 明确客户端观察到的接口契约，复刻项目使用可替换的模拟服务。 |

## 10. 当前实施记录

XR 已完成 USB 设备登记、Compass 安装包和沙盒索引采集、Mach-O 与 Objective-C 类/方法静态索引（11 类、137 方法）及关键方法解释。此前的一次采集被另一个 App 的权限弹窗遮挡，报告已标记归属不符；最新 `copyapp analyze --ui-backend ios-mcp` 在截图前后均确认原版 Compass 位于前台，并通过 `copyapp verify`。原版与独立复刻版均通过 iOS MCP 在 XR 上完成截图、方位锁定点击、位置显示和点击坐标进入 Apple Maps；对照和剩余差异见 `docs/xr-rebuild-verification.md`。rootless iOS MCP 派生服务已通过 Filza 安装并重载 SpringBoard，USB 转发后的截图、前台识别、启动和点击均真机成功。`copyapp experiment` 已把按 UDID 自动建立 USB 转发、UI 点击和 Frida 计数串成自动流程，原版 Compass 的方位盘实验观测到三个关键方法各调用一次，地图实验观测到 `_openMaps` 一次，详见 `docs/compass-xr-analysis.md`。另用 Kimi 3.0.9 验证了普通 App 的主程序真实脱壳：磁盘文件 `cryptid=1`，运行时恢复 4096 字节，分析副本 `cryptid=0`；最初的主程序分析包仍有 3 个加密扩展；后续 `decrypt-package` 已在 XR 上对 Kimi 的主程序及 3 个扩展、DeepSeek 的主程序及 1 个扩展完成整包恢复，分别核查 17 和 32 个 Mach-O，见 `docs/full-package-decryption.md`。一条新的 `root-run` 通道已在 XR 上实测，可通过精确 UDID 的 USB Frida 服务执行一次性 root 操作，不需手机端输入。试用 `unfair` 整包解密时，修正页对齐后仍在读取 FairPlay 重映射页处超时，因此没有把它并入正式流程。iCTRL Mac 客户端与适配器本地测试通过；XR 上的 iOS 16 兼容试验版 runner 已完成配对、加密 UI 调用、Compass 截图与方位锁定点击，见 `docs/ictrl-xr-validation.md`。iOS 17/26 两台设备尚未连接测试；扩展脱壳已在 XR 的两个样本上成功，但跨系统和跨保护策略的通用性、完整沙盒与网络采集、一句话自动复刻仍未验证。M1–M6 的完整验收条件均未完成。

`copyapp analyze --decrypt` 已把 USB UI、App 包、沙盒元数据、整包解密、解密后静态索引与 Objective-C 类索引连成一次命令。DeepSeek 2.4.4 在 XR 上四阶段全部通过，报告位于 `cases/deepseek-onepass-decrypt-fixed-20261015/analysis.md`，证据哈希经 `copyapp verify` 校验通过。截图确认为 DeepSeek 登录页；没有账号会话，所以仍缺少登录后页面和功能流程证据。

XR 的设备 OCR 曾两次使 SpringBoard 崩溃并触发 ElleKit Safe Mode；保存崩溃与标记证据后，现装 0.1.3 包已移除设备端 OCR 工具，`describe_screen` 的 OCR 请求也被安全拒绝。连续截图加 Mac Vision OCR 真机通过，原版 Compass 返回 20 项可见文本、稳定前台归属和屏幕点映射。两套 UI 后端现均能执行同一条 Compass 点击加 Frida 方法计数实验，结果均为目标方法 1 次；iCTRL 路径可自动启动配对 runner 并建立指定设备的临时 USB 转发。详见 `docs/xr-ocr-validation.md` 与 `docs/ictrl-xr-validation.md`。这仍只是 XR 上一个交互的双后端重复验证，不满足三系统与三流程的完整验收。

`copyapp playbook` 已提供有限动作的可重放 UI 脚本。源码已知夹具 Counter 的同一脚本在 XR 的 iCTRL 与 iOS MCP 后端均核对首页、按钮和计数加一，并保存带哈希的证据；一次启动动画导致的过早观察作为失败案例保留，播放器现限次重试观察。见 `docs/fixture-xr-validation.md`。

`copyapp candidates` 现把已验证的 UI/Frida 实验按类名和 selector 关联至精确哈希的 Objective-C 实例方法索引，产生 REA 待分析地址及源证据。Compass 方位盘实验生成了 4 个候选并通过哈希校验。该关联不等于运行时 IMP 与磁盘方法体一致，也不自动证明窗口内每次调用由点击导致；后续需 REA 调用链与重复动态实验核实。

Compass 候选 `tappedCompass:` 已按静态地址 `0x100001960` 送入 REA/Ghidra，返回 `_hasBearing` 分支到 `setBearing` 或 `unsetBearing` 的伪代码及 Evidence ID；新增的报告结论已纳入 `cases/compass-xr-deep-report-v4-20261015/` 并通过 `copyapp verify`。这补上了一条真机动作 → 动态方法计数 → 静态地址 → 反编译函数 → 报告结论的实际链路，但仍需验证运行时 IMP 与静态函数体的对应及取消分支。

随后在 XR 上用 iCTRL 连续点击原版 Compass 两次，Frida 分别记录 `unsetBearing=1, setBearing=0` 与 `unsetBearing=0, setBearing=1`，截图分别显示红色锁定标记消失与恢复。更新的 `cases/compass-xr-deep-report-v5-20261015/` 已纳入双方向实验并通过 `copyapp verify`；运行时 IMP 与静态函数体的严格对应仍待解决。

Frida 方法记录现对 arm64e IMP 去除指针认证并保存所属模块、加载基址和偏移。XR 上新两次 Compass 双方向实验的 `tappedCompass:`、`setBearing`、`unsetBearing` 运行时模块偏移分别与采集 Mach-O 的静态偏移 `0x1960`、`0x1978`、`0x1a08` 一致；`copyapp candidates` 会把偏移冲突排除出 REA 队列。REA/Hopper 与 REA/Ghidra 又对同一二进制的点击入口、锁定设置/取消、表盘图层更新分别给出独立函数证据；结果已进入 `cases/compass-xr-deep-report-v8-20261015/` 并通过校验。尚未证明手机加载代码字节与采集副本完全相同，也未验证其他 iOS 系统上的 PAC 行为。

Hopper 和 Ghidra 又对原版 `CompassBearingView::layoutSubviews` 的相同地址 `0x100001e48` 给出函数证据：锁定方位和当前角度有差值时，内外圆弧形成方位偏差扇区；角度相同或未锁定时，图层 path 为空。该结论已进入通过哈希验证的 `cases/compass-xr-deep-report-v9-20261015/`。复刻版已按此实现填充扇区，并由 `copyapp install` 更新到 XR；但静止设备上的成对截图只确认红色标记出现/消失，没有足够角度差来验证扇区形状或旋转后的几何关系。

随后通过 Frida 在原版 `CompassBearingView._angle` 施加可恢复的 45° 偏移并调用 `updateLayer`，在复刻版则偏移 `CMDeviceMotion.heading` 的读取结果。原版运行时内外半径分别是 82/119 pt；REA/Ghidra 又确认填充色为 `UIColor.redColor`。据此调整复刻版扇区半径、图层顺序和红色，并安装至 XR。`cases/compass-offset-comparison-v2-20261015/` 的原版/复刻版截图及源实验均通过哈希验证；指定扇区区域的红色掩码交并比为 0.95344，主导 RGB 桶相同。最新原版深度报告 `cases/compass-xr-deep-report-v10-20261015/` 也通过校验。两边注入点不同，真实转动、动画与其他系统仍未由该数值证明。

`copyapp analyze --resume` 已加入逐阶段状态和恢复：成功阶段经身份/哈希核对后复用，失败或损坏的输出归档到 `attempts/` 后重试，历史错误留存；跨阶段 App 版本不一致会拒绝合并。XR 上以不可达 SSH 端口制造包/沙盒失败，随后只重试这两阶段并复用 USB 界面采集，最终案例校验通过。这覆盖 M6 的一个失败恢复场景；decryption 崩溃恢复、UI 后端切换与三系统重启恢复仍未验收。

续跑阶段现在额外记录 survey 的界面 JSON/截图和 bundle 的静态、Objective-C 索引等派生产物哈希，不再只核对主清单。XR 新案例 `cases/fixture-xr-resume-derived-20261015/` 的三阶段完成并通过校验；复制该案例、故意损坏 ObjC 索引后续跑，`cases/fixture-xr-resume-derived-repair-20261015/` 显示 survey 与 sandbox 复用、bundle 从第 1 次归档并重新采集为第 2 次，最终再次通过校验。旧案例缺少这组额外哈希，按原兼容路径处理；需要同等级保障时应重新采集。

后续已把 Notes 和 Catalog 也写成同一套 `copyapp playbook` 输入，分别用 XR 的 iCTRL 与 iOS MCP 执行。Counter、Notes、Catalog 共六份案例均通过，Notes 的两次新增还与导出的 SQLite 4 行快照对应。M1 在 XR 上的三条固定脚本已有证据；三系统、后端故障切换、延迟与覆盖率基准仍待完成。

沙盒前后差异现有 `copyapp sandbox-diff`：核对两份只读元数据快照的设备、App、容器和深度；可选绑定同一时间窗口内完成且校验通过的 UI playbook，保存完整原始证据与哈希。XR 上围绕测试夹具 Notes 的一次新增，界面数值从 4 到 5，SQLite 文件与 Documents 目录的修改时间发生变化；`cases/fixture-sandbox-diff-with-action-20261015/` 和夹具深度报告 v6 均通过校验。报告导入时会从原始快照重新计算差异；这只证明可见元数据变化，未读取该次数据库正文。

`copyapp playbook-auto` 增加两套 UI 后端的受控切换：主后端失败时，仅在该次运行尚未尝试 `tap` 或 `tap_label` 的条件下切换，两个子案例及错误均保留，并核对脚本、设备和 App 身份。XR 上以缺失的 iCTRL 客户端制造触控前连接失败，随后 iOS MCP 完成夹具 Catalog 的观察、点击、验证和截图；`cases/fixture-catalog-ui-failover-v2-20261015/` 通过哈希校验。真实 iCTRL 客户端作为主后端时，`cases/fixture-catalog-ui-auto-primary-20261015/` 又完成同一脚本而未触发切换。这验证了连接前故障切换及正常主路径；runner/DDI 重启、触控结果不确定时的恢复和 iOS 17/26 仍待验收。

M5 的对照入口现有 `copyapp compare-playbooks`：先要求同一设备、同一后端和相同步骤，再保存原版与复刻版的原始脚本证据、逐步截图和像素差；截图须通过稳定和目标内容就绪检查。XR 上 Compass 方位锁定的两次点击已用新版脚本重跑，原版和复刻版的指定红色标记区域分别记录 `0→134→0` 与 `0→58→0`，完整对照位于 `cases/compass-bearing-comparison-checked-20261015/` 并通过哈希校验。首轮误拍 App 切换画面的案例保留为失败诊断。
地图流程也已用两套 `playbook` 在 XR 上重放：原版与复刻版都在点击相同坐标后进入 Apple Maps 前台，成对对照位于 `cases/compass-maps-comparison-20261015/` 并通过校验。地图落点、定位拒绝状态和实时方位变化的同类对照尚未完成；iOS 17/26 仍待连接验收。
随后在两边 `UIApplication` 地图 URL 打开方法上加了只读 Frida 探针，再次点击坐标。原版和复刻版各捕获到一次相同的 `maps:ll=…&trackingMode=2` URL；两边最终的 Maps 稳定截图都显示相同地图区域和定位蓝点，证据位于 `cases/compass-maps-url-comparison-v2-20261015/` 并通过哈希校验。这样验证了当前授权位置的地图请求与可见目的地；权限拒绝、其他位置和 Maps 内部语义仍待测。Compass 最新深入报告为通过校验的 `cases/compass-xr-deep-report-v11-20261015/`。
REA/Ghidra 进一步串起原版定位授权变化、开始/停止更新、设置空位置、坐标隐藏和地名清空六个函数。静态证据支持拒绝或受限时隐藏坐标/海拔并清空地名；复刻版据此改掉了错误的“Location permission required”占位文本。新包通过 TrollStore 安装后，已授权状态下的坐标到 Maps 脚本再次在 XR 上通过，见 `cases/compass-location-empty-maps-regression-20261015/`。随后在 XR 上临时把原版与复刻版定位权限各设为 Never；两者都隐藏了位置字段，但复刻版初始纵向布局有差异。修复后，原版/复刻版灰色中心盘的纵向像素范围为 315–394/314–395，方位大字为 679–728/680–728。`cases/compass-location-denied-comparison-20261015/` 保存了修复前后截图和权限恢复证据，并通过哈希校验；两款 App 的权限已恢复为使用期间。原版最新 `cases/compass-xr-deep-report-v14-20261015/` 已纳入拒绝权限的真机界面。
最新方位锁定成对对照位于 `cases/compass-bearing-sector-comparison-20261015/`，原版与复刻版的红色像素计数分别为 `0→146→0`、`0→57→0`；两者均通过指定的颜色先升后降检查，图像和报告哈希也已校验。该检查不声称扇区形状已经对齐。

源码已知的 `fixture/CopyAppFixture` 已在 Xcode 27 构建出 iOS 16 部署目标的 App、动态 Framework 和分享扩展，包含 SwiftUI/UserDefaults、UIKit/SQLite 和模拟目录三条流程。XR 上用 TrollStore 安装、iOS MCP 操作，三流程的页面和状态均已实测；计数器偏好设置、笔记数据库、Frida 调用、Framework 调用以及从 XR 导出主程序的 REA/Ghidra 函数证据已核对，详见 `docs/fixture-xr-validation.md`。`copyapp install` 现将传输、哈希校验、TrollStore 安装与安装记录核对合成一条命令，并在 XR 更新夹具后成功启动。`copyapp report` 已将 Compass 和夹具的静态索引、REA 函数、Frida 实验、UI 和数据证据组合成带引用的深入报告及复刻规格，并验证证据身份和文件哈希；结构化功能结论目前由 agent 审阅撰写，尚非 `analyze` 一次命令自动推断。REA/Hopper 已在正常 macOS 用户会话中对 XR 导出的分享扩展完成函数反编译，并进入夹具报告；旧受限环境超时记录及运行边界见 `docs/rea-hopper-integration.md`。iOS 17/26 兼容仍未验收。

## 11. 待确认的测试输入

1. 第一款实际目标 App 及其三条代表性流程。
2. iPhone 14（iOS 17.3.1）和 iPhone 11（iOS 26.0.1）的越狱工具、bootstrap 类型及实机连接状态；这决定 M0/M1 的具体兼容性工作量。XR 是 iOS 16.1.1，Dopamine rootless。
3. 复刻时允许使用的品牌与素材范围，以及是否有可用的测试账号/后端环境。

当前试点 App 为 Compass，三条流程为实时航向、方位锁定、位置与地图。第三方目标和复刻素材范围可在这个试点闭环验收后再选。

2026-10-15 范围更新：用户暂缓 iOS 17 和 iOS 26 两台手机的验收，继续使用越狱 iPhone XR 测第二个系统 App Calculator。`cases/calculator-xr-deep-report-v3-20261015/` 已将完整采集、稳定的 `7 + 8 = 15` 脚本、REA/Hopper/Ghidra 方法分析、动态按钮 ID 与可访问性替换层的双入口探针，以及 `CalculatePerformExpression` 的真实表达式 `(7)+(8)` 和输出 `15` 汇总为可校验报告。`docs/calculator-feature-spec.json` 给出竖屏首页和基础加法两条复刻流程；横屏、其他运算及私有框架内部算法仍待分析。长期跨系统验收要求保留，当前不启动。

Calculator 的独立复刻版现也在 XR 上形成 Analyze→Rebuild→Compare 闭环：`rebuild/CalculatorClone/build/dist/CopyAppCalculator.ipa` 0.1.2 (3) 经 TrollStore 安装并启动，同设备同 iOS MCP 后端的九步原版/复刻版脚本均完成；`cases/calculator-basic-comparison-v4-20261015/` 的清除和结果截图分别有 0.00829、0.00883 平均 RGB 绝对差，并通过 `copyapp verify`。具体取证与仍未覆盖的路径见 `docs/calculator-xr-rebuild-verification.md`。

Calculator 发现的辅助功能层替换当前 IMP 问题已转成通用能力：`copyapp experiment --binary ... --objc-index ...` 在同一次点击中分别记录当前 Objective-C IMP 和 App 本体静态入口，并按二进制哈希、索引、加载模块路径及偏移核对。XR 实测数字 7 让两处入口各命中 1 次；`copyapp candidates` 保留当前 IMP 冲突，同时凭独立静态入口命中恢复 `buttonPressed:` 的精确 REA 候选。`cases/calculator-static-entry-candidates-20261015/` 通过 `copyapp verify`，60 项本地测试通过。该结果推进 M3/M6 的跨 App 复用，但尚不等于一条自然语言命令自动完成深度报告和复刻；iOS 17/26 继续暂缓。

在同一 XR 上又对 Calculator 采集了 `100 + 10%` 和 `5 + 2 = =` 的原版脚本，分别观察到 `10→110` 与 `7→9`；两条路径的复刻版基线为 `100.1` 与 `7`，据此修正状态转换。独立复刻 App 0.1.3 (4) 经 TrollStore 更新后，同设备同 iOS MCP 后端的两组成对对照通过；原有 `7 + 8 = 15` 回归也通过。`cases/calculator-xr-deep-report-v6-20261015/` 已纳入四条规格流程及完整脚本证据，`copyapp report` 现在会在导入 playbook 目录时核对其身份、截图就绪状态和证据哈希；`copyapp ocr-file` 可对保存截图生成带源哈希的 OCR 文件，报告导入时还要求源截图同批纳入并重新核对裁剪输入哈希。百分比截图的两端显示区 OCR 都得到 `10`/`110`；重复等号的细线 `9` 以截图核读，Vision 未稳定识别。其余运算和科学模式、M6 的一句话自动编排仍需完成；iOS 17/26 继续暂缓。

通用 `copyapp view-tree` 现可在目标 App 前台以 Frida Objective-C bridge 读取当前 UIKit 窗口、父子关系、frame、标签文字和可访问性属性，并保存扫描脚本与截图供哈希核对。XR 上原版 Calculator 扫出 1 窗口、47 节点，复刻版 1 窗口、43 节点；原版 DisplayView 的子 UILabel 可直接读出结果，补上无障碍树及 OCR 对细线 `9` 的缺口。两边重新运行重复等号脚本后，各自的运行时显示 UILabel 均为 `9`。`copyapp report` 导入视图树时会校验设备、App、前台、节点结构与证据文件；`cases/calculator-xr-deep-report-v7-20261015/` 已加入这组证据。扫描仅覆盖当时已加载的 UIKit 子视图；隐藏页面与跨系统行为仍待验证。

视图扫描又增加 `--no-launch`，用于完成操作脚本后要求目标仍在前台并直接读取当前页面；XR 上复刻版结果屏幕用该模式再次读到 UILabel `9`，证据 `cases/calculator-clone-view-tree-no-launch-20261015/` 通过校验。Calculator 报告 v8 改用紧邻原版视图扫描的脚本重放案例 `cases/calculator-repeat-original-v2-20261015/`，缩小“截图与视图状态属于不同运行”的不确定性。

同一 `view-tree` 又在已知源码夹具的 SwiftUI Counter 页实测：`_UIHostingView<CounterView>` 与绘制层可见于 40 节点 UIKit 树，但计数内容不对应 UILabel。工具现同时保存 iOS MCP/iCTRL 可用的无障碍树；XR 的 `cases/fixture-swiftui-counter-view-tree-v2-20261015/` 给出 `Counter: 4`、Increment 与 Reset 文案，完整证据通过校验并进入夹具深度报告 v8。这验证了工具在 UIKit 与 SwiftUI 两种实现上的取证边界，不能把 SwiftUI 的 UIKit 子树当成完整语义树。

`copyapp flow-capture` 现把一条 UI playbook 和紧随其后的无重启视图扫描组合成单个哈希证据案例，校验设备/App/后端、脚本哈希、顺序和 60 秒内的时间窗口；失败会保留已完成的子阶段且不会在脚本失败后继续扫描。XR 原版 Calculator 与独立复刻版的 `5 + 2 = =` 均已用此命令完成，末端显示标签同为 `9`，两份父案例、成对截图对照和 Calculator 深度报告 v9 均通过校验。这推进 M3/M6 的跨流程自动化，但还需要把函数跟踪、REA 选择与结论撰写编排起来。

同一 `flow-capture` 现在可选 `--method` 与匹配的 `--binary`/`--objc-index`，在每次点击窗口统计当前 Objective-C IMP 与已采集主程序静态入口。XR 系统 Calculator 的六次点击各命中两个入口 1 次，原版 `5 + 2 = =` 最终视图树读到 `9`；`cases/calculator-repeat-traced-flow-original-20261015/` 的三阶段证据与深度报告 v10 均通过校验，67 项本地测试通过。此能力推进 M3/M6 的 UI→代码关联，但仍需自动选择目标方法、REA 解释与特征规格生成；iOS 17/26 按用户要求暂缓验证。

`candidates --flow` 已能把上述完整流程的六次点击自动变成一个带步骤来源的静态函数候选，保留辅助功能 IMP 与主程序入口偏移冲突。`rea-queue` 又对候选文件和精确二进制进行哈希校验，按观察次数排序并限定函数数目；XR Calculator 候选 `0x10000eb0c` 已由 Ghidra 12.1.4 自动分析，Evidence ID `ev_2c41c7ba72cef7da1bb2a7d59d34a9f08ad2ff7730628d07c3b966f889721b47`，队列及所有嵌套来源文件通过校验。失败会停止后续函数并保存失败结果。此链路仍需要 agent 审阅桥接后的函数体、撰写结论及生成规格，尚未达到完整一句话复刻。

`copyapp report` 又增加整条 `rea-queue` 的导入校验：不仅核对外层文件哈希，还重新核对内嵌候选案例、设备/App/二进制身份、所选地址以及每个 REA Evidence ID、provider 和伪代码。Calculator 深度报告 v12 已纳入该完整队列。该机制使“点击→候选地址→反编译证据”的选择链可审阅，仍不代替对函数语义的人工或 agent 解释。

新增 `copyapp investigate-flow` 将已验证的分析案例和 UI 脚本一命令接到方法选择、真机操作/Frida、候选绑定与 REA。方法选择只在一个动作入口明显领先时自动执行，否则在触屏前产出候选清单供 agent 选择；已解密 IPA 的主程序可按精确成员与哈希提取，未解密磁盘主程序拒绝直接分析。XR Calculator 的完整命令案例 `cases/calculator-one-command-investigation-20261015/` 通过 58 个嵌套文件哈希校验：自动选中 `buttonPressed:`，六个点击窗口两处入口各命中一次，结果 UILabel 为 `9`，Ghidra 给出同一地址的 Evidence ID。DeepSeek 已解密分析包的主程序也在本机从 IPA 提取并匹配 ObjC 索引。`review-brief.md` 仅列事实和下一步解释边界；自动撰写完整报告/规格、跨流程关联和一句话复刻仍未完成。

报告导入器可把一命令调查作为单个证据组，重验父清单与 UI 流程、方法选择、候选、REA 队列的跨阶段身份和哈希。Calculator 深度报告 v13 已引用整案，实测可复核；这减少了 coding agent 拼接证据的手工步骤，但尚未自动理解深层函数和生成独立 App。

XR 上第二个一命令案例使用源码已知的 SwiftUI 夹具 Counter：方法侦察把 `showCounter`、`showNotes` 等低分入口列出并在触屏前请求选择；显式选择 `showCounter` 后，入口点击窗口当前 IMP 和主程序静态入口各命中一次，Increment 窗口两者均为零、界面计数 4→5。一次候选格式问题后，`investigate-flow --resume` 复用已采集 UI/Frida 阶段并完成 Ghidra 队列；父案例和导入它的夹具报告 v9 均已校验。报告仍需 agent 做深层语义解释；该验证不覆盖 iOS 17/26。

方法侦察进一步用各次 `tap_label` 的可见文案与 Objective-C 操作方法后缀做唯一匹配；XR 夹具 Counter 无需手动选择已重跑成功。Notes 脚本的两个点击自动选择 `showNotes` 和 `addNote`，两步的当前 IMP 与静态入口计数分别为 `[1,0]`、`[0,1]`，界面 `Saved notes: 5→6`；两处入口都完成 Ghidra 分析，整案和夹具深度报告 v10 校验通过。此启发式只给候选，仍需动态命中与函数分析支撑解释。

`copyapp rea-bridge` 现能从已验证的 REA 候选队列自动跟踪唯一的本地匿名函数，限制深度与数量，遇到分支歧义保存全部候选并停止选择。Calculator XR 的真实队列自动得到 `0x10000eb0c → 0x10000e9b8`，后者列出 10 个分支；整个来源队列、Ghidra 函数证据和决策图已校验并进入深度报告 v14。下游分支仍需根据运行时按钮 ID 与伪代码作语义判定，不能由静态边单独声称某次点击执行了某分支。

夹具第三条 Catalog 流程同样通过自动入口选择：XR 点击 `Catalog · Framework` 时 `showCatalog` 的当前 IMP 与静态入口各命中一次，随后 UI 显示 Alpha/Beta 两条样例；Ghidra 函数地址 `0x1000057c0`。Counter、Notes、Catalog 三条一命令调查都已完成并由夹具深度报告 v11 统一导入，推进 M3 的三流程证据链验收。复刻规格与深层函数语义仍由 agent 解释，不能把三条证据链等同于完整 App 复刻。

新增 `copyapp investigate-app` 以一条命令顺序执行同一分析案例的多份 playbook，父清单绑定分析索引、设备、App、脚本哈希及子案例；`--resume` 重验后跳过已完成流程。XR 夹具 Counter、Notes、Catalog 三条流程已在一条任务中全部完成，父案例登记 193 项文件。报告器重验三个子调查后以单个 `app.all` 证据 ID 导入夹具深度报告 v12。此项推进 M6 编排，但 agent 仍需解释函数含义、产出功能规格并驱动独立复刻与对照。

M5 的多流程对照现由 `copyapp rebuild-check` 编排：规格 ID、成对脚本语义动作及已安装版本在触屏前固定，逐条运行、比较和复核版本，失败时可从验证过的完整子流程续跑。XR Calculator 原版 1.0.0 (1.0) 与独立复刻版 0.1.3 (4) 的三条选定流程一次运行完成，6 张成对截图分别覆盖清除/加法、百分比中间/结果、两次等号；`cases/calculator-xr-rebuild-check-20261015/` 的父案例和所有比较证据通过哈希校验，图片审阅确认对应显示值为 `0→15`、`10→110`、`7→9`。逐流程显式视觉检查仍为 `unreviewed`，图片审阅不证明其他运算或完整 App 等价；iOS 17/26 按用户要求继续暂缓。

新一轮将规格中的 `final_view` 文本/屏幕区域断言接入同一多流程入口：每侧都用 `flow-capture` 在脚本之后读取未重新启动的 UIKit 树，检查显示区域恰有一个可见且完全匹配的 `UILabel`，再比较原始脚本截图。XR 上 `cases/calculator-xr-rebuild-check-with-view-20261015/` 三条流程一次完成，原版与复刻版的末端标签各自给出 `15`、`110`、`9`，位置分别落在屏幕约 y=220 与 y=225；有界区域排除了键盘上的 `9`。127 项案例文件哈希校验通过。这比图片人工核读增加了可重验的结构化结果，但只验证三个时点的 UIKit 文本；百分号中间值、动画、长数字和其他运算仍需专门断言或实验。

Analyze 侧新增 `copyapp draft-analysis`：先重验完整 `investigate-app` 的分析索引、设备/App、三条脚本、Frida、候选与 REA，再自动组织只含直接事实与未知项的 `findings.json`、待审 `feature-spec.json`、审阅清单及带原始证据的草稿报告。夹具的三流程案例通过 210 文件校验；真实 Calculator 在 XR 上又完成加法、百分比、重复等号三条一命令调查，父案例 180 项证据，自动草稿 197 项文件，均通过校验。三条末端 UIKit 标签依次为 `15`、`110`、`9`，工具仅将其作为上半屏候选列出；`review_status=needs_semantic_review` 阻止草稿规格进入 `rebuild-check`。该能力减少事实汇编工作，尚未自动解释下游函数语义、数据流与完整复刻规则，M3/M6 的深度解释关卡仍需 coding agent 审阅完成。

Calculator 的人工审阅结论现与新的三流程整案合并为 `cases/calculator-xr-deep-report-v15-20261015/`：沿用既有 UI、沙盒、Hopper/Ghidra、Frida 与 REA 桥接证据，新增 `app.all` 180 项来源及两个直接观察结论。报告含 41 组证据、397 个复制/生成文件，`copyapp verify` 通过；`docs/calculator-feature-spec-v2.json` 的三条计算流程均引用这次整案，并保留已有的末端 UIKit 数值断言。自动事实草稿与经语义审阅的深入报告分开保存；这满足 XR 上该试点的三流程取证解释，但未证明所有 Calculator 功能，也不代替任意 App 的自动语义分析。

后续 XR Calculator 已加入 C/AC 分流的 Ghidra 与 Frida 证据、`C → 0 → = → 8` 原版行为，并将独立复刻版更新至 0.1.5 (6)；四条所选流程在同版原版/复刻版末端 UIKit 文字断言均通过，深度报告为 `cases/calculator-xr-deep-report-v16-20261015/`。`copyapp branch-map` 现可离线重验多份流程的来源哈希、设备/App/二进制归属和点击计数，合并原始第 3 参数与已选分支入口。XR 四流程的 27 个点击窗口产出 `cases/calculator-button-branch-map-20261015/`；清除键及一处数字点击涉及多入口，保留原始命中而不自动断言单一实现。此项推进 M6 的证据整理，自动解释函数语义、自动生成完整复刻 App 与跨 App 泛化仍未完成。

`copyapp report` 已把 `branch-map` 作为可引用的结构化证据：导入时从已钉住的来源流程重新计算参数与分支映射，核对目标 App、设备及主程序哈希，再把流程、二进制与重放来源索引保存在报告证据包。Calculator 的 `cases/calculator-xr-deep-report-v17-20261015/` 包含 51 组证据、546 个文件；`copyapp verify` 通过。从报告内副本重跑得到相同的 27 条观察与映射。`docs/calculator-feature-spec-v4.json` 与真机验收所用 v3 的流程要求相同，仅更新报告来源。自动语义解释与跨 App 自动复刻仍需推进。

Rebuild 侧新增 `copyapp rebuild-plan`：读取已校验的深度报告及已审阅规格，只从该规格引用的原版 playbook/flow-capture 选输入，复制原版脚本并仅替换复刻 Bundle ID，提前运行 `rebuild-check` 的成对结构检查；有 `final_view` 时用来源流程末端 UIKit 文本区分相似脚本。XR Calculator 的 `cases/calculator-rebuild-plan-v1-20261015/` 自动形成加法、百分比、连续等号和 C 后等号四对脚本；首页没有被引用的原版 playbook，明确留作待补。生成脚本尚不等于独立 App 的实现或实际真机对照，一句话自动复刻的代码生成与迭代仍未完成。

上述自动计划的四对脚本已在 XR 真机执行。首轮 `cases/calculator-generated-plan-rebuild-check-20261015/` 虽通过数字 15、110、9、8 的末端断言，截图审阅发现原版 `C→=→8` 后清除键为 AC，而复刻版 0.1.5 (6) 为 C。规格 v5 扩展 `final_view.also`，以精确文本和按钮区域同时断言清除键；旧证据离线重验为原版通过、复刻版失败。独立复刻版修正等号后清除键状态并更新至 0.1.6 (7)，TrollStore 安装在 XR。报告 v18 生成的 `cases/calculator-rebuild-plan-v2-20261015/` 四对脚本再跑 `cases/calculator-generated-plan-rebuild-check-v7-20261015/`：原版/复刻版四条流程的数字与 C/AC 末端断言全部通过，八组截图和案例哈希验证通过。首页 playbook、更多输入状态及视觉差异仍未完成；iOS 17/26 按用户安排继续暂缓。

XR 又采集 `cases/calculator-initial-flow-original-20261015/`：首页按 AC 后末端 UIKit 显示 `0+AC`，并通过哈希校验。`cases/calculator-xr-deep-report-v19-20261015/` 与规格 v6 将该首页流程纳入证据和精确断言。`cases/calculator-rebuild-plan-v3-20261015/` 从报告自动配出全部五对脚本、没有待补项；在 XR 运行的 `cases/calculator-five-flow-rebuild-check-v7-20261015/` 固定原版 1.0.0 (1.0) 和复刻版 0.1.6 (7)，双方首页、加法、百分比、连续等号、C 后等号的数字加清除键状态断言全部通过，九组截图及案例哈希验证通过。这完成 Calculator XR 选定流程的报告→脚本交接→真机复核，但不是任意 App 一句话自动生成源码；未测输入、完整页面与像素差仍为缺口。

Compass 迁移验证：`cases/compass-xr-deep-report-v16-20261015/` 将首页、方位锁定、跳转 Maps 三条已完成的原版 UI 流程纳入证据；`cases/compass-rebuild-plan-v1-20261015/` 自动配出全部三对脚本，零待补。XR 真机对照尚未完成：首页观察步骤能读到角度符号，但稳定截图后对无障碍内容的就绪检查连续五次未读到该符号，案例 `cases/compass-generated-plan-rebuild-check-v2-20261015/` 记录了失败。此处不算复刻回归；需先查明 Compass 的截图后无障碍快照行为，再继续三流程对照。

Compass 后续排查证明重复截图可使 iOS MCP 的无障碍文本暂时为空，尽管截图仍显示角度。Playbook 的截图就绪和观察步骤现可回退到 Mac Vision OCR，并把 OCR 输入哈希与截图绑定；真机完成案例含此回退证据。截图审阅又发现复刻版锁定角度标签与邻近刻度数字重叠，现已修正。`cases/compass-xr-deep-report-v18-20261015/`、`cases/compass-rebuild-plan-v3-20261015/` 和 XR 上的 `cases/compass-three-flow-rebuild-check-v4-20261015/` 组成三条流程的报告→脚本→复刻对照闭环，复刻版 0.1.3 (4)，案例哈希校验通过。实测锁定状态的红色线条随采集亮度变化，不把颜色脉冲当作确定性通过条件；三条流程的视觉判定仍是 `unreviewed`，剩余动态状态、完整 UI 和通用源码生成未完成。iOS 17/26 仍按用户要求不验证。

Agent 交接新增 `copyapp agent-task`：读取已校验的深入报告和 `rebuild-plan`，重新核对报告/规格哈希、每条来源 playbook、复刻脚本只改 Bundle ID，以及成对脚本预检，生成含原始 UI、REA、实验路径及真机命令的 `TASK.md`、`task.json` 和哈希清单。XR Compass 三流程与 Calculator 五流程的交接包分别为 `cases/compass-agent-task-v1-20261015/`、`cases/calculator-agent-task-v1-20261015/`，均显示输入就绪。这减少 Coding Agent 从报告手动找证据的工作，但尚未自动调用 Agent、生成复刻源码或证明任意 App 的全功能复刻；这些仍是 M6 的缺口。

独立命令入口新增 `copyapp agent-run`，支持已安装的 Codex CLI 或 Claude Code。启动前重验 `agent-task` 及其报告/计划来源，拒绝只选部分流程的任务或仓库外工程路径；Codex 使用 workspace-write 与自动审批审查，Claude Code 使用 auto 权限模式，均不开放绕过审批的选项。运行记录保留命令、stdout/stderr、会话 ID 和来源任务哈希；CLI 成功退出仅标记 `agent_exited_unverified`。两种提供者的真实任务 dry run 和假 CLI 执行测试已完成，但尚未在此路径实际运行外部模型并验证自动生成源码，不能据此宣称一键复刻完成。在当前 Codex 会话中应直接按任务实施，避免递归启动 Agent。

交付核验新增 `copyapp agent-delivery`：重验完整 Agent 任务、同一设备上的 TrollStore 安装记录和 `rebuild-check` 案例，绑定当前源码树与 IPA 哈希、安装版本以及每条脚本/比较索引。XR 上 Compass 的 `cases/compass-agent-delivery-v1-20261015/` 结果为三条流程执行通过但视觉未审；Calculator 的 `cases/calculator-agent-delivery-v1-20261015/` 为五条末端行为断言通过但视觉未审。两份交付均无独立 `agent-run` 记录，不宣称这些已有源码由外部 Agent 自动生成。该命令为后续自动循环提供可验收的停止条件，但任意 App 的源码生成、完整页面覆盖和动态视觉判定仍未完成。

交付案例 v2 进一步封存生成当时的源码 tar 与安装 IPA，使工程后续更新不会破坏旧版交付的复核依据。`cases/compass-agent-delivery-v2-20261015/` 和 `cases/calculator-agent-delivery-v2-20261015/` 的外部任务、对照、安装记录及内部源码/IPA 快照均通过 `copyapp verify`。源码快照的内容哈希在不解包执行的前提下重算；此归档证明交付时保存了哪些字节，不证明其知识产权状态或全功能实现。

Analyze 交接新增事实草稿内的 `TASK.md`/`task.json`：把每条已调查流程的原版脚本、末端视图/截图、逐点击追踪及已生成的 REA 伪代码直接链接给当前 Coding Agent，列出正式 findings、可执行规格、深入报告与未知项的完成条件。`copyapp verify` 对新版草稿重验源分析、源调查、草稿报告和脚本哈希。夹具三流程 `cases/fixture-auto-draft-v4-20261015/` 和真实 Calculator 三流程 `cases/calculator-auto-draft-v3-20261015/` 均已生成并通过校验。这一步减少证据转交操作；函数语义解释仍由 Agent 完成，未证明任意 App 自动生成报告或完整复刻。

`copyapp agent-run` 现可接受上述深度分析审阅任务，也可接受既有复刻任务。两类任务均先验证来源；分析任务只传送已钉住的证据和正式报告要求，不创建复刻工程源码快照。真实 Calculator 草稿分别完成 Codex 与 Claude Code 的本地 CLI dry run，案例为 `cases/calculator-analysis-codex-run-dry-20261015/`、`cases/calculator-analysis-claude-run-dry-20261015/`，两者的任务归属和哈希校验通过。尚未实际启动独立 Agent 解释语义，也未自动验收其报告；在当前 Codex 会话中继续直接执行审阅任务，不嵌套启动 Agent。

分析交付新增 `copyapp analysis-delivery`：通过原版 playbook 哈希而非易变的流程名称，把新版深度报告的每条规格绑定到 `draft-analysis` 的调查任务；拒绝缺失流程、原样待审预期、不同 App/原始分析/调查来源和过期报告。XR Calculator v20 从此前审阅的 v19 结论及 43 组原有证据重新封装，三条调查流程经脚本哈希全部映射，并在 `cases/calculator-analysis-delivery-v1-20261015/` 保存报告、规格、结论快照与核验记录；两个案例均通过 `copyapp verify`。该门槛只证明来源、覆盖和文件一致性，不能证明功能解释正确，也未运行独立 Codex/Claude 语义审阅。

从上述 Calculator v20 正式报告继续生成 `cases/calculator-rebuild-plan-v4-20261015/` 和 `cases/calculator-agent-task-v2-20261015/`：五条规格流程均有匹配原版脚本，0 项证据缺口，任务状态 `ready_for_agent`。该任务又与已安装的 XR 复刻版 0.1.6 (7) 和此前保存的五流程真机对照组成 `cases/calculator-agent-delivery-v3-20261015/`；整条新交接链的案例哈希验证通过，5/5 末端行为断言通过，5/5 视觉检查仍未审。这复用了原有真机对照，没有重新执行设备触控，也未证明源码由独立 Agent 自动生成或整个 Calculator 等价。

视觉侧新增 `copyapp visual-audit`，从已校验的 `rebuild-check` 读取全部成对截图，在声明且覆盖至少半屏的 ROI 内计算归一化 RGB 平均差及单像素差异比例，保存来源图像哈希；`copyapp verify` 会重算。XR Calculator 五流程的 9 对图片在 `[0,80,414,820]` 区域、平均差上限 0.015 和差异像素比例上限 3% 下均落入阈值，最大值分别为 0.01122 与 2.069%；见 `cases/calculator-five-flow-visual-audit-v1-20261015/`。阈值为看过既有截图后设置的事后诊断，未升级原对照的 `unreviewed` 状态，也未证明其他界面、动态状态或完整视觉等价。

Calculator 继续扩展四条真机运算流程：除零、小数加法、正负号加法和乘法。`docs/calculator-feature-spec-v7.json` 在原五流程基础上补充直接观察的末端行为；`cases/calculator-edge-rebuild-check-v1-20261015/` 对原版与复刻版各自重放并直接读取末端 UIKit 视图树，四条流程的双边精确文本断言均通过，案例哈希已验证。9 对截图的差异指标见 `cases/calculator-edge-visual-audit-v1-20261015/`，视觉状态仍未审。详细范围和观察差异见 `docs/calculator-edge-xr-verification.md`；这些新增流程尚未进入方法级逆向深度报告，不能据此声明整款 Calculator 已复刻。

为消除显示区和零键均标为 `0` 的自动点击歧义，`tap_label` 新增可选矩形区域筛选，`rebuild-check` 和 `compare-playbooks` 会拒绝不一致的成对区域；保存的点击中心也受区域复核。`docs/calculator-feature-spec-v8.json` 采用两份区域化脚本，`cases/calculator-decimal-region-rebuild-check-v1-20261015/` 已在 XR 原版与复刻版各执行两次零键，点击中心均为 `(108,779.5)`，末端 UIKit `0.3` 双边断言与案例哈希通过。

iCTRL 区域化标签路径从当前 App 的可见元素树筛出区域内唯一可操作元素，以精确 Bundle ID 与元素类型取得并复核引用。`flow-capture` 的 iCTRL 脚本和末端 UIKit 扫描改为共用一个 USB 会话，避免第二次唤起 runner 把目标 App 切到后台。`cases/calculator-decimal-region-ictrl-rebuild-check-v1-20261015/` 保留首轮视图扫描失败记录，并在 `--resume` 后完成原版/复刻版四次零键引用点击、双边 `0.3` UIKit 断言及哈希校验。全套 134 个本地测试通过。

Calculator 的四条新增原版流程又以 Frida 同时记录 `buttonPressed:` 当前 IMP、主程序静态入口、原始按钮参数和五个已定位下游偏移；乘号 6、除号 5 命中运算符入口，正负号 3、小数点 10 命中另一入口，末端 UIKit 分别为 63、Error、3、0.3。四份 `flow-capture` 加入 `cases/calculator-xr-deep-report-v21-20261015/`，该报告含 56 组来源、九条机器可读流程；`analysis-delivery-v2`、`rebuild-plan-v5`、`agent-task-v3` 均通过校验，计划为 9/9 原版脚本就绪。XR 统一 `rebuild-check-v1` 的九条末端断言均通过，`agent-delivery-v4` 绑定已安装 0.1.6 (7) 的源码和 IPA；18 对截图的区域指标在先前阈值内，但九条显式视觉状态仍未审。详见 `docs/calculator-edge-xr-verification.md`。

M6 的分析入口新增 `copyapp prepare-analysis`：以已校验的原始分析和 1–12 条原版脚本为输入，先预检 REA provider，再可恢复地串行运行 `investigate-app` 与 `draft-analysis`，状态停在 `needs_semantic_review`。XR Calculator 一条新流程实际跑过 UI/Frida，REA CLI 未配置及 JDK 路径错误的两次失败队列均留在 `attempts/`；修正路径后续跑只重做 REA 并生成新的审阅任务，`cases/calculator-preparation-live-20261015/` 哈希核验通过。既有三流程调查也经复用模式生成 `cases/calculator-preparation-reused-20261015/`，重复 `--resume` 时草稿哈希不变。完整语义解释、独立 Agent 自动执行、复刻交付与三系统验收依然各自需要证据。

复刻任务的范围门槛已允许有意选择报告子集：`selected_flows_ready` 可以交给 Codex/Claude Code，执行记录保留所选与未选 ID；`agent-delivery` 可以从覆盖更多流程的同版真机对照中抽取任务内结果，并明确列出未选和额外检查的流程。Calculator v21 的九条报告流程中选取加法、百分比和重复等号三条，生成 `cases/calculator-selected3-plan-20261015/`、`cases/calculator-selected3-task-20261015/`、`cases/calculator-selected3-codex-dry-20261015/` 与 `cases/calculator-selected3-delivery-20261015/`，四份案例均通过哈希及来源校验。3/3 末端行为断言复用既有 XR 对照，视觉未审；Codex 仅做 CLI 预演，未声明独立 Agent 自动生成源码。

Calculator 又通过 Frida 读取原版与复刻版 UILabel 的实际字体名和字号，发现原版结果区是 `.SFUI-ThinG2` 93pt、标签高 111pt，旧复刻是公开 Thin 100pt、标签高 100pt；函数/数字/运算键也有字重字号差。直接按私有字体名创建会在 XR 回退成 Times New Roman，故最终采用公开系统字体并按保存截图调结果标签几何。当前独立复刻 0.1.10 (11) 已安装至 XR，`cases/calculator-nine-flow-rebuild-check-v11-20261015/` 的 9/9 末端断言通过；18 对截图相同区域的归一化 RGB 差均值由旧版 0.008513 降到 0.003665，最大值由 0.013639 降到 0.004556，`cases/calculator-nine-flow-visual-audit-v11-20261015/` 和 `cases/calculator-agent-delivery-v11-20261015/` 均通过校验。字形细节、动态状态及未覆盖页面仍需验证，详见 `docs/calculator-typography-xr-review.md`。

复刻交接新增 `copyapp prepare-rebuild`，从已审阅的深度报告一次生成带来源哈希的计划和 Agent 任务，可指定 1–12 条流程并以 `--resume` 复用已验证阶段，损坏阶段存入 `attempts/`。`cases/calculator-rebuild-preparation-20261015/` 使用 Calculator v21 报告选择三条代表流程，状态 `selected_flows_ready`，案例及来源核验通过；重复续跑保持计划和任务哈希不变。它只缩短报告到任务的人工拼接，源码实现、真机验证和独立 Agent 执行仍按交付门槛分别证明。

视觉交付新增 `copyapp visual-review`：逐张绑定原版、复刻版及并排截图的哈希，要求每对截图都有审阅判断和具体说明，`agent-delivery --visual-review` 可引用它并单独记录主观审阅状态。Calculator 0.1.10 的九流程 18 对截图已全部逐图看过，`cases/calculator-nine-flow-visual-review-v11-20261015/` 记录 ± 字形、数字笔画和顶部系统文字的轻微差异；`cases/calculator-agent-delivery-visual-reviewed-v11-20261015/` 状态为 `selected_behavior_verified_visual_reviewed_with_differences`，9/9 行为断言通过、0/9 未审流程、9/9 流程有轻微差异。两份案例及引用来源均通过哈希校验；人工判断的真伪不能由哈希证明，且动态画面和未测功能仍未覆盖。

上述视觉审阅也接到 `prepare-rebuild` 新生成的 Calculator 三流程任务：`cases/calculator-prepared-selected3-reviewed-delivery-20261015/` 重验了同版源码、IPA、安装和九流程真机对照，所选 3/3 末端行为断言通过，所选截图均有逐图结论，其余六条流程列为任务外范围。该案例通过 `copyapp verify`，证明报告到新任务再到现有设备交付的来源链可接通；它复用原有复刻源码，仍未证明独立 Agent 从零自动实现。

第二技术栈试点使用已知源码夹具验证从分析报告到独立实现的可复用性。旧夹具脚本没有 `scenario_id` 和截图就绪条件，首次 `prepare-rebuild` 在预检中正确拒绝；补齐后在 XR 重新采集 SwiftUI Counter、UIKit/SQLite Notes 和 Framework Catalog 三条完整原版流程。`cases/fixture-xr-deep-report-v14-20261015/` 引用新证据并指定 `dev.copyapp.fixtureclone`，`cases/fixture-rebuild-preparation-v2-20261015/` 的三条复刻任务均为 `ready_for_implementation`，整体状态 `ready_for_agent`，无脚本缺口。独立 `rebuild/FixtureClone` 通过 Xcode 编译、IPA 包检查和 XR TrollStore 安装；`cases/fixture-three-flow-rebuild-check-v1-20261015/` 的三条原版/复刻版脚本均完成。交付器新增操作后脚本断言统计，使 SwiftUI 数值增量和 Catalog 文本可被独立计数；`cases/fixture-clone-agent-delivery-v1-20261015/` 记录 3/3 行为断言通过。重启复刻版后 Counter 1→2、Notes 1→2，沙盒元数据出现 SQLite 和偏好设置文件，IPA 内含 CloneCatalogCore Framework。五对截图的审阅把 Counter/Notes 原版与复刻版既有数据基线不同标为两条流程的重大视觉差异，Catalog 为轻微顶部系统文字差异；没有声明视觉等价。详见 `docs/fixture-clone-xr-verification.md`。独立外部 Agent 的自动源码生成、分享扩展、完整数据内容与 iOS 17/26 仍未验证。

复刻对照新增 `copyapp rebuild-task-check --task <TASK_CASE> --out <CASE>`：从已验证的任务读取确切设备、报告来源、计划、后端和选定脚本，在触屏前核对报告原件与计划副本的内容及来源哈希。首次预检发现计划的 JSON 重新序列化会改变文件哈希，修正后比较脚本内容并分别验证原件哈希；XR 上 `cases/fixture-three-flow-rebuild-check-v2-20261015/` 通过新入口完成 Counter、Notes、Catalog 三条对照及案例核验。[重新生成的夹具任务 v3](cases/fixture-rebuild-preparation-v3-20261015/task/TASK.md)已经优先展示短命令，保留展开后的长命令供审查，案例核验通过。

新入口的真机对照继续生成 `cases/fixture-three-flow-visual-review-v2-20261015/` 和 `cases/fixture-clone-agent-delivery-v2-20261015/`，来源、截图和交付哈希均核验通过。三条操作后断言再次通过；Counter 原版 10→11、复刻版 2→3，Notes 原版 10→11、复刻版 2→3，基线差异仍记为两条流程的重大视觉差异。短命令已证明可接入交付，但尚未让不同 App 的既有数据自动对齐。

第三轮 XR 验证先读出 Counter/Notes 原版 11、复刻版 3，再只用复刻版现有 UI 各补 8 次，原版数据保留不动；补齐的脚本和案例保存在 `cases/fixture-baseline-alignment-v1-20261015/`。`cases/fixture-three-flow-rebuild-check-v3-20261015/` 重新确认双方均为 11→12，Catalog 文字一致；`cases/fixture-three-flow-visual-review-v3-20261015/` 逐审五对图片，全为顶部系统文字、时间及轻微间距差异；`cases/fixture-clone-agent-delivery-v3-20261015/` 记录 3/3 行为断言通过、0 重大视觉差异、0 未审流程。三个案例均通过 `copyapp verify`。这只解决夹具可见数字的历史基线；SQLite 行内容、其它页面及独立外部 Agent 从零生成仍未证明。

M6 分析侧新增 `copyapp prepare-app`，在原版脚本已选定时，把所选 provider 的工具链预检、`analyze` 和 `prepare-analysis` 接成单一可恢复入口。XR 上 `cases/calculator-prepare-app-live-20261015/` 对 Calculator 单流程重新采集包、沙盒元数据和 UI，完成 Frida/REA 调查并生成 `preparation/draft/TASK.md`；父案例及来源子案例通过 `copyapp verify`。重复 `--resume` 未增加采集尝试次数，已完成草稿哈希保持不变。新增五项测试覆盖成功、来源篡改、工具链预检失败及带 `--decrypt` 的采集中断恢复；当时完整测试为 157 项通过。该入口停在语义审阅，不自动声明深度报告完成；其解密分支尚未通过新入口单独实机验证。

M6 后续修正：REA 已从 Copy APP 默认流程解除依赖。`prepare-app`、`prepare-analysis`、`investigate-app` 与 `investigate-flow` 默认 `--provider none`，不运行 REA doctor 或函数队列；有唯一方法时继续 Frida 跟踪和静态候选，没有可选方法时仍保留 UI 案例。显式 `--provider ghidra|hopper` 才进行原来的预检与反编译。报告和审阅任务接受无 REA 证据，明确把未验证的函数体与深层语义列为未知；历史 REA 案例继续可验。
原生函数证据后续补强：新增 `native-disasm` 与 `native-queue`，将精确哈希的主程序静态候选地址交给 Xcode llvm-objdump，限定每个函数最多 1024 字节并记录 LC_FUNCTION_STARTS 边界、截断状态和指令数。无 REA 的 `investigate-flow` 自动尝试该队列；缺少本机反汇编器时保留 unavailable 记录但不阻断 UI/Frida 调查。报告导入器可单独核验并引用原生汇编；已有 XR 夹具三流程证据的离线无 REA 回放生成的草稿与任务均通过校验。仍需 XR 再连接后实测默认入口；汇编不自动等于函数语义。
无 REA 原生队列进一步支持受限静态跟随：只沿 LC_FUNCTION_STARTS 中存在、位于本机 `__text` 的唯一直接 `bl` 目标，默认至多 2 层和 4 个后续函数；多目标、间接分派、指令输出截断或达到上限时停下并保存决策。XR Calculator 已有主程序证据离线重跑时从 `0x10000eb0c` 唯一跟随到 `0x10000e9b8`，两份汇编及来源链经重新核验。该静态边不证明原版点击运行了该下游函数。
跳转表边界补充：原生汇编解析现在将字面 `b`/条件分支与 `bl` 分开记录，仅在唯一且有函数起点的本地直接目标上自动跟随。Calculator 的 `0x10000e9b8` 包含多个明确 `b` 目标和一个计算跳转 `br`；队列把多目标记录为 ambiguous 并停下，不猜测按钮到分支的映射。

REA 独立化进展：Copy APP 自带 `ghidra-function`、`ghidra-queue` 和 `--provider ghidra-direct`。后者接入 `investigate-flow`、`investigate-app`、`prepare-analysis`、`prepare-app`，从运行时/静态候选选函数，调用外部 Ghidra/JDK，生成可校验的伪代码与 Agent 审阅任务，无需 REA CLI 或其桥接进程。XR Calculator 的 `cases/calculator-prepare-app-ghidra-direct-live-20261015/` 已从新采集走到 `needs_semantic_review`；旧复刻版的无 REA 三流程对照也已达到 3/3 末端断言通过、六对截图逐审有轻微差异。Direct Ghidra 仍是反编译证据生产，不自动等于完整函数语义或新源码生成。

大型 App 证据边界：DeepSeek 20.8 MB 主程序的首次 `ghidra-queue` 在 Ghidra 默认自动分析第 540 秒超时，虽然 Ghidra 继续调用 post-script 输出伪代码。Copy APP 的完成判定和报告校验现均拒绝此种部分分析。新增有哈希证据的 `--disable-analyzer` / `--ghidra-disable-analyzer` 配置后，同一 DeepSeek 二进制与 `DSButton::objcOnTap` 候选在关闭 `Objective-C Message Analyzer` 后 431 秒完成自动分析；`cases/deepseek-direct-ghidra-profiled-queue-20261015/`、限定入口报告及分析交付均通过来源校验，登录后行为和间接回调目标仍未知。整条 `investigate-flow --provider ghidra-direct` 配置路径亦在 XR 真机生成 `cases/deepseek-direct-ghidra-profiled-investigation-20261015/`，包含入口 UI、Frida 命中、原生汇编、直接 Ghidra 伪代码；来源和证据哈希校验通过。192 项单元测试通过。REA MIT 许可分析选项思路的归属和许可文本见 `docs/third-party/REA-LICENSE.txt`。

多函数反编译效率：`ghidra-queue` 选出多个地址时，Copy APP 自带的 Java post-script 现在在同一个 Ghidra 导入中逐函数运行并保留各自证据。对 XR 采集的 Calculator 主程序，批量适配器在一次真实 Ghidra 进程中完成 `buttonPressed:` 和它的直接调用目标 `FUN_10000e9b8`；两份结果分别通过来源校验，约 25 秒结束。再以 XR Fixture App 两处真实 Frida 观察入口运行完整 `ghidra-queue`，`cases/fixture-notes-direct-ghidra-batch-queue-20261015/` 的单次导入、两份结果与候选来源通过语义校验。伪完成拒绝由测试覆盖；完整回归测试现为 194 项通过。

独立下游函数链：`ghidra-queue --native <NATIVE_QUEUE>` 现在验证候选与原生反汇编的同一来源，并从唯一直接调用的静态跟随结果中加入下游地址；`investigate-flow --provider ghidra-direct` 自动传入自身的原生队列。每个结果明确标记运行时观察入口或静态跟随来源，审阅摘要与 `draft/TASK.md` 同步标注；静态边不宣称本次点击执行了下游函数。`cases/calculator-direct-ghidra-follow-queue-20261015/`、XR 真机 `cases/calculator-direct-ghidra-follow-investigation-20261015/` 和 `cases/calculator-direct-ghidra-follow-preparation-20261015/` 已完成，父案例和整案调查语义校验通过。`cases/calculator-direct-follow-reviewed-report-v3-20261015/` 的正式限定范围报告展示两函数来源和伪代码链接，报告索引正确记录调查中的两份直连函数证据。改写跟随来源地址并重算哈希后仍被拒绝。完整回归测试现为 195 项通过。深层函数含义、间接调用和跨流程状态仍需 Coding Agent 取证审阅。

新证据到复刻交接：`agent-task` 现从直连 Ghidra 队列及整案调查直接列出逐函数伪代码与原生汇编，供当前 Coding Agent 阅读。以 Calculator 加法的限定范围报告和规格生成 `cases/calculator-direct-follow-rebuild-plan-20261015/`、`cases/calculator-direct-follow-agent-task-20261015/`；任务 `ready_for_agent`，两份伪代码及两份汇编已在任务清单。沿用先前独立编写并安装的 CalculatorClone 0.1.10，在 XR 上完成 `cases/calculator-direct-follow-rebuild-check-20261015/`：所选流程末端 `15` 断言通过，两对截图经 `cases/calculator-direct-follow-visual-review-20261015/` 逐张审阅为轻微差异，`cases/calculator-direct-follow-agent-delivery-20261015/` 来源校验通过。这个案例证明新证据可驱动复刻交接与验收，不能宣称旧源码由新报告自动生成，也不覆盖其他 Calculator 功能。

第三方 App 的无 REA 分析到复刻闭环已在同一 XR 上推进到三条登录页流程：DeepSeek v10 深度报告及分析交付引用 UI、Frida、原生函数、直接 Ghidra 和限定的网络观察；`cases/deepseek-three-flow-rebuild-preparation-v10-20261015/` 从报告生成密码入口、Sign up 和条款 Cancel 的复刻任务。独立实现 `dev.copyapp.deepseekclone` 0.1.3 (4) 已安装；`cases/deepseek-three-flow-rebuild-check-v10-20261015/` 对三条流程的原版与复刻版均完成脚本并通过操作后及末端断言。六对截图在 `cases/deepseek-three-flow-visual-review-v10-20261015/` 逐张审阅，三条流程均有鲸鱼图形、字标或顶部系统文字的轻微差异。`cases/deepseek-three-flow-agent-delivery-v10-20261015/` 封存源码、IPA 与同机对照哈希，四份任务/对照/审阅/交付案例均通过 `copyapp verify`。详见 `docs/deepseek-three-flow-xr-verification.md`。范围仅到接受条款之前的登录页；独立 Agent CLI 自动生成源码、认证和后续页面、完整网络语义及 iOS 17/26 仍未验证。

一命令入口在 XR 又完成 `cases/deepseek-three-flow-prepare-app-network-live-20261015/`：以原版密码入口、Sign up、条款 Cancel 三份脚本调用 `prepare-app --decrypt --network --provider none`，同一父案例生成安装包/沙盒索引、整包恢复、三份 UI/Frida/网络观察和待语义审阅任务；`copyapp verify` 通过。相同参数续跑没有重复触屏，分析索引、调查清单与任务哈希不变。重复整包恢复还暴露了设备 helper 的 ZIP 时间戳非确定性：相同主程序、扩展及源快照产生不同原始 IPA 哈希。Mac 端现在检查非加密成员字节和成员列表，仅允许 helper 省略 `SC_Info` 收据，再用源归档元数据重组分析 IPA。两份历史原始包离线归一化及新一轮 XR `cases/deepseek-canonical-prepare-app-network-live-20261015/` 均得到相同的 IPA SHA-256 `9d4610e4e3587b8ca500aa3d7a08a8eabb498113e9589700a7bc099a09d46185`；新一轮父案例校验通过，本地 222 项测试通过。该归一化不证明其他 App 的脱壳兼容性，也不替代深度语义审阅。

独立 `decrypt-package` 的验证缺口已补：命令现在保存源快照路径与哈希、设备运行记录、解密清单和所有主要产物的哈希到 `manifest.json`；`copyapp verify` 重新解析源包及分析包，核对版本和设备身份、原加密代码变化、未变成员及 canonical ZIP、所有 Mach-O 加密头和 Objective-C 索引。XR 新实跑 `cases/deepseek-verifiable-decrypt-live-20261015/` 自动写出该清单并通过语义校验，恢复 2 个原加密二进制、检查 32 个 Mach-O，归一化 IPA 哈希仍为上述值。嵌入在新 `analyze`/`prepare-app` 案例中的脱壳子案例也会由父案例 `verify` 重验；已有 `cases/deepseek-canonical-prepare-app-network-live-20261015/` 补充子案例清单后父案例通过。完整本地测试现为 223 项通过。原始设备 IPA 在归一化后不保留，因此传输哈希仍是执行时记录，不能事后重新计算；跨系统兼容性继续待实测。

独立 Coding Agent 的分析运行增加可选 `agent-run --verify-analysis`：仅接受来源已验证的语义审阅任务，将正式报告目的地钉为运行案例的 `reviewed-report/`，在模型进程结束后自动调用 `analysis-delivery` 检查报告是否引用同一分析、完整调查与每条来源脚本。成功时另存 `analysis-delivery/`，缺报告或交付被拒时返回非零并保留诊断；CLI 进程正常退出仍单独记录为 `agent_exited_unverified`，不等于语义正确。`cases/deepseek-three-flow-verified-analysis-agent-dry-20261015/` 已对真实三流程任务完成 Codex dry run 与来源校验；假 CLI 测试覆盖有报告、缺报告和被拒报告三种结局。当前 Codex 会话没有递归启动外部模型，实际外部 Agent 自动写出报告的效果仍未验证。

复刻 Agent 对应增加可选 `agent-run --verify-rebuild`：仅接受已验证的实现任务，预留运行案例下的 `install/`、`rebuild-check/`、`visual-review/` 和 `agent-delivery/`；提示 Agent 在指定真机安装、重放任务内全部流程并逐图审阅。进程退出后，Copy APP 使用现有交付器重验同一任务、源码、已安装 IPA、设备版本、对照脚本与视觉判断。所选流程必须有操作后或末端行为断言，所有截图审阅且无重大视觉差异才返回成功；否则保留交付或拒绝原因并返回非零。轻微差异保留在交付中，自填审阅者名称不能证明判断客观正确。真实 DeepSeek 三流程任务的 `cases/deepseek-three-flow-verified-rebuild-agent-dry-20261015/` 已完成 Codex dry run 与来源校验，假 CLI 测试覆盖完整交付、重大差异、缺失设备证据及任务类型不符；尚未实际启动外部模型生成复刻源码。

XR 重新连接后完成 `cases/xr-no-rea-doctor-reconnected-20261015/`，USB、截图、DVT、SSH、Frida、iOS MCP 和 iCTRL 均可用。`cases/deepseek-no-rea-reconnected-live-20261015/` 在当前设备连接上以 `--provider none --decrypt --network` 重新运行原版密码入口；整包恢复、UI/运行时调查和审阅任务均完成，父案例通过 `copyapp verify`。归一化分析 IPA 的哈希仍为 `9d4610e4e3587b8ca500aa3d7a08a8eabb498113e9589700a7bc099a09d46185`。这是单条流程的采集验证；全面语义报告和从零自动生成复刻源码仍是未完成项。

独立终端的 `copyapp copy` 现把 `prepare-app`、经校验的分析 Agent、`prepare-rebuild` 和经校验的复刻 Agent 串成一个可恢复案例。阶段来源固定到设备、原版脚本哈希、目标及复刻 Bundle ID、分析 provider 和项目目录；父案例 `verify` 重验各正式交付。失败的 Agent 运行保留现场，续跑不自动重复可能改动手机状态的工作。模拟 Agent 测试覆盖四段成功、续跑复用、失败后不重放、报告目标不符及已交付视觉差异被篡改后的拒绝。尚未在独立终端启动真实 Codex/Claude CLI 完成这一总入口的端到端实跑，也尚未让系统仅凭 App 名称自动探索代表性脚本。

XR 沙盒证据补充：历史 DeepSeek 分析的数据库尺寸已变化，`sandbox-file` 正确拒绝将新文件归入旧索引。以重新连接时验证过的同版分析案例只读采集 `Documents/FlyVerifySDKDataList.sqlite`，`sqlite-schema` 保存了三张表的结构且没有读取记录；来源案例和模式案例均通过校验。`cases/deepseek-sandbox-report-live-v2-20261015/` 引入沙盒 161 项元数据、安装 entitlement 键、30 个嵌入 Framework 和该数据库结构，明确区分字段声明与实际使用。`copyapp report-portfolio` 再要求同设备、同 App 版本/构建和同一解密主程序哈希，把它与先前 436 行的登录流程深度报告组织成 `cases/deepseek-comprehensive-xr-20261015/report.md`，共 709 行，来源与链接重新核验通过。不同采集时点的运行事件和沙盒状态没有被当作同时发生；登录后行为和自动从零复刻仍未证明。

Agent 流程发现新增 `copyapp discover-check`：先拒绝错误 Bundle ID、重复动作路径、无初始观察或无稳定且内容就绪末端截图的脚本，再在精确设备上顺序重放三至十二条流程，封存脚本副本、点击和画面证据。失败后续跑不自动重复可能已执行的触控。XR 的 `cases/deepseek-three-flow-discovery-check-live-20261015/` 对密码入口、Sign up 和条款 Cancel 三条已知脚本完成同机实测并通过父案例校验；`copyapp copy --discovery` 现可直接接收该来源固定的脚本集合，拒绝设备、App 或 UI 后端不符。项目内 `skills/copyapp-copy/SKILL.md` 规定从用户仅给 App 的请求出发，由当前 Coding Agent 观察界面、编写并验收代表性脚本，再进入分析和复刻。此试验验证的是脚本验收器与交接；尚未证明外部模型能独立探索任意 App 并完成整条流程。

独立终端的 `copyapp copy --auto-discover` 现加入前置发现 Agent：从指定设备和 Bundle ID 编写候选脚本，调用 `discover-check` 真机验收三至十二条流程，再把验收案例、脚本哈希和 Agent 运行记录固定进父案例。失败或不确定的 Agent 运行保留现场，续跑不会自动重新执行触控。模拟 Agent 测试已覆盖成功交接、续跑复用、失败不重放和脚本/案例变更拒绝；尚未用真实外部 Codex/Claude CLI 从零完成整条流程，也未证明任意 App 的自动探索覆盖率。

XR 真机进一步运行固定脚本的外部进程，`cases/clock-auto-discovery-agent-live-20261016/` 在 Clock 世界时钟、闹钟未保存编辑和秒表启停重置三条流程上完成真实重放，Agent 案例及内层发现案例均通过校验。`cases/clock-auto-copy-live-20261016/` 从 `--auto-discover` 进入父流程，复用相同类型的固定脚本替身，完成真机发现、整包/沙盒/脱壳信息采集和三流程调查，随后因替身分析 Agent 未产出正式报告而正确停在 `analysis_agent_needs_review`。首次运行曾在 Clock 全部 Mach-O 已是 `cryptid=0` 时被脱壳校验器误拒；校验器已修成仅在来源 IPA 全部头部均无加密标记时接受零恢复项，同一案例续跑完成准备阶段。此实测验证的是编排、真机证据与拒绝门槛，不代表真实模型已完成自主探索或复刻。

父流程新增 `--agent-provider current`，供当前 Codex/Claude Code 会话自己完成语义报告和独立 App，而不嵌套启动外部 CLI。它在分析与复刻两处保存明确任务并暂停，续跑分别核验正式 `analysis-delivery` 与无外部运行记录的 `agent-delivery`，仍要求每条选定流程行为断言、全部截图审阅且无重大视觉差异。模拟交接测试覆盖两次暂停、续跑完成及拒绝将 `current` 和外部自动发现混用；真机完整交付见下段。

真实 `current` 父流程现已在 XR 完成：`cases/clock-current-workflow-live-20261016/` 从已验收的 Clock 三流程发现案例采集原版包、沙盒和 UI/函数候选，暂停等待当前 Agent；当前 Agent审阅本次证据并导入同设备、同主程序 SHA-256 的较早 Ghidra/Frida 函数案例，形成正式报告与 `analysis-delivery`，明确分开两轮采集时点。续跑生成复刻任务；`rebuild/ClockCurrentProbe/` 基于项目此前独立编写的 ClockClone 源码重用实现，改为新 Bundle ID，并根据首轮视觉审阅修正北京日期显示和城市弹窗布局。新 IPA 在 XR 安装后，三条原版/复刻版对照的 3/3 行为断言、3/3 末端 UIKit 断言通过；10 对截图逐张审阅为轻微差异、无重大差异。`agent-delivery` 保存源码和已安装 IPA 快照，父案例最终为 `complete` 并通过整案校验。该结果证明当前会话的暂停/续跑与选定范围交付，不证明独立外部 Agent 从零写出源码或完整 Clock 等价。城市字母索引与完整城市库、城市/闹钟保存、长时和后台计时、iOS 17/26 未验证。

新目标 Clock 试点从 Bundle ID `com.apple.mobiletimer` 出发，由当前 Agent 观察 XR 并定义世界时钟城市选择、闹钟编辑取消和计时器铃声选择三条安全流程。第一次重放揭示 `fresh_launch` 不会自动关闭弹窗，于是每条脚本都添加 Cancel 回到入口页；第二次重放揭示 Alarm 标签与标题重名，于是限定点击区域。最终 `cases/clock-three-flow-discovery-region-live-20261015/` 三条均通过。`prepare-app --provider none` 完成 36 条包路径、58 个主程序类、1358 个方法、31 个链接库与 26 条沙盒元数据；主程序没有加密加载命令。自动方法候选误选 `MTAWorldClockPadViewController::addClock:`，真机零命中；额外实验在 XR 上确认 `MTAWorldClockTableViewController::showAddView` 及闹钟、计时器选择页入口，并使用 Copy APP 直连 Ghidra 解释同哈希主程序的有界函数。正式报告与复刻任务分别见 `cases/clock-three-flow-no-rea-reviewed-report-v3-20261015/` 和 `cases/clock-three-flow-rebuild-preparation-v4-20261015/`。

独立的 `rebuild/ClockClone` 已打包安装在同一 XR；`cases/clock-three-flow-rebuild-check-v6-20261015/` 的三条成对脚本和末端 UIKit 断言全通过，9 对截图均经 `cases/clock-three-flow-visual-review-v6-20261015/` 逐张审阅。交付状态为 `selected_behavior_verified_visual_gap`：世界时钟与闹钟进入页的快照仍有重大导航栏差异；后续手工稳定截图显示部分元素最终呈现，当前的稳定帧判定与页面就绪条件不足以排除此类中间帧。`rebuild_check` 已允许无营销版本字段的系统 App 以构建号和路径固定安装身份，并支持 `UITableViewLabel` 末端断言；playbook 截图至少观察五帧。所有变更只在 iOS 16 XR 上实测，未覆盖 Clock 保存/计时服务、iOS 17/26 或外部 CLI 从零自动复刻。

后续在 XR 上复现启动后、底部标签切换后的截图过早采集：无障碍文本已可用但导航栏像素尚未完整。`playbook.py` 在新启动、底部标签点击及稳定截图前加入有界等待；Copy Clock 闹钟页补齐床图标和 SET UP 胶囊。使用未改动的原任务脚本重跑 `cases/clock-three-flow-task-check-v9-20261015/`，三条操作后脚本和末端 UIKit 断言均通过；九对图片在 `cases/clock-three-flow-visual-review-v9-20261015/` 逐张审阅，重大差异为零，三个流程仍有轻微差异。[交付记录](cases/clock-three-flow-agent-delivery-v9-20261015/report.md)通过哈希校验。此前 v6 结论保留为历史尝试，当前已验证范围仍限于三条未保存操作，完整 Clock 功能和独立 Agent CLI 自动生成尚未证明。

Clock 第四条流程扩展到 Stopwatch：XR 原版 Start、Stop、Reset 的单次短时操作与归零均已保存，`cases/clock-stopwatch-direct-ghidra-20261015/` 中 startLapTimer、pauseLapTimer、resetLapTimer 在各自点击窗口的当前 IMP 与静态入口各命中一次，三段 Ghidra 伪代码显示 startTime、offset 与分段清理的状态转移。`cases/clock-four-flow-no-rea-reviewed-report-v5-20261015/` 引用单独验证的秒表 flow-capture，`cases/clock-four-flow-rebuild-preparation-v7-20261015/` 从四条来源脚本生成完整任务。Copy Clock 新增运行时计时、暂停、重置和当前分段；[四流程交付](cases/clock-four-flow-agent-delivery-v1-20261015/report.md)在 XR 上通过 4/4 操作后与末端断言，13 对截图逐张审阅均为轻微差异，重大差异为零。`MTUITimeView` 的末端文字现在可在指定可见区域核对。未验证多分段、秒表后台/重启状态、闹钟保存、城市保存和 Timer 倒计时；外部 Agent CLI 与 iOS 17/26 尚未实测。

Clock 第五条流程加入 Timer Start/Cancel：在 XR 原版同一 `com.apple.mobiletimer` 主程序上，`cases/clock-timer-countdown-direct-ghidra-20261015/` 将 `MTATimerViewController::startTimer:` 和 `cancelTimer:` 的当前 IMP 与静态入口命中分别绑定到对应点击窗口，并保存 Copy APP 直连 Ghidra 伪代码；这些是函数执行证据，不等于完整计时服务的因果证明。`cases/clock-five-flow-no-rea-reviewed-report-v6-20261015/` 与 `cases/clock-five-flow-rebuild-preparation-v8-20261015/` 将第五条功能写入报告和任务。Copy Clock 实现前台倒计时、暂停、继续和取消；第一次 XR 对照发现运行页漏掉铃声行，修正后重新打包安装并执行 `cases/clock-five-flow-task-check-v2-20261015/`。五条行为脚本和末端 UIKit 断言均通过，16 对截图由 `cases/clock-five-flow-visual-review-v2-20261015/` 逐张审阅，均有轻微差异，无重大差异；[交付记录](cases/clock-five-flow-agent-delivery-v2-20261015/report.md)封存安装 IPA 和源码。原版个别稳定帧会缺少已可访问的按钮或铃声行，复现截图不稳定性已在审阅中注明。尚未验证计时到期通知、后台/重启恢复、城市与闹钟保存、多分段秒表、外部 Agent CLI 从零生成，以及 iOS 17/26。

Clock 第六条流程扩展 Stopwatch 两次 Lap：`cases/clock-stopwatch-two-laps-traced-flow-20261015/` 在 XR 原版的两次 Lap 点击窗口里分别记录 `MTAStopwatchViewController::lapLapTimer` 和 `MTAStopwatchLapTableViewController::addLap:` 的当前 IMP 与同哈希主程序静态入口各命中一次；`cases/clock-stopwatch-two-laps-ghidra-lap-v2-20261015/` 与 `cases/clock-stopwatch-two-laps-ghidra-table-v2-20261015/` 保存不经 REA 的伪代码。原版列表倒序显示当前 Lap 3、已完成 Lap 2/Lap 1，已完成较慢/较快分段为红/绿。Copy Clock 新增多行分段显示和 Reset 清空；[六流程正式报告](cases/clock-six-flow-no-rea-reviewed-report-v8-20261015/report.md)、[复刻任务](cases/clock-six-flow-rebuild-preparation-v10-20261015/task/TASK.md)及[真机交付](cases/clock-six-flow-agent-delivery-v2-20261015/report.md)均通过来源校验。XR 统一 iOS MCP 对照 6/6 行为脚本及末端 UIKit 断言通过，21 对截图逐张审阅均有轻微差异、无重大差异；完整本地回归测试 249 项通过。额外的 iCTRL 原版脚本完成且保存更完整的按钮画面；iCTRL 的复刻版 `page_source` 调用超时，日志约三分钟后确认失败，随后的 SpringBoard 只读观察成功，但复刻版同后端对照仍未完成。完整 Clock、后台/重启、长期计时、外部 Agent CLI 从零生成及 iOS 17/26 尚未验证。

Playbook 观察新增 `exact_labels`，按无障碍元素完整标签匹配并独立记录缺失项；原有 `contains` 子串判断和必要时的 OCR 回退保持兼容。XR Clock 空闲秒表的 `Stopwatch` 会让旧的 `contains: ["Stop"]` 误通过，`cases/clock-exact-label-negative-run-20261015/` 现在按预期拒绝；`cases/clock-exact-label-positive-run-20261015/` 和 `cases/clock-exact-label-positive-ictrl-run-20261015/` 在 iOS MCP/iCTRL 分别确认 `Lap`、`Start` 的完整标签。比较流程会重新核对已保存的无障碍证据，并拒绝原版与复刻版使用不同的观察条件。三个案例的保存证据均可校验，完整本地回归测试为 255 项通过。精确断言依赖无障碍树，不能用 OCR 的相似文字代替控件存在；它也尚未自动替换既有脚本的模糊断言。

XR 的严格秒表脚本又完成一次 iOS MCP 原版/复刻版成对对照：行为与末端 UIKit 断言通过，但四张原版截图均漏绘无障碍树中存在的 Lap、Start、Stop、Reset 圆按钮，故不能用该组图片做按钮视觉等价判断。随后 iCTRL 在相同的两端脚本上完整重放四个状态；原版与复刻版按钮均出现在截图里，`cases/clock-exact-label-paired-ictrl-check-v5-20261015/` 通过父案例校验，`cases/clock-exact-label-paired-ictrl-visual-review-v1-20261015/` 将四对画面逐张记为轻微差异、无重大差异。期间发现 DVT 启动的第三方 App 有时不更新 iCTRL 的前台缓存；Playbook 现在用显式 Bundle ID 获取 iCTRL 页面并检查页面归属，在 iOS MCP 可用时用它核对同机前台身份，包括 `flow-capture` 的共享隧道路径。仅有 iCTRL 时仍尝试其自身前台读数，若失准则失败留证。完整回归测试 258 项通过。该对照证明选定秒表流程，不证明全 App、后台计时或跨系统兼容。

截图视觉就绪从无障碍文本中独立出来：可选 `ready_ocr_labels` 让 Playbook 对保存的完整截图执行 macOS Vision OCR，并要求所列文字逐项完整匹配；其图片哈希、OCR 来源、缺失文字进入案例，比对器重新核验，原版/复刻版脚本不允许条件不同。历史漏绘截图的离线 OCR 读不到 Lap/Start，当前 XR 的正例在 iCTRL 两端 4/4 张状态图完整显示所需按钮，`cases/clock-painted-label-paired-ictrl-check-v2-20261016/` 通过真机对照与父案例校验，`cases/clock-painted-label-paired-ictrl-visual-review-v1-20261016/` 逐张记录轻微差异。`cases/clock-painted-label-negative-stop-20261016/run/` 在空闲页要求图像里的 `Stop`，即使 `Stopwatch` 可见也按预期失败且证据可校验。第一次正例在视图树采集阶段发现 Frida 默认挑选了同时连接的 iPad；采集、追踪和脱壳代码已改为按 UDID 精确选 USB 设备，随后 XR 完整对照通过。完整回归测试 264 项通过。OCR 文字缺失可能是识别失败，仍需人工审图判断原因；任意 App 的全功能探索与复刻尚未证明。

2026-10-16 新的 Calculator `--auto-discover --agent-provider current` 父案例已在 iOS 16.1.1 的 XR 上完成。当前 Agent 从真机可见的按键和无障碍树重新编写三条脚本：`0.1 + 0.2 = 0.3`、`−9 + 2 = −7`、`50% = 0.5`；第一次发现尝试因原版清零键显示 `all clear` 而脚本请求 `clear` 安全失败，第二次改为坐标清零，最终又加入截图 OCR 就绪约束；`cases/calculator-current-auto-workflow-20261016/discovery-agent/discovery/` 验收 3/3 条脚本，早期尝试保留。父流程随后采集同一系统 Calculator 的包、18 条沙盒元数据、16 个本地主程序 ObjC 类/112 个方法、30 个动态库以及三条输入流程的 Frida 当前 IMP/静态入口命中；主程序没有加密加载命令，整包恢复项为零。正式报告 `cases/calculator-current-auto-workflow-20261016/analysis-agent/reviewed-report/` 还引用同一主程序哈希的早期 Copy APP 直连 Ghidra 函数案例，区分两轮采集时点与运行时观察/静态推断。当前 Agent 从空工程编写 `rebuild/CalculatorFreshProbe/`，Xcode 编译、签名、在 XR 安装并对照；首次图片发现 0 键文字居中，修正后重新打包和安装。最终 `rebuild-check-v2` 的三条行为及末端 UIKit 断言均通过，三对截图逐张审阅为轻微差异、无重大差异；`agent-delivery` 和父案例标为完成并经哈希重验。仅覆盖这三条基本计算路径，不能推断除零、连续运算、系统计算引擎、完整 UI 或任意 App 的自主复刻；外部 Codex/Claude CLI 从零闭环及 iOS 17/26 仍未验证。

2026-10-16 入口与报告可读性补强：`copyapp apps --udid <XR_UDID> --all` 在 XR 返回 182 个安装条目，包含 `com.apple.calculator`、`com.apple.compass` 和 `com.apple.mobiletimer`；默认仍只列用户安装的 App。`copyapp report` 将已采集 `Assets.car` 具名资源与只读沙盒元数据整理为有界附录，避免它们只出现在 JSON 里。`cases/calculator-rich-inventory-report-20261016/` 使用同一份 XR 分析与已审 findings 重新生成报告，列出 1 个资源目录/3 个资源名、18 条沙盒元数据（13 目录、5 文件），并以 `cases/calculator-rich-inventory-analysis-delivery-20261016/` 再次通过来源与脚本关联核验。资源名称、路径及扩展名不证明本次点击使用它们，报告没有读取文件内容。

2026-10-16 Calculator UI 静态链补充：对同哈希主程序的 `CalculatorController.loadView`→`0x100004ad0`、`CalculatorKeypadView.layoutSubviews`→`0x100021510`、`DisplayViewController.loadView`→`0x1000283a4`→`0x100027e68` 分别用 Copy APP 直连 Ghidra 保存入口与本地函数证据，七个案例均通过哈希校验。根控制器向 root view 添加显示区与键盘区；键盘布局遍历按钮、设置 frame，基础模式第 5 行的零键使用 `CGRectUnion` 合并两个矩形；显示区设置黑色背景、建立滑动/长按/双击识别器。上述静态代码与 XR 保存的 UI 树、截图相符，但三条运算流程只跟踪 `CalculatorModel.buttonPressed:`，没有动态测量这些 UI 初始化函数或手势结果。[新版深入报告](cases/calculator-ui-deep-report-20261016/report.md)和[分析交付](cases/calculator-ui-deep-analysis-delivery-20261016/report.md)均通过来源核验，仍将 Calculate 私有框架内部算法列为未知。

2026-10-16 UI 手势链补充：`swipe`、`long_press`、`double_tap` 已纳入发现、重放、Frida/网络操作窗口、原版与复刻版参数比较以及交付断言关卡。XR 已安装 iOS MCP 0.1.4，三种入口均列出并完成有界调用。Calculator 显示区左滑的 iCTRL 无障碍断言确认结果 `9→0`，iOS MCP 的末端截图也显示 `0`。长按、双击只验证通道可用及 App 保持前台，不推出特定功能结果。iCTRL 的滑动时长使用速度档近似，双击间隔不能按脚本精确设置。详情及英文切换见[中文手势指南](docs/ui-gesture-playbooks.zh-CN.md)。此前静态 UI 报告的采集时间和本次手势重放不同，报告本身尚未更新为动态手势结论。

随后用原版 Calculator 输入 `98`，XR 的 iCTRL 无障碍断言确认左滑后为 `9`。独立复刻版 0.1.1 (3) 加入显示区左滑删除末位与明确的无障碍结果值，同一脚本也通过 `98→9`；[成对对照](cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-comparison/report.md)保存末端画面，目视结果一致但仍有字形、颜色和状态栏差异。新版复刻版还重新完成[三条既有运算流程](cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-check/manifest.json)，末端断言均通过；[三对截图审阅](cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-visual-review/report.md)均记轻微差异。当前只验证这一条左滑状态，不推广到其他数字格式或完整 App。

Translate 陌生 App 试点：XR 上采集了系统 Translate 1.0（构建 216.4）的首页与包线索；首次使用时选择了“不分享录音”。Playbook 新增 1–128 字符、最多 512 UTF-8 字节的 `type_text`，纳入发现、跟踪、对照和安全故障切换。iCTRL 在原版 Translate 中输入合成词 `hello` 后通过界面断言；iOS MCP 虽报告字符已派发，界面没有接受，故当前 XR 的已验证文本流程仅使用 iCTRL。[三流程发现案例](cases/translate-xr-discovery-20261016/manifest.json)将合成文本、Favorites 空状态、Conversation 待机界面逐条重放并通过来源核验。语义分析报告与独立复刻仍在后续阶段；边界和英文切换见[中文文本脚本指南](docs/ui-text-playbooks.zh-CN.md)。
