# Copy APP

第一版正在实现“分析 → 复刻 → 真机对照”流程。Mac 端通过 USB 读取安装信息、屏幕与无障碍元素；通过越狱机上的 SSH 只读导出包和索引数据沙盒；本地解析 Mach-O。iOS MCP 的截图、前台识别、App 启动和点击已在 iPhone XR 上验收。原版 Compass 的关键交互已取得 Frida 调用证据；DeepSeek 和 Kimi 的主程序及扩展也已在 XR 上自动恢复为完整可分析 IPA。按用户当前安排，iOS 17/26 两台设备暂不验收；一键生成完整复刻仍在开发。

REA 不属于正式链路的运行依赖。深入函数分析优先用 Copy APP 直连 Ghidra；旧 REA 入口保留作可选兼容。代码借鉴、许可及尚未移植的能力见[独立运行边界](docs/rea-independence.md)。

当前最完整的真实 App 示例是 XR 上的 [DeepSeek 综合逆向报告](cases/deepseek-comprehensive-xr-20261015/report.md)：以 `copyapp report-portfolio` 核对同设备、同 App 版本及同一解密主程序，汇合三条登录页的 UI/函数/网络分析和另一次沙盒/SQLite 结构分析。报告保留两轮证据的各自时点；原始数据库和 IPA 仍在忽略的本地 `cases/` 中。登录后功能、从零自动生成完整复刻和 iOS 17/26 仍未验收。

一个新的无账号系统 App 试点也在 XR 上完整经过三条流程发现、无 REA 包与函数分析、正式报告、独立源码、TrollStore 安装和同机对照：[Clock 报告](cases/clock-three-flow-no-rea-reviewed-report-v3-20261015/report.md) → [复刻任务](cases/clock-three-flow-rebuild-preparation-v4-20261015/task/TASK.md) → [Copy Clock 源码](rebuild/ClockClone) → [交付核验 v9](cases/clock-three-flow-agent-delivery-v9-20261015/report.md)。世界时钟城市选择、未保存闹钟编辑和计时器铃声选择的 3/3 条脚本及末端 UIKit 断言通过；9 对截图均已逐张审阅，没有重大视觉差异，三个流程仍有轻微差异。首屏截图曾在 UIKit 尚未完成绘制时采集到缺失的导航栏，重放器现在对启动、底部标签切换和稳定截图增加就绪等待。该试点没有实现 Clock 的保存、倒计时和后台能力，也没有证明独立终端的一命令 Agent 流程。

Clock 试点现已扩展到四个主标签：[四流程分析报告](cases/clock-four-flow-no-rea-reviewed-report-v5-20261015/report.md)引用 Stopwatch 的 Start、Stop、Reset 三个同二进制方法在对应点击窗口的 Frida 命中和 Copy APP 直连 Ghidra 伪代码。[四流程复刻任务](cases/clock-four-flow-rebuild-preparation-v7-20261015/task/TASK.md)与[XR 交付核验](cases/clock-four-flow-agent-delivery-v1-20261015/report.md)记录 4/4 行为断言、4/4 末端 UIKit 断言和 13 对已审截图；均有轻微视觉差异，没有重大差异。复刻版 Stopwatch 可开始、暂停、重置并显示当前分段；多分段、后台计时、闹钟保存和 Timer 倒计时仍未验证。`rebuild-check` 现允许有界区域内的系统 `MTUITimeView` 文本作为末端断言，不会把屏幕外的同名视图当作通过。

新生成的直接 Ghidra 案例包含有界 `function-facts.json`（函数签名、静态调用者与被调用者）及对应的 REA MIT 许可副本；[XR 导出分享扩展的真实案例](cases/fixture-share-direct-facts-license-20261015/summary.json)已通过来源校验。静态关系不代表这些调用在某次点击中执行。
`function-facts.json` v2 又加入有界基本块、指令引用和可识别字符串的短预览；XR 导出分享扩展的[真实 Ghidra 输出](cases/fixture-share-direct-topology-v3-20261015/function-facts.json)与[报告导入](cases/fixture-share-direct-topology-report-20261015/report.md)已验证。旧 v1 证据仍可校验。这些线索是静态分析，不能代替真机分支轨迹。

## 独立终端的一命令入口

当目标 App 的代表性原版 playbook 已确定，并且手机、脱壳 helper、Codex 或 Claude Code CLI 已就绪，可在**独立终端**运行：

```sh
.venv/bin/copyapp copy \
  --udid <UDID> --bundle <ORIGINAL_BUNDLE_ID> \
  --script playbooks/<FLOW_1>.json --script playbooks/<FLOW_2>.json \
  --script playbooks/<FLOW_3>.json \
  --project rebuild/<NEW_CLONE> --rebuilt-bundle <NEW_BUNDLE_ID> \
  --agent-provider codex --out cases/<NEW_WORKFLOW_CASE>
```

它顺序执行 `prepare-app`、经过交付核验的分析 Agent、`prepare-rebuild`、经过真机交付核验的复刻 Agent；默认整包脱壳、采集网络元数据且不依赖 REA。需要直接 Ghidra 函数证据时，可加 `--analysis-provider ghidra-direct --ghidra-dir <GHIDRA_DIR> --java-home <JDK_HOME>`。`copyapp verify cases/<NEW_WORKFLOW_CASE>` 会重验最终的来源链。成功只表示选定流程具备来源关联的报告、行为断言、逐图审阅和无重大视觉差异；其余页面与服务端行为保留为未验证。若 Agent 阶段失败，案例保存现场，`--resume` 复用已经通过的阶段，但不会自动再次运行可能改动手机状态的失败 Agent；审阅其输出后使用新的案例重试。当前这条总入口已通过模拟 Agent 的完整路径与拒绝测试，尚未从独立终端用真实 Agent CLI 完成端到端实跑。它仍要求先选出代表性脚本，不能仅凭 App 名称自动发现全部功能。

用户只给 App 时，当前 Codex/Claude 可按 [`copyapp-copy` Skill](skills/copyapp-copy/SKILL.md) 观察首页并编写三条代表性脚本。`copyapp discover-check --udid <UDID> --bundle <BUNDLE> --script <FLOW> ... --out cases/<DISCOVERY>` 先检查脚本身份、不同点击路径和有界步骤，再在同一手机上重放每条流程；`copyapp copy` 可用 `--discovery cases/<DISCOVERY>` 直接读取验收后的脚本副本。XR 上三条 DeepSeek 登录页脚本的[实测发现验收](cases/deepseek-three-flow-discovery-check-live-20261015/report.md)和父案例哈希均通过。脚本仍由 Agent 按真实界面编写，自动发现任意 App 全部页面的能力尚未验证。

## iPhone XR 实测（iOS 16.1.1）

- USB 配对、系统与 App 信息、Developer Disk Image 挂载、截图、无障碍读取和 App 包目录索引已通过。`/var/jb` 可列出，包含 Dopamine 与 Procursus 标记。
- `copyapp doctor` 已在 XR 上保存一次可复核的设备能力基线：精确 USB 身份、截图、DVT 文件访问、已配对 mobile SSH、Frida 进程枚举、iOS MCP 与 iCTRL 均通过；证据在本地 `cases/xr-doctor-20261015/`。该结果不推断另两台手机的兼容性。
- XR 重新连接后，`cases/xr-no-rea-doctor-reconnected-20261015/` 再次检出上述八项能力。新跑的 `cases/deepseek-no-rea-reconnected-live-20261015/` 使用 `prepare-app --decrypt --network --provider none` 完成 DeepSeek 密码入口的一命令采集、整包恢复和待语义审阅任务，父案例通过 `copyapp verify`；分析 IPA 的 SHA-256 与此前两次恢复一致。该任务仍需 Coding Agent 解读证据，不能把采集完成当作全面报告。
- 对 `com.apple.tips` 的采集发现这台设备的 Tips 被 TrollStore 用作持久化入口：当前界面实际为 TrollStore Helper，因此更换 `com.apple.compass` 为实测目标。
- Compass 已采集到主界面截图、无障碍元素、安装元数据和包目录索引，证据哈希校验通过。截图含设备位置，默认仅保存在本地。
- 第二个目标 Calculator (`com.apple.calculator`) 已在同一 XR 完成包、UI、沙盒索引和实机运算。REA/Hopper 与 Ghidra 把按钮入口追到 Swift 分支，Frida 证明系统可访问性替换层之后仍进入主程序原始方法，并观察到私有 Calculate.framework 的 `CalculatePerformExpression` 接收 `(7)+(8)`、返回 `15`。新增的乘法、正负号、小数点和除零流程也取得逐点击分支轨迹；九条规格与 56 组证据进入[Calculator 深度报告 v21](cases/calculator-xr-deep-report-v21-20261015/report.md)，哈希校验通过。横屏、科学模式及更多边界仍待测。
- Calculator 的三条流程现又在 XR 上重新采集了 `buttonPressed:` 当前 IMP 与主程序入口的逐次原始第 3 参数；同一点击两端读数相同。`flow-capture` 的受限 `--branch-offset` 还对五个下游入口做了逐步真机计数：数字、加号、百分比、等号和清除均命中 Ghidra 静态分发表预测的入口，详见[按钮分发记录](docs/calculator-button-dispatch-xr.md)。`investigate-flow` 对选中的 `buttonPressed:` 自动保留原始参数；分支函数内部状态和完整算法仍待解释。
- [Copy Calculator](rebuild/CalculatorClone) 已编译为独立 iOS 16 App，经 TrollStore 安装至 XR；当前 0.1.10 (11) 的九条选定流程均通过末端 UIKit 断言，[真机对照](cases/calculator-nine-flow-rebuild-check-v11-20261015/report.md)、[字体与显示区复核](docs/calculator-typography-xr-review.md)及[逐图审阅交付](cases/calculator-agent-delivery-visual-reviewed-v11-20261015/report.md)均保存证据。18 对截图已记录轻微差异，没有宣称像素级一致。
- 无 REA 的独立路径也在 XR 上走到了复刻交付：[原版分析报告](cases/calculator-no-rea-reviewed-report-20261015/report.md) → [自动复刻任务](cases/calculator-no-rea-rebuild-preparation-v4-20261015/task/TASK.md) → [同机脚本对照](cases/calculator-no-rea-rebuild-check-20261015/report.md) → [逐图审阅与交付](cases/calculator-no-rea-agent-delivery-20261015/report.md)。`7 + 8 = 15` 的末端 UIKit 断言通过，两对画面均有轻微差异。该链复用了已存在的 CalculatorClone 0.1.10 源码和安装包，证明无 REA 报告可以驱动任务与验收，但不证明从报告自动生成了源码或完整 App 等价。
- 加密目标也已走通无 REA 的“整包恢复 → 报告 → 新源码 → XR 对照”闭环：DeepSeek 2.4.4 的[整包恢复](cases/deepseek-prepare-app-no-rea-20261015/analysis/decrypted/decryption.json)检查 32 个 Mach-O，恢复主程序和分享扩展；[限定登录入口报告](cases/deepseek-no-rea-reviewed-report-ready-20261015/report.md)与[实现任务](cases/deepseek-no-rea-rebuild-preparation-ready-20261015/task/TASK.md)通过来源校验。独立编写的 [DeepSeekClone](rebuild/DeepSeekClone) 在 XR 上安装并对照，密码入口弹出条款框，初始/末端脚本断言及末端 UIKit 文字断言通过；[交付记录](cases/deepseek-no-rea-agent-delivery-20261015/report.md)如实标记两对截图有明显视觉差异。它只覆盖未同意条款前的一次交互，不涉及账号认证或登录后功能。
- 默认无 REA 调查现可在静态方法名不唯一时，从操作前 UIKit 树的可见按钮类筛选动作入口。[DeepSeek 真机自动入口案例](cases/deepseek-no-rea-auto-method-investigation-20261015/manifest.json)没有传 `--method` 或 REA provider，自动选出 `DSButton::objcOnTap`，Frida 记录一次点击时当前 IMP 与主程序静态入口各命中一次，原生汇编完成。视图类只用于提出候选，运行时轨迹仍需人工解释。[无 REA 路径与边界](docs/no-rea-analysis.md)。
- 无 REA 的 DeepSeek 深入路径现把真机 `blr x19` 回调目标纳入 Copy APP 自身的 Ghidra 队列：[三函数案例](cases/deepseek-direct-ghidra-indirect-profiled-queue-20261015/queue.json)一次导入反编译按钮入口、静态直接目标及运行时间接目标，来源与地址链通过语义校验。回调层继续指向本机函数，当前没有把条款弹窗的具体生成代码或登录后行为断定为已还原。
- 新的 `copyapp ghidra-indirect` 可从已验证调查自动找出有限 `blr` 位点，在 XR 上重放原版脚本并把实际寄存器目标接进 Ghidra，无需 REA 或手填分支地址。[组合案例](cases/deepseek-ghidra-indirect-one-command-20261015/manifest.json)通过指令字节、跨阶段身份及语义校验；更新的[限定范围报告](cases/deepseek-no-rea-indirect-profile-report-v2-20261015/report.md)和[复刻任务](cases/deepseek-no-rea-indirect-agent-task-v2-20261015/TASK.md)把三层函数证据交给 Coding Agent。现有复刻版在 XR 的[交付复验](cases/deepseek-no-rea-indirect-agent-delivery-v2-20261015/report.md)通过 1/1 条行为断言，两个画面仍有较大视觉差异。
- XR 又在同一密码入口步骤观测到内层 `blr x19` 指向 `0x1002f908c`，并在独立重放中直接命中该回调入口。Copy APP 直连 Ghidra 的函数伪代码与这些运行时观察已进入[深入报告 v3](cases/deepseek-no-rea-nested-profile-report-v3-20261015/report.md)和[新复刻任务](cases/deepseek-no-rea-nested-rebuild-preparation-v3-20261015/task/TASK.md)；它们都通过来源校验。回调入口被执行，不等于条款弹窗的构造路径或同意后的导航已完全确定。
- [深入报告 v4](cases/deepseek-no-rea-privacy-profile-report-v4-20261015/report.md)进一步结合 Ghidra 与 XR 逐步跟踪：隐私检查函数读取 `LoginCheckBox.checked`，点击窗口里它、`0x1002b0268` 和另一条大函数 `0x10074f5b4` 分别命中；报告明确记录 `0x1002b0268` 的内层间接调用目标更像清理路径，未把它误作弹窗显示函数。[复刻任务 v4](cases/deepseek-no-rea-privacy-rebuild-preparation-v4-20261015/task/TASK.md)在 XR 又完成原版/复刻版对照，[交付复验](cases/deepseek-no-rea-privacy-agent-delivery-v4-20261015/report.md)为 1/1 条行为断言通过、两张截图均有重大视觉差异。实际弹窗构造细节仍待进一步函数分析。
- [深入报告 v5](cases/deepseek-no-rea-privacy-chain-report-v5-20261015/report.md)纳入 Copy APP 直连 Ghidra 对 `0x10074f5b4` 的完整函数伪代码和有界调用关系：可见 `AlertManager` 装配 `UIWindow`、`DSLoginModal2` 的取消/确认按钮、根视图控制器和显示窗口的调用；该函数在 XR 的目标点击窗口实际命中。[复刻任务 v5](cases/deepseek-no-rea-privacy-rebuild-preparation-v5-20261015/task/TASK.md)已从此报告生成。Swift 参数、按钮回调和同意后的行为尚未还原。
- DeepSeekClone 0.1.2 (3) 已按上述报告补上独立重绘的鲸鱼图形、按钮图标和条款强调文字，并在同一 XR 上重新安装及[逐流程对照](cases/deepseek-no-rea-privacy-rebuild-check-v6-20261015/report.md)。密码入口的末端 UIKit 断言 1/1 通过；[逐图审阅](cases/deepseek-no-rea-privacy-visual-review-v6-20261015/report.md)将两张截图的差异均记录为轻微，[交付核验](cases/deepseek-no-rea-privacy-agent-delivery-v6-20261015/report.md)保留对应源码与 IPA。鲸鱼轮廓和字标仍有差别；没有扩展到登录后功能。
- IPA 静态索引现在自动读取可用的 `Assets.car` 命名资源、类型、像素尺寸及变体，并对单独的 `copyapp ipa` 产物保存可校验的来源清单。DeepSeek 解密分析包的[资源索引](cases/deepseek-assets-index-20261015/ipa-report.md)记录 198 个名称，含 `Auth/google`、`Auth/apple`、`Login/lock` 和 `deepseekWhaleIcon`；[深入报告 v6](cases/deepseek-no-rea-assets-report-v6-20261015/report.md)将它们与原包哈希绑定，[复刻任务 v6](cases/deepseek-no-rea-assets-rebuild-preparation-v6-20261015/task/TASK.md)可直接引用。目录不导出图像像素，也不证明具体界面使用了哪个资源变体。
- [DeepSeek 三流程报告 v7](cases/deepseek-no-rea-three-flow-report-v7-20261015/report.md)新增注册入口弹窗和条款取消路径。XR 的注册入口在点击窗口命中隐私检查与模态窗口装配函数各一次，却未命中密码入口所用的 `DSButton::objcOnTap` 两个钩点；不能据此合并两者的顶层回调。Copy APP 的末端 UIKit 断言现支持 `absent`，可检查取消后弹窗按钮消失。[三流程任务](cases/deepseek-no-rea-three-flow-rebuild-preparation-v7-20261015/task/TASK.md)已生成；DeepSeekClone 0.1.3 (4) 在 XR 的[真机对照](cases/deepseek-no-rea-three-flow-rebuild-check-v7-20261015/report.md)通过 3/3 条所选行为及末端断言，[六张画面审阅](cases/deepseek-no-rea-three-flow-visual-review-v7-20261015/report.md)均为轻微差异，[交付核验](cases/deepseek-no-rea-three-flow-agent-delivery-v7-20261015/report.md)可复查源码与 IPA。取消流程曾有两次原版点击没有弹框，失败尝试保存在对照案例；独立有界跟踪和恢复重放成功。三条流程都限于未同意条款的登录页，尚不能代表完整 App。
- `prepare-analysis` 现能对同一 App 的多条原版脚本断点续跑：失败的流程采集会先归档到 `attempts/`，已完成的流程继续复用。XR 的[三流程准备案例](cases/deepseek-no-rea-three-flow-analysis-preparation-v8-20261015/manifest.json)完成 3/3 条采集；它生成的是待语义审阅任务。[来源绑定的报告 v10](cases/deepseek-no-rea-three-flow-network-report-v10-20261015/report.md)与[分析交付](cases/deepseek-no-rea-three-flow-network-delivery-v10-20261015/report.md)已校验 3/3 条脚本，并加入登录页网络观察与重复重放的时间边界。全程未调用 REA；现有结论仍限于登录页，交付校验不代替对函数解释的人工审阅。
- DeepSeekClone 0.1.3 (4) 又在 XR 上按 v10 报告完成[三流程复刻任务](cases/deepseek-three-flow-rebuild-preparation-v10-20261015/task/TASK.md)、[原版/复刻版真机对照](cases/deepseek-three-flow-rebuild-check-v10-20261015/report.md)、[六对截图逐张审阅](cases/deepseek-three-flow-visual-review-v10-20261015/report.md)和[交付核验](cases/deepseek-three-flow-agent-delivery-v10-20261015/report.md)：密码入口、Sign up、Cancel 的操作后及末端 UIKit 断言均为 3/3 通过；每条流程都有轻微视觉差异，没有未审图片。源码与已安装 IPA 已封存并通过哈希校验；没有独立 Agent CLI 自动生成源码的记录。完整范围与限制见[XR 三流程验收](docs/deepseek-three-flow-xr-verification.md)。
- `prepare-app --decrypt --network` 已在同一 XR 对 DeepSeek 三条原版登录流程走通从安装包采集、整包恢复到 UI/Frida/URLSession 观察及[待审任务](cases/deepseek-three-flow-prepare-app-network-live-20261015/preparation/draft/TASK.md)；父案例通过核验，重复 `--resume` 未增加设备采集次数。设备 helper 重新打包的 ZIP 时间戳曾使相同代码产生不同 IPA 哈希；Copy APP 现核对其他成员后保留源 ZIP 元数据。更新后的[单流程完整入口](cases/deepseek-canonical-prepare-app-network-live-20261015/manifest.json)在 XR 产生与两份既有恢复案例归一化后相同的 IPA 哈希，详见[整包恢复记录](docs/full-package-decryption.md)。
- [FixtureClone](rebuild/FixtureClone) 已作为第二种技术栈试点在 XR 编译、安装和实测：[夹具报告 v14](cases/fixture-xr-deep-report-v14-20261015/report.md)到[三流程任务](cases/fixture-rebuild-preparation-v2-20261015/task/TASK.md)均可校验；[交付记录](cases/fixture-clone-agent-delivery-v1-20261015/report.md)显示 SwiftUI Counter、UIKit/SQLite Notes、Framework Catalog 三条操作后断言通过。Counter/Notes 的已有数据基线不同，截图已明确记为重大差异。证据范围见[真机验证记录](docs/fixture-clone-xr-verification.md)。
- 同版 Calculator 复刻又在 XR 上完成除零、小数加法、正负号加法及乘法四组原版/复刻版重放；`Error`、`0.3`、`3`、`63` 四个末端 UIKit 结果均在两边通过精确断言，9 对截图的区域差异另做诊断。证据和未覆盖范围见 [补充运算验证](docs/calculator-edge-xr-verification.md)；完整视觉和全功能等价仍未确认。
- UI playbook 的 `tap_label` 现支持可选 `region_points: [x1,y1,x2,y2]`，同名元素只在指定点坐标区域内匹配。XR 小数加法已用 iOS MCP 和 iCTRL 两套后端区分显示区与零键，原版和复刻版均重测通过；详见[补充运算验证](docs/calculator-edge-xr-verification.md)。
- 报告 v21 自动生成的[九流程复刻计划](cases/calculator-rebuild-plan-v5-20261015/runbook.md)和 [Agent 任务](cases/calculator-agent-task-v3-20261015/TASK.md)均无原版脚本缺口；当前 0.1.10 的 [XR 统一对照](cases/calculator-nine-flow-rebuild-check-v11-20261015/report.md)有 9/9 末端 UIKit 断言通过。18 对截图的区域平均差比 0.1.6 降低约 57%；之后的[逐图审阅](cases/calculator-nine-flow-visual-review-v11-20261015/report.md)将全部 18 对标为轻微差异，[交付案例](cases/calculator-agent-delivery-visual-reviewed-v11-20261015/report.md)记录 9/9 行为断言通过、视觉已审且有差异。上述结论限于保存的九条流程和画面。
- 系统 App 的数据容器未通过 House Arrest 开放。XR 已安装 Procursus 的 OpenSSH 服务端；通过 USB 端口转发和专用 SSH 公钥，以 `mobile` 账号完成只读连接。
- 已从 XR 只读导出 Compass 的 `.app` 包：55 个文件，并生成带文件哈希的清单、分析快照 IPA、Mach-O 静态索引和 Objective-C 类/方法索引（11 类、137 方法）。主程序未发现 `LC_ENCRYPTION_INFO`；本流程没有执行脱壳。该结果不能推断其他 App 的加密状态。
- 已通过 USB SSH 获取 Compass 数据容器的 24 项元数据索引（未读取文件内容），并结合 Ghidra 对 11 个本地定义的 Objective-C 类及关键方法做了初步解释。可审阅的案例见 [Compass XR 报告](docs/compass-xr-analysis.md)，机器可读的三流程目标见 [复刻规格](docs/compass-feature-spec.json)。`copyapp report` 已把 Compass 与源码已知夹具的分散证据组装为带证据 ID、函数伪代码、动态实验和完整方法附录的可验证报告；本地结果分别在 `cases/compass-xr-deep-report-v15-20261015/` 与 `cases/fixture-xr-deep-report-v12-20261015/`。Compass 报告包含双向方位锁定实验、运行时 IMP 与静态模块偏移核对、Hopper/Ghidra 对关键函数的交叉分析、45° 受控扇区实测、地图 URL 运行时证据，以及定位授权变化时的静态函数链和拒绝授权的真机界面。夹具报告还包含笔记操作前后的沙盒元数据差异、SwiftUI Counter 页的视图/无障碍联合观察，以及 Counter、Notes 和 Catalog 三条一命令调查证据。两份最新报告的每条复刻流程都引用已导入的证据 ID。
- Frida 方法计数器已在 Copy Compass 和原版系统 Compass 中真机挂载；`experiment` 把启动、挂载、点击、前后截图与调用计数串成无需手机端输入的实验。原版 Compass 的一次方位盘点击记录到三个方位相关方法各调用一次。
- `decrypt-main` 已在 XR 上对磁盘 `cryptid=1` 的 Kimi 3.0.9 主程序完成真实运行时恢复；旧的单主程序分析包正确报告另外 3 个扩展仍加密。新的 `decrypt-package` 在同一手机上自动恢复 DeepSeek 的 2 个、Kimi 的 4 个原加密可执行文件，并分别检查包内 32、17 个 Mach-O，全部通过；见 [整包脱壳实测](docs/full-package-decryption.md)与 [Kimi 试点](docs/kimi-decryption-pilot.md)。
- REA/Ghidra 已在源码已知的 iOS 夹具上沿 Objective-C/Swift 桥接入口追到 SQLite 建表与 `INSERT` 实现。REA/Hopper 已对 XR 导出的夹具分享扩展和真实 Compass 主程序完成函数反编译；证据分别进入夹具与 Compass 深度报告。受限执行环境中的早期超时和运行条件见 [REA 与 Hopper 集成记录](docs/rea-hopper-integration.md)。
- [源码已知测试夹具](fixture/CopyAppFixture/README.md) 已在 XR 安装并跑通 SwiftUI 计数、UIKit/SQLite 笔记和 Framework 目录三条流程。UI、沙盒内容、Frida 调用与 XR 导出二进制的 REA/Ghidra 结果见 [夹具真机验证](docs/fixture-xr-validation.md)。
- 已验证无需在手机输入的 root 操作通道：`root-run` 通过指定 UDID 的 USB Frida 服务启动一次性进程，经已配对的 mobile SSH 取回退出码和日志；执行前核对两条通道的设备 UDID。XR 上已实测 `uid=0` 并自主移除失败的试验包，不增加 root SSH 登录或网络监听。
- Copy APP 的 rootless iOS MCP 界面插件已作为独立 `.deb` 通过 XR 上的 Filza 安装；`dpkg` 显示 `install ok installed`。SpringBoard 重载后，USB 转发上的 `copyapp-ios-mcp` 服务通过身份检查，已实测 414×896 JPEG 截图、前台识别、App 启动和屏幕点击。USB 无障碍 `press` 返回激活请求但未实际点击；iOS MCP 的 `tap` 已在原版和复刻版上产生可见状态变化。iCTRL 的 Mac 端加密客户端与适配器也已在 XR 的 iOS 16 兼容试验版 runner 上完成配对、加密 RPC、Compass 截图和方位锁定点击。详见 [iCTRL XR 实测](docs/ictrl-xr-validation.md)。
- 独立 UIKit 复刻工程 [Copy Compass](rebuild/CompassClone) 已用 Xcode 27 编译为 iOS 16 目标。普通 USB 安装服务接受 IPA，但首次启动因代码签名被拒；清除这一测试安装后，TrollStore 成功安装最新版。原版和复刻版均已在 XR 上通过 iOS MCP 实测实时方位、位置显示、点击方位锁定及点击坐标跳转 Apple Maps。[XR 复刻实测记录](docs/xr-rebuild-verification.md)列出证据、修正过的界面归属和剩余差异。
- Compass 的[深入报告 v18](cases/compass-xr-deep-report-v18-20261015/report.md)引用三条原版 UI 流程，[自动复刻交接 v3](cases/compass-rebuild-plan-v3-20261015/runbook.md)由此生成全部三对脚本；复刻版 0.1.3 (4) 在 XR 上完成[三流程真机对照](cases/compass-three-flow-rebuild-check-v4-20261015/report.md)并通过证据哈希校验。iOS MCP 连续截图后偶发空无障碍文本，采集器会以绑定原图哈希的 Mac Vision OCR 作为回退。锁定角度标签的叠字已修正；动态画面差异仍需人工审阅，三条流程的自动视觉判定均为 `unreviewed`。
- 本地 IPA 索引器已用 [Dopamine 3.0.11 官方发布包](https://github.com/opa334/Dopamine/releases/tag/3.0.11)验证：解析 147 个包文件、9 个 Framework 和 15 个 Mach-O，主程序的动态库清单及 `cryptid=0` 与 `otool` 一致。该包来自公开发布页，不能充当手机已安装 App 的原始证据；手机上的 Dopamine Bundle ID 另带签名后缀。

已确认前台归属的一次式案例保存在本地 `cases/compass-xr-mcp-onepass-20261015/`；原版与复刻版的交互截图也保存在 `cases/`。这些目录默认不进入 Git。`copyapp verify` 可检查初步采集、完整 `analyze` 案例、深入报告或 App 包获取目录里记录的文件哈希；这属于本地一致性检查，不提供防篡改签名。

## 安装

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools
.venv/bin/pip install -e .
```

iOS 16 上的截图与无障碍读取需要开发者模式及已挂载的 Developer Disk Image。若尚未挂载，可运行：

```sh
.venv/bin/pymobiledevice3 mounter auto-mount --udid <UDID>
```

## 使用

```sh
.venv/bin/copyapp devices
.venv/bin/copyapp doctor --udid <UDID> --out cases/<DEVICE_BASELINE>
.venv/bin/copyapp apps --udid <UDID>
.venv/bin/copyapp survey --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID> --launch
.venv/bin/copyapp analyze --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID> --launch
.venv/bin/copyapp analyze --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID> --launch --ui-backend ios-mcp
.venv/bin/copyapp analyze --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID> --launch --ui-backend ios-mcp --decrypt
.venv/bin/copyapp analyze --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID> --resume --ui-backend ios-mcp
.venv/bin/copyapp verify cases/<CASE_ID>
.venv/bin/copyapp ipa /path/to/app.ipa --out cases/<CASE_ID>/static
.venv/bin/copyapp check-ipa /path/to/candidate.ipa --bundle <BUNDLE_ID> --out cases/<CASE_ID>/decryption-check
.venv/bin/copyapp decrypt-main --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID>/decryption
.venv/bin/copyapp decrypt-package --udid <UDID> --bundle <BUNDLE_ID> --snapshot cases/<ACQUIRE_CASE>/bundle-snapshot.ipa --out cases/<CASE_ID>/full-decryption
.venv/bin/copyapp rea-function --file /path/to/recovered/main --sha256 <BINARY_SHA256> --procedure 0xADDRESS --provider ghidra --out cases/<CASE_ID>/rea/function-1 --rea-script /path/to/rea/scripts/rea.mjs --ghidra-dir /path/to/ghidra --java-home /path/to/jdk
.venv/bin/copyapp candidates --udid <UDID> --bundle <BUNDLE_ID> --binary /path/to/executable --objc-index cases/<CASE_ID>/static/objc-index.json --experiment cases/<EXPERIMENT_CASE> --out cases/<CANDIDATE_CASE>
.venv/bin/copyapp candidates --udid <UDID> --bundle <BUNDLE_ID> --binary /path/to/executable --objc-index cases/<CASE_ID>/static/objc-index.json --flow cases/<TRACED_FLOW> --out cases/<CANDIDATE_CASE>
.venv/bin/copyapp rea-queue --candidates cases/<CANDIDATE_CASE> --provider ghidra --limit 8 --rea-script /path/to/rea/scripts/rea.mjs --ghidra-dir /path/to/ghidra --java-home /path/to/jdk --out cases/<REA_QUEUE>
.venv/bin/copyapp rea-bridge --queue cases/<REA_QUEUE> --limit 4 --max-depth 2 --rea-script /path/to/rea/scripts/rea.mjs --ghidra-dir /path/to/ghidra --java-home /path/to/jdk --out cases/<BRIDGE_CASE>
.venv/bin/copyapp native-disasm --file /path/to/recovered/main --sha256 <BINARY_SHA256> --address 0xADDRESS --out cases/<NATIVE_FUNCTION>
.venv/bin/copyapp native-queue --candidates cases/<CANDIDATE_CASE> --limit 4 --out cases/<NATIVE_QUEUE>
.venv/bin/copyapp investigate-flow --udid <UDID> --analysis cases/<ANALYSIS_CASE> --script playbooks/<FLOW>.json --out cases/<INVESTIGATION_NO_REA>
.venv/bin/copyapp prepare-app --udid <UDID> --bundle <BUNDLE_ID> --script playbooks/<FLOW>.json --out cases/<PREPARATION_NO_REA>
.venv/bin/copyapp investigate-flow --udid <UDID> --analysis cases/<ANALYSIS_CASE> --script playbooks/<FLOW>.json --backend ios-mcp --provider ghidra --rea-script /path/to/rea/scripts/rea.mjs --ghidra-dir /path/to/ghidra --java-home /path/to/jdk --out cases/<INVESTIGATION>
.venv/bin/copyapp investigate-app --udid <UDID> --analysis cases/<ANALYSIS_CASE> --script playbooks/<FLOW_1>.json --script playbooks/<FLOW_2>.json --backend ios-mcp --provider ghidra --rea-script /path/to/rea/scripts/rea.mjs --ghidra-dir /path/to/ghidra --java-home /path/to/jdk --out cases/<APP_INVESTIGATION>
.venv/bin/copyapp decrypt-extension --udid <UDID> --bundle <BUNDLE_ID> --appex '<EXTENSION_NAME>' --out cases/<CASE_ID>/extension
.venv/bin/copyapp root-run --udid <UDID> --out cases/<CASE_ID>/root-command -- /var/jb/usr/bin/id
.venv/bin/copyapp assemble-ipa --snapshot cases/<ACQUIRE_CASE>/bundle-snapshot.ipa --recovered cases/<CASE_ID>/decryption --out cases/<CASE_ID>/assembly
.venv/bin/copyapp objc /path/to/arm64-macho --out cases/<CASE_ID>/static
.venv/bin/copyapp trace --udid <UDID> --bundle <BUNDLE_ID> --method 'ClassName::selector:' --seconds 10 --out cases/<CASE_ID>/trace.json
.venv/bin/copyapp experiment --udid <UDID> --bundle <BUNDLE_ID> --method 'ClassName::selector:' --x 207 --y 325 --seconds 2 --out cases/<CASE_ID>/experiment
.venv/bin/copyapp experiment --udid <UDID> --bundle <BUNDLE_ID> --method 'ClassName::selector:' --x 207 --y 325 --binary /path/to/App.app/App --objc-index cases/<CASE_ID>/static/objc-index.json --out cases/<CASE_ID>/direct-experiment
.venv/bin/copyapp ocr-file cases/<CASE_ID>/step-09-screenshot.jpg --roi 220 210 400 330 --out cases/<CASE_ID>/display-ocr.json
.venv/bin/copyapp view-tree --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID>/view-tree
.venv/bin/copyapp view-tree --udid <UDID> --bundle <BUNDLE_ID> --no-launch --out cases/<CASE_ID>/current-view
.venv/bin/copyapp flow-capture --udid <UDID> --backend ios-mcp --script playbooks/<FLOW>.json --out cases/<CASE_ID>/flow
.venv/bin/copyapp flow-capture --udid <UDID> --backend ios-mcp --script playbooks/<FLOW>.json --method 'ClassName::selector:' --binary cases/<ANALYSIS>/acquired/bundle/<APP>.app/<APP> --objc-index cases/<ANALYSIS>/acquired/static/objc-index.json --out cases/<CASE_ID>/traced-flow
.venv/bin/copyapp acquire --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID>/acquired
.venv/bin/copyapp sandbox --udid <UDID> --bundle <BUNDLE_ID> --out cases/<CASE_ID>/sandbox-index.json
.venv/bin/copyapp ax observe --udid <UDID>
```

`--launch` 会先打开目标 App；不带该参数时，先在手机上手动打开目标 App，停留在要记录的页面。`survey` 不会触控或修改 App 数据；生成的 `report.md` 会说明缺失的证据。`cases/` 默认忽略，避免把手机上的信息误提交到 Git。

`doctor` 按精确 USB UDID 记录设备版本、截图、DVT 文件访问、rootless 标记、mobile SSH 身份、Frida 进程枚举及两套 UI 服务的当前状态。iCTRL 探测会启动已配对 runner；其余探测只读取状态。缺少密钥或配对客户端会记为 `not_configured`，单项失败不会丢失其他证据；若 USB 设备身份无法核对则返回非零。用 `copyapp verify cases/<DEVICE_BASELINE>` 检查截图、设备详情和报告的哈希。SSH 默认使用现有本地 `22222` 转发和 `cases/ssh/` 的固定密钥；换设备时需配置该设备对应的 USB 转发与已钉住的主机密钥，身份不符会明确记录。

`copyapp branch-map --flow cases/<FLOW_1> --flow cases/<FLOW_2> --method 'ClassName::selector:' --binary cases/<ANALYSIS>/acquired/bundle/<APP>.app/<APP> --out cases/<BRANCH_MAP>` 可离线汇总已完成的 `flow-capture`：先重验来源案例、点击与视图树归属和主程序哈希，再把每次点击的原始第 3 参数与所选函数入口命中对应。输入流程须使用 `--arg2-u32-method` 和 `--branch-offset`，并绑定同一 App、设备和主程序。输出保留逐步计数和各案例的探针范围；对多分支及探针覆盖不一致的情形显式标记，不推断函数语义。[XR Calculator 四流程映射](cases/calculator-button-branch-map-20261015/report.md)来自 27 个点击窗口。

这份映射可用 `copyapp report --evidence branch.buttons=<BRANCH_MAP>` 导入正式报告。导入时重新按来源流程计算映射，并将四份原始流程与主程序复制到报告证据包；[Calculator 报告 v17](cases/calculator-xr-deep-report-v17-20261015/report.md)已实测导入，报告内副本再次运行 `branch-map` 后 27 条逐步观察与汇总结果均一致。

`copyapp rebuild-plan --report cases/<DEEP_REPORT> --out cases/<REBUILD_PLAN>` 从已校验的深入报告和已审阅的复刻规格中选取被引用的原版 playbook，生成仅改顶层 Bundle ID 的复刻 playbook 草案、成对结构检查结果及 `rebuild-check` 命令。若一个规格引用了不同终态的流程，且设有 `final_view`，它会用保存的 UIKit 末端文字选对来源；仍无法判断时标为歧义。XR Calculator 的[自动复刻交接 v3](cases/calculator-rebuild-plan-v3-20261015/runbook.md)已从报告生成全部 5 对脚本，并在 XR 上完成[五流程真机对照](cases/calculator-five-flow-rebuild-check-v7-20261015/report.md)。此命令不生成 App 源码，也不证明未测行为。

`copyapp agent-task --report cases/<DEEP_REPORT> --plan cases/<REBUILD_PLAN> --udid <UDID> --project rebuild/<APP>Clone --out cases/<TASK>` 将报告和计划核对后生成 Coding Agent 的 `TASK.md`、`task.json` 与哈希清单。它逐条核对来源证据、原版脚本及复刻脚本只改 Bundle ID，并把 UI 截图、REA 伪代码、实验和验收命令链接到实现任务；`copyapp verify <TASK_CASE>` 还会重验其来源报告与计划。XR 上的 [Compass 三流程任务](cases/compass-agent-task-v1-20261015/TASK.md)和 [Calculator 五流程任务](cases/calculator-agent-task-v1-20261015/TASK.md)均显示脚本输入就绪。`ready_for_agent` 仅表示全部报告流程的输入可开始实现；如果只选择部分流程，会列出未选项目。Coding Agent 仍须编写源码、编译、真机安装并复核。

`copyapp prepare-rebuild --report cases/<DEEP_REPORT> --flow <FLOW_ID> --udid <UDID> --project rebuild/<APP>Clone --out cases/<PREPARATION>` 把上述计划和任务两步合成一个可续跑入口，生成 `<PREPARATION>/plan/` 与 `<PREPARATION>/task/TASK.md`。省略 `--flow` 时选报告全部流程；重复执行须带 `--resume`，会核对报告、流程选择和设置，复用已验证阶段，并将损坏或不完整的子案例移到 `attempts/`。状态可能是 `ready_for_agent`、`selected_flows_ready` 或 `needs_evidence`；最后一种状态以非零退出，须补齐原版流程证据。XR 的 [Calculator 三流程交接](cases/calculator-rebuild-preparation-20261015/task/TASK.md)已通过 `copyapp verify`，重复续跑没有重新生成计划或任务。

复刻版安装后，运行 `copyapp rebuild-task-check --task cases/<PREPARATION>/task --out cases/<REBUILD_CHECK>`，即可按该任务钉住的设备、UI 后端和所选流程执行完整原版/复刻版真机对照；任务未指定设备时补 `--udid <UDID>`。它在操作手机前重新核对任务、报告、计划、原始证据与两份脚本；中断后用相同参数加 `--resume`。XR 上[夹具三流程的任务直连对照](cases/fixture-three-flow-rebuild-check-v3-20261015/report.md)、[逐图审阅](cases/fixture-three-flow-visual-review-v3-20261015/report.md)及[交付](cases/fixture-clone-agent-delivery-v3-20261015/report.md)均通过来源校验。先只用复刻版 UI 将 Counter 和 Notes 的历史可见计数各从 3 补到原版的 11，第三轮对照两边均为 11→12；3/3 行为断言通过，五对图片均记录轻微差异。该结果只覆盖三条脚本，且不证明两边 SQLite 记录内容一致。

分析 Agent 写出正式报告后，可运行 `copyapp analysis-delivery --task cases/<DRAFT> --report cases/<DEEP_REPORT> --out cases/<ANALYSIS_DELIVERY>`。它重验草稿任务和正式报告、目标 App/原始分析/完整调查身份，并要求报告规格以原版脚本 SHA-256 覆盖每条调查流程，且将草稿的待审预期改为具体结果；交付目录保存 findings 与规格快照。Calculator 的[三流程分析交付核验](cases/calculator-analysis-delivery-v1-20261015/report.md)已通过，百分比流程在报告中重命名但凭脚本哈希对应成功。该报告继续生成[五流程复刻计划](cases/calculator-rebuild-plan-v4-20261015/runbook.md)、[Agent 任务](cases/calculator-agent-task-v2-20261015/TASK.md)及[复刻交付核验](cases/calculator-agent-delivery-v3-20261015/report.md)；后者复用了同版源码和先前的 XR 五流程真机对照，没有重复操作手机。报告 v20 复用已有审阅结论，没有附独立 Agent CLI 运行记录；本核验不自动判断反编译解释的正确性。

从普通终端发起独立 Coding Agent 时，可用 `copyapp agent-run --task cases/<TASK> --provider codex|claude --out cases/<RUN>`。它接受 `draft-analysis` 的语义审阅任务，也接受 `agent-task` 的复刻任务；两者都要求来源可验证且位于当前仓库。复刻任务还要求报告全部选定流程已具备原版脚本、工程路径在仓库内。Codex 使用 workspace-write 与自动审批审查，Claude Code 使用 auto 权限模式。命令把 Agent 输出、错误和会话 ID 保存到本地案例。语义审阅任务可加 `--verify-analysis`：Agent 必须把正式报告写到 `<RUN>/reviewed-report`，进程退出后 Copy APP 自动运行 `analysis-delivery` 检查全部调查流程并保存 `<RUN>/analysis-delivery`；缺报告或来源不符返回非零，诊断留在 `analysis-verification.json`。这仍不自动证明函数解释正确。先加 `--dry-run` 可检查调用而不启动 Agent；[DeepSeek 三流程固定交付路径预演](cases/deepseek-three-flow-verified-analysis-agent-dry-20261015/run.json)已通过来源校验，尚未实际启动外部模型。既有 Calculator 的 [Codex 分析调用预演](cases/calculator-analysis-codex-run-dry-20261015/run.json)、[Claude 分析调用预演](cases/calculator-analysis-claude-run-dry-20261015/run.json)，以及 [Codex 复刻调用预演](cases/compass-agent-run-dry-20261015/run.json)、[Claude 复刻调用预演](cases/calculator-claude-agent-run-dry-20261015/run.json)均已通过。`agent_exited_unverified` 只表示 CLI 正常退出，绝不代表报告语义、源码、安装或真机对照通过。在已经运行的 Codex/Claude 会话内，直接执行 `TASK.md`，无需嵌套启动另一个 Agent。

复刻任务可加 `agent-run --verify-rebuild`：Agent 将安装记录、任务直连真机对照和逐图审阅分别保存到 `<RUN>/install`、`<RUN>/rebuild-check` 和 `<RUN>/visual-review`。进程退出后 Copy APP 自动生成并校验 `<RUN>/agent-delivery`，核对同一源码、IPA、设备、版本与所选脚本。选定流程须有操作后或末端行为断言，所有截图须审阅；缺证据、未通过行为断言、未审图片或重大视觉差异会使命令返回非零并写入 `rebuild-verification.json`，同时保留已生成的交付材料。轻微视觉差异仍在交付中列明，不等于像素一致。[DeepSeek 三流程固定交付路径预演](cases/deepseek-three-flow-verified-rebuild-agent-dry-20261015/run.json)已通过任务来源校验；实际外部 Agent 自动生成源码并完成真机对照尚未验证。

报告可以只选择第一版要实现的三条代表流程。此时 `agent-task` 状态为 `selected_flows_ready`，`agent-run` 会保留所选和未选流程清单；`agent-delivery` 可引用覆盖更多流程的真机对照，但只给任务内流程计数并列出额外检查项。[Calculator 三流程任务](cases/calculator-selected3-task-20261015/TASK.md)从九流程报告生成，[Codex 调用预演](cases/calculator-selected3-codex-dry-20261015/run.json)和[当前 0.1.10 的三流程交付核验](cases/calculator-selected3-delivery-v11-20261015/report.md)均通过来源验证。交付中的 3/3 末端断言引用已有 XR 九流程对照，六条未选流程未计入该任务；视觉仍为 `unreviewed`，也没有独立 Agent 实际执行记录。

完成源码、IPA 安装和真机对照后，运行 `copyapp agent-delivery --task cases/<TASK> --install cases/<INSTALL>/install.json --check cases/<REBUILD_CHECK> --out cases/<DELIVERY>`。它核对源码树与 IPA 当前哈希、安装和对照是否为同一设备及同一复刻版、每条脚本和比较结果是否覆盖交接任务，并在交付案例中封存源码 tar 与 IPA，便于后续修改工程后重验历史结果；可选 `--run <AGENT_RUN_CASE>` 绑定独立 Agent 的运行记录。XR 的 [Compass 交付核验](cases/compass-agent-delivery-v2-20261015/report.md)记录三条流程执行完成、视觉未审；[Calculator 交付核验](cases/calculator-agent-delivery-v2-20261015/report.md)记录五条流程的末端行为断言通过、视觉未审。两者均未附独立 Agent 运行记录，因此不宣称这些既有复刻源码由 `agent-run` 自动生成。交付核验不会把选定流程扩展为全 App 等价。

`analyze` 将现有的 USB 初步采集、SSH 只读 App 包获取与静态索引、沙盒元数据索引顺序执行，输出涵盖设备、二进制依赖、Objective-C 类、界面归属和沙盒的 `analysis.md` 及各阶段证据。加 `--decrypt` 后还会执行整包解密、逐个 Mach-O 复核和解密后类索引，并把结果并入同一报告；需先准备固定版本 helper。先启动上述 SSH USB 转发并配置专用密钥。某一步失败时仍保留已取得的证据、标明失败并返回非零状态；它尚不执行方法反编译或自动复刻。XR 实测表明启动原版 Compass 时，另一个 App 的系统定位弹窗仍可能占据前台；此类画面会被标记为界面归属不符。

新案例会在每一阶段写入 `run-state.json`。同一 UDID 与 Bundle ID 可用 `--resume` 继续：通过身份和哈希校验的阶段直接复用，失败或校验不符的部分输出移入 `attempts/` 后重跑；历史错误保留在状态文件中。阶段间核对 App 版本/构建号，防止把更新前的界面与更新后的二进制拼成同一案例。新状态还保存界面 JSON、截图及派生静态/ObjC 索引的哈希；XR 上故意损坏 ObjC 索引后，续跑只重新采集包阶段，证据见 `cases/fixture-xr-resume-derived-repair-20261015/`。旧状态没有这些额外哈希，需重新采集才有同等级保障。此前 XR 的 `cases/compass-resume-pilot-20261015/` 曾用不可达的 SSH 端口使包与沙盒阶段失败，随后恢复两阶段而复用界面阶段。

启动进程不保证页面立即进入前台。默认 USB 截图的目标归属标为未验证；选择 `--ui-backend ios-mcp` 后，流程在截图前后读取前台 Bundle ID，两次都匹配才标为 `verified_frontmost`。仍需检查截图具体内容。系统 App 的数据沙盒通常不会通过 House Arrest 开放，此时报告会记录失败而不是推断沙盒为空。

`ipa` 可独立解析本地已有的 IPA，索引 Framework、扩展、Mach-O 链接库与加密标记。它不会从手机脱壳；把某个本地 IPA 与实机安装记录关联前，应核对 Bundle ID、版本、构建号和二进制哈希。

`check-ipa` 对候选脱壳产物检查主程序、嵌入二进制的加密命令状态及 Bundle ID；未读出的代码或 `cryptid` 非零会让检查失败。它只验证头部标记，不能单独证明解密出的代码字节正确，也不执行脱壳。结果会统计但不列出可能含账号信息的 `SC_Info` 文件。

`decrypt-main` 通过 USB SSH 获取目标主程序的磁盘文件，启动目标进程后由 Frida 读取对应运行时加密区；在写出分析副本前校验设备 UDID、模块身份、未加密头部、加密区边界和字节差异。当前只支持 thin arm64 主程序。`assemble-ipa` 要求原包快照与脱壳来源哈希一致，只替换主程序并检查包内全部 Mach-O；仍加密的扩展会让完整性检查失败。这两个命令输出的都是**分析副本**，签名已失效，不承诺可安装。

`decrypt-package` 是 XR 已验证的完整路径。先运行 `sh scripts/prepare-ipadecrypt-helper.sh` 获取固定提交的设备 helper；命令检查本机和设备端的 helper SHA-256、USB Frida 与 SSH 指向同一 UDID、原包版本/构建号及传输哈希。它限时启动 helper，恢复主程序和扩展；再逐一检查包内 Mach-O，并确认每个原加密二进制只有加密区和 `cryptid` 字段发生变化。Mac 端还核对归档成员及未加密文件字节，只允许省略 `SC_Info` 收据，并用原包的 ZIP 元数据重组分析 IPA，避免设备端时间戳影响内容哈希。成功后自动生成解密后的 IPA 静态索引和主程序 Objective-C 类/方法索引，并写出可用 `copyapp verify <DECRYPT_CASE>` 再次审计的独立案例；[XR 实跑结果](cases/deepseek-verifiable-decrypt-live-20261015/manifest.json)已通过。输出仍是**分析 IPA**，不保证可安装。`decrypt-extension` 提供已运行扩展的直接 Frida 读取接口；XR 上对 Kimi/DeepSeek 分享扩展的附加均超时，因此当前正式整包路径使用 `decrypt-package`。`assemble-ipa` 的 `--recovered` 可重复提供已验证的主程序与扩展案例。

`rea-function` 对精确哈希的二进制调用 REA 的指定 provider，保存完整证据、伪代码和摘要。`--timeout` 会给所选 provider 留出较短的内部启动期限，以便外层超时前完成错误报告和清理；显式设置 `REA_GHIDRA_STARTUP_TIMEOUT_MS` 或 `REA_HOPPER_STARTUP_TIMEOUT_MS` 时尊重该设置。REA 查询现在使用独立进程组；外层超时时会先终止整组，再强制清理仍运行的子进程，已用真实父子进程做本机验证。大型 App 的 Ghidra 自动分析可能超过默认期限，应为单次任务选择足够的 `--timeout`。REA/Ghidra 与 REA/Hopper 都已在源码已知夹具上验证；Hopper 需在可访问 Spotlight/Apple Events 的正常 macOS 用户会话中启动。详见 [REA 与 Hopper 集成记录](docs/rea-hopper-integration.md)。

无需 REA 的反编译入口包括单函数 `copyapp ghidra-function --file <MACHO> --sha256 <SHA256> --address 0xADDRESS --ghidra-dir <GHIDRA_INSTALL_DIR> --out cases/<CASE>`、按已验证候选排序的 `copyapp ghidra-queue --candidates cases/<CANDIDATES> --ghidra-dir <GHIDRA_INSTALL_DIR> --java-home <JDK_HOME> --out cases/<QUEUE>`，以及整条调查的 `--provider ghidra-direct`。Copy APP 自带最小 Ghidra headless 脚本，保存函数伪代码、来源哈希、脚本与日志；正式报告可用 `--evidence ghidra.queue=cases/<QUEUE>` 导入。它仍需要外部 Ghidra 和 JDK。默认 `prepare-app` 的方法筛选与汇编路径可独立运行；显式选择 `ghidra-direct` 时将候选队列接入调查和 Agent 审阅任务，且无需 REA。XR Calculator 百分比候选的[直连案例](cases/calculator-direct-ghidra-percent-20261015/report.md)、加法的[候选队列](cases/calculator-direct-ghidra-queue-addition-v3-20261015/queue.json)及[一命令真机准备任务](cases/calculator-prepare-app-ghidra-direct-live-20261015/preparation/draft/TASK.md)均已运行并通过来源校验。完整边界见[无 REA 分析路径](docs/no-rea-analysis.md)。

大型二进制可在独立命令中加 `--disable-analyzer 'Objective-C Message Analyzer'`，或在整条调查中加 `--ghidra-disable-analyzer 'Objective-C Message Analyzer'`；所选配置、Copy APP 脚本哈希及生效结果均进入案例。Ghidra 即使在自动分析超时后继续输出伪代码，Copy APP 也会判失败，避免把部分分析当作完整结果。[分析配置与许可说明](docs/no-rea-analysis.md)。

上述三流程报告已形成[分析交付](cases/calculator-three-flow-no-rea-analysis-delivery-20261015/report.md)和[复刻任务](cases/calculator-three-flow-no-rea-rebuild-preparation-20261015/task/TASK.md)。在 XR 上复用已安装的 CalculatorClone 0.1.10 做[三流程对照](cases/calculator-three-flow-no-rea-rebuild-check-20261015/report.md)：加法、百分比、重复等号的末端 UIKit 断言均通过，六对截图的[逐张审阅](cases/calculator-three-flow-no-rea-visual-review-20261015/report.md)发现轻微差异；[交付记录](cases/calculator-three-flow-no-rea-agent-delivery-20261015/report.md)通过哈希验证。该源码早于本次无 REA 报告，本结果不证明报告自动生成了复刻 App。

`candidates` 将已完成的点击/Frida 实验中的非零方法计数，与**同一精确哈希二进制**的 Objective-C 实例方法索引按类名和 selector 关联，生成可直接送入 `rea-function` 的地址队列。它检查实验的设备、Bundle ID、前后台归属与截图哈希，并复制源证据供 `copyapp verify` 核对。`experiment` 同时传入 `--binary` 和 `--objc-index` 时会挂钩当前 Objective-C IMP 与 App 本体静态入口，记录各自命中次数及模块偏移。系统辅助功能层替换当前 IMP 时，`candidates` 保留该冲突，并在静态入口独立命中的条件下恢复原二进制函数候选。未提供静态入口的实验仍需当前 IMP 模块/偏移匹配；旧实验缺少偏移字段时仅按类名与 selector 匹配。即使偏移一致，也不证明手机上加载的代码字节与采集副本完全相同；观察窗口内调用不自动证明由点击引起。XR Calculator 的完整实测见 [Calculator 复刻验证](docs/calculator-xr-rebuild-verification.md)。Compass 的证据链见[点击到函数的实测](docs/compass-runtime-static-rea.md)。[Frida 指针与模块 API](https://frida.re/docs/javascript-api/)

`candidates --flow` 直接读取带方法跟踪的 `flow-capture` 案例，按每个点击步骤保留命中次数和来源；报告导入器会先校验脚本、App、设备、截图/视图树及静态二进制哈希。`rea-queue` 再按静态入口和当前 IMP 的观察次数排序，对候选的精确地址逐个调用指定 REA provider；失败会停止后续函数并保留已完成结果与失败记录。XR Calculator 的[流程候选](cases/calculator-traced-flow-candidates-20261015/candidates.json)定位到 `0x10000eb0c`，[Ghidra 队列](cases/calculator-traced-flow-rea-queue-20261015/queue.json)已成功保存完整函数证据，二者通过 `copyapp verify`。报告器可校验整条队列及来源后导入，见[深度报告 v12](cases/calculator-xr-deep-report-v12-20261015/report.md)。选择哪个函数与解释反编译结果仍需 agent 审阅，调用计数不单独证明因果。

`investigate-flow` 默认不依赖 REA：有静态候选时调用 Xcode 自带 `llvm-objdump` 保存有界 ARM64 汇编（默认最多 4 个函数，可用 `--function-limit` 调整）；工具不可用时保留失败记录并继续生成 UI/Frida 证据。工具还会在函数起点表确认目标时，沿唯一的本地直接 `bl` 调用或 `b` 分支有界跟随；多目标、间接分派和截断窗口会停止选择。汇编和静态边不是反编译源码，也不证明点击实际执行了下游函数。`investigate-flow` 默认不依赖 REA：把已验证的 `analyze` 案例和一条 playbook 接到方法候选、真机 UI/Frida 采集与静态候选；仅显式选择 `--provider ghidra|hopper` 时才运行 REA 队列。它按方法名生成可查看的候选排名，选择分数明显领先的动作入口，也会用各次点击的可见标签匹配唯一的导航或操作方法；默认无 REA 模式在方法不唯一时继续采集 UI 证据，并明确标记没有方法跟踪；显式选择 REA 时，模糊方法会保存 `method-scout.json` 并在操作设备前停下，可用同一输出目录加 `--resume --method 'Class::selector:'` 继续，原候选清单会保留。中途失败时，`--resume` 会重验并复用已完成阶段，避免重复操作手机。加密 App 会从已校验的解密 IPA 中提取主程序，未解密的磁盘主程序会被拒绝。XR 上[Calculator 一命令案例](cases/calculator-one-command-investigation-20261015/manifest.json)已完整成功，包含[待审摘要](cases/calculator-one-command-investigation-20261015/review-brief.md)；[SwiftUI 夹具 Counter 自动选择案例](cases/fixture-counter-autoselect-investigation-20261015/manifest.json)、[UIKit/SQLite Notes 双入口自动选择案例](cases/fixture-notes-autoselect-investigation-20261015/manifest.json)与[Catalog 自动选择案例](cases/fixture-catalog-autoselect-investigation-20261015/manifest.json)均已在 XR 完成，并进入[夹具深度报告 v12](cases/fixture-xr-deep-report-v12-20261015/report.md)。同一目标解析器还从 XR 的 DeepSeek 解密分析包提取并核对主程序哈希。报告器现可将整个调查作为一个带跨阶段身份核验的证据导入，见[深度报告 v14](cases/calculator-xr-deep-report-v14-20261015/report.md)。深层函数语义与复刻规格仍需 coding agent 审阅生成。

`investigate-app` 将同一分析案例下最多 12 条有界 playbook 顺序执行为一个任务，逐条保留 `investigate-flow` 原始案例和状态。失败时 `--resume` 会重验并跳过已完成的子流程；不同 Bundle ID、设备或脚本哈希会在操作手机前拒绝。XR 夹具的[三流程总案例](cases/fixture-app-investigation-20261015/manifest.json)在一条命令内完成 Counter、Notes、Catalog，父清单含 193 项证据文件；报告器会重验每个子案例和脚本身份，[夹具深度报告 v12](cases/fixture-xr-deep-report-v12-20261015/report.md)已用单个 `app.all` 证据 ID 引用全案。功能解释与复刻规格仍需 coding agent 审阅生成。

`prepare-analysis` 把已验证的 `analyze` 案例、1–12 条原版脚本接成可恢复的调查与语义审阅任务：`.venv/bin/copyapp prepare-analysis --udid <UDID> --analysis cases/<ANALYSIS> --script playbooks/<FLOW>.json --out cases/<PREPARATION>`。成功后检查 `<PREPARATION>/draft/TASK.md` 并由当前 Codex/Claude Code 审阅、补证和生成正式报告；`needs_semantic_review` 只表示材料齐备。失败后用同样输入加 `--resume`，已完成的调查不会重复触屏。`--investigation cases/<EXISTING>` 可复用已完成且身份匹配的调查案例，不操作手机。[Calculator 三流程复用演练](cases/calculator-preparation-reused-20261015/manifest.json)已通过 `copyapp verify`，产出新的待审任务。

若已选定 1–12 条原版 UI 脚本，可用 `copyapp prepare-app --udid <UDID> --bundle <BUNDLE_ID> --script playbooks/<FLOW>.json --out cases/<CASE>` 从已安装 App 一次接通 USB 采集、选定流程调查和审阅任务生成；默认仅采集 UI/Frida 和原生汇编，显式 `--provider ghidra-direct` 使用 Copy APP 自带 Ghidra 队列，显式 `--provider ghidra|hopper` 使用旧 REA 桥接；加 `--decrypt` 时同一轮执行已验证的整包恢复，前提是设备上的 root Frida 和固定 helper 可用。失败后以原参数加 `--resume`，已验证阶段无需重新触屏。XR 上 [Calculator 直连 Ghidra 单流程实跑](cases/calculator-prepare-app-ghidra-direct-live-20261015/manifest.json)从采集到审阅任务均已完成且不调用 REA。XR 上 DeepSeek 2.4.4 的 `--decrypt` 分支也已完成整包恢复、UI/Frida 跟踪和旧 REA/Ghidra 函数分析；[准备任务](cases/deepseek-prepare-app-encrypted-20261015/manifest.json)达到 `needs_semantic_review`。经审阅的[限定登录门控报告](cases/deepseek-password-gate-reviewed-report-v3-20261015/report.md)和[交付核验](cases/deepseek-password-gate-analysis-delivery-v2-20261015/report.md)覆盖所选 1/1 条流程；其他页面和登录后行为仍未分析。大型二进制的 Ghidra 默认自动分析曾超时；对当时 REA 分析 profile 禁用 `Objective-C Message Analyzer` 后完成，范围与剩余工作见 [DeepSeek 加密 App 试点](docs/deepseek-encrypted-flow-xr-verification.md)。

显式选择 `--provider ghidra|hopper` 时，新调查开始触屏前，`prepare-analysis` 会调用所选 REA provider 的 `doctor` 并保存 `toolchain-doctor.json`。REA 脚本可用 `--rea-script` 或 `COPYAPP_REA_SCRIPT` 指定，Ghidra/JDK 可用 `--ghidra-dir`、`--java-home` 或对应的 `GHIDRA_INSTALL_DIR`、`JAVA_HOME`。XR 上[Calculator 单流程实跑](cases/calculator-preparation-live-20261015/manifest.json)经历了 REA CLI 缺失和 JDK Home 配置错误；续跑保留了两次失败队列，复用已采集的 UI/Frida 证据，只重跑 REA，并最终生成哈希验证通过的审阅任务。它尚不是经语义审阅的深度报告。

`copyapp draft-analysis --analysis cases/<ANALYSIS> --investigation cases/<APP_INVESTIGATION> --out cases/<DRAFT>` 在整案已完成后重验分析索引、设备/App 身份、每条脚本及已有的 Frida、原生汇编和可选反编译证据链，生成事实草稿 `findings.json`、待审 `feature-spec.json`、审阅入口 `review-dossier.md` 与引用完整证据的 `report/`。新版还生成 `TASK.md` 和 `task.json`：逐流程链接原版脚本、末端截图、视图树，以及采集到的点击追踪和可选伪代码，明确 Coding Agent 必须产出经审阅的结论、可执行规格及新报告；`copyapp verify` 会重验其来源分析、调查和草稿报告。它只描述采集时明确通过的观察断言、点击窗口计数、已分析函数地址、沙盒元数据数量和未知项；`review_status=needs_semantic_review` 会阻止直接送入 `rebuild-check`。[夹具三流程交接任务](cases/fixture-auto-draft-v4-20261015/TASK.md)及其案例已通过校验。Coding agent 仍需沿已有运行时、静态及可选伪代码证据补全功能原理、可执行规格和未覆盖状态，不能将事实草稿当作已完成的深入分析。

同一入口现也在真实 Calculator 上完成三条流程：[整案调查](cases/calculator-app-investigation-20261015/manifest.json)保存 180 项证据文件，三条末端 UIKit 树依次显示 `15`、`110`、`9`；[自动事实草稿及审阅任务](cases/calculator-auto-draft-v3-20261015/TASK.md)通过哈希校验。草稿只将屏幕上部文字列为候选，不把它擅自判为计算结果，也不推导 Calculate.framework 的算法。既有[人工审阅深度报告](cases/calculator-xr-deep-report-v14-20261015/report.md)继续提供关键调用链解释；自动草稿是其可复用的取证起点。

`copyapp rebuild-check --udid <UDID> --feature-spec docs/calculator-feature-spec.json --pair calculator-basic-addition playbooks/calculator-basic.json playbooks/calculator-basic-clone.json --pair calculator-relative-percent playbooks/calculator-percent-original.json playbooks/calculator-percent-clone.json --pair calculator-repeat-equals playbooks/calculator-repeat-original.json playbooks/calculator-repeat-clone.json --backend ios-mcp --out cases/<REBUILD_CHECK>` 将规格中的选定流程逐条运行原版与复刻版，再保存同设备、同后端、同场景的截图对照。它在触屏前检查脚本的动作、标签、坐标及初始条件，并固定两款 App 的已安装版本/路径；每条流程后再次核对版本。中途失败可用相同输入加 `--resume`，已完成且哈希通过的原始脚本结果不会重复触屏。XR Calculator 的[三流程总验收](cases/calculator-xr-rebuild-check-20261015/report.md)已完成，六张成对截图的[图片审阅](cases/calculator-xr-rebuild-check-20261015/visual-review.md)记录 `0→15`、`10→110`、`7→9`；这些选定状态的匹配不能推导全部功能等价。

`copyapp visual-audit --check cases/<REBUILD_CHECK> --roi X1 Y1 X2 Y2 --max-mean 0.015 --max-changed 0.03 --out cases/<AUDIT>` 可离线重算整案每张成对截图在指定区域内的归一化平均 RGB 差和超过 24 灰度级的像素比例；区域至少覆盖屏幕一半。它重新核对来源对照及每张图片哈希，`copyapp verify` 会再次计算指标。XR Calculator [五流程九张截图审计](cases/calculator-five-flow-visual-audit-v1-20261015/report.md)在 `[0,80,414,820]` 区域均落在上述阈值内，最大平均差 0.01122、最大差异像素比例 2.069%；[人工查看记录](docs/calculator-v7-visual-review.md)列出可见差异。这些阈值是在查看截图后设定的诊断尺度，不能追认为预先声明的视觉验收；原 `rebuild-check` 的视觉状态仍为 `unreviewed`。

`copyapp visual-review --check cases/<REBUILD_CHECK> --judgments docs/<REVIEW>.json --reviewer '<NAME>' --out cases/<VISUAL_REVIEW>` 将审阅者对每张并排截图的 `match`、`minor_difference` 或 `major_difference` 判断及具体说明绑定到原图、复刻图、并排图和真机对照的哈希。必须覆盖全部截图对。`agent-delivery` 可加 `--visual-review cases/<VISUAL_REVIEW>`，交付状态会单独列出主观审阅与脚本视觉检查；任何差异都不会被改写成“完全一致”。[Calculator 九流程 18 对逐图审阅](cases/calculator-nine-flow-visual-review-v11-20261015/report.md)记录了按钮字形、数字笔画和系统顶部文字的轻微差异；[新版交付](cases/calculator-agent-delivery-visual-reviewed-v11-20261015/report.md)仍限定于保存的画面和九条流程。审阅者身份由命令填写，并非独立认证。

新的 `prepare-rebuild` 三流程任务也与同版安装、九流程真机对照和逐图审阅组成[三流程交付](cases/calculator-prepared-selected3-reviewed-delivery-20261015/report.md)：所选 3/3 行为断言通过、0/3 未审，另外六条对照流程单独列出且不计入任务范围；案例核验通过。这仍复用已存在的源码与设备证据，不代表外部 Agent 自动生成了 App。

规格流程可选 `final_view: {"text": "15", "region_points": [0, 150, 414, 341]}`。设置后，`rebuild-check` 对原版和复刻版使用 `flow-capture`，在脚本结束后不重启 App 地采集当前 UIKit 视图树；只有指定屏幕区域内恰好一个可见 `UILabel` 的文本与规格完全一致才通过。XR Calculator 的[带视图断言的三流程验收](cases/calculator-xr-rebuild-check-with-view-20261015/report.md)已实测：两端最终显示标签分别为 `15`、`110`、`9`，六份状态检查及 127 项案例文件通过哈希校验，[图片审阅](cases/calculator-xr-rebuild-check-with-view-20261015/visual-review.md)单独记录可见差异。这条断言只覆盖保存时刻的 UIKit 标签；SwiftUI 绘制、自绘数字、动画及其他未观察状态需要其他证据，逐流程视觉状态仍标为 `unreviewed`。

`rea-bridge` 从已验证的 REA 队列自动追踪唯一的本地匿名调用目标，按函数数和深度限制继续；遇到多个分支会保存清单并停止选择。XR Calculator 的[桥接追踪](cases/calculator-bridge-follow-20261015/bridge-map.json)从 `0x10000eb0c` 唯一进入 `0x10000e9b8`，随后列出 10 个分支供 agent 结合按钮 ID 审阅。它复制原始候选/REA 队列并核对每个跟随边、函数哈希、地址、provider 和伪代码；[深度报告 v14](cases/calculator-xr-deep-report-v14-20261015/report.md)已导入整条追踪。静态调用图不证明特定点击执行了某个下游分支。

`report` 将一个已验证的 `analyze` 案例、agent 撰写的 `findings.json`、可选复刻规格和选定证据组装到新目录。每个 `--evidence ID=PATH` 可指向 `rea-function` 输出目录、已完成的 `experiment` 目录或单个文件。它会核对 REA 的二进制哈希与采集包、Evidence ID、provider、分析配置、函数身份和伪代码文本的一致性，以及实验的 Bundle ID、前台状态和前后截图哈希；非“待验证”的结论必须引用已导入证据。输出包含 `report.md`、`report-index.json`、证据副本和 `feature-spec.json`（若提供），可再用 `copyapp verify <报告目录>` 检查。Compass 和夹具的结构化结论分别见 [compass-findings.json](docs/compass-findings.json) 与 [fixture-findings.json](docs/fixture-findings.json)。证据的语义解释仍由 coding agent 审阅撰写，哈希通过不自动证明结论正确。

`view-tree` 在目标 App 前台时通过 Frida 读取当前 UIKit 窗口与有限深度的子视图，保存类名、父子关系、frame、可访问性文本、常见标签/按钮文字以及 UILabel 字体名称和字号；同时保存可用的 iOS MCP/iCTRL 无障碍观察树。扫描源脚本、截图和树数据都带哈希。XR Calculator 的原版与独立复刻版已各自捕获；字体差异及修复见[真机复核](docs/calculator-typography-xr-review.md)。SwiftUI 夹具的 `_UIHostingView<CounterView>` 没有对应的 UILabel 计数文本，同次无障碍树则给出 Counter 数值和按钮。`report` 导入该目录时会核对目标设备、App、前台归属、节点结构和证据哈希。一次视图树只代表当时已加载的页面，不代表完整页面图或原始源码。

`flow-capture` 将一份 playbook 与紧随其后的 `--no-launch` 视图扫描合成一个案例，子案例各自保留原始证据，父清单记录脚本哈希、设备/应用/后端身份和两阶段状态。操作脚本失败后不会继续视图扫描；失败证据仍可校验。报告导入会核对两个子案例、扫描顺序及不超过 60 秒的间隔。XR 的原版 Calculator 与复刻版 `5 + 2 = =` 已各用这一条命令完整复现，两个最终显示标签均为 `9`，见[复刻验收](docs/calculator-xr-rebuild-verification.md)。

`network-flow --udid <UDID> --backend ios-mcp --script <PLAYBOOK> --out cases/<CASE>` 在同一次受限 UI 流程中附着目标 App 的 Frida 进程并观察 URLSession 任务恢复。它只保存协议、主机、HTTP 方法、路径层数和非加密的 32 位路径指纹；不保存原始路径、查询、请求头、请求体或响应。逐次事件仅在受控点击的短时间窗口内标上步骤编号，窗口外事件不归因于点击；其他网络 API 可能漏掉。用 `copyapp verify` 校验案例后，可通过 `report --evidence network.<ID>=cases/<CASE>` 导入同设备、同 App 的报告。XR 的 [DeepSeek 条款弹窗前网络观察](cases/deepseek-network-preagree-report-v2-20261015/report.md)在 7 个 URLSession 实现上记录了 3 条 POST resume hook 事件，目标主机为 `apmplus.volces.com` 和 `log-auth.zztfly.com`，均未落在点击窗口内；没有点击条款同意。一次任务可能经过多个实现，事件数不等于去重请求数。路径指纹可被字典猜测，不能作为隐私保护哈希，也不能据主机名推定接口用途。

需要把网络事件与方法、界面绑定在**同一次操作**时，使用 `flow-capture --network`，可同时加 `--method` 及匹配的 `--binary`/`--objc-index`。这条命令现在把 `playbook/`、`trace/`、`network/` 和末端 `view-tree/` 保存到同一父案例；报告导入会复核每个子案例、脚本、设备、App、点击步骤与静态二进制身份。XR 的[两次 DeepSeek 联合重放](cases/deepseek-preagree-unified-repeat-report-20261015/report.md)均在密码入口点击窗口记录 `DSButton::objcOnTap` 两个入口各一次，末端出现条款弹窗。两次各观察到一条发往 `log-auth.zztfly.com` 的 POST resume 事件；第一次事件落在点击窗口内，第二次落在窗口外。这个差异说明网络时间归属不稳定，不能据此断定点击与请求有因果关系。

`investigate-flow`、`investigate-app`、`prepare-analysis` 和 `prepare-app` 均可显式加 `--network`，将同一次 UI 调查的网络子证据沿候选方法、原生汇编及审阅任务传递；恢复运行会核对该选项，避免混用不同采集范围。XR 的[单流程调查](cases/deepseek-network-investigation-20261015/review-brief.md)、[App 调查](cases/deepseek-network-app-investigation-20261015/manifest.json)和[待审任务](cases/deepseek-network-analysis-preparation-v2-20261015/draft/TASK.md)已走通无 REA 的网络证据路径。待审任务会列出网络证据链接、事件数和主机，但事件数不代表去重请求数，也不自动推断业务接口。

对已选定的主程序函数，`flow-capture --branch-offset 0xOFFSET --branch-return-u32-offset 0xOFFSET` 可在同一次点击窗口内保存该入口的调用次数与函数返回寄存器低 32 位原值。`--branch-register 0xOFFSET:x19` 可在已选指令位置读取一个 x0–x30 寄存器；仅当其指针落在当前 App 主程序镜像内时保存对应偏移，否则只记录未映射状态。两种采集的偏移必须同时列在 `--branch-offset` 中，并需要匹配已采集主程序的 `--binary`、`--objc-index` 和入口 `--method`；每步各最多保存 256 个样本，溢出会明确标记。值的类型与含义仍须结合反编译及界面证据解释。此通用入口已通过本地测试与 Frida 脚本语法检查；该通用入口尚无新入口的真机复测。DeepSeek 登录条款门控此前由[一次性真机探针](cases/deepseek-password-gate-branch-probe-20261015/probe.json)记录返回低位 `0`，不能把该旧案例说成新入口的实测。

可选的 `--method` 会在脚本每个点击步骤统计指定 Objective-C 方法的调用；配合匹配的 `--binary` 和 `--objc-index`，同一运行还会计数 App 主程序中的原始静态入口。三个子案例均带哈希，报告导入会核对点击步骤、设备、App 与二进制身份。XR 系统 Calculator 的六次点击各记录一次可访问性替换 IMP 和一次主程序 `0xeb0c` 入口命中，结果视图树读到 `9`；见[组合案例](cases/calculator-repeat-traced-flow-original-20261015/manifest.json)及[深度报告 v12](cases/calculator-xr-deep-report-v12-20261015/report.md)。点击窗口内的调用计数是时间关联，不单独证明调用因果或参数。

两个 XR 试点可运行 `sh scripts/compose-pilot-report.sh compass cases/<NEW_CASE>` 或 `sh scripts/compose-pilot-report.sh fixture cases/<NEW_CASE>` 重建，脚本会在生成后调用 `copyapp verify`。报告器已用 DeepSeek 的已解密案例核对：优先展示解密后主程序和类索引，同时保留磁盘快照索引；没有账号会话时，登录后行为仍标记未知。单独导入的截图或数据文件只由报告器校验内容哈希，设备和 App 归属须从其采集记录另行确认。

`install` 将本地 IPA 经指定 XR 的 USB SSH 传输、校验 SHA-256、调用该设备现有的 TrollStore helper，然后用安装服务核对 Bundle ID 与版本；暂存 IPA 在结束时删除。已在 XR 上用测试夹具实测更新并启动，完整记录在 `cases/fixture-cli-install-20261015/install.json`。例如：

```sh
.venv/bin/copyapp install --udid <UDID> --ipa <LOCAL_IPA> --out cases/<INSTALL_CASE>
```

`root-run` 用于已安装 root Frida 服务及已配对 mobile SSH 的越狱机。它只对精确匹配的 USB UDID 启动命令，确认 SSH 也指向同一设备，保存命令、输出和退出码到指定本地案例目录，最多保存 1 MiB 输出并清理手机上的临时日志。指定的可执行文件必须是绝对路径；需要限制长任务时，在设备命令前加 `/var/jb/usr/bin/timeout`。该入口具有 root 权限，只应在可信的本机工作区使用。

`trace` 和 `experiment` 需要可选依赖 `pip install -e '.[trace]'` 和设备上的 Frida 服务；它们只计数指定 Objective-C 实例方法在观察窗口内的调用，不保存参数或返回值。成功附加但计数为零仅代表窗口内没观察到调用；附加失败会写入错误证据并返回非零状态。`experiment` 还需要已安装的 iOS MCP 设备服务；默认按 `--udid` 自动建立并回收独立 USB 转发，无需预先开转发终端。截图可能包含位置等私人信息，默认保存在 Git 忽略的 `cases/` 下。XR 上原版 Compass 的方位盘和地图跳转实验已采到真实方法调用，见 `docs/compass-xr-analysis.md`。

`playbook-auto` 可在同一设备上先尝试 iCTRL 或 iOS MCP，主后端在**尚未尝试任何触控**时失败，才用另一个后端重放；两次尝试和出错原因都留在同一哈希校验案例。任何 `tap`/`tap_label` 已被调用后，即使 RPC 报错也不自动重试，避免把一次可能成功的有状态动作执行两遍。XR 上用缺失的 iCTRL 客户端制造连接前失败，再由 iOS MCP 完成夹具 Catalog 脚本，案例为 `cases/fixture-catalog-ui-failover-v2-20261015/`。例如：

```sh
.venv/bin/copyapp playbook-auto --udid <UDID> --primary ictrl --fallback ios-mcp --script fixture/CopyAppFixture/playbooks/catalog.json --out cases/<CASE>
```

`acquire` 默认通过 USB 转发的 SSH 端口 22222 连接手机；先运行 `.venv/bin/pymobiledevice3 usbmux forward 22222 22 --serial <UDID>`，再给目标账号配置专用密钥，确保 `cases/ssh/id_ed25519` 与 `cases/ssh-known-hosts` 已存在。可用 `--ssh-user root` 或 `--ssh-user mobile` 指定账号；也可用 `--ssh-identity`、`--ssh-known-hosts` 和 `--ssh-port` 指定其他路径或端口。可选 `--transport afc2` 使用 AFC2。SSH 路径会同时索引主程序的 Objective-C 类、方法、类型编码与静态实现地址；不反编译方法体。分析快照 IPA 的 ZIP 时间戳固定，方便对相同文件内容复现哈希。

采集器只读复制目标 `.app` 包，记录各文件哈希，并生成供解析的 `bundle-snapshot.ipa`；这是重新打包的分析快照，不能当作原始可安装 IPA。非普通文件（包括符号链接）会跳过并记入清单。若主程序 `cryptid` 非零，可接续 `decrypt-main`；扩展需在其对应进程运行时另行恢复。当前尚未获取完整数据沙盒或网络运行轨迹。

`sandbox` 读取数据容器的相对路径、类型、大小和修改时间，默认深度 8；不会复制文件正文。它依赖与 `acquire` 相同的 USB SSH 通道。

对需要解释数据模型的具体文件，`sandbox-file` 从**已验证的分析案例**中挑选最多四个常规文件，并再次核对精确设备、App 版本、数据容器身份、目录类型和大小后经 USB SSH 只读复制；每个文件上限 64 MiB，总量 128 MiB。原始文件只保存在本地忽略的 `cases/` 中，可能含私有数据。随后 `sqlite-schema` 可只导出数据库结构：

```sh
.venv/bin/copyapp sandbox-file --udid <UDID> --analysis cases/<ANALYSIS> --path Documents/<DATABASE>.sqlite --out cases/<CAPTURE>
.venv/bin/copyapp sqlite-schema --case cases/<CAPTURE> --path files/Documents/<DATABASE>.sqlite --out cases/<SCHEMA>
```

XR 的[夹具文件采集](cases/fixture-sandbox-file-capture-20261015/capture.json)、[SQLite 结构](cases/fixture-sandbox-file-schema-20261015/report.md)和[来源绑定报告](cases/fixture-sandbox-schema-report-20261015/report.md)已通过校验，识别出 `notes(id, text)`；报告没有导出表记录。旧沙盒索引缺少容器身份哈希时会被拒绝，需要重新 `analyze`。单次复制和 WAL 组合可能不是同一瞬间的数据库快照，不能从表结构推断具体读写行为。

偏好设置可用 `plist-schema --case cases/<CAPTURE> --path files/Library/Preferences/<BUNDLE>.plist --out cases/<PLIST_SCHEMA>` 生成有界的键路径与类型目录；它不导出键值或数组长度。XR 的[Fixture 偏好结构](cases/fixture-prefs-schema-20261015/report.md)记录 `/fixture.counter` 为整数；[合并数据模型报告](cases/fixture-sandbox-data-model-report-20261015/report.md)把它与 SQLite 结构绑定到同一分析案例。原始 plist 仍留在忽略的本地采集目录，可能含私有数据。

`sandbox-diff` 对同一设备、App 和容器的两份沙盒索引比较新增、删除及元数据变化；传入 `--action` 时，还要求已完成且通过哈希校验的 UI playbook 处在两次采集之间。它把两份快照、操作证据、差异和报告一起保存，可交给 `copyapp verify` 或 `copyapp report --evidence`。例如：

```sh
.venv/bin/copyapp sandbox-diff --before cases/before.json --after cases/after.json --action cases/playbook-run --out cases/sandbox-diff
```

修改时间或大小变化不能单独证明文件正文怎样变化；需要内容结论时仍须定向取回并检查对应文件。

`ax` 是不依赖越狱 tweak 的 USB 无障碍备用接口。`observe` 已在 XR 的系统定位弹窗上读到按钮；`press --caption '<当前元素的完整 caption>'` 会请求激活一个唯一匹配的元素，必须再观察屏幕确认结果。XR 上对系统定位授权按钮的一次实测返回“Activation request sent”，但弹窗仍在，说明这个接口不能作为已验证的系统弹窗触控后端。

## iOS MCP 界面适配器（开发中）

Mac 端已加入 `copyapp ui`，仅调用 iOS MCP 的界面观察、触控和 App 启动工具；任意 shell、文件写入和安装工具不在适配器的允许列表内。它只连接 `127.0.0.1`，需要先把设备端 8090 端口通过 USB 转发到 Mac：

```sh
.venv/bin/pymobiledevice3 usbmux forward 22223 8090 --serial <UDID>
.venv/bin/copyapp ui health
.venv/bin/copyapp ui wake
.venv/bin/copyapp ui observe
.venv/bin/copyapp ui screenshot --out cases/<CASE_ID>/ui.jpg
.venv/bin/copyapp ui ocr --out cases/<CASE_ID>/ocr-source.jpg
.venv/bin/copyapp ui tap --x 180 --y 400
.venv/bin/copyapp ui launch --bundle com.apple.compass
```

`ui wake` 用于熄屏时先唤醒并尝试回到主屏；随后仍要用 `observe` 或 `screenshot` 核对结果。XR 重载 SpringBoard 后第一次截图是黑屏，唤醒后同一接口取得了正常的 414×896 JPEG。
`ui ocr` 只从设备取截图，在 Mac 的独立 Vision 进程中识字。它会先比对连续截图是否趋于稳定，并记录前台 App、屏幕亮锁状态和坐标映射。XR 的 iOS 16.1.1 上，设备端 Vision OCR 曾两次导致 SpringBoard 崩溃；现装的 0.1.3 包不再暴露设备 OCR 工具，真机验证了直接调用被拒绝且服务保持健康。即使 iOS MCP tweak 暂时不可用，也可用 `copyapp ui ocr --backend usb --udid <UDID> --out cases/<CASE_ID>/screen.png` 直接通过已配对的 USB 截图并在 Mac 识字；此后端只支持 OCR 和截图，返回坐标属于截图像素。实测记录见 [XR OCR 验证](docs/xr-ocr-validation.md)。

适配器已通过本地协议测试和 XR 真机截图、前台识别、启动、点击验收。已引入的 [设备端源码及构建说明](device/ios-mcp/README.md)将监听限制为回环地址，并在两端过滤非 UI 工具；Mac 客户端只接受标识为 `copyapp-ios-mcp` 的改造版服务。当前固定用于构建研究的上游提交为 `witchan/ios-mcp@62c4464f688c8f269419924b1a19c996de75f175`；Theos 提交为 `304e0799973e8145f32e4ca2de6c747a84b758ce`，SDK 为 iPhoneOS16.5。工具链保存在仓库外的工作区目录，不会随本仓库提交。

## iCTRL 界面适配器（XR 真机已验收）

Mac 端 `copyapp ui --backend ictrl` 通过上游 iCTRL 的加密客户端调用已配对 runner，只开放界面观察、触控、截图和 App 启动等方法；不自行实现或绕过配对协议。当前研究源码固定为 `OpenMinis/iCTRL@d88bbf0b3a5addead31b4298d605d7ac7a87d6e7`。运行 `sh scripts/build-ictrl-client.sh` 可从该提交构建 `../toolchains/ictrl-macos` 并执行上游密码学自检；现有本机运行结果全部通过。runner 启动后先建立 USB 转发；首次配对需要在手机上批准，指纹应与客户端显示的一致：

```sh
.venv/bin/pymobiledevice3 usbmux forward 22224 8200 --serial <UDID>
../toolchains/ictrl-macos --host 127.0.0.1:22224 pair --name 'Copy APP'
.venv/bin/copyapp ui health --backend ictrl
.venv/bin/copyapp ui observe --backend ictrl
.venv/bin/copyapp ui screenshot --backend ictrl --out cases/<CASE_ID>/ictrl.jpg
.venv/bin/copyapp ui tap --backend ictrl --ref '<元素 ref>'
```

上游客户端将配对密钥保存在用户的 `~/.ictrl/token.json`，不要放进案例或 Git。`copyapp ui` 只接 `127.0.0.1` 的 USB 转发端口；返回值带有后端名称和 UTC 时间。一次验证只允许一个界面后端发动作。iCTRL 的 `page_source`、元素 `ref` 和截图与 iOS MCP 的原始结果分别保存，不能假设两者元素 ID 相同。XR 已完成加密配对，`copyapp ui --backend ictrl` 的健康检查、观察、截图、启动和 Compass 方位锁定点击均在真机成功执行；iOS 17/26 尚未验收。

`copyapp experiment --backend ictrl` 和 `--backend ios-mcp` 共用同一套“启动目标 → 核对前台 → 截图 → Frida 挂钩 → 点击 → 再截图”实验逻辑。未传 `--port` 时，iCTRL 路径会在指定 USB 设备上启动已安装且已配对的 runner，并建立临时转发；两种后端的点击坐标均为屏幕点，截图保留各自原始分辨率。XR 的原版 Compass 同一坐标与方法已在两端实测调用 1 次，详见 [iCTRL 真机记录](docs/ictrl-xr-validation.md)。

可重放的界面脚本用 `copyapp playbook --udid <UDID> --backend ictrl|ios-mcp --script fixture/CopyAppFixture/playbooks/counter.json --out cases/<CASE_ID>` 运行。脚本仅允许观察、截图和有目标的点击；示例明确要求 fresh launch，读取点击前计数并断言点击后增加 1。每步核对目标 App 在前台，观察在启动动画期间可限次重试；输出 `manifest.json` 与原始证据，可用 `copyapp verify` 校验。XR 上 Counter、Notes、Catalog 三份脚本已分别通过两种后端，记录见 [夹具验证](docs/fixture-xr-validation.md)。

`copyapp compare-playbooks --original cases/<原版脚本结果> --rebuilt cases/<复刻版脚本结果> --out cases/<对照>` 将同一设备、同一 UI 后端和场景的两次已完成脚本按步骤配对，保存原始证据、并排截图与像素差图。被比较的截图必须带有画面稳定与目标内容就绪检查；无障碍读取为空时，截图 OCR 回退会保存原图和识字结果，并在比较时验证其哈希关联。脚本可配置区域颜色脉冲或原版/复刻版颜色计数匹配检查；传感器驱动的动态线条不适合无条件采用硬阈值。XR 先前一组 Compass 方位锁定对照的红色标记计数分别为原版 `0→134→0`、复刻版 `0→58→0`，后续静止重复采集又出现不同计数；见 [XR 复刻实测记录](docs/xr-rebuild-verification.md)。像素差和颜色计数只描述指定画面与区域，不证明整体视觉或功能等价。

脚本的 `expect_foreground` 步骤可验证点击后切到指定 App。XR 上原版与复刻版均已用相同坐标点击并确认 Apple Maps 前台，成对证据在 `cases/compass-maps-comparison-20261015/`；地图内落点仍未核验。

## 复刻工程

`rebuild/CompassClone` 用 UIKit、CoreMotion、CoreLocation 和程序化绘图实现三条 Compass 流程。运行 `sh rebuild/CompassClone/package.sh` 可生成 `rebuild/CompassClone/build/dist/CopyAppCompass.ipa`。脚本用 `ldid` 做临时签名，供 TrollStore 等越狱安装路径处理；普通 USB 安装服务虽然接受 IPA，XR 的 SpringBoard 仍拒绝启动，日志见本地 `cases/rebuild-launch-syslog.txt`。通过 TrollStore 安装的最新版已在 XR 运行，实测及差异见 [XR 复刻实测记录](docs/xr-rebuild-verification.md)。
