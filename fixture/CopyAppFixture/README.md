# Copy APP 源码已知测试夹具

这是用于检验分析报告真伪的独立 iOS 16+ App，Bundle ID 为 `dev.copyapp.fixture`。运行 `sh package.sh` 会用 XcodeGen/Xcode 构建主 App、`FixtureCore.framework` 和 `FixtureShare.appex`，再以本地测试签名打包到 `build/dist/CopyAppFixture.ipa`。源码不包含账号或远程服务。

| 流程 | 源码事实 | 预期可观察证据 |
| --- | --- | --- |
| Counter | `CounterView.swift` 使用 SwiftUI `@AppStorage("fixture.counter")` | 点击 Increment 后数字变化；数据容器的偏好设置发生变化 |
| Notes | `NotesViewController.swift` 使用 UIKit 与 SQLite3 | 点击 Add sample note 后计数增加；`Documents/fixture-notes.sqlite` 写入；静态代码含建表、INSERT、bind、step |
| Catalog | `CatalogViewController.swift` 调用 `FixtureCore.mockResponse()` | 列出 Alpha、Beta；主程序链接嵌入 Framework，内容为本地模拟数据 |

分享扩展是独立的 `FixtureShare.appex`；主页面提供 **Share sample text** 入口。扩展会读取系统分享的固定合成文本并显示 `Received: Copy APP fixture sample text`。XR/iOS 16 与 iPhone 14/iOS 17 的选定分享路径已验证；不保证任意内容类型或扩展都兼容。

本机编译的主程序、Framework 和扩展均为 `cryptid=0`，因为它们未经过 App Store FairPlay 加密；不能将其当作砸壳成功样本。夹具用于核对已知源码、包索引、UI、沙盒变化和运行跟踪，正式能力边界见[当前状态](../../docs/current-status.zh-CN.md)。生成的 IPA、签名资料和手机证据留在被 Git 忽略的本地目录。
