# macOS 开发支持

[English](macos-support.md) · [实施与验收清单](macos-implementation-plan.md)

macOS 支持是在现有 iOS 支持之上新增。iOS 命令、设备链路和 v1 历史 case 保留原有含义。
当前分支已有采集、有界重放、审阅报告和重建计划命令，**尚未完成 Mac App 的完整分析／重建验收**。
不要用虚拟 UDID 或 IPA 来表示 Mac。

ChatComputer 负责虚拟桌面和键鼠输入；当前 Coding Agent 负责解释与实现，不启动另一个
Agent 或 ChatComputer 内置模型循环。上游 MCP 目前主要返回文本和图片，Copy APP 的
有界客体采集器补充精确 App 身份与结构化 AX 观察，不依赖上游尚未实现的 shell 接口。

控制权限尚未就绪时，可按[共享文件与分发包采集](macos-acquisition.md)运行 `mac share-probe`
和 `mac share-probe-check`，由客体 Finder 完成一次唯一探针文件的复制，记录字节往返。
ZIP／DMG 输入使用 `mac import-app`；DMG 在 macOS 27 上以只读、禁止执行的方式挂载，
并在 `verify` 时重新比对。加密或需要交互接受许可的镜像会被拒绝。以上不等于 App 已安装、
已运行或已完成界面验收，原始文件仍留在被 Git 忽略的本地案例中。

用户没有预选流程时，先按[代表流程发现](macos-discovery.md)观察、重放并审阅 3–12 个不同流程，
使用 `mac discover-check` 保存选择理由、已知能力和未知范围。再用 `mac report --discovery`
生成正式行为报告，保留已验收的流程来源和已发现的能力 ID。发现阶段只证明输入准备就绪。

## 交给 Agent

在 Codex 或 Claude Code 中打开这个开发分支，把下面的任务复制进去：

```text
请用当前 Copy APP 项目和 ChatComputer 分析 macOS 上的「App 名称」。
先阅读 AGENTS.md 和 skills/copyapp-mac/SKILL.md，确认准确的虚拟 Mac、App 和构建，
采集有代表性的流程，审阅原始证据后交付带引用的行为报告。
保留现有 iOS 支持，在当前 Agent 会话内完成解释和实现，并明确已验收范围与未完成门槛。
```

需要独立复刻时，再补充要复现的行为，让 Agent 继续生成经审阅的重建计划并实现。
开发命令已有本地／模拟协议测试，客体实测和实体 Mac 验收仍未完成，不能把已准备的任务
或通过的协议检查当作已经交付的 App。

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

doctor 的 `needs_setup` 案例可以通过文件一致性校验，但表示环境尚未就绪。成功 doctor
只证明传输和截图可用，不等于 App 身份、深度分析或复刻已经就绪。

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
密钥或 pairing token。每次连接重新检查身份；变化时新建审阅过的登记，不覆盖旧证据。

`inspect` 只采集本地 `.app` 静态包，记录完整文件清单和安全的内部符号链接，分别固定
完整可执行文件和 arm64 分片哈希，并检查 Mach-O 声明的 macOS 平台。它拒绝 iOS 和
Intel-only 输入，不会把受保护系统文件标志传播到研究副本；原 App 不变。

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

## 尚待完成

尚需完成客体实际重放验收、沙盒／数据采集、流程发现验收、真实样本构建和客体安装／启动、真实成对复验、
完整视觉审阅及交付。验收要求两个样本 App、各三条流程、各三轮对照，
并对一个样本做实体 Mac 复验。运行时代码分析单独验证权限边界。这些都必须以实际证据
关闭，不能用本地协议测试代替虚拟机或真机验收。

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
