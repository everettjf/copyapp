# Text entry in UI playbooks

**Language:** English | [简体中文](ui-text-playbooks.zh-CN.md)

Use `type_text` after a tap has focused an empty input field. The action accepts 1–128 printable Unicode characters, at most 512 UTF-8 bytes. It does not clear an existing value or press Return. Use synthetic text in discovery scripts because raw scripts and backend results are retained in ignored local `cases/`.

```json
{"action": "tap", "x": 207, "y": 320}
{"action": "type_text", "text": "hello"}
{"action": "observe", "contains": ["hello"]}
```

`copyapp playbook`, `discover-check`, flow traces, paired comparison, rebuild checks and delivery gates recognize this action. The step record includes a text hash and length; the saved source script still contains the text. Original and rebuilt scripts must type the same bytes, and a backend failure after typing is never retried automatically through the other backend because completion may be uncertain.

**Require visible outcome evidence.** A text-input RPC may report that it dispatched characters even when the app did not accept them. On the iOS 16.1.1 XR, the [iCTRL Translate replay](../cases/translate-xr-text-pilot-ictrl-v2-20261016/manifest.json) entered synthetic `hello` and passed a subsequent UI assertion. The [iOS MCP Translate replay](../cases/translate-xr-text-pilot-ios-mcp-v2-20261016/manifest.json) reported five characters dispatched but failed the same assertion; a separate bulk-input probe also left that field empty. Use iCTRL for this Translate flow until its iOS MCP focus/input path is repaired and verified.

The [two-device matrix](two-device-verification-matrix.md) adds a control case: on both XR/iOS 16.1.1 and iPhone 14/iOS 17.3.1, **both** iOS MCP and iCTRL visibly entered the same synthetic `copyapp-fixture-hello` string into Safari's address field without submitting a search. The four flow-capture cases passed `copyapp verify`. Therefore, the XR Translate failure does not establish a device-wide iOS MCP text-input failure; field focus, App behavior and backend dispatch still need App-specific checks.

The [three-flow Translate discovery case](../cases/translate-xr-discovery-20261016/manifest.json) verifies one synthetic text flow and two reversible navigation flows through iCTRL. Discovery confirms only those observed states; a semantic report and rebuild still need their own evidence.
