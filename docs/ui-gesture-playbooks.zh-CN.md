# UI 手势脚本

**语言：** [English](ui-gesture-playbooks.md) | 简体中文

Copy APP 的 playbook 除 `tap`、`tap_label` 外，现支持 `swipe`、`long_press`、`double_tap`。坐标使用后端观察到的屏幕**点**，不是 Retina 像素。原版与复刻版对照时使用同一脚本和同一后端。`discover-check` 将手势纳入操作路径身份；`compare-playbooks` 和 `rebuild-check` 会拒绝参数不同的手势配对。Frida 方法与有界网络跟踪可按操作窗口记录观察，但窗口内命中不等于证明因果关系。

```json
{
  "schema_version": 1,
  "bundle_id": "com.apple.calculator",
  "scenario_id": "display-delete-digit",
  "fresh_launch": true,
  "steps": [
    {"action": "observe", "contains": ["Result"]},
    {"action": "tap", "x": 58, "y": 383},
    {"action": "tap", "x": 257, "y": 484},
    {"action": "swipe", "from_x": 346, "from_y": 280,
     "to_x": 132, "to_y": 280, "duration_ms": 350, "steps": 20},
    {"action": "observe", "contains": ["Result"]},
    {"action": "screenshot", "stable": true, "ready_contains": "Result"}
  ]
}
```

使用 `copyapp playbook --udid <UDID> --backend ios-mcp|ictrl --script <文件> --out cases/<案例>` 重放，再运行 `copyapp verify cases/<案例>`。作为自动发现候选时，需要独立的场景 ID、可识别首页的初始观察、至少一次操作，以及带 `ready_contains` 的稳定末端截图。界面能提供明确状态时，应在操作后加入断言；手势 RPC 成功只说明后端接受了操作。

| 操作 | 参数 | 约束 |
| --- | --- | --- |
| `swipe` | `from_x`、`from_y`、`to_x`、`to_y`；可选 `duration_ms`（默认 300）、`steps`（默认 20） | 仅水平或垂直，至少 15 点；时长 100–2000 毫秒；步数 2–60 |
| `long_press` | `x`、`y`；可选 `duration_ms`（默认 800） | 300–3000 毫秒 |
| `double_tap` | `x`、`y`；可选 `interval_ms`（默认 100） | 50–300 毫秒 |

全部坐标必须在设备屏幕范围内。两套后端都支持这些操作，但 iCTRL 的滑动协议使用起点、方向、距离以及三档速度。Copy APP 将请求时长映射为 `fast`（≤125 毫秒）、`normal`（126–375 毫秒）或 `slow`（>375 毫秒）；iCTRL 的实际时长和中间步数不能精确对应。iCTRL 双击也使用自己的间隔，因此脚本中的 `interval_ms` 只有 iOS MCP 能精确传递。每个案例保留后端身份，原版与复刻版应在同一后端比较。

在 iOS 16.1.1 的越狱 iPhone XR 上，[iCTRL 滑动案例](../cases/calculator-gesture-swipelive-20261016/ictrl-v4-run/manifest.json)通过无障碍断言确认 Calculator 结果从 `9` 变为 `0`；[iOS MCP 0.1.4 滑动案例](../cases/calculator-gesture-swipelive-20261016/ios-mcp-0.1.4-swipe-run/manifest.json)保存了末端截图。[iOS MCP](../cases/calculator-gesture-swipelive-20261016/ios-mcp-0.1.4-extra-run/manifest.json) 与 [iCTRL](../cases/calculator-gesture-swipelive-20261016/ictrl-extra-run/manifest.json) 的长按、双击试验都完成并保持 Calculator 前台。这些试验验证了调用通道，并未验证特定功能结果。一次 iCTRL 截图 OCR 漏读了可见的键盘数字，而截图和无障碍树正确；报告中应区分三类证据。

第二条[原版重放](../cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-original-run/manifest.json)输入 `98`，确认显示区左滑后为 `9`，证明该状态下一次删除一位数字。独立的 [CalculatorFreshProbe 源码](../rebuild/CalculatorFreshProbe/Sources/CalculatorViewController.swift)已实现这条选定手势；[复刻版重放](../cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-clone-v2-run/manifest.json)通过相同的 `98→9` 无障碍断言，[成对比较](../cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-comparison/report.md)通过来源和截图校验。目视确认结果一致，但字形、颜色与状态栏有小幅差异。新版复刻版还通过[原先三条运算流程的回归对照](../cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-check/manifest.json)；[三对截图已逐张审阅](../cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-visual-review/report.md)，均有轻微差异。验证范围限于一条左滑输入状态与原先选定的运算流程，不代表全部手势方向、数字格式或 Calculator 行为。
