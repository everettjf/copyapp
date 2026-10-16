# 不安装 REA 的分析路径

Copy APP 的默认 `--provider none` 不启动 REA、Ghidra 或 Hopper。`prepare-app` 仍采集已安装 App、沙盒元数据和已选 UI 流程；加密主程序需要先走已有的整包恢复与校验。每条流程可能形成三个递进的证据层级：

1. **UI 层**：脚本、前台归属、截图、无障碍与 UIKit 视图树。静态方法名无法唯一选入口时，带 `tap_label` 的流程先采集操作前视图，尝试用该可见按钮所属的运行时类匹配唯一动作方法。视图采集失败或仍不唯一时继续采集 UI，并明确记录没有方法跟踪。
2. **运行时与静态绑定层**：选出方法时记录逐点击 Frida 命中、主程序静态入口命中、原始参数和按二进制哈希绑定的候选地址。没有命中的候选也不阻断 UI 调查。
3. **原生函数层**：本机有 Xcode `llvm-objdump` 时，对候选函数保存至多 1024 字节的 ARM64 汇编窗口。若 Mach-O 有函数起点表，窗口在下一函数起点截断。队列只沿唯一且位于本机 `__text`、有函数起点的直接 `bl` 或 `b` 目标继续，默认最多两层、四个后续函数。多目标、计算跳转和截断调用清单停止自动选择。工具不可用时记录 `unavailable`，前两层仍可完成。

这些层级可以进入同一份 `draft-analysis` 审阅任务，再由当前 coding agent 根据证据撰写正式报告和复刻规格。汇编、函数起点与静态分支是代码线索；它们不证明某次点击执行了该下游分支，也不是原作者源码。没有观察或推导依据的函数语义保持未知。

## 命令

```sh
.venv/bin/copyapp prepare-app --udid <UDID> --bundle <BUNDLE_ID> --script playbooks/<FLOW>.json --out cases/<PREPARATION>
.venv/bin/copyapp native-queue --candidates cases/<CANDIDATES> --limit 4 --follow-depth 2 --follow-limit 4 --out cases/<NATIVE_QUEUE>
.venv/bin/copyapp native-disasm --file <DECRYPTED_OR_UNENCRYPTED_MACHO> --sha256 <SHA256> --address 0xADDRESS --out cases/<FUNCTION>
.venv/bin/copyapp ghidra-function --file <DECRYPTED_OR_UNENCRYPTED_MACHO> --sha256 <SHA256> --address 0xADDRESS --ghidra-dir <GHIDRA_INSTALL_DIR> --out cases/<DECOMPILATION>
.venv/bin/copyapp hopper-function --file <DECRYPTED_OR_UNENCRYPTED_MACHO> --sha256 <SHA256> --address 0xADDRESS --out cases/<HOPPER_FUNCTION>
.venv/bin/copyapp hopper-queue --candidates cases/<CANDIDATES> --limit 4 --out cases/<HOPPER_QUEUE>
.venv/bin/copyapp ghidra-queue --candidates cases/<CANDIDATES> --ghidra-dir <GHIDRA_INSTALL_DIR> --java-home <JDK_HOME> --limit 4 --out cases/<QUEUE>
.venv/bin/copyapp ghidra-queue --candidates cases/<CANDIDATES> --native cases/<NATIVE_QUEUE> --branch-flow cases/<TRACED_FLOW> --ghidra-dir <GHIDRA_INSTALL_DIR> --java-home <JDK_HOME> --limit 4 --out cases/<INDIRECT_QUEUE>
.venv/bin/copyapp ghidra-indirect --udid <UDID> --investigation cases/<INVESTIGATION> --objc-index cases/<ANALYSIS>/decrypted/static/objc-index.json --ghidra-dir <GHIDRA_INSTALL_DIR> --java-home <JDK_HOME> --out cases/<INDIRECT_FOLLOW>
.venv/bin/copyapp prepare-app --udid <UDID> --bundle <BUNDLE_ID> --script playbooks/<FLOW>.json --provider ghidra-direct --ghidra-dir <GHIDRA_INSTALL_DIR> --java-home <JDK_HOME> --out cases/<PREPARATION>
.venv/bin/copyapp prepare-app --udid <UDID> --bundle <BUNDLE_ID> --script playbooks/<FLOW>.json --provider hopper-direct --out cases/<HOPPER_PREPARATION>
```

`ghidra-function` 使用 Copy APP 自带的 Java post-script，直接调用 Ghidra Headless；它不会启动 REA，也不复制 REA 的桥接代码。命令核对原始 Mach-O 的 SHA-256、请求地址和 Ghidra 返回的函数入口，保存伪代码、脚本、日志及完整证据清单。`ghidra-queue` 从已验证的 Frida/静态候选中按命中次数选取有限函数；传入 `--native <NATIVE_QUEUE>` 时，还会从同一二进制已核验的原生汇编队列选取唯一直接调用的下游函数。选出多个函数时在一次 Ghidra 导入和自动分析中依次反编译，分别保存函数证据与共用会话日志。`--provider ghidra-direct` 将候选和原生队列自动接到 `investigate-flow`、`investigate-app`、`prepare-analysis` 与 `prepare-app`，其产物进入同一份审阅任务和正式报告；`--function-limit` 限制运行时入口数，额外的静态跟随函数由原生队列自身的深度及数量上限约束。工具链会在手机操作前预检。`copyapp report --evidence ID=<DECOMPILATION_OR_QUEUE>` 可导入单函数或整队列案例。外部 Ghidra 和兼容 JDK 仍是反编译所需的工具，Copy APP 自身不附带它们。旧 `--provider ghidra|hopper`（REA 后端）已删除；当前接受 `none`、`ghidra-direct` 与 Copy APP 自己的 `hopper-direct`。伪代码须由 Coding Agent 结合动态证据审阅，不能当作原始源码或点击因果证明。

`hopper-function` 使用本仓库 Python 脚本直接调用 Hopper；`hopper-queue` 根据已校验的候选地址逐函数分析。集成路径在手机操作前预检 Hopper 安装，保存原始 Mach-O、ARM64 slice、函数地址、脚本和伪代码哈希。Hopper 需外部 GUI 安装和正常 macOS 用户会话，受限会话的 Spotlight 查询可能导致启动失败。与 Ghidra 不同，当前 Hopper 队列尚不自动跟随直接或间接调用。详见[独立 Hopper 接入](rea-hopper-integration.md)。

对 `blr` 间接调用，可用 `flow-capture` 在原机一次点击中记录指定指令和寄存器的目标地址，再让 `ghidra-queue --branch-flow` 选择同一步观测到的 App 内目标。Copy APP 会重验原生汇编确有该 `blr`、目标是 Mach-O 精确函数起点、Frida 案例与候选属于同一二进制，并把全部来源复制进队列。它只确定观察窗口内执行过该目标；功能因果关系还要结合下游伪代码和 UI 实验审阅。

`ghidra-indirect` 把这两个步骤合成一次调用：从已验证调查的原生队列自动发现至多八个 `blr` 位点，重放保存的原版脚本采寄存器，再用直接 Ghidra 批量分析同一步真正观测到的目标。结果的 `queue/` 子目录可直接作为 `copyapp report --evidence` 输入。重放会再次操作原版 App，因此要先确认所选脚本的点击范围和初始状态；若多处分支或没有命中，保留失败案例并改为定向脚本，不把未命中解释成不存在该功能。

新的直接 Ghidra 案例还会写出 `function-facts.json`：函数签名、Ghidra 的有界静态调用者与被调用者、thunk/external 标记和缺失间接调用的限制说明。Copy APP 校验文件哈希、函数地址及名称；旧案例继续按原格式验证。调用关系是 Ghidra 静态观察，不证明某次手机操作执行了这些边。来源和移植边界见[REA 独立运行说明](rea-independence.md)。

若分支轨迹已成功保存但 Ghidra 阶段失败，以相同参数和输出路径加 `--resume`：Copy APP 重新核对来源、脚本、选中的 `blr` 位点和真机轨迹，只重跑 Ghidra；失败队列归档到 `attempts/`。若失败发生在真机脚本阶段，要求用新案例调查初始状态，避免悄悄重复一次可能改变状态的点击。已完成案例的 `--resume` 只做来源与语义校验，不操作手机。

REA 可作为历史证据来源，但不是默认或直接 Ghidra 流程的运行依赖。Copy APP 保留自己编写的证据格式、候选选择、ARM64 跟随、Ghidra Headless 脚本和报告校验；只借鉴了 REA 关于 Ghidra 分析器选项的实现思路，并保存其 MIT 许可文本。将来若移植 REA 其他代码，应限定到所需功能，记录原文件、版本和许可；Ghidra、JDK、Frida 及手机侧组件仍是各自独立的外部工具。

单函数和独立队列可显式加 `--disable-analyzer 'Objective-C Message Analyzer'`；整条调查和 `prepare-app` 可加 `--ghidra-disable-analyzer 'Objective-C Message Analyzer'`。Copy APP 在 Ghidra 自动分析前关闭这个分析器，案例保存配置脚本、配置结果和哈希，续跑也核对所选配置。该配置用于调查大型 App 的分析耗时，可能改变 Ghidra 得到的伪代码，报告应注明所用配置。配置脚本参考了 REA 的 MIT 许可分析选项思路，许可文本保存在 [REA-LICENSE.txt](third-party/REA-LICENSE.txt)。默认配置不关闭任何分析器；如果 Ghidra 日志显示自动分析超时，即使目标函数伪代码已写出，Copy APP 也将这次结果判为失败。

## 已验证范围

- 本地单元测试覆盖默认无 REA、操作前视图选入口及失败回退、没有 Objective-C 方法、没有静态候选、原生工具不可用、函数边界与跟随结果的来源核验，以及 Ghidra 直连案例的来源和篡改拒绝。
- 从 XR 既有夹具证据离线重放的三条流程，在去掉 REA 后生成并校验了多流程调查、分析草稿及 `TASK.md`。单流程仅 UI、UI 加方法候选、以及包含原生汇编的报告导入都成功。
- XR Calculator 既有候选的本机反汇编从入口 `0x10000eb0c` 静态跟随到 `0x10000e9b8`，然后发现 10 个本地直接分支目标并停止自动选择；两份汇编及队列来源核验通过。

**XR 真机已验收**：在 iPhone XR / iOS 16.1.1 上以默认 `--provider none` 直接运行 `prepare-app`，完成 Calculator 的手机采集、原生候选分析、事实草稿和 `TASK.md`。随后另行重放五次点击，同时观测十个候选分支，并生成了无 REA 的正式报告与来源关联交付；两者均通过 `copyapp verify`。案例分别位于 `cases/calculator-prepare-app-no-rea-live-20261015`、`cases/calculator-no-rea-reviewed-report-20261015` 和 `cases/calculator-no-rea-analysis-delivery-20261015`。报告仅覆盖竖屏 `7 + 8 = 15` 等已采证据；更广的功能和语义仍须逐项验证。iOS 17/26 仍按用户安排暂缓。

**复刻交接与真机闭环已验收**：`rebuild-plan`、`agent-task` 与 `rebuild-task-check` 现能从 `app_investigation` 的多条已验证子流程中按脚本哈希及末端视图断言选出正确原版脚本。`cases/calculator-no-rea-rebuild-preparation-v4-20261015` 给出了 `ready_for_agent` 任务；在同一 XR 上复用已安装的独立 CalculatorClone 0.1.10 执行 `cases/calculator-no-rea-rebuild-check-20261015`，末端 `15` 与 `C` 的 UIKit 断言两端通过。两对截图审阅均为轻微差异，`cases/calculator-no-rea-agent-delivery-20261015` 已保存已验证的任务、安装、对照和逐图审阅关联。现有复刻源码早于本次无 REA 报告，不应宣称由这次报告自动生成。

**加密 App 的独立新源码试点**：XR 上 `prepare-app --decrypt` 以 `provider=none` 对 DeepSeek 2.4.4 恢复主程序与分享扩展，32 个 Mach-O 检查通过。大规模方法索引无法唯一确定按钮入口时，默认调查仍保存 UI 证据；根据同次 UIKit 树中 `DSButton` 的类归属，另行明确选择 `DSButton::objcOnTap` 并重放，Frida 记录当前 IMP 与静态入口各一次命中，本机汇编跟到本地函数后在间接回调处停止。增加末端弹窗就绪文字的原版脚本后，`cases/deepseek-no-rea-reviewed-report-ready-20261015`、分析交付和复刻任务均通过校验。当前 Coding Agent 独立编写 `rebuild/DeepSeekClone`，编译为 iOS 16 App，TrollStore 安装到 XR；`cases/deepseek-no-rea-agent-delivery-20261015` 记录 1/1 条选定行为断言通过，同时两对图片均有明显品牌图形和图标差异。此试点没有证明完整 DeepSeek 复刻、其他登录方式或认证行为。

**无需手动指定入口的真机复验**：改进方法筛选后，`cases/deepseek-no-rea-auto-method-investigation-20261015` 在同一 XR 上只给解密分析包和登录入口脚本运行 `investigate-flow`，没有传 `--method` 或 REA provider。操作前 UIKit 视图将 “Continue with Password” 关联到 `DSButton`，唯一选出 `objcOnTap`；点击窗口里当前 IMP 和主程序静态入口各命中一次。原生反汇编完成，`rea_status=not_requested`，案例哈希和跨阶段身份校验均通过。视图类筛选只是候选生成；运行时命中证明观察窗口内执行过入口，不单独证明按钮到下游函数的全部因果链。

**直接 Ghidra 真机来源验证**：XR Calculator 的三条原版流程再次由默认 `provider=none` 采集并完成无 REA 分支观测。对原版二进制中百分比路径的候选地址 `0x10000f09c`，`ghidra-function` 直接运行本机 Ghidra，生成 `cases/calculator-direct-ghidra-percent-20261015`；该案例通过来源校验，并被 `cases/calculator-three-flow-no-rea-reviewed-report-20261015` 导入。三条流程的分析交付及复刻任务分别位于 `cases/calculator-three-flow-no-rea-analysis-delivery-20261015` 和 `cases/calculator-three-flow-no-rea-rebuild-preparation-20261015`。这些报告与任务已通过 `copyapp verify`。新增的 `cases/calculator-direct-ghidra-queue-addition-v3-20261015` 则从 Calculator 加法的实际候选直接选函数并运行 Ghidra；`cases/calculator-direct-ghidra-app-investigation-20261015` 经 XR 真机再采集，生成 `cases/calculator-direct-ghidra-preparation-20261015/draft/TASK.md`，审阅任务已包含伪代码与原生汇编，均未调用 REA。

**三流程复刻对照**：同一 XR 上的 `cases/calculator-three-flow-no-rea-rebuild-check-20261015` 将加法、`100 + 10% = 110`、重复等号三个原版流程与已安装 CalculatorClone 0.1.10 对照；两端各流程末端 UIKit 断言均通过。六对截图逐张审阅，记录顶部返回文字、数字笔画与正负号字形的轻微差异。`cases/calculator-three-flow-no-rea-agent-delivery-20261015` 连同分析交付、复刻任务和真机对照均已通过来源校验。本次复用的复刻源码早于这份新报告，不能据此宣称“由无 REA 报告自动生成 App”。本地 192 项单元测试通过。

**一命令直连验收**：`cases/calculator-prepare-app-ghidra-direct-live-20261015` 在 XR 上从采集 Calculator 开始，完成一条加法流程的 UI/Frida、原生汇编和直接 Ghidra 反编译，再产出 `preparation/draft/TASK.md`。父案例、来源子案例和工具链记录通过 `copyapp verify`；状态 `needs_semantic_review`，因为反编译结果仍需 Coding Agent 审阅和归纳。没有启动 REA。此验证是单条流程，不能证明任意 App 或三条流程都能在 Ghidra 下成功。

**大型加密 App 的配置对照**：DeepSeek 2.4.4 解密主程序约 20.8 MB，同一 `DSButton::objcOnTap` 候选在 Ghidra 默认自动分析中于第 540 秒超时；旧运行虽写出伪代码，当前 Copy APP 校验会拒绝。显式关闭 `Objective-C Message Analyzer` 后，Ghidra 在 431 秒完成自动分析，`cases/deepseek-direct-ghidra-profiled-queue-20261015` 的候选、配置脚本、输出与二进制哈希通过校验。[限定入口报告](../cases/deepseek-no-rea-direct-profile-report-20261015/report.md)和[分析交付](../cases/deepseek-no-rea-direct-profile-analysis-delivery-20261015/report.md)引用该证据并保持登录后及间接回调行为为未知。这里比较的是两次不同分析配置的运行，不能保证其他大型 App 有相同耗时或伪代码质量。

**大型 App 真机整条调查**：使用相同的显式分析配置，XR 上的 `cases/deepseek-direct-ghidra-profiled-investigation-20261015` 从原版登录入口 UI、Frida 观察和静态候选运行到直接 Ghidra 反编译，调查状态为 `complete`，`copyapp verify` 与跨阶段身份校验均通过。这个流程没有调用 REA；入口函数内的间接回调、认证和登录后行为仍需进一步取证。

**多函数直连验证**：Copy APP 的批量 post-script 在本机 Ghidra 中对 XR 采集的 Calculator 主程序只导入一次，依次反编译 `0x10000eb0c` 和直接调用目标 `0x10000e9b8`；`cases/calculator-direct-ghidra-batch-v2-20261015` 的两份函数结果均通过二进制哈希、入口地址与脚本来源校验。随后以 XR Fixture App 的两处 Frida 观察入口运行完整 `ghidra-queue`，`cases/fixture-notes-direct-ghidra-batch-queue-20261015` 的单次导入、两份伪代码、候选来源和全部证据通过队列语义校验。队列故障拒绝亦有单元测试覆盖。完整回归测试为 194 项通过。

**自动下游函数链**：`cases/calculator-direct-ghidra-follow-queue-20261015` 把 Calculator 的运行时入口及其在原生汇编中唯一确定的直接调用目标一起送入一次 Ghidra 会话。队列保存候选、原生汇编和两份伪代码；语义校验重算静态跟随决策。`cases/calculator-direct-ghidra-follow-investigation-20261015` 在 XR 上由 `investigate-flow --provider ghidra-direct` 自动得到相同的两层证据；`cases/calculator-direct-ghidra-follow-preparation-20261015` 的 `draft/TASK.md` 将下游函数明确标为静态跟随，父案例及整案调查通过校验。正式[限定范围报告](../cases/calculator-direct-follow-reviewed-report-v3-20261015/report.md)现直接列出两函数的地址、来源类型与伪代码链接，报告和函数计数索引通过校验。篡改下游来源地址并同步更新哈希后，语义校验仍拒绝该队列。下游函数的实际点击命中仍未由此证明。完整回归测试为 195 项通过。

**复刻交接实测**：基于同一函数链的[单流程规格](calculator-direct-follow-feature-spec.json)生成正式报告、复刻计划和 `cases/calculator-direct-follow-agent-task-20261015/TASK.md`。任务直接链接两份伪代码与原生汇编。XR 上用已安装的独立 CalculatorClone 0.1.10 对照，`cases/calculator-direct-follow-rebuild-check-20261015` 的末端 `15` 断言通过，两对截图经 `cases/calculator-direct-follow-visual-review-20261015` 逐张标记轻微差异，`cases/calculator-direct-follow-agent-delivery-20261015` 通过来源校验。旧复刻源码先于该报告，不能据此声称由报告自动生成。

**运行时间接调用目标的无 REA 实测**：在 XR 上重放 DeepSeek 密码入口，`cases/deepseek-on-tap-closure-branch-20261015` 记录 `DSButton::objcOnTap` 静态入口与下游 `0x100820dac` 的 `blr x19` 在同一步各命中一次，`x19` 指向 App 内精确函数起点 `0x1002ff218`。`cases/deepseek-direct-ghidra-indirect-profiled-queue-20261015` 一次导入同一解密主程序，反编译运行时入口 `0x100821558`、静态直接目标 `0x100820cec` 和该运行时间接目标；三份伪代码、候选、原生指令、原始流程及跨阶段地址绑定均通过校验。目标 `0x1002ff218` 是一个薄回调层，其伪代码把 `0x1002f908c` 作为函数指针传入 `0x1002fc930`；这两个地址均有 Mach-O 函数起点，当前只保存了对应原生汇编。这个结果解释了按钮通用回调的部分路径，尚不能把条款弹窗归因到某个具体分支，也未完成账号认证逆向。完整本地回归测试为 197 项通过。

**自动间接跟随及交付复验**：`cases/deepseek-ghidra-indirect-one-command-20261015` 由 `ghidra-indirect` 从已有调查自动找出 `0x100820dac` 的 `blr x19`，在 XR 上重放保存的脚本，再一次导入 Ghidra 得到相同三层函数；组合案例的哈希与语义校验通过。本次运行后为新加入的来源校验补录了同哈希的 ObjC 索引和调查清单副本，后续运行由命令直接保存。验证器额外核对原 Mach-O 的 ARM64 指令字节；人为改动保存的寄存器名称并重算外层文件哈希后仍拒绝该案例。新[正式报告](../cases/deepseek-no-rea-indirect-profile-report-v2-20261015/report.md)把已观测目标、静态伪代码与未知的弹窗因果分开；[复刻任务](../cases/deepseek-no-rea-indirect-agent-task-v2-20261015/TASK.md)直接链接三份伪代码、原生汇编和分支轨迹。同一 XR 的[真机对照](../cases/deepseek-no-rea-indirect-rebuild-check-v2-20261015/report.md)通过 1/1 条末端行为断言；[逐图审阅](../cases/deepseek-no-rea-indirect-visual-review-v2-20261015/report.md)记录两张画面均有较大图形差异，[交付案例](../cases/deepseek-no-rea-indirect-agent-delivery-v2-20261015/report.md)保留该状态。复刻源码来自先前试点，这次新报告没有自动生成新源码。已完成案例的 `--resume` 证实不访问手机或 Ghidra；模拟的 Ghidra 失败案例在不重复真机点击的情况下归档旧队列并完成重试。完整本地回归测试为 199 项通过。
