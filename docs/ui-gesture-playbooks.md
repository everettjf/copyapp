# UI gesture playbooks

**Language:** English | [简体中文](ui-gesture-playbooks.zh-CN.md)

Copy APP playbooks accept `swipe`, `long_press`, and `double_tap` alongside `tap` and `tap_label`. Coordinates are screen **points** from the selected backend's observation, not Retina pixels. Use the same script and backend when comparing an original app with its rebuild. `discover-check` includes gestures in its action-path identity; `compare-playbooks` and `rebuild-check` reject different gesture parameters before accepting a pair. Frida method and bounded network traces can attribute observations to these action windows, but a hit in a window does not prove causality.

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

Run it with `copyapp playbook --udid <UDID> --backend ios-mcp|ictrl --script <FILE> --out cases/<CASE>` and then `copyapp verify cases/<CASE>`. For a discovery candidate, include a distinct scenario ID, an identifying first observation, at least one action, and a stable final screenshot with `ready_contains`. Use an explicit post-action state assertion whenever the UI exposes one; a successful gesture RPC alone says only that the backend accepted the action.

| Action | Fields | Bounds |
| --- | --- | --- |
| `swipe` | `from_x`, `from_y`, `to_x`, `to_y`; optional `duration_ms` (300), `steps` (20) | Horizontal or vertical, at least 15 points; duration 100–2000 ms; steps 2–60 |
| `long_press` | `x`, `y`; optional `duration_ms` (800) | Duration 300–3000 ms |
| `double_tap` | `x`, `y`; optional `interval_ms` (100) | Interval 50–300 ms |

Every coordinate must fit the device screen. Both backends support these actions, but iCTRL expresses a swipe as start point, direction, distance, and one of three velocities. Copy APP maps requested duration to `fast` (≤125 ms), `normal` (126–375 ms), or `slow` (>375 ms); iCTRL's actual duration and intermediate steps are not exact matches. iCTRL also uses its own double-tap interval, so the script's `interval_ms` is exact only for iOS MCP. Preserve the backend in every case and compare results on the same backend.

On the jailbroken iPhone XR running iOS 16.1.1, the [iCTRL swipe replay](../cases/calculator-gesture-swipelive-20261016/ictrl-v4-run/manifest.json) confirmed Calculator's accessibility result changed from `9` to `0`; the [iOS MCP 0.1.4 swipe replay](../cases/calculator-gesture-swipelive-20261016/ios-mcp-0.1.4-swipe-run/manifest.json) saved the final screenshot. [iOS MCP](../cases/calculator-gesture-swipelive-20261016/ios-mcp-0.1.4-extra-run/manifest.json) and [iCTRL](../cases/calculator-gesture-swipelive-20261016/ictrl-extra-run/manifest.json) both completed bounded long-press and double-tap probes on the Calculator display. Those probes establish call availability and retained foreground state, not a specific app behavior. One iCTRL screenshot OCR missed visible keypad digits even though the screenshot and accessibility tree were correct; keep screenshot, OCR, and accessibility findings separate.

A second [original replay](../cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-original-run/manifest.json) entered `98` and confirmed a left display swipe produced `9`, establishing one-digit deletion for that state. The independent [CalculatorFreshProbe source](../rebuild/CalculatorFreshProbe/Sources/CalculatorViewController.swift) now implements that selected gesture. Its [clone replay](../cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-clone-v2-run/manifest.json) passed the same `98→9` accessibility assertions; the [paired comparison](../cases/calculator-gesture-swipelive-20261016/ictrl-delete-digit-comparison/report.md) passed source and screenshot checks. Visual inspection found the same visible result with small glyph, color and status-bar differences. The updated clone also passed the [three prior arithmetic comparisons](../cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-check/manifest.json); [all three screenshot pairs were reviewed](../cases/calculator-gesture-swipelive-20261016/clone-0.1.1-regression-visual-review/report.md) with minor differences. This covers one left-swipe input state and the prior selected arithmetic flows, not all gesture directions, numeric formats or Calculator behavior.

The [two-device verification matrix](two-device-verification-matrix.md) adds the same committed `98→9` original-Calculator script on both named iPhones through both UI backends. All four flow-capture cases verify; before/after screenshots and the final UIKit result label establish the visible deletion. This tests a single portrait input state, not gesture parity across all apps or clone builds.
