# Calculator XR：五流程截图查看记录

来源是 [五流程真机对照](../cases/calculator-five-flow-rebuild-check-v7-20261015/report.md)保存的 9 张原版/复刻版成对截图。本次逐张查看了 initial、addition、percent、repeat equals 和 clear repeat 的全部截图，没有重新操作手机。可复核的[区域像素审计](../cases/calculator-five-flow-visual-audit-v1-20261015/report.md)覆盖画面坐标 `[0,80,414,820]`，其 `audit.json` SHA-256 为 `79d7083f08a06357f89ac6e668c69998629e5dee66ad683dee598dcd2096eca9`。

在这些保存的状态中，数字文本、C/AC 状态、按键排列、圆角、主色和大致对齐没有发现明显的内容级错位。九对图的区域归一化平均 RGB 差为 0.00580–0.01122；最大通道差超过 24 的像素比例为 1.422%–2.069%。画面顶部系统返回提示分别显示不同的上一个 App 名称；这一区域不在审计 ROI 内，也不应被解读为 Calculator 内容。按键文字与细线数字仍有可见的细微字体栅格差异，现有截图不足以确定字体或渲染原因。

逐张查看不等于预先声明的视觉测试通过。像素阈值是在看到图像后选的诊断尺度，原对照案例的 `visual_checks_status` 仍为 `unreviewed`。本记录不覆盖按下动画、横屏、其他运算、动态类型、不同系统版本、权限变化或整款 App 的视觉一致性。
