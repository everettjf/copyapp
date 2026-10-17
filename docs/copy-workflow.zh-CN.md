# Copy APP 工作流程

**语言：** [English](copy-workflow.md) | 简体中文

Copy APP 把指定越狱 iPhone 上选定功能的“分析”和“复刻”组织为可续跑、按证据验收的流程。`current` 模式供已经打开的 Codex 或 Claude Code 会话执行；独立终端也可选择外部 Agent CLI，但真实模型从头到尾自主完成的路径尚未验收。

新 Mac 和手机先运行 `sh scripts/bootstrap-macos.sh`，再运行 `.venv/bin/copyapp onboard --stage rebuild`；同时连着多台设备时加 `--udid`。它保存 Mac 与手机能力报告及有序修复步骤。手机端服务就绪后，在一个终端持续运行 `.venv/bin/copyapp tunnel --udid <UDID>`，同时提供完整流程所需的 SSH 与 iOS MCP 转发。首次 SSH 主机指纹核对和手机配对弹窗仍需明确完成。

[Translate XR 完整案例](translate-xr-workflow.zh-CN.md)（[English](translate-xr-workflow.md)）展示了不依赖 REA 的三流程实测：iCTRL 文字输入、审阅报告、独立 UIKit 复刻、原版/复刻版真机对照以及逐张截图审阅。案例明确标出已经覆盖的行为和剩余差异。

## 1. 发现代表性流程

```sh
.venv/bin/copyapp copy --udid <UDID> --bundle <原版_BUNDLE_ID> \
  --auto-discover --agent-provider current \
  --project rebuild/<新工程> --rebuilt-bundle <复刻版_BUNDLE_ID> \
  --out cases/<新案例>
```

首次调用生成 `discovery-agent/TASK.md` 并暂停，不会先操作手机。当前 Agent 观察真实 App，在 `discovery-agent/candidates/` 编写 3–12 条不同且有界的 UI 脚本，再以同一设备、Bundle ID 和 UI 后端运行 `copyapp discover-check`，将通过的案例保存到 `discovery-agent/discovery/`。失败案例保留诊断，检查手机状态后再试。验收绑定脚本内容、设备身份和真机重放证据；它只证明选定路径，不代表覆盖整个 App。

每条脚本可包含有界点击、滑动、长按和双击。界面可观察时应加入操作后状态断言；后端接受手势调用不代表预期界面效果已发生。参数与后端差异见[中文手势指南](ui-gesture-playbooks.zh-CN.md)（[English](ui-gesture-playbooks.md)）。

涉及输入框的 App 可在聚焦空字段后使用[有界文本输入](ui-text-playbooks.zh-CN.md)（[English](ui-text-playbooks.md)）。须检查后续界面：输入 RPC 成功不代表文字已显示在 App 中。

已有验收案例可用 `--discovery <案例>`；已有脚本可重复使用 `--script <文件>`。这三种输入互斥。

## 2. 采集与解释

对完全相同的 `copyapp copy` 命令添加 `--resume`。父流程先重验发现结果，再用 `prepare-app` 采集安装包、沙盒、请求的脱壳结果及 UI/运行时调查证据。状态为 `analysis_agent_needs_review` 时，阅读 `analysis-agent/TASK.md` 和来源证据，在 `analysis-agent/reviewed-report/` 写正式报告与 `feature-spec.json`，然后运行 `copyapp analysis-delivery` 保存到 `analysis-agent/analysis-delivery/`。交付关卡检查来源身份和每条流程的证据关联；反编译函数的语义仍须由 Agent 审阅，未知部分要明确标注。

默认链路不依赖 REA。需要直接反编译时，可选 `--analysis-provider ghidra-direct --ghidra-dir <目录> --java-home <目录>`，或 `--analysis-provider hopper-direct`（可用 `--hopper-app <Hopper.app>` 指定路径）。前者需要 Ghidra 和 JDK；后者需要在正常 macOS 用户会话中运行已授权的 Hopper GUI。iOS 16.1.1 XR 上的 `investigate-flow --provider hopper-direct` 已完整运行 UI 重放、Frida 跟踪与 Hopper 反编译，结果进入校验通过的报告。完整的 Hopper `copy` 分析到复刻流程仍待测。Frida 的运行时命中与静态伪代码是不同证据，不能单凭其中一项认定完整实现。

## 3. 实现与真机对照

再次续跑后，`prepare-rebuild` 生成关联报告的复刻任务，并停在 `rebuild-agent/TASK.md`。在指定的 `--project` 编写独立 Xcode 工程，在绑定设备上安装并保存证据。开发证书签名的 IPA 可用 `copyapp install --transport usb --udid <UDID> --ipa <IPA> --out <案例>`；现有 TrollStore 安装路径仍是默认值。校验安装案例后，使用 `rebuild-task-check` 在同一 UI 后端对照原版与复刻版选定流程。逐张审阅截图，保存 `visual-review`，最后运行不带 `--run` 的 `agent-delivery`。父流程要求每条选定流程通过行为或末端视图断言、全部图片已审且无重大差异；轻微差异仍需记录。

最后一次 `--resume` 仅在所有子案例和来源关联通过时将父案例标为完成。`copyapp verify cases/<案例>` 可以重验哈希，但不能证明语义解释正确，也不能证明未测功能等价。已处于 Coding Agent 会话时不要嵌套启动 `copyapp agent-run` 或另一个 Codex/Claude 进程。

## 当前验收边界

iOS 16.1.1 的 iPhone XR 已完成 Clock 三流程的当前 Agent 父案例：正式报告、独立 App 源码、安装、3/3 行为与末端视图断言及 10 对逐张审阅的截图，截图均有轻微差异。另一个[Clock 自动发现父案例](../cases/clock-current-auto-workflow-20261016/manifest.json)使用三条先前编写的脚本，在同一案例内完成发现、报告、独立工程、安装和三流程真机交付；父案例 517 项证据文件通过校验，源码改自既有独立实现。新的[Calculator 父案例](../cases/calculator-current-auto-workflow-20261016/manifest.json)由当前 Agent 根据 XR 实际界面新写三条脚本并从空工程编写 UIKit 复刻版；三条运算流程的双端行为与末端视图断言均通过，三对截图均已审为轻微差异、无重大差异，交付与父案例通过核验。外部进程试验仍使用固定脚本。陌生 App 的普适发现、真实外部 CLI 自主闭环和全功能等价尚未验证。iPhone 14/iOS 17.3.1 已验证 USB、iCTRL、SSH 采集、iOS MCP 界面操作、开发证书签名复刻版安装、一条原版/复刻版同机运算流程，以及一款加密 App 与扩展的整包恢复；Frida 跟踪可附加前台复刻版，但系统 Calculator 仍失败。iOS 26 尚未实测。

参见 [中文 README](../README.zh-CN.md)、[英文 README](../README.md) 和 [详细试验记录](../PLAN.md)。
