# UI 脚本中的文本输入

**语言：** [English](ui-text-playbooks.md) | 简体中文

先点击并聚焦空输入框，再使用 `type_text`。它接受 1–128 个可打印 Unicode 字符，UTF-8 最多 512 字节；不会清空原有内容，也不会按回车。发现脚本应使用合成测试文本，因为原始脚本与后端结果会保存在本地忽略的 `cases/` 中。

```json
{"action": "tap", "x": 207, "y": 320}
{"action": "type_text", "text": "hello"}
{"action": "observe", "contains": ["hello"]}
```

`copyapp playbook`、`discover-check`、流程跟踪、原版/复刻版比较、复刻检查与交付关卡都识别该操作。步骤记录只写文本哈希和长度，但保存的原始脚本仍含文本。原版与复刻版脚本必须输入相同字节。输入尝试后若后端失败，系统不会自动切换另一后端重试，因为操作是否已完成可能不确定。

**必须验证界面结果。** 输入 RPC 返回“已派发字符”不等于 App 接受了文字。在 iOS 16.1.1 的 XR 上，[iCTRL Translate 重放](../cases/translate-xr-text-pilot-ictrl-v2-20261016/manifest.json)输入合成词 `hello`，后续 UI 断言通过；[iOS MCP Translate 重放](../cases/translate-xr-text-pilot-ios-mcp-v2-20261016/manifest.json)报告派发五个字符，但同一断言失败，另一次批量输入试验也未使该输入框出现文字。Translate 的这条流程暂用 iCTRL，直到其 iOS MCP 聚焦/输入路径修复并实测。

[双机矩阵](two-device-verification-matrix.zh-CN.md)新增了对照案例：XR/iOS 16.1.1 与 iPhone 14/iOS 17.3.1 上，iOS MCP 和 iCTRL **都**能把同一个合成字符串 `copyapp-fixture-hello` 可见地输入 Safari 地址栏，且没有提交搜索。四份 `flow-capture` 案例通过 `copyapp verify`。所以 XR Translate 失败不能推出 XR 的 iOS MCP 文本输入整体不可用；输入框焦点、App 行为与后端派发仍需逐 App 检查。

[Translate 三流程发现案例](../cases/translate-xr-discovery-20261016/manifest.json)通过 iCTRL 验证了合成文本输入和两条可恢复的页面导航。它只确认这些已观察状态；语义报告和复刻版仍需独立证据。
