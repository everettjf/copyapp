# Text entry in UI playbooks

[English](ui-text-playbooks.md) · [简体中文](ui-text-playbooks.zh-CN.md) · [Workflow](copy-workflow.md)

Use `type_text` after focusing an input field. It accepts 1–128 printable Unicode characters, at most 512 UTF-8 bytes. It does not clear an existing value or press Return. Prefer synthetic text: source playbooks and backend results remain in ignored local `cases/`.

```json
{"action": "tap", "x": 100, "y": 201}
{"action": "type_text", "text": "copyappfixture"}
{"action": "observe", "contains": ["copyappfixture"]}
```

`playbook`, `discover-check`, flow traces, paired comparison, rebuild checks and delivery gates recognize this action. The step record stores text length and hash; the source script retains the actual text. Original and rebuilt scripts must type the same bytes. A backend failure after typing is never retried automatically through another backend because the action may already have taken effect.

**Assert the visible outcome.** A successful input RPC does not prove that the app received the text; focus and keyboard state matter. Inspect the screen and accessibility/OCR result, and record any automatic submission or transformation separately. Use the same starting field state for a paired comparison. See [current status](current-status.md) for the tested backend scope.
