# Notes 选定流程复刻

[English](README.md) · 简体中文

这个独立 UIKit App 实现了 XR/iOS 16 分析选定的三条本地 Notes 流程：文件夹导航、纯文本笔记创建与本地持久化、标题及正文搜索。Bundle ID 为 `com.copyapp.notes`，最低 iOS 16.0。源码独立编写，数据写入复刻版自身 Documents 容器的 JSON 文件；未导入 Apple 的代码、资源、数据或账户状态。

Mac 安装 Xcode、XcodeGen 和 `ldid` 后，在本目录运行 `sh package.sh`，得到 `build/dist/CopyAppNotes.ipa`。XR 实测通过 Copy APP 的 TrollStore 路径安装；普通 USB 安装需要该 Bundle ID 对应的开发签名与描述文件。

这只是选定流程对照，不能代表完整 Notes 复刻。三条成对脚本通过，三组截图审阅为轻微差异。重复测试使原版与复刻版积累的合成笔记数量不同。iCloud、富文本、附件、共享、锁定及 iOS 17 原版 Notes 行为均未覆盖。
