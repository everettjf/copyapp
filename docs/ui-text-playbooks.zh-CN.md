# UI 脚本中的文本输入

**语言：** [English](ui-text-playbooks.md) | 简体中文

先点击并聚焦空输入框，再使用 `type_text`。它接受 1–128 个可打印 Unicode 字符，UTF-8 最多 512 字节；不会清空原有内容，也不会按回车。发现脚本应使用合成测试文本，因为原始脚本与后端结果会保存在本地忽略的 `cases/` 中。

```json
{"action": "tap", "x": 100, "y": 201}
{"action": "type_text", "text": "copyappfixture"}
{"action": "observe", "contains": ["copyappfixture"]}
```

`copyapp playbook`、`discover-check`、流程跟踪、原版/复刻版比较、复刻检查与交付关卡都识别该操作。步骤记录只写文本哈希和长度，但保存的原始脚本仍含文本。原版与复刻版脚本必须输入相同字节。输入尝试后若后端失败，系统不会自动切换另一后端重试，因为操作是否已完成可能不确定。

**必须验证界面结果。** 输入 RPC 返回“已派发字符”不等于 App 接受了文字。XR/iOS 16 的旧 [iOS MCP Translate 重放](../cases/translate-xr-text-pilot-ios-mcp-v2-20261016/manifest.json)点击 `(207,320)`，报告派发五个字符，但可见文字断言失败。同一旧脚本在 `cases/ios16-translate-old-tap-control-20261017/` 再次失败：截图有光标而无键盘。新的[同脚本四路检查](two-device-verification-matrix.zh-CN.md)点击输入提示附近的 `(100,201)`，键盘出现，iOS 16/17 的两种后端都显示精确合成文字。此对照表明点击与聚焦状态不同；不能从一次 RPC 成功或一次点击失败推断整套输入能力。

[双机矩阵](two-device-verification-matrix.zh-CN.md)也检查 Safari：两台手机的两种后端均把 `copyapp-fixture-hello` 可见地输入地址栏，没有提交搜索。四份 Safari 和四份新 Translate `flow-capture` 案例均通过 `copyapp verify`。iOS 17 的 Translate 在合成文字输入后自动显示结果，虽然脚本没有按提交键；翻译语义未评估。

[Translate 三流程发现案例](../cases/translate-xr-discovery-20261016/manifest.json)通过 iCTRL 验证了合成文本输入和两条可恢复的页面导航。它只确认这些已观察状态；语义报告和复刻版仍需独立证据。
