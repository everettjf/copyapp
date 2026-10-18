# UI gesture playbooks

[English](ui-gesture-playbooks.md) · [简体中文](ui-gesture-playbooks.zh-CN.md) · [Workflow](copy-workflow.md)

Playbooks accept `swipe`, `long_press` and `double_tap` alongside `tap` and `tap_label`. Coordinates are screen **points** from the selected backend's observation, not Retina pixels. Run original and rebuilt scripts from comparable states with the same backend. `discover-check`, `compare-playbooks` and `rebuild-check` validate action identity and bounds before accepting a pair.

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

Run `copyapp playbook --udid <UDID> --backend ios-mcp|ictrl --script <FILE> --out cases/<CASE>`, then `copyapp verify cases/<CASE>`. A discovery candidate needs a distinct scenario ID, identifying first observation, meaningful action and stable final screenshot. Prefer an explicit post-action assertion: a successful gesture RPC alone does not prove a UI result.

| Action | Fields | Bounds |
| --- | --- | --- |
| `swipe` | `from_x`, `from_y`, `to_x`, `to_y`; optional `duration_ms` (300), `steps` (20) | At least 15 points; 100–2000 ms; 2–60 steps. |
| `long_press` | `x`, `y`; optional `duration_ms` (800) | 300–3000 ms. |
| `double_tap` | `x`, `y`; optional `interval_ms` (100) | 50–300 ms. |

Coordinates must fit the observed screen. iCTRL maps swipe duration to `fast` (≤125 ms), `normal` (126–375 ms) or `slow` (>375 ms); its real duration and intermediate points need not match iOS MCP. Its double-tap interval is also backend-defined. Keep screenshots, accessibility results and OCR conclusions separate. A Frida hit during a gesture is temporal evidence, not proof that the hit caused the visible change. See [current status](current-status.md) for tested devices and open backend limits.
