# 分析到复刻工作流

[English](copy-workflow.md) · 简体中文 · [文档目录](README.zh-CN.md)

Copy APP 对精确指定的一台手机与一个已安装 App 构建运行可续跑、有证据门槛的流程。先按[安装指南](setup.zh-CN.md)配置并运行 `copyapp doctor`。在现有 Codex 或 Claude Code 会话中使用 `--agent-provider current`：它等待当前 Agent 完成任务，不会再启动一个 Agent 进程。需要独立 CLI 进程时才选择 `codex` 或 `claude`。

## 1. 发现代表性行为

```sh
.venv/bin/copyapp copy --udid <UDID> --bundle <ORIGINAL_BUNDLE> \
  --auto-discover --agent-provider current \
  --rebuilt-bundle <NEW_BUNDLE>
```

新任务默认写入工作区的 `output/<Bundle ID>-<UTC 时间>-<唯一编号>/`：
`project/` 放独立源码，`evidence/` 放报告、截图及检查结果。
可用 `--output-dir output/my-job` 自定义任务目录，也保留原有的
`--project <源码目录> --out <案例目录>`。路径须位于所选工作区内
（可用 `--workspace <目录>`）；仓库根目录的 `output/` 已被 Git 忽略，现有示例和案例不移动。
续跑时固定命令打印的 `--output-dir`（或原有 `--out`、`--project`），
其余设置保持相同，再加 `--resume`；不会自动猜测最近一次任务。

首次暂停会生成 `discovery-agent/TASK.md`。观察真实 App，写 3–12 条不同的有界 UI 脚本。每条应标明起始页面、包含有意义的操作、尽可能断言可见末端状态并保存稳定截图。按任务要求运行 `copyapp discover-check`，校验案例后用**完全相同**的 `copy` 参数加 `--resume` 续跑。已有脚本可重复传 `--script <FILE>`；已校验的发现案例可用 `--discovery <CASE>`。这两种方式替代 `--auto-discover`。

每条 playbook 只使用一个 UI 后端。原版与复刻版对照时使用同一后端、对齐起始状态。操作边界见[手势](ui-gesture-playbooks.zh-CN.md)和[文字输入](ui-text-playbooks.zh-CN.md)指南。RPC 返回成功不是结果断言。保留失败或结果不明的尝试；再次点击前先查看当前画面。

## 2. 采集并解释证据

发现案例通过后，`copy` 采集包、沙盒、界面与请求的运行证据，再于 `analysis-agent/TASK.md` 暂停。阅读二进制索引、界面、轨迹及可选的 Ghidra/Hopper 伪代码；撰写审阅过的 `findings.json`、`feature-spec.json`，按任务创建并校验正式 `copyapp report` 与 `analysis-delivery`。`analyze` 生成的 `analysis.md` 只是采集索引。每条重要功能结论都要有来源案例，标明观察或推断；未知的服务端或原生行为仍标为未知。

加密二进制可能需要[分析 IPA 恢复](full-package-decryption.md)。如果已安装 Mach-O 本来就未加密，只记录来源快照，不称为“解密成功”。Ghidra 与 Hopper 可选；[直连 Hopper](rea-hopper-integration.zh-CN.md)不依赖 REA。静态候选函数与相近时间的 Frida 命中是两种不同证据。

实现前盘点已知的用户可见能力，并设定[审阅后的覆盖目标](coverage-targets.zh-CN.md)。用 `coverage-plan` 固定目标、选定流程、权重与延期／阻塞项。清单不够确定时，使用有名字的目标，不给出无法支撑的百分比。

## 3. 构建、安装和对照

继续续跑父流程。`prepare-rebuild` 生成 `rebuild-agent/TASK.md`。在指定路径实现独立 Xcode 工程，使用不同的 Bundle ID，在精确选定的手机上构建、签名并安装。开发签名 IPA 的命令：

```sh
.venv/bin/copyapp install --transport usb --udid <UDID> \
  --ipa <SIGNED_IPA> --out cases/<INSTALL>
.venv/bin/copyapp verify cases/<INSTALL>
```

适配的包也可走 TrollStore。安装案例不证明启动或功能等价。运行任务要求的原版／复刻版成对检查，逐张查看截图，保存明确的 `visual-review`，再以 `agent-delivery` 绑定源码、安装和检查案例。改变数据的流程还应对照相关沙盒内容的前后变化；界面计数一致不代表持久化一致。模拟服务端行为必须标注为模拟。

子案例均通过后再次续跑 `copy`。完成的父案例说明选定证据门槛通过；`copyapp verify cases/<WORKFLOW>` 复核保存哈希与来源链接，不证明语义正确或其他流程。最后运行 `coverage-delivery`，对每项已知能力给出审阅结论。分别报告目标覆盖、阶段完成度、已验证的已知覆盖；分母必须有依据，并列出未知项。

指定设备结果及限制见[当前状态](current-status.zh-CN.md)。原始案例只保存在被 Git 忽略的本地目录。
