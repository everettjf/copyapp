# 夹具分享扩展：iOS 16 与 17 真机验证

[English](fixture-share-extension-two-device.md) · [简体中文](fixture-share-extension-two-device.zh-CN.md)

已知源码夹具有 **Share sample text** 按钮，通过系统 `UIActivityViewController` 分享固定文本 `Copy APP fixture sample text`，从真实的用户分享入口打开包内 `FixtureShare.appex`。在 0.1.2（build 3）中，扩展读取该分享项并在标题下显示 `Received: Copy APP fixture sample text`，不保存或传输内容。

| 设备 | 已安装夹具 | 系统路径 | 结果 |
| --- | --- | --- | --- |
| iPhone XR / iOS 16.1.1 / Dopamine rootless | 0.1.2（3），TrollStore 安装 ad hoc IPA | Share sample text → More → Suggestions → Copy APP Fixture | iOS MCP 12 步脚本完成，收到的精确文本和截图均确认 |
| iPhone 14 / iOS 17.3.1 / Relaxin RootHide | 0.1.2（3），USB 安装 Apple Development 签名 IPA | Share sample text → More → Suggestions → Copy APP Fixture | iOS MCP 14 步脚本完成，收到的精确文本和截图均确认 |

当前安装案例是 `cases/ios16-fixture-share-data-install-retry-20261017` 与 `cases/ios17-fixture-share-data-install-20261017`。内容链路案例是 `cases/ios16-fixture-share-data-playbook-20261017` 与 `cases/ios17-fixture-share-data-playbook-20261017`，均通过 `copyapp verify`；末端 UIKit 观察和截图都包含精确的 `Received:` 文本。脚本纳入版本库：[iOS 16](../fixture/CopyAppFixture/playbooks/share-extension-ios16.json) 与 [iOS 17](../fixture/CopyAppFixture/playbooks/share-extension-ios17.json)。旧版 0.1.1（2）仅入口案例仍保留在 `cases/ios16-fixture-share-playbook-v2-20261017` 与 `cases/ios17-fixture-share-playbook-v5-20261017`。

0.1.2 的 XR 更新首次也超时；停止主 App 与扩展进程后，同一 SHA-256 匹配的包重试成功，失败案例保留在 `cases/ios16-fixture-share-data-install-20261017`。XR 的无障碍树把若干分享目标称为 `Activity`，因此脚本用截图确认 More 列表并点击已观察到的行坐标。iOS 17 返回重复的 `More` 元素，横向滚动时图标位置也会变化；脚本先等待稳定截图再点击。这是两台设备的限定脚本，不代表固定坐标可通用于任意分享菜单。

新增按钮后，原版夹具的 Counter、Notes、Catalog 三条脚本分别在两机重新完成。六个回归案例分别为 `cases/ios16-fixture-share-regression-{counter,notes,catalog}-20261017` 与 `cases/ios17-fixture-share-regression-{counter,notes,catalog}-20261017`，均通过 `copyapp verify`。Notes 重放会在每台测试机增加一行合成笔记。

0.1.2 文本接收更新后，同样三条原版夹具流程又分别在两机完成。当前构建的六个案例为 `cases/ios16-fixture-share-data-regression-{counter,notes,catalog}-20261017` 与 `cases/ios17-fixture-share-data-regression-{counter,notes,catalog}-20261017`，均通过 `copyapp verify`。本轮界面回归没有重新检查 SQLite 行内容；该内容此前已在[存储验收](releases/v0.1.2.zh-CN.md)单独核查。

在仓库根目录，安装对应夹具并启动 iOS MCP 后可重跑：

```sh
.venv/bin/copyapp playbook --udid <XR_UDID> --backend ios-mcp \
  --script fixture/CopyAppFixture/playbooks/share-extension-ios16.json \
  --out cases/fixture-share-ios16-recheck
.venv/bin/copyapp playbook --udid <IPHONE_14_UDID> --backend ios-mcp \
  --script fixture/CopyAppFixture/playbooks/share-extension-ios17.json \
  --out cases/fixture-share-ios17-recheck
```

这补齐了**这两台手机上的已知源码夹具分享扩展用户入口和一条纯文本输入链路**；仍未验证其他内容类型、存储或网络行为、其他扩展、其他 iOS 版本或整 App 复刻等价。原始截图、IPA 与签名材料保存在本机被 Git 忽略的 `cases/`。
