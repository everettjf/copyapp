# UI 脚本中的文字输入

[English](ui-text-playbooks.md) · 简体中文 · [工作流](copy-workflow.zh-CN.md)

先让输入框获得焦点，再使用 `type_text`。它接受 1–128 个可打印 Unicode 字符，最多 512 个 UTF-8 字节；不会自动清空旧值或按回车。优先使用合成文字，因为来源脚本和后端结果保存在被忽略的本地 `cases/`。

```json
{"action": "tap", "x": 100, "y": 201}
{"action": "type_text", "text": "copyappfixture"}
{"action": "observe", "contains": ["copyappfixture"]}
```

`playbook`、`discover-check`、流程跟踪、成对比较、复刻检查和交付门槛均识别此操作。步骤记录保存文字长度与哈希；来源脚本仍包含原文。原版与复刻版必须输入相同字节。输入后若后端报错，不能自动换后端重试，因为输入可能已经生效。

**必须断言可见结果。** 输入 RPC 成功不证明 App 收到了文字；焦点和键盘状态都会影响结果。检查画面及无障碍／OCR 结果，另外记录自动提交或内容转换。成对比较须让输入框处于同一初始状态。已测后端范围见[当前状态](current-status.zh-CN.md)。
