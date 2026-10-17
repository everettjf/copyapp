# Text entry in UI playbooks

**Language:** English | [简体中文](ui-text-playbooks.zh-CN.md)

Use `type_text` after a tap has focused an empty input field. The action accepts 1–128 printable Unicode characters, at most 512 UTF-8 bytes. It does not clear an existing value or press Return. Use synthetic text in discovery scripts because raw scripts and backend results are retained in ignored local `cases/`.

```json
{"action": "tap", "x": 100, "y": 201}
{"action": "type_text", "text": "copyappfixture"}
{"action": "observe", "contains": ["copyappfixture"]}
```

`copyapp playbook`, `discover-check`, flow traces, paired comparison, rebuild checks and delivery gates recognize this action. The step record includes a text hash and length; the saved source script still contains the text. Original and rebuilt scripts must type the same bytes, and a backend failure after typing is never retried automatically through the other backend because completion may be uncertain.

**Require visible outcome evidence.** A text-input RPC may report that it dispatched characters even when the app did not accept them. On the iOS 16.1.1 XR, the older [iOS MCP Translate replay](../cases/translate-xr-text-pilot-ios-mcp-v2-20261016/manifest.json) tapped `(207,320)`, reported five characters dispatched and failed the visible-text assertion. The same old script failed again in `cases/ios16-translate-old-tap-control-20261017/`: its screenshot shows a caret but no keyboard. A new [same-script four-way check](two-device-verification-matrix.md) taps the visible input placeholder at `(100,201)`; the keyboard appears and exact synthetic text is visible through both backends on both iOS 16 and 17. The differing tap/focus state explains the bounded comparison; do not infer a general input defect from an RPC success or one failed tap.

The [two-device matrix](two-device-verification-matrix.md) also checks Safari: both backends visibly entered `copyapp-fixture-hello` in its address field on both phones without submitting a search. All four Safari and all four new Translate `flow-capture` cases pass `copyapp verify`. On iOS 17, Translate displayed an automatic result after synthetic input even though the script did not press a submit key; the translation's meaning was not assessed.

The [three-flow Translate discovery case](../cases/translate-xr-discovery-20261016/manifest.json) verifies one synthetic text flow and two reversible navigation flows through iCTRL. Discovery confirms only those observed states; a semantic report and rebuild still need their own evidence.
