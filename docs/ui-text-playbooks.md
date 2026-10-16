# Text entry in UI playbooks

**Language:** English | [简体中文](ui-text-playbooks.zh-CN.md)

Use `type_text` after a tap has focused an empty input field. The action accepts 1–128 printable Unicode characters, at most 512 UTF-8 bytes. It does not clear an existing value or press Return. Use synthetic text in discovery scripts because raw scripts and backend results are retained in ignored local `cases/`.

```json
{"action": "tap", "x": 207, "y": 320}
{"action": "type_text", "text": "hello"}
{"action": "observe", "contains": ["hello"]}
```

`copyapp playbook`, `discover-check`, flow traces, paired comparison, rebuild checks and delivery gates recognize this action. The step record includes a text hash and length; the saved source script still contains the text. Original and rebuilt scripts must type the same bytes, and a backend failure after typing is never retried automatically through the other backend because completion may be uncertain.

**Require visible outcome evidence.** A text-input RPC may report that it dispatched characters even when the app did not accept them. On the iOS 16.1.1 XR, the [iCTRL Translate replay](../cases/translate-xr-text-pilot-ictrl-v2-20261016/manifest.json) entered synthetic `hello` and passed a subsequent UI assertion. The [iOS MCP replay](../cases/translate-xr-text-pilot-ios-mcp-v2-20261016/manifest.json) reported five characters dispatched but failed the same assertion; a separate bulk-input probe also left the field empty. Use iCTRL for text-entry flows on this device until the iOS MCP focus/input path is repaired and verified. This finding does not establish that every app or iOS version behaves the same way.

The [three-flow Translate discovery case](../cases/translate-xr-discovery-20261016/manifest.json) verifies one synthetic text flow and two reversible navigation flows through iCTRL. Discovery confirms only those observed states; a semantic report and rebuild still need their own evidence.
