# iOS 16 与 17 双机验证矩阵

[English](two-device-verification-matrix.md) · [简体中文](two-device-verification-matrix.zh-CN.md)

此表区分“通道可用”和“App 有可见结果”。设备为 iPhone XR / iOS 16.1.1 / Dopamine rootless，以及 iPhone 14 / iOS 17.3.1 / Relaxin RootHide。本地 `cases/` 证据被 Git 忽略，需在测试 Mac 上用 `copyapp verify <CASE>` 核验；提交的脚本不含手机私有数据。

| 能力 | XR / iOS 16 | iPhone 14 / iOS 17 | 边界 |
| --- | --- | --- | --- |
| USB、截图、开发者文件系统、固定主机密钥的 mobile SSH、Frida、iOS MCP、已配对 iCTRL | `cases/ios16-v0110-doctor-20261017/` 全部可用 | `cases/ios17-v0110-doctor-20261017/` 全部可用 | 各代表一台手机的当前配置；能力探针通过不等于 App 行为通过。两份 v0.1.10 案例通过 `copyapp verify`。 |
| 包、静态与有界沙盒证据 | Calculator 当前 Agent 父案例 `cases/calculator-current-auto-workflow-20261016/` 完成 | Calculator 父案例 `cases/ios17-calculator-current-parent-20261017/` 完成 | 只覆盖该构建及选定路径，未取得整个实时数据容器的一致性快照。 |
| 加密 App 分析 | XR 发布记录中的 DeepSeek/Kimi 整包恢复 | [iPhone 14 记录](relaxin-roothide-iphone14.md)中的 Remoboard 主 App 与键盘扩展恢复 | 分析 IPA 不保留原签名；其他保护手段未覆盖。 |
| 选定报告 → 独立 App → 同机对照 | Calculator 父案例 3/3 结果、三对截图审阅 | Calculator 父案例 4/4 结果、五对截图审阅 | 两份独立源码均早于所引用的父案例；未证明整 App 等价或零样本生成。 |
| 可选 Hopper 直连反编译 | `cases/fixture-counter-hopper-investigation-v2-20261016/` 将夹具 UI、Frida、候选与 Hopper 调查贯通并导入报告 | `cases/ios17-hopper-current-parent-20261017/` 完成 `--analysis-provider hopper-direct` 的 Calculator `copy` 父案例，包含一条原版跟踪、Hopper 伪代码、审阅报告、签名独立复刻版、一条通过的成对结果及两对截图审阅 | 仅一条入口和流程。源码早于父案例；伪代码不是原始源码或完整算法。 |
| 两种界面后端：左滑删位 | **同一提交脚本** `playbooks/ios17-calculator-delete-digit.json` 在 iOS MCP 与 iCTRL 均显示 `98 → 9`：`cases/ios16-calculator-gesture-{iosmcp,ictrl}-v016-20261017/` | 同脚本、同结果：`cases/ios17-calculator-gesture-{iosmcp,ictrl}-20261017/` | 仅一条竖屏左滑和一组数字；前后截图与末端 UIKit 文字验证了可见效果。 |
| 两种界面后端：Safari 文本输入 | **同一提交脚本** `playbooks/ios17-safari-synthetic-address-input.json` 在 Safari 地址栏通过两个后端显示 `copyapp-fixture-hello`：`cases/ios16-safari-text-{iosmcp,ictrl}-20261017/` | 同脚本、同可见文字：`cases/ios17-safari-text-{iosmcp,ictrl}-20261017/` | 未提交搜索；其他输入框仍需逐一验证聚焦及可见结果。 |
| 两种界面后端：Translate 文本输入 | **同一提交脚本** `playbooks/ios17-translate-synthetic-input.json` 在两个后端都显示 `copyappfixture` 和键盘：`cases/ios16-translate-text-{iosmcp,ictrl}-20261017/` | 同脚本、同精确原文：`cases/ios17-translate-text-{iosmcp,ictrl}-20261017/`；自动出现翻译结果 | 仅一段合成文字。未按提交键；没有评估 iOS 17 自动翻译结果的语义质量。四份案例均通过校验。 |
| 两种界面后端：Clock 秒表 | **同一提交脚本** `playbooks/ios17-clock-stopwatch-start-stop.json` 经两个后端启动、停止非零秒表：`cases/ios16-clock-stopwatch-{iosmcp,ictrl}-20261017/` | 同脚本、同可见启停：`cases/ios17-clock-stopwatch-{iosmcp,ictrl}-20261017/` | 每个后端各一次短时前台运行，保存停止态截图和 UIKit 文字；未覆盖后台计时、闹钟与通知。四份案例均通过校验。 |
| URLSession 观察与 Translate 输入 | `cases/ios16-translate-network-v0110-20261017/` 完成同一输入脚本并附加 8 个任务启动 hook | `cases/ios17-translate-network-v0110-20261017/` 完成同一脚本，经 RootHide Frida 独立服务附加 7 个 hook | 两份案例通过校验，均记录到**零条**任务启动事件。仅证明限定窗口内 hook 附加与界面重放成功；不能据此推断没有网络流量。其他网络 API、进程和时间窗口不在观察范围内。 |
| URLSession 正事件对照：App Store Search 标签 | 一次启动失败和单独成功启动调查保留后，同一提交脚本 `playbooks/ios17-appstore-search-network-control.json` 捕获 21 条事件，其中 6 条落在点击窗口：`cases/ios16-appstore-search-network-retry-v0110-20261017/` | 同脚本捕获 12 条事件，其中 3 条落在点击窗口：`cases/ios17-appstore-search-network-v0110-20261017/` | 两份完成案例均通过校验。证明这些 App Store 进程和窗口内可采集任务启动元数据；时间相邻不证明每条请求均由点击引起。XR 首次失败案例保留。未执行搜索、安装或购买。 |
| 同一独立 Clock 复刻项目跨系统 | 复刻版通过秒表成对对照、停止态与运行态重启检查、iCTRL 回归和运行中升级至构建 5；构建 4 经核对后重试成功，构建 5 首次通过 | 同一源码通过成对对照、停止态与运行态重启检查、iCTRL 回归及签名后运行中升级至构建 5 | [双机记录](clock-clone-two-device.zh-CN.md)。构建 5 的两机安装及停止态重启案例通过校验；安装案例保存 IPA 快照。v0.1.9 的状态丢失已修复；计时值、标签文案和样式仍有差异，长时间后台计时及 Clock 全功能未验证。 |
| 复刻版秒表后台约一分钟 | 离开 App 70.2 秒后，运行值从 `00:01.25` 增至 `01:31.80`；启动、返回、停止案例均通过校验 | 离开 App 76.8 秒后从 `00:01.25` 增至 `01:36.55`；对应三份案例均通过校验 | [后台记录](clock-background-two-device.zh-CN.md)。每机仅一次；未核对原版 Clock、数小时挂起、设备重启、系统时间变化或精确计时误差。 |
| 已知源码夹具分享扩展 | [v0.1.5](releases/v0.1.5.zh-CN.md)中的固定文本接收与 Counter/Notes/Catalog 回归 | 相同 | 仅一种纯文本输入；其他内容类型和无关扩展未验证。 |
| 陌生 App 入口与三条界面路径：Apple Podcasts | 完成新功能页后，`cases/ios16-podcasts-main-survey-20261017/` 确认 Podcasts 处于前台；`cases/ios16-podcasts-discovery-20261017/` 的资料库、搜索、现在收听 3/3 通过。 | 初次启动失败时屏幕显示 SpringBoard 的 Podcasts 欢迎页。完成引导、选择 WLAN Only 并越过新功能页后，`cases/ios17-podcasts-main-survey-20261017/` 确认 Podcasts 处于前台；`cases/ios17-podcasts-discovery-20261017/` 的同三个目的页 3/3 通过。 | 四份完成案例均通过 `copyapp verify`；六张末端截图已逐张查看。两机资料库数据不同，坐标脚本也分别编写。此处只验证进入 App、导航与可见终态；未验证砸壳、深度报告、生成源码、播放或整 App 等价。 |

XR 旧 Translate 脚本点击 `(207,320)`，iOS MCP 虽返回字符派发成功，界面却无文字。同一旧脚本在 `cases/ios16-translate-old-tap-control-20261017/` 再次失败，截图有光标而无键盘。新共享脚本点击可见输入提示 `(100,201)`，键盘出现，两机两后端都通过。这证明该界面存在随点击及聚焦状态变化的差异，不能据此推断 XR 整机的 iOS MCP 文本输入失败。

iOS 17 的 Translate 和 Clock 尚未完成首次使用引导时，iOS MCP 与原生 RSD 的启动请求报错；iCTRL 启动 Translate 也报错。但屏幕实际显示 SpringBoard 的对应 App **Welcome / Accept & Continue** 页面，因此不能把这些报错当作 App 未安装或损坏的证据。测试手机上的 Translate 随后完成首次使用设置：无线数据选 WLAN Only、可选 Siri/听写音频分享选 Not Now；Clock 欢迎页也已完成。两个 App 此后进入各自进程，通过上表的选定流程；重新运行的 `cases/ios17-{translate,clock}-post-onboarding-survey-20261017/` 也通过校验，采集前后的前台 Bundle ID 均与目标一致。失败尝试保留在 `cases/ios17-translate-{entry-survey,native-survey,ictrl-launch-probe}-20261017/` 与 `cases/ios17-clock-{entry-survey,native-survey}-20261017/`。首次使用选择属于设备状态，提交脚本以能够进入正常界面为前提。

Podcasts 在 iOS 17 上重现相同的首次启动现象：第一次 `survey --launch` 失败，随后单独采到 SpringBoard 的欢迎页。完成欢迎页、无线数据选择后，两机均进入 Podcasts 并通过各自的三流程发现验收。XR 还出现了单独的资料库介绍页。这些引导操作只在测试机上执行；提交的导航脚本从正常标签栏开始。iOS 17 截图含已关注节目，XR 资料库为空，因此脚本按设备状态断言就绪内容，不把账号数据当作跨机相同输出。

v0.1.7 发布后，XR 的 Calculator 和 Translate 父案例、iOS 17 的四流程 Calculator 和一流程 Hopper 父案例再次通过 `copyapp verify`。v0.1.10 正式发布页下载的 wheel 与发布 SHA-256 一致，并从独立 `/tmp` 安装目录加载版本与 CLI 入口；两机新建的 doctor 和 Translate 网络观察案例也通过 `copyapp verify`。这些是产物、通道及证据完整性检查，不是重新执行所有原版/复刻版流程，也不能证明无关 App 行为。

仍需解决的产品级门槛包括：陌生 App 的自主发现和全新源码生成、独立 Claude CLI 运行、更广的 App 状态与服务端行为、Clock 更长时间及受系统事件干扰的计时、TrollStore 升级首次成功率，以及完整沙盒与网络解释。App Store 的正事件只覆盖一个进程和有界时间窗口，不能解释全部请求或服务端行为。更宽的结论不能由绿色设备探针、选定流程通过或发布标签推出。iOS 26 不在此双机矩阵内。
