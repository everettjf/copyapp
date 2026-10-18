# UI 手势脚本

[English](ui-gesture-playbooks.md) · 简体中文 · [工作流](copy-workflow.zh-CN.md)

playbook 除 `tap`、`tap_label` 外，还支持 `swipe`、`long_press` 和 `double_tap`。坐标是所选后端观察到的屏幕**点**，不是 Retina 像素。原版与复刻版应从可比状态开始，使用同一后端。`discover-check`、`compare-playbooks` 和 `rebuild-check` 在接受成对结果前会核对操作身份与边界。

```json
{
  "schema_version": 1,
  "bundle_id": "com.example.app",
  "scenario_id": "open-detail",
  "fresh_launch": true,
  "steps": [
    {"action": "observe", "contains": ["Items"]},
    {"action": "swipe", "from_x": 320, "from_y": 280,
     "to_x": 120, "to_y": 280, "duration_ms": 350, "steps": 20},
    {"action": "observe", "contains": ["Detail"]},
    {"action": "screenshot", "stable": true, "ready_contains": "Detail"}
  ]
}
```

运行 `copyapp playbook --udid <UDID> --backend ios-mcp|ictrl --script <FILE> --out cases/<CASE>`，再运行 `copyapp verify cases/<CASE>`。发现候选脚本需要不同的场景 ID、可识别的首个观察、有效操作和稳定的末端截图。尽量加操作后断言：手势 RPC 成功本身不证明界面结果。

| 操作 | 字段 | 边界 |
| --- | --- | --- |
| `swipe` | `from_x`、`from_y`、`to_x`、`to_y`；可选 `duration_ms`（300）、`steps`（20） | 至少 15 点；100–2000 毫秒；2–60 步。 |
| `long_press` | `x`、`y`；可选 `duration_ms`（800） | 300–3000 毫秒。 |
| `double_tap` | `x`、`y`；可选 `interval_ms`（100） | 50–300 毫秒。 |

坐标须落在实际观察的屏幕内。iCTRL 把滑动时长映射为 `fast`（≤125 毫秒）、`normal`（126–375 毫秒）或 `slow`（>375 毫秒）；实际时长和中间点不一定与 iOS MCP 完全相同。双击间隔也由其后端决定。截图、无障碍结果和 OCR 结论要分开记录。手势期间的 Frida 命中是时间相关证据，不证明它造成了可见变化。已测设备和未解后端限制见[当前状态](current-status.zh-CN.md)。
