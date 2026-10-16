# Calculator 字体与显示区真机复核

设备：iPhone XR，iOS 16.1.1。原版为 `com.apple.calculator`；独立复刻版为 `dev.copyapp.calculator`。以下结论只针对本机竖屏、保存的页面和输入状态。

## 原版运行时字体

`copyapp view-tree` 现在从当前 UIKit `UILabel.font` 保存字体名称和 point size。原版及前后两版复刻的原始案例分别在 [原版](../cases/calculator-font-original-20261015/view-tree.json)、[0.1.6](../cases/calculator-font-clone-v7-20261015/view-tree.json) 和 [0.1.8](../cases/calculator-font-clone-v9-20261015/view-tree.json)，均通过 `copyapp verify`。

| 位置 | 原版 XR 观察 | 复刻版 0.1.6 | 当前实现 0.1.10 |
| --- | --- | --- | --- |
| 结果数字 | `.SFUI-ThinG2` 93pt | `.SFUI-Thin` 100pt | 公开系统 Thin 112pt，标签高 111pt |
| C/AC | `.SFUI-Medium` 34pt | `.SFUI-Regular` 35pt | 系统 Medium 34pt |
| ±、% | `.SFUI-MediumG3` 34pt | `.SFUI-Regular` 35pt | 系统 Medium 34pt |
| 数字键 | `.SFUI-Regular` 40pt | `.SFUI-Regular` 42pt | 系统 Regular 40pt |
| 运算符 | `.SFUI-Medium` 46pt | `.SFUI-Regular` 42pt | 系统 Medium 46pt |
| 小数点 | `.SFUI-Semibold` 40pt | `.SFUI-Regular` 42pt | 系统 Semibold 40pt |

原版结果 UILabel 的绝对顶部约 220.5pt、高 111pt、右边缘 380pt。旧复刻标签顶部 225pt、高 100pt。曾尝试通过 `UIFont(name:)` 直接加载 `.SFUI-ThinG2` 和 `.SFUI-MediumG3`，但 0.1.7 在 XR 的视图树实际返回 **TimesNewRomanPSMT**；因此未沿用私有名称。0.1.8 改回公开系统字体；0.1.9 只把结果字体设为 112pt，100pt 高标签导致实际字形未变。0.1.10 同时把结果标签改为顶部约 220.5pt、高 111pt，才得到接近原版的字形尺寸。这些中间尝试分别保留在本地 `calculator-font-clone-v8/v9`、`calculator-font-check-v10/v11` 案例中。

## 同设备对照结果

当前 [0.1.10 (11) 安装记录](../cases/calculator-clone-install-v11-20261015/install.json) 与[九流程真机对照](../cases/calculator-nine-flow-rebuild-check-v11-20261015/report.md)绑定。九条流程的原版和复刻版末端 UIKit 文本断言全部通过；18 对保存截图的[区域审计](../cases/calculator-nine-flow-visual-audit-v11-20261015/report.md)采用预先沿用的 `[0,80,414,820]` 区域与 0.015/3% 阈值，18 对均在阈值内。v11 的归一化 RGB 差均值/最大值为 0.003665/0.004556；原 0.1.6 案例为 0.008513/0.013639。差异像素比例均值从 1.770% 降至 0.891%。

在结果区 `[180,220,380,325]` 的诊断裁剪中，首页 `0` 的平均差从 0.03702 降到 0.00861，除零 `Error` 从 0.1288 降到 0.02458。原版 `0` 的亮像素外接框约为 `(329,243)–(375,309)`，0.1.10 复刻为 `(329,243)–(374,309)`。这些结果来自[0.1.10 两流程对照](../cases/calculator-font-check-v11-20261015/report.md)，不是另设的产品验收阈值。

代理逐图查看保存的首页、加法、百分比、重复等号、清除后重复、除零、小数、正负号和乘法共 18 对截图，未见按钮缺失、数字截断或明显布局错位。仍可见的差别包括结果字形的细节、± 的字形和顶部状态栏/返回上一 App 的系统文字。[逐张审阅](../cases/calculator-nine-flow-visual-review-v11-20261015/report.md)将每张图标为 `minor_difference` 并记录说明，来源图像和真机对照的哈希可复核。`rebuild-check` 自身的脚本视觉字段仍为 `unreviewed`；逐图审阅是单独的主观记录，未证明动画、横屏科学模式、全部中间状态或跨系统视觉等价。

最新版 [交付案例](../cases/calculator-agent-delivery-visual-reviewed-v11-20261015/report.md)封存源码与实际安装 IPA 的哈希，9/9 末端行为通过；18 对截图均已逐图审阅并记录轻微差异。审阅者身份由命令自行声明，画面判断仍需按本机保存的图像理解。
