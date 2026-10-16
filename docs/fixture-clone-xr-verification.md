# 混合技术栈夹具的 XR 复刻验证

设备：iPhone XR / iOS 16.1.1。原版为 `dev.copyapp.fixture`，复刻版为 `dev.copyapp.fixtureclone` 0.1.0 (1)。这是一款已知源码测试夹具，用于校准 Copy APP 对 SwiftUI、UIKit/SQLite 和独立 Framework 的分析与复刻路径；复刻工程 [FixtureClone](../rebuild/FixtureClone) 为另写的实现。

## 从报告到任务

旧版夹具脚本缺少 `scenario_id` 和截图就绪条件，不能作为成对重放输入。修订后的 Counter、Notes、Catalog 三条脚本在 XR 上分别完成[真机采集](../cases/fixture-counter-comparable-ready-flow-20261015/manifest.json)、[真机采集](../cases/fixture-notes-comparable-ready-flow-20261015/manifest.json)和[真机采集](../cases/fixture-catalog-comparable-ready-flow-20261015/manifest.json)。[夹具报告 v14](../cases/fixture-xr-deep-report-v14-20261015/report.md)导入这三条流程，规格指定独立 Bundle ID。[一命令复刻交接](../cases/fixture-rebuild-preparation-v2-20261015/task/TASK.md)状态为 `ready_for_agent`，三条流程均有可引用原版脚本，无证据缺口；报告、交接及来源哈希通过验证。

## 独立复刻与真机结果

复刻版采用 SwiftUI 计数页面、UIKit 导航和笔记页、SQLite 持久化，以及自建的 `CloneCatalogCore.framework` 生成目录项。[分析 IPA 的静态索引](../cases/fixture-clone-static-v1-20261015/ipa-index.json)确实列出该 Framework；[安装记录](../cases/fixture-clone-install-v1-20261015/install.json)绑定了安装在 XR 上的 IPA 哈希、Bundle ID 和版本。

[三流程真机对照](../cases/fixture-three-flow-rebuild-check-v1-20261015/report.md)使用报告自动生成的成对脚本，状态 `complete`，两边都成功重放。Counter 和 Notes 在操作后各通过一次数字 `+1` 断言，Catalog 在点击后看到 Alpha、Local sample A、Beta、Local sample B。重新启动复刻版进程后，再单独重放[Counter](../cases/fixture-clone-counter-relaunch-20261015/manifest.json)和[Notes](../cases/fixture-clone-notes-relaunch-20261015/manifest.json)：前者可见值从 1 到 2，后者保存数从 1 到 2。[复刻版沙盒元数据](../cases/fixture-clone-sandbox-after-relaunch-20261015/sandbox-index.json)列出 `Documents/fixture-notes.sqlite` 及 App 偏好设置文件；未在本轮独立读取数据库正文或偏好设置键值。

五对截图的[逐图审阅](../cases/fixture-three-flow-visual-review-v1-20261015/report.md)指出：Counter 原版从 9 到 10，复刻版从 0 到 1；Notes 原版从 9 到 10，复刻版从 0 到 1。两边各自满足增量断言，但已有数据基线不同，四对截图因此标为重大差异。Catalog 的两行文本和布局接近，顶部返回上一 App 的系统文字有轻微差异。没有把功能增量通过写成视觉一致。[交付核验](../cases/fixture-clone-agent-delivery-v1-20261015/report.md)据此报告 3/3 操作后脚本断言通过、2 条流程有重大截图差异、0 条未审流程，并保存源码及已安装 IPA 的快照。

本次只验证 XR 上三条代表流程。分享扩展、数据库行内容、更多页面和 iOS 17/26 均未在复刻版验收。复刻源码是在当前 Codex 会话中实现，没有独立 `agent-run` 生成源码记录；案例的哈希校验不能证明未观察行为等价。

## 任务直连命令复测

新增 `copyapp rebuild-task-check --task cases/fixture-rebuild-preparation-v2-20261015/task --out cases/<NEW_CHECK>`，从已验证任务自动读取设备、后端和三组脚本，在触屏前重新核对原始报告证据。用它在 XR 取得的[第二轮真机对照](../cases/fixture-three-flow-rebuild-check-v2-20261015/report.md)再次为 `complete` 且来源核验通过；[逐图审阅](../cases/fixture-three-flow-visual-review-v2-20261015/report.md)记录 Counter 10→11 对比 2→3、Notes 10→11 对比 2→3 的基线差异，[第二轮交付](../cases/fixture-clone-agent-delivery-v2-20261015/report.md)仍为 3/3 操作后断言通过、两条流程有重大视觉差异。新生成的[任务模板 v3](../cases/fixture-rebuild-preparation-v3-20261015/task/TASK.md)直接显示这条短命令；原有任务保留原哈希。

## 对齐测试数据后的第三轮

先用四条只读观察脚本确认原版 Counter 和 Notes 均为 11、复刻版均为 3。随后仅通过复刻版自身的 Increment counter 和 Add sample note 按钮各操作 8 次；[Counter 补齐脚本](../cases/fixture-baseline-alignment-v1-20261015/scripts/counter-seed-clone.json)及[Notes 补齐脚本](../cases/fixture-baseline-alignment-v1-20261015/scripts/notes-seed-clone.json)检查起始值、操作增量与终值 11；未清除或修改原版数据。第三轮[任务直连对照](../cases/fixture-three-flow-rebuild-check-v3-20261015/report.md)显示 Counter 和 Notes 两边均从 11 到 12，Catalog 的两行内容相同。五对图片[逐图审阅](../cases/fixture-three-flow-visual-review-v3-20261015/report.md)均为轻微差异，主要是顶部系统返回 App 名称、时间和少量间距；[交付核验](../cases/fixture-clone-agent-delivery-v3-20261015/report.md)记录 3/3 操作后断言通过、0 条重大视觉差异、0 条未审流程，所有案例通过 `copyapp verify`。

这次对齐只解决可见计数基线，不证明 SQLite 两边的记录内容相同；也不扩展到这三条脚本之外的功能。截图判断依赖保存图片的人工审阅，来源哈希只能证明审阅对象未改变。
