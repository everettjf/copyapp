# DeepSeek 登录页三流程：XR 真机分析与复刻验收

设备为越狱 iPhone XR / iOS 16.1.1；原版 `com.deepseek.chat` 为 2.4.4 (3)，独立实现的 `dev.copyapp.deepseekclone` 为 0.1.3 (4)。[原版深度报告 v10](../cases/deepseek-no-rea-three-flow-network-report-v10-20261015/report.md)包含三条已选登录页流程、关键函数证据、包与资源索引，以及有边界的 URLSession 观察；[分析交付](../cases/deepseek-no-rea-three-flow-network-delivery-v10-20261015/report.md)核对三条原版脚本来源。默认流程没有调用 REA。

[复刻任务](../cases/deepseek-three-flow-rebuild-preparation-v10-20261015/task/TASK.md)从该报告生成，选定密码入口、Sign up 和条款弹窗 Cancel，均停留在条款同意之前。[XR 对照](../cases/deepseek-three-flow-rebuild-check-v10-20261015/report.md)在相同设备和 UI 后端上重放原版与复刻版：三条流程的操作后脚本断言及末端 UIKit 文本断言均通过。Cancel 后两边都回到登录首页，未点击 Agree。

[六对截图的逐张审阅](../cases/deepseek-three-flow-visual-review-v10-20261015/report.md)把三条流程的画面都标为轻微差异：复刻版鲸鱼图形的轮廓与原版不同，字标笔画有差别，顶部系统返回名称不同；登录按钮、条款弹窗位置和文字接近。审阅只覆盖保存的静态画面，不能证明动画或未测页面一致。

[交付核验](../cases/deepseek-three-flow-agent-delivery-v10-20261015/report.md)封存了源码快照、已安装 IPA、安装记录、真机对照和视觉审阅。结果为 3/3 条已选行为断言通过、0 条未审视觉流程、3 条有轻微视觉差异。没有独立 Agent CLI 生成源码的运行记录，因而不能从这份交付推断源码由外部 Agent 自动生成。

三条流程都属于未接受条款的登录页。密码表单、账号认证、服务端行为、Agree 后的状态、其他页面和 iOS 17/26 真机兼容尚未验收。网络事件与点击的时间关系在重复采集中不稳定；报告保留了这一限制。
