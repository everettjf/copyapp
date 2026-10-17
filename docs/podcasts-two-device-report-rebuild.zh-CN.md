# Apple Podcasts 在 iOS 16 与 17 上的分析和全新源码复刻

[English](podcasts-two-device-report-rebuild.md) · [简体中文](podcasts-two-device-report-rebuild.zh-CN.md)

本记录覆盖 iPhone XR / iOS 16.1.1 / Dopamine rootless 和 iPhone 14 / iOS 17.3.1 / Relaxin RootHide 上的选定流程。目标为系统 Apple Podcasts（`com.apple.podcasts`），两机的构建号分别是 1710.17 和 4023.410.2。本机 `cases/` 被 Git 忽略，可在测试 Mac 上用 `copyapp verify <CASE>` 核对来源记录。

## 分析

[XR 报告](../cases/ios16-podcasts-reviewed-report-20261017/report.md)与 [iPhone 14 报告](../cases/ios17-podcasts-reviewed-report-20261017/report.md)分别涵盖包采集、内嵌 Framework 和扩展、选定 UIKit 类、资料库/搜索/现在收听页面、有界沙盒元数据、网络任务启动元数据及未知项。[XR](../cases/ios16-podcasts-analysis-delivery-20261017/report.md)与 [iPhone 14](../cases/ios17-podcasts-analysis-delivery-20261017/report.md) 的分析交付各核验了三条有来源流程；报告和交付都通过 `copyapp verify`。

Hopper 在两种构建上分别解释标签控制器的 `viewDidLoad` 和 `PodcastsStoreUI.SearchLandingCell` 的初始化主体：后者创建插画视图、文字标签并布置约束。这是反编译器的解释，不是 Apple 原始源码。Copy APP 新增了内嵌 Framework 静态 hook 的完整相对路径匹配。XR 的搜索点击窗口中，`SearchLandingCell::initWithFrame:` 的当前 IMP 与静态偏移各命中 12 次；iOS 17 的 hook 正确附加，但同一限定窗口内该初始化方法为零次。视图可能在附加前已创建或在窗口外创建；命中数本身不证明点击因果。

两机主程序都没有加密加载命令，因此 Podcasts 没有检验砸壳路径。XR 和 iOS 17 的搜索窗口分别记录 13 与 11 条 URLSession 任务启动元数据，另两条采样流程为零。这不能解释响应内容、全部网络活动或服务端实现。沙盒索引只包含限定范围的元数据，也不是用户数据的原子快照。

## 独立实现与真机对照

[PodcastsFreshProbe 源码](../rebuild/PodcastsFreshProbe/README.md)在审阅报告后全新编写，使用公开 UIKit、系统图标和独立 Bundle ID `com.copyapp.podcasts.fresh`。Xcode 27 面向 iOS 16 及以上编译；XR 用 TrollStore 安装临时签名 IPA，iPhone 14 用 Apple Development 签名 IPA 经 USB 安装。[XR](../cases/ios16-podcasts-fresh-install-20261017/install.json)和 [iPhone 14](../cases/ios17-podcasts-fresh-install-20261017/install.json) 的安装案例均通过校验。

[XR 成对检查](../cases/ios16-podcasts-fresh-check-20261017/report.md)和 [iPhone 14 成对检查](../cases/ios17-podcasts-fresh-check-20261017/report.md)在各自手机上分别重放原版与复刻版的资料库、搜索和现在收听。六条末端 UIKit 标题断言及脚本就绪标记全部通过。每机保存三对截图，并分别完成 [XR 逐图审阅](../cases/ios16-podcasts-fresh-visual-review-20261017/report.md)与 [iPhone 14 逐图审阅](../cases/ios17-podcasts-fresh-visual-review-20261017/report.md)。

| 设备 | 成对导航 | 视觉判断 | 交付 |
| --- | --- | --- | --- |
| XR / iOS 16.1.1 | 3/3 标题及就绪标记通过 | 资料库与现在收听有轻微差异；搜索的分类插画和控件有重大差异 | [选定行为通过，视觉有缺口](../cases/ios16-podcasts-fresh-delivery-20261017/report.md) |
| iPhone 14 / iOS 17.3.1 | 3/3 标题及就绪标记通过 | 三对均有重大差异；原版含账号相关节目卡片及封面，复刻版没有 | [选定行为通过，视觉有缺口](../cases/ios17-podcasts-fresh-delivery-20261017/report.md) |

两机计划、任务、安装、成对检查、视觉审阅和交付全部通过 `copyapp verify`。这验证了两台指定手机上的流程工具与选定导航，**不证明**视觉一致、播放、关注、下载、搜索结果、推荐逻辑、账号同步、购买或整 App 等价。源码由当前 Agent 编写；尚无独立 Claude CLI 运行或完全自动的零样本源码生成。
