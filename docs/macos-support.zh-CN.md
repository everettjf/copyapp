# macOS 预览支持

[English](macos-support.md) · [实施与验收清单](macos-implementation-plan.md)

**v0.2.0** 正式版同时支持越狱 iOS 和macOS；v0.1.2 为上一版仅支持 iOS 的版本。iOS 命令、设备链路和 v1 历史 case 保留原有含义。
当前分支已有采集、有界重放、报告、独立构建和选定交付；自有样例已完成指定行为交付，
不代表整 App 等价、深层函数分析或任意 Mac 兼容。
不要用虚拟 UDID 或 IPA 来表示 Mac。

ChatComputer 负责虚拟桌面和键鼠输入；当前 Coding Agent 负责解释与实现，不启动另一个
Agent 或 ChatComputer 内置模型循环。上游 MCP 目前主要返回文本和图片，Copy APP 的
有界客体采集器补充精确 App 身份与结构化 AX 观察，不依赖上游尚未实现的 shell 接口。

控制权限尚未就绪时，可按[共享文件与分发包采集](macos-acquisition.md)运行 `mac share-probe`
和 `mac share-probe-check`，由客体 Finder 完成一次唯一探针文件的复制，记录字节往返。
ZIP／DMG 输入使用 `mac import-app`；DMG 在 macOS 27 上以只读、禁止执行的方式挂载，
并在 `verify` 时重新比对。加密或需要交互接受许可的镜像会被拒绝。以上不等于 App 已安装、
已运行或已完成界面验收，原始文件仍留在被 Git 忽略的本地案例中。
`mac data-file` 可根据已验证的客体 App 采集案例读取一个明确指定的数据文件，保留两次读取的
一致性与来源记录。它只接受受限位置的普通文件，不代表文件归属已被证明、数据完整或数据库快照原子一致。
`mac data-schema --format plist|sqlite` 从已验证的数据案例提取键／类型或数据库元数据，
正式报告通过 `--data ID=CASE` 引用其中的 `structure.json`。生成结构不输出取值、表行或 SQL 正文；
原始字节仍在本地子案例中。结构证据不能替代界面行为证据，也不能证明不同时间的观察同时发生。

用户没有预选流程时，先按[代表流程发现](macos-discovery.md)观察、重放并审阅 3–12 个不同流程，
使用 `mac discover-check` 保存选择理由、已知能力和未知范围。再用 `mac report --discovery`
生成正式行为报告，保留已验收的流程来源和已发现的能力 ID。发现阶段只证明输入准备就绪。

## 安装与首次使用

通过 Agent 上手，可直接复制 [README 中的 Mac 任务](../README.zh-CN.md#macos-与-chatcomputer)。下面的命令由 Agent 执行；客体初始化与系统授权仍可能需要你在界面上操作。

### 1. 准备宿主与仓库 CLI

截至 **2026-10-22**，[ChatComputer 官方安装说明](https://github.com/chatcomputer/chatcomputer#install)列出 Apple Silicon、macOS 27、至少 16GB 内存及约 70GB 可用空间。这是上游要求，不是新的 Copy APP 兼容性测试。Copy APP 另需 Python 3.9+、Swift 编译器和 macOS SDK；构建 Xcode 工程需要完整 Xcode。安装其他 ChatComputer 版本时，重新检查上游要求。

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp mac --help
```

已有检出直接复用，保留本地改动。bootstrap 只安装本地 Python CLI，不会安装 ChatComputer、Xcode 或客体服务。Mac 目标接着运行下文的 `mac doctor`；`onboard` 属于 iPhone 配置入口。

### 2. 安装并打开 ChatComputer

已有 Homebrew 时：

```sh
brew install --cask chatcomputer/tap/chatcomputer
open -a ChatComputer
```

也可以从[官方 Releases](https://github.com/chatcomputer/chatcomputer/releases)下载 `ChatComputer.zip`，解压后把 `ChatComputer.app` 放进“应用程序”。这种安装方式还需在 ChatComputer 的 **Settings → Coding agents** 中配置 `chatcomputer` 命令；Homebrew cask 会一并安装命令。当前官方 cask 为 0.9.11，更新版本仍需单独检查就绪情况。

在界面里完成虚拟 Mac 初始化及要求的录屏／控制授权，保持 ChatComputer 运行，并确认目标 App 已安装且能在**虚拟 Mac 内**打开。0.9.11 初始化完成但仍停留在模型配置页的情况见下文；使用外部 Agent 不需要启动其内置模型循环。

### 3. 先检查传输，再确认准确客体与 App

继续按下文“环境与采集器”和“登记虚拟机与观察 App”操作。把采集器部署到指定客体，在客体里授予辅助功能权限；每次尝试用新案例目录，保留后续阶段需要引用的成功案例。

首次配置可用于行为观察的标志是：传输／截图检查、采集器健康与准确环境登记成功，目标 App 身份明确，并拿到可用的截图／AX 观察。`needs_setup`、权限缺失或观察截断需要继续处理，不能把文件校验通过当作环境就绪。之后再进入流程发现、报告和实现。

## 交给 Agent

在 Codex 或 Claude Code 中打开源码检出，把下面的任务复制进去：

```text
请用当前 Copy APP 项目和 ChatComputer 分析 macOS 上的「App 名称」。
先阅读 AGENTS.md 和 skills/copyapp-mac/SKILL.md，确认准确的虚拟 Mac、App 和构建，
采集有代表性的流程，审阅原始证据后交付带引用的行为报告。
保留现有 iOS 支持，在当前 Agent 会话内完成解释和实现，并明确已验收范围与未完成门槛。
```

需要独立复刻时，再补充要复现的行为，让 Agent 继续生成经审阅的重建计划并实现。
开发命令已有本地／模拟协议测试、指定客体的自有样例交付和一次实体 Mac 选定行为手动复验。
Stocks 已达到离线原型的有界评分目标，严格交付继续延期；不能把已准备的任务或协议检查当作已交付的 App。

快照清点、保留安全快照的恢复和中断处理见[恢复流程](macos-recovery.md)。
`snapshot-inspect` 只读公开元数据；`snapshot-take`／`snapshot-restore` 需要已就绪的准确环境。
恢复后使用新的 MCP 和采集器会话，旧共享目录不会回滚。上游快照只有本次集成的操作前租约检查，
不能证明操作期间原子地排除了人接管；元数据与重新连接也不能替代 App 行为复验。

Stocks 已完成客体采集、三条原始流程、正式行为报告和独立构建／安装。历史 build 4 的三轮
9/9 组选定行为检查通过，195 对完整截图保留离线行情／新闻替代、菜单、悬停反馈和删除
弹框层级等明显差异。此处的通过率不代表全 App 覆盖率。
后续 Stocks build 5 保留删除确认框下的管理窗口，并区分取消／删除按钮；28 步客体针对性
重放通过，已打开六张完整截图核对取消保留列表、再次确认删除及正常退出。该修复不替代旧版
完整配对审阅，新闻／行情内容和菜单等剩余差异仍未解决，也未产生新的通过验收交付。
build 6 另修复冷启动空列表页及 Add Symbol 搜索入口，31 步客体重放和 11 项行为断言通过；
后续成对运行在原版搜索处失败：屏幕可见 AAPL 行暂未出现在 AX 树中。保留失败并检查状态后，
修订搜索脚本在原版与复刻版分别通过，使用唯一 AX 断言后的文字位置点击和有界等待；
要求 1280×800 截图上的 1080×670 窗口位于 (100,56)。新报告仍为 11 项已知能力、3 项目标，
失败的诊断脚本、现场检查和单独清理均保留。随后版本 7 的新 `check-5` 三轮 **9/9** 组行为
对照通过；207 对完整截图已全部审阅（414 次图像引用，320 张精确去重的完整 PNG）。
`visual-review-5` 验证审阅覆盖，零尺寸不匹配，仍有 **207 项明显差异**。修正后的弹窗层叠
和冷启动空列表状态可见，但离线内容、菜单、悬停反馈、样式和示例统计数据等仍有差异。
九组声明的起始任务状态相当，不代表内容视觉等价；Stocks 仍无通过验收的交付或已验证能力覆盖。
用户随后提出有界目标，新默认采用[80 分、最多三轮](fidelity.md)。复用已验证并完整审阅的
版本 7 证据后，选定离线原型的审阅分为 **81/100**（行为 100、布局 80、细节 45），
`fidelity-check-1` 达到该档位，停止继续打磨。该目标晚于原始重放设定，没有新增客体运行，
也未修改任何旧视觉判断；207 项明显差异仍保留。此结果不等于严格交付、客观相似度或能力覆盖率。
自有 AppKit 样例的三条客体原始流程也已形成正式报告，冻结目标为已知九项能力中的七项；
单独的[独立编辑器](../examples/macos/IndependentEditor/README.md)已构建并安装，三轮共 9/9 组行为对照通过。
修复 Window 菜单后，新 `check-3` 的三轮 9/9 组行为对照通过，285 对完整截图已全部审阅
（完整 PNG 精确去重为 459 张）：零项明显差异，285 项轻微差异仍记录独立 App 名称、
时钟／光标／Dock 阶段及原生面板目录历史／焦点。`delivery-1` 已通过选定行为交付验证，
已验收范围为已知九项能力中的七项（77.78%），撤销／剪贴板和一般窗口管理仍延期。
该分母不包含所有 AppKit 行为；自有样例源代码可见，也不属于盲源复刻测试。旧 `check-2`
及其六项明显菜单差异仍完整保留。Stocks 的交付验收仍未通过。
用户接管／输入中断、快照后的 App 行为和物理 Mac 复验等门槛仍开放；物理主机尝试在启动 App
前因锁屏而受阻。准确案例及状态见[实施清单](macos-implementation-plan.md)。
后续快照状态实验未通过：取快照虽生成元数据，却返回代理断连错误；编辑器随后换了进程，
未保存的测试文字丢失。环境已修复就绪，运行中 App 状态保留仍是失败门槛；进一步快照实验
应先保存需要保留的工作，使用可丢弃的测试状态。

另已完成真实客体单文件数据检查：明确选择自有样例 Bundle ID 的偏好 plist，原始文件案例、
不含值的键／类型结构和引用该结构的独立正式报告均通过验证。`/fixture.wrap` 为布尔类型，
也记录了原生面板元数据的类型。该采集晚于 UI 流程，不代表原子数据库快照、全部键的写入归属
或完整 App 数据验收；归档子案例中的原始字节仍仅保存在本地。

原生 Swift 构建保留 xcrun 返回的带版本 SDK 路径，并向构建子进程显式传递同一路径的
`SDKROOT`，把该设置写入日志。原生回归直接检查 Mach-O 中的 SDK 版本；此前缺少此环境时，
本机工具链会把 SDK 记为部署目标 14.0，样例因此出现旧式窗口装饰。历史构建案例保持原记录，
仍可验证；修复后的构建产生新案例。

验收开发可使用[自有 AppKit 样例](../examples/macos/BehaviorFixture/README.md)。它是原始测试 App，
包含原生文件对话框、编辑与统计、设置持久化和多窗口；宿主冒烟测试不等于客体采集、独立重建或对照交付。

在完整控制权限尚未就绪时，可准备**不带 `--request-accessibility`** 的采集器，
把经过校验的部署目录放入客体已有共享 inbox，核对后从客体 Finder 打开其启动器。
`mac probe-collector --vm-directory <VM> --collector-build <BUILD> --out <CASE>`
只做两次新的健康请求，校验构建、会话、实例和从该共享目录首次观察到的客体身份，并记录实际客体 OS。
它不申请或授予权限，不能替代 `mac connect`、桌面控制或行为验收。真实客体探针已观察到
macOS 27.0.1（26A434）、辅助功能权限为 false；初始化仍在第 4 步。

## 环境与采集器

在 Apple Silicon Mac 上安装 ChatComputer，完成图形界面中的客体初始化。然后运行：

```sh
.venv/bin/copyapp mac doctor --out cases/mac-transport
.venv/bin/copyapp verify cases/mac-transport
.venv/bin/copyapp mac build-collector --out cases/mac-collector-build
.venv/bin/copyapp verify cases/mac-collector-build
.venv/bin/copyapp mac prepare-collector --build cases/mac-collector-build \
  --out cases/mac-collector-deployment --request-accessibility
.venv/bin/copyapp verify cases/mac-collector-deployment
chatcomputer share add "$PWD/cases/mac-collector-deployment/payload"
```

只读共享这一份部署目录。使用 ChatComputer 返回的客体路径，在**虚拟 Mac 的 Finder**
里打开并执行 `Start Collector.command`。它检查虚拟机和共享目录，在客体用户的
`~/Applications/CopyAppTools/<hash>/` 安装精确哈希的采集器，不修改宿主系统。

`--request-accessibility` 让采集器请求客体辅助功能权限，实际授权仍由客体所有者通过
系统设置完成；它不会自动授予权限。ChatComputer 另需自身的客体录屏和控制权限。
仅编译和执行协议自检不会请求这些权限。默认使用 ad-hoc 签名；需要稳定 TCC 身份时用
`--signing-identity` 指定合适的稳定签名并保留该构建。签名变化可能需要重新授权。

更新临时签名的采集器后，要重新核对客体权限。本次 macOS 27 客体的系统开关仍指向
旧哈希目录；经已授权的单 App 权限重置，再在系统设置中添加准确的新 App 路径后，
新采集器的 AX 探针才变为 true。单 App 重置使用
[Apple 文档中的系统工具](https://developer.apple.com/documentation/xcode/resetting-access-to-protected-resources-in-macos)。
Copy APP 不会自动重置隐私权限；蓝色开关不能代替新构建的健康检查。

doctor 的 `needs_setup` 案例可以通过文件一致性校验，但表示环境尚未就绪。成功 doctor
只证明传输和截图可用，不等于 App 身份、深度分析或复刻已经就绪。

本次 ChatComputer 0.9.11 实测中，保存初始快照后 VM 状态已为 `ready`，但首次运行界面
仍显示模型配置。正常退出并重新打开 ChatComputer 后，外部 MCP 可以直接使用桌面，
无需配置其内置模型；重新打开后仍需运行 doctor 核实实际传输状态。客体账户凭据保留在
ChatComputer 自己的本机存储中，不作为 Copy APP 案例、报告或 GitHub 材料的输入。

## 登记虚拟机与观察 App

```sh
.venv/bin/copyapp mac connect \
  --vm-directory "$HOME/.chatcomputer/ChatComputer.vm" \
  --collector-build cases/mac-collector-build --out cases/mac-environment
.venv/bin/copyapp verify cases/mac-environment
.venv/bin/copyapp mac inspect --app /path/to/Example.app --out cases/mac-package
.venv/bin/copyapp verify cases/mac-package
.venv/bin/copyapp mac observe --environment cases/mac-environment \
  --app-path /Applications/Example.app --bundle example.app --ax \
  --out cases/mac-ui-observation
.venv/bin/copyapp verify cases/mac-ui-observation
```

非默认 ChatComputer 数据目录须显式指定。登记会固定 VM ID、机器／硬件标识哈希、测试
配置、ChatComputer 可执行文件、采集器构建、客体身份及系统版本；不会复制口令、模型
密钥或 pairing token。同时保存 MCP 初始化原始请求／响应及其自报服务身份，与安装的
App 版本分开记录。本次 App 为 0.9.11；通过 CLI 别名的 doctor 自报 MCP 版本 `0`，
登记时通过解析后的 App 可执行文件自报 `0.9.11`。后续连接比较保存的服务身份，
不从 App 版本推导它。每次连接重新检查身份；变化时新建审阅过的登记，不覆盖旧证据。

`inspect` 只采集本地 `.app` 静态包，记录完整文件清单和安全的内部符号链接，分别固定
完整可执行文件和 arm64 分片哈希，并检查 Mach-O 平台声明：接受 1（macOS）或
6（Mac Catalyst），拒绝 iOS、iOS Simulator、冲突的平台声明和
Intel-only 输入，不会把受保护系统文件标志传播到研究副本；原 App 不变。
Catalyst 索引单独记录 `macho_platform: 6` 和 `runtime: mac_catalyst`；包采集通过
不能证明界面重放或复刻通过。

`observe --ax` 要求准确的前台进程和启动时间，保存有界 AX 树、原始 MCP 截图及前后
身份。不传 `--ax` 时只采集 App 身份。截图和 AX 为先后观察，不能声称同时采集；截断
和权限缺失保持显式。报告还需要 Agent 审阅，不能从界面观察直接推断函数语义。

采集器使用独立会话、请求 ID、请求哈希和宿主排他锁。启动请求留存开始标记，断连或
恢复后不盲目重放。共享目录不会随客体快照回滚，旧结果不得作为新观察。

## 重放与审阅选定行为

```sh
.venv/bin/copyapp mac acquire --environment cases/mac-environment \
  --app-path /Applications/Example.app --bundle example.app \
  --out cases/mac-acquisition
.venv/bin/copyapp verify cases/mac-acquisition
.venv/bin/copyapp mac playbook --acquisition cases/mac-acquisition \
  --script cases/mac-flow.json --out cases/mac-flow
.venv/bin/copyapp verify cases/mac-flow
```

`acquire` 经采集器导出有界 App 包，对比完整的客体源文件／副本／再次读取的源文件清单。
重放在流程前后重新固定包哈希，键鼠输入前要求准确前台进程的 AX／截图观察。
最小脚本结构如下，选择器和期望值必须换成目标 App 的实际观察：

```json
{
  "schema_version": 2,
  "platform": "macos",
  "scenario_id": "visible-editor",
  "bundle_id": "example.app",
  "app_path": "/Applications/Example.app",
  "steps": [
    {"action": "launch"},
    {"action": "expect_text", "selector": {"identifier": "editor"}, "text": "Expected text"}
  ]
}
```

动作包括 launch、screenshot、click、click_element、key、type、scroll、drag、quit、
expect_text、expect_file、expect_stopped 和 wait。元素必须唯一匹配；截断的 AX 树不能
用于元素选择。文本默认精确匹配，包含判断须显式加 `match: contains`。文件断言使用本轮
输出目录内的相对路径，选择 `text_equals`、`json_equals` 或 `sha256` 之一；输入文本中的
`{{output_dir}}` 会换成本轮客体输出目录。变化中的文件、符号链接及越界输出会被拒绝。
失败会保留，动作不会自动重复；新建尝试前先检查当前 App 状态。

审阅原始界面、输出证据后，按 [review JSON 契约](macos-review.md)运行 `mac report` 和
`mac rebuild-plan`。前者固定有来源的结论与功能规格，后者冻结已知能力清单、目标覆盖率
和原版／复刻版脚本，生成当前 Agent 执行的 `TASK.md`。它们不证明实现或交付完成，
也不执行深层函数分析。报告结论及能力清单的完整性仍由审阅者负责。

## 当前验收边界

两个样本各三条流程、各三轮成对行为检查及完整截图审阅已有证据；自有编辑器完成 7/9 已知能力
交付，Stocks 仅完成 81 分的选定离线原型目标，明显差异保留。单个偏好文件采集／结构报告、
同一二进制的实体 Mac 选定行为复验、真实人工接管后的输入拒绝、受控回复丢失以及用户明确授权
Agent 代点交回后的恢复均有独立证据。后者不冒称真人手动交回。

新版采集器暂停轮询后的一次取快照／保留安全快照的恢复，已通过真实客体的未保存 Unicode 文本、
换行状态和相同进程身份核对；旧失败案例保持失败。它不暂停全部客体 I/O，也不回滚宿主共享目录。
详见[恢复说明](macos-recovery.md)和实施账本。严格 Stocks 交付、更广数据和函数运行时分析仍属于后续范围，
不能由这些指定样本证据推导整 App 等价或任意 Mac 支持。

## 构建并安装独立 App

重建计划中的 App 路径应位于登记环境的 `environment.json` → `install_root` 下，且为
直接子目录。默认位置是**客体**的 `~/Applications/CopyAppRebuilds`，与原 App 分开。
旧计划若指定了其他位置，应保留旧证据并重新生成计划。

在计划固定的宿主工程目录实现源码后，选择一种构建方式：

```sh
# 已配置独立 Bundle ID 和产品名的 Xcode 工程。
.venv/bin/copyapp mac build-app --plan cases/mac-rebuild-plan \
  --xcode-project IndependentEditor.xcodeproj --scheme IndependentEditor \
  --configuration Debug --out cases/mac-build

# 或直接编译带 @main 入口的 Swift 文件，使用源码中的 Info.plist。
.venv/bin/copyapp mac build-app --plan cases/mac-rebuild-plan \
  --swift-source Main.swift --info-plist Info.plist \
  --resources Resources --out cases/mac-build-swift
.venv/bin/copyapp verify cases/mac-build
.venv/bin/copyapp mac install --build cases/mac-build --out cases/mac-install
.venv/bin/copyapp verify cases/mac-install
```

构建参数中的路径相对于宿主工程目录；多个文件重复 `--swift-source`，没有资源目录时
不传 `--resources`。直接 Swift 构建使用 Swift 5 语言模式、`@main`、arm64 和默认 macOS
14.0 最低版本，可选 Debug／Release 优化；最低版本用 `--deployment-target` 修改。
Xcode 构建读取工程自己的最低版本和 entitlements，不会再替换其完成的签名。
默认签名为 ad-hoc（`-`），需要时用 `--signing-identity` 指定稳定签名身份。

构建案例保存计划、源码副本、编译器／签名工具身份、SDK 元数据、完整有界日志和带签名
App 索引。从保存的副本编译，拒绝输入文件变化；Xcode 新建的空 workspace 元数据目录
单独记录。只在工程顶层排除 `.git`、`.build`、`DerivedData`、`__pycache__` 和 `.DS_Store`。
构建案例须放在源码目录之外。这证明本机构建及来源关系，不等于公证、安装或行为验收。

安装使用构建来源中的准确登记环境，在新 inbox 会话暂存已验证的包，检查客体副本的签名
和文件清单，再以禁止覆盖的原子操作创建目标目录；不会启动 App。已有文件、目录或符号
链接都不能被替换。安装开始标记阻止中断后盲目重放，失败和原始回复会保留。结果未知时
先观察客体和证据，不要直接重装。成功后仍需重新采集复刻版、成对重放和视觉审阅。

## 成对复验与选定行为交付

按[成对复验与交付契约](macos-checks.md)继续：

1. `mac check-plan` 在新一轮运行前固定实际界面设置、起始窗口和截图遮罩。
2. `mac rebuild-check` 重新采集已安装的复刻版，按冻结脚本依次运行每轮原版／复刻版，
   检查语言、外观、显示设置、窗口位置和起始文本断言。失败不自动重放。
3. 阅读生成的 `VISUAL_REVIEW.md`，打开每对完整、未遮罩截图，填写模板后运行
   `mac visual-review`，逐项记录差异和起始状态是否可比。
4. 对冻结清单中的每项已知能力给出明确决定，用 `mac delivery` 绑定源代码、构建、安装、
   成对检查和审阅结果。

交付要求目标能力均经确认、全部选定行为断言通过、完整视觉审阅、图像尺寸一致、起始
状态等价且没有重大视觉差异；小差异仍保留。目标覆盖率、已验证的已知能力覆盖率和选定
流程通过率分别报告。网络和重置策略的文字声明不会被当成已验证的隔离或数据重置。
这些命令检查来源和门槛，不认证主观判断、整 App 等价或实体 Mac 行为。
