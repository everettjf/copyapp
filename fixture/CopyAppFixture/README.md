# Copy APP 源码已知测试夹具

这是用于检验分析报告真伪的独立 iOS 16+ App，Bundle ID 为 `dev.copyapp.fixture`。运行 `sh package.sh` 会用 XcodeGen/Xcode 构建主 App、`FixtureCore.framework` 和 `FixtureShare.appex`，再以本地测试签名打包到 `build/dist/CopyAppFixture.ipa`。源码不包含账号或远程服务。

| 流程 | 源码事实 | 预期可观察证据 |
| --- | --- | --- |
| Counter | `CounterView.swift` 使用 SwiftUI `@AppStorage("fixture.counter")` | 点击 Increment 后数字变化；数据容器的偏好设置发生变化 |
| Notes | `NotesViewController.swift` 使用 UIKit 与 SQLite3 | 点击 Add sample note 后计数增加；`Documents/fixture-notes.sqlite` 写入；静态代码含建表、INSERT、bind、step |
| Catalog | `CatalogViewController.swift` 调用 `FixtureCore.mockResponse()` | 列出 Alpha、Beta；主程序链接嵌入 Framework，内容为本地模拟数据 |

分享扩展是独立的 `FixtureShare.appex`，用于检验扩展枚举与二进制状态；它不属于上述三条主流程。Fixture 本机编译出的主程序、Framework、扩展均为 `cryptid=0`，这表示它们由本机构建且未被 App Store FairPlay 加密，**不能**作为砸壳成功的样本。当前本地 `copyapp ipa` 正确识别三个 Mach-O、一个 Framework 和一个扩展；`copyapp objc` 从主程序识别 6 个本地 Objective-C 类与 `showCounter`、`showNotes`、`showCatalog`、`addNote` 等入口。REA/Ghidra 已沿 `addNote` 追到真正的 SQLite 写入闭包，证据与限制见 `docs/rea-hopper-integration.md`。

XR 的真机安装和三条主流程已通过，页面、计数器偏好设置、笔记数据库、Frida 调用与从 XR 导出二进制的 REA/Ghidra 证据见 [夹具真机验证](../../docs/fixture-xr-validation.md)。可用 `copyapp install --udid <UDID> --ipa build/dist/CopyAppFixture.ipa --out cases/<CASE>` 从 Mac 端重新安装，无需手机输入。分享扩展的实际调用和 iOS 17/26 跨系统验证仍待完成。
