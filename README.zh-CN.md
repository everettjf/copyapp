# Copy APP

[English](README.md) · 简体中文 · [繁體中文](docs/readme/README_zh-TW.md) · [日本語](docs/readme/README_ja.md) · [한국어](docs/readme/README_ko.md) · [Türkçe](docs/readme/README_tr.md) · [Русский](docs/readme/README_ru.md) · [Tiếng Việt](docs/readme/README_vi.md) · [ไทย](docs/readme/README_th.md) · [Deutsch](docs/readme/README_de.md) · [Español](docs/readme/README_es.md) · [Français](docs/readme/README_fr.md) · [Українська](docs/readme/README_uk.md) · [Polski](docs/readme/README_pl.md) · [Português (Brasil)](docs/readme/README_pt-BR.md) · [العربية](docs/readme/README_ar.md) · [فارسی](docs/readme/README_fa.md) · [Bahasa Indonesia](docs/readme/README_id.md) · [Italiano](docs/readme/README_it.md) · [Ελληνικά](docs/readme/README_el.md)

[项目网站](https://xnu.app/copyapp/) · [图文介绍](docs/articles/copyapp-overview.zh-CN.md) · [文档目录](docs/README.zh-CN.md) · [已发布版本](docs/releases/v0.1.2.zh-CN.md) · [参与贡献](CONTRIBUTING.zh-CN.md) · [Apache-2.0 许可证](LICENSE)

Copy APP 对越狱 iPhone 上已安装的 iOS App 取证分析，并协助 Coding Agent 创建**独立、可运行的 iOS App**，复现经过审阅的一组功能。它采集安装包、沙盒、界面和运行时证据，生成有来源引用的报告与功能规格，再在同一台手机上对照原版和新 App。当前正式发布版为 **v0.1.2**。

开发分支正在保留 iOS 支持的同时新增 [ChatComputer／macOS 支持](docs/macos-support.zh-CN.md)。[实施清单](docs/macos-implementation-plan.md)区分已实现基础设施与尚待完成的闭环验收；正式发布的 v0.1.2 仍为 iOS 版本。

Mac 样例：[自有行为夹具](examples/macos/BehaviorFixture/)和
[独立 Stocks 演示](examples/macos/Stocks/)；Stocks 仅覆盖选定本地行为，使用标明的离线演示数据，验收边界见样例说明。

在此分支处理 **Mac App** 时，让 Agent 阅读 `AGENTS.md` 和 `skills/copyapp-mac/SKILL.md`，可直接复制 [Mac 专用任务](docs/macos-support.zh-CN.md#交给-agent)。下方 iPhone 任务继续走原有 iOS 流程。

<a id="从这里开始"></a>

## 从这里开始：交给 Codex 或 Claude Code

在 Mac 上打开能执行本地命令的 **Codex 或 Claude Code**，用 USB 连接并解锁已越狱的 iPhone。把下面这段任务复制到 Agent 对话里，将 App 名称换成你的目标即可；不知道 Bundle ID 也没关系。

```text
请使用 https://github.com/everettjf/copyapp，帮我分析并复刻 USB 连接的越狱 iPhone 上的「App 名称」。
如果还没有检出项目，请克隆到一个新目录；已有检出则在其中工作。
先阅读 AGENTS.md 和 skills/copyapp-start/SKILL.md，检查并配置环境，识别准确的手机和 App，再完成分析、独立实现、真机安装与同机对照。
能直接执行的步骤请替我完成；需要我在手机上确认或补充目标信息时，再告诉我具体操作。最后给我报告、可运行工程、已验证的功能和剩余差异。
按 docs/fidelity.md 执行：目标默认 80/100 分，最多三轮实现／检查（首轮计入）。达标或耗尽轮数就停止；未达标和剩余差异如实报告。
```

Agent 会读取仓库里的[首次使用 Skill](skills/copyapp-start/SKILL.md)，再按任务调用分析、复刻和验收流程。**你不需要逐条输入下方的 CLI 命令，也不需要先安装某个专属扩展。** Mac 环境由 Agent 检查和配置；手机信任、首次授权和签名条件仍可能需要你参与。

只想先分析，把第一句改成“帮我分析……，这次先不复刻”；只想检查连接，改成“完成并校验首次 USB survey 后停止”。更多任务示例见[交给 Agent 的首次运行任务](docs/first-run-agent.zh-CN.md)。喜欢自己操作 CLI，可以直接看[手动安装与首次采集](#手动安装与首次采集)。

开发分支默认 **80 分、最多三轮**；快速原型可选 70，精细复刻可选 90。核心选定行为须通过，
其余视觉差异明确保留，不再无限打磨。该分数与客观图像相似度、已知能力覆盖率分开。
[有界复刻流程](docs/fidelity.md)使用 `fidelity-plan --fidelity 80 --max-iterations 3`；
旧严格交付和独立父工作流仍保留原验收语义。

## 架构一览

![Mac 与指定越狱 iPhone 通过 USB 协作，完成分析与对照](docs/assets/social/01-system-map.png)

Mac 协调 Coding Agent、证据与构建；指定的 iPhone 提供 App 文件和观察结果。组件边界和证据关系见[详细架构说明](docs/architecture.zh-CN.md)。

## 两项交付

1. **分析：**固定手机和 App 版本；检查安装包、Mach-O、依赖库、类、资源和有界沙盒元数据；采集选定界面、操作与运行轨迹；审阅带证据 ID、实现推断和未知项的报告。
2. **复刻：**依据已知能力清单选定阶段目标；实现独立 Xcode 工程；构建、签名、安装；在原版与复刻版重放同一组流程，逐张审阅截图并报告实际覆盖与差异。

简单 App 可以设较完整的阶段目标。复杂 App 应先选定有用的功能范围；只有明确已知能力的分母，百分比才有意义。选定流程通过不代表整 App 等价。详见[覆盖目标方法](docs/coverage-targets.zh-CN.md)。

Mac 负责编排和构建。OpenSSH 采集文件，iOS MCP 提供越狱环境下的界面观察与控制，iCTRL 是可选的 XCTest 界面后端，Frida 用于有界运行时取证。Ghidra 和 Hopper 是可选的本机代码分析工具，**不依赖 REA 运行**。详见[架构说明](docs/architecture.zh-CN.md)。

[示例工程](examples/README.md)已集中在 `examples/rebuild/`；下文命令中的 `rebuild/<NEW_PROJECT>` 是用户新建工程的输出位置。

### 证据、对照与交付

![安装包、沙盒、界面和运行时证据汇入有来源的报告；Hopper 片段是已保存证据的示意图](docs/assets/social/02-evidence.png)

![iPhone 14 上原版 Calculator 与独立复刻版完成选定的 7 + 8 = 15 流程](docs/assets/social/03-calculator-comparison.png)

![两项交付：有来源的分析报告，以及标明覆盖与缺口的独立可运行 iOS App](docs/assets/social/04-deliverables.png)

这些图说明工作流和经过筛选的公开观察。Calculator 对照仅覆盖一条指定流程，仍有视觉差异；Hopper 片段展示保存的证据，并非恢复出的原始源码。详见[真机证据与限制](docs/current-status.zh-CN.md)。

## 当前 `main` 的实测范围

以下结论只适用于指定手机和选定流程，不保证任意设备或 App 兼容。[当前状态](docs/current-status.zh-CN.md)记录 v0.1.2 的范围及剩余问题。

| 手机 | 越狱方式与已测范围 | 当前限制 |
| --- | --- | --- |
| iPhone XR · iOS 16.1.1 | Dopamine rootless；SSH、Frida、iOS MCP 与 iCTRL；Notes、Calculator、Translate 和 Clock 的选定分析／复刻路径 | 可选的开发者文件列表可能报 `ConnectionTerminatedError`；SSH 包／沙盒采集可用。 |
| iPhone 14 · iOS 17.3.1 | Relaxin/RootHide；原版 Calculator 采集、Frida 跟踪，以及经 iOS MCP 完成四条原版／独立 App 运算对照 | v0.1.2 修复 v0.1.1 的 iCTRL 会话故障，两轮各四条成对流程通过；重启及其他设备上的新清理逻辑仍待复验。 |
| iPhone 11 · iOS 26.0.1 | Relaxin/RootHide；Calculator、Clock 原版分析、签名独立 App 和选定运算／秒表成对检查 | iOS MCP 新启动后可能得到黑帧；已观察的故障经有界返回主屏／重启恢复。 |

尚未证明整 App 功能覆盖、无视觉差异、重新越狱后的长期稳定，或第二台实体 Mac 的全新配置。原始 IPA、完整案例截图、沙盒内容和凭据只保存在被 Git 忽略的本地目录（案例为 `cases/` 或任务 `output/`，凭据沿用原存储），不作为发布附件；文档中的少量 Calculator 示意画面经过单独筛选。

## 手动安装与首次采集

以下是给手动使用 CLI 的读者准备的入口。通过 Agent 使用时，它会执行这些步骤。第一次 USB 采集需要 Python 3.9+、已解锁并连接的 iPhone，以及手机上的“信任此电脑”；这个阶段无需 tweak、SSH、Frida 或 Xcode 签名。

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
.venv/bin/copyapp apps --udid <UDID> --all
```

在手机上打开目标 App，确认准确的 Bundle ID，再采集并校验：

```sh
.venv/bin/copyapp survey --udid <UDID> --bundle <BUNDLE_ID> \
  --ui-backend usb --out cases/first-survey
.venv/bin/copyapp verify cases/first-survey
```

阅读 `cases/first-survey/report.md`，每次重试使用新的输出目录。完整分析还需 OpenSSH、精确设备 SSH 路由、Copy APP iOS MCP tweak 和兼容的 Frida 服务；iCTRL 按需加入。复刻另需完整 Xcode、签名团队或 TrollStore。用 `onboard --stage analyze` 和 `doctor --udid <UDID>` 检查就绪情况，按[完整安装指南](docs/setup.zh-CN.md)及[分析到复刻工作流](docs/copy-workflow.zh-CN.md)继续。

## 运行完整分析到复刻流程

在当前 Codex 或 Claude Code 会话中执行：

```sh
.venv/bin/copyapp copy \
  --udid <UDID> --bundle <ORIGINAL_BUNDLE_ID> \
  --auto-discover --agent-provider current \
  --rebuilt-bundle <NEW_BUNDLE_ID>
```

新任务默认写入工作区的 `output/<Bundle ID>-<UTC 时间>-<唯一编号>/`：
`project/` 放独立源码，`evidence/` 放报告、截图及检查结果。
可用 `--output-dir output/my-job` 自定义任务目录，也保留原有的
`--project <源码目录> --out <案例目录>`。路径须位于所选工作区内
（可用 `--workspace <目录>`）；仓库根目录的 `output/` 已被 Git 忽略，现有示例和案例不移动。
续跑时固定命令打印的 `--output-dir`（或原有 `--out`、`--project`），
其余设置保持相同，再加 `--resume`；不会自动猜测最近一次任务。

命令会在流程发现、正式分析报告和独立实现三个环节暂停，等待当前 Agent 完成并校验交付；每次用原参数加 `--resume` 续跑。`current` 不会启动嵌套 Agent。独立 CLI 进程可选 `--agent-provider codex` 或 `claude`。若已有流程，可用 `--discovery <CASE>` 或重复的 `--script <FILE>` 替代 `--auto-discover`。命令与门槛见[工作流指南](docs/copy-workflow.zh-CN.md)。

## 项目理念与贡献

把原始观察与解释分开。重要结论绑定设备、App 构建和可校验来源；保留失败尝试和未知项。原版与复刻版应从可比状态对照，只报告真正测过的行为。保留所用上游项目的署名和许可证。欢迎改进安装体验、有界分析、可重现真机检查、无障碍支持和翻译；见[贡献指南](CONTRIBUTING.zh-CN.md)。

## 许可证

Copy APP 自有代码和文档采用 [Apache License 2.0](LICENSE)。仓库中引用或改造的第三方材料保留各自的许可和署名：[iOS MCP](device/ios-mcp/LICENSE) 为 MIT，[iCTRL](vendor/ictrl/LICENSE) 为 Apache-2.0，保留的 [REA 许可证](docs/third-party/REA-LICENSE.txt)为 MIT。项目主许可证不会替代这些上游声明。

## 致谢

Copy APP 使用或参考 [witchan/ios-mcp](https://github.com/witchan/ios-mcp)、[OpenMinis/iCTRL](https://github.com/OpenMinis/iCTRL)、[Frida](https://frida.re/)、[pymobiledevice3](https://github.com/doronz88/pymobiledevice3)、[londek/ipadecrypt](https://github.com/londek/ipadecrypt)、[Ghidra](https://github.com/NationalSecurityAgency/ghidra) 和可选的 [Hopper](https://www.hopperapp.com/)。Hopper 直连接口曾参考 MIT 许可的 REA 实现，许可证保存在 [docs/third-party/REA-LICENSE.txt](docs/third-party/REA-LICENSE.txt)。iCTRL 的准确来源、许可和本地改动见[上游记录](vendor/ictrl/UPSTREAM.md)。
