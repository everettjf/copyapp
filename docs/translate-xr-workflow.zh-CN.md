# Translate XR：从分析到可运行复刻

**语言：** [English](translate-xr-workflow.md) | 简体中文

这是在已越狱 iPhone XR（iOS 16.1.1）上完成的 Copy APP 第一版案例。原版为 Apple Translate 1.0（216.4），Bundle ID 为 `com.apple.Translate`；独立复刻版为 `com.copyapp.translate.freshprobe`。[父流程](../cases/translate-current-workflow-20261016/manifest.json)的最终状态是 `complete`，全程不依赖 REA。Xcode 27 以 iOS 16.0 为最低版本编译复刻版，随后在真机安装并重放 UI 流程。

## 本次覆盖

| 流程 | 原版与复刻版的结果 | 边界 |
| --- | --- | --- |
| 文字输入 | 打开输入卡、输入测试文字 `hello`、确认文字可见、关闭并返回 Translation | 没有提交或执行翻译 |
| Favorites 空状态 | 打开 Favorites、确认空状态文字、返回 Translation | 没有测试已有收藏 |
| Conversation 待机 | 打开 Conversation、确认待机提示、返回 Translation | 没有点击麦克风或测试语音 |

[XR 成对测试](../cases/translate-current-workflow-20261016/rebuild-agent/rebuild-check-v4/report.md)完成三条流程，每条保存两组成对截图。[六张截图的逐张审阅](../cases/translate-current-workflow-20261016/rebuild-agent/visual-review/report.md)在此范围内只发现轻微视觉差异，主要是图标、少量文字位置和语言卡片细节。这证明的是选定行为，不代表整个 Translate 等价。

## 分析证据

- [审阅报告](../cases/translate-current-workflow-20261016/analysis-agent/reviewed-report/report.md)关联安装包、Objective-C 元数据、沙盒、UI 截图、Frida 跟踪和有界 ARM64 汇编，并区分直接观察与未知实现。
- 主程序及 CacheDelete 扩展在本次获取的包中已无加密头；解密助手没有恢复或修改代码字节。
- 主程序链接 UIKit、SwiftUI、AVFoundation、Vision/VisionKit、CoreData 和 Apple 私有的 Translation 框架。链接依赖只说明可用技术，不能单独证明某次交互走了哪条代码路径。
- 点击输入卡关闭按钮时，`TranslateInputCard::closeButtonPressed` 的静态入口偏移 `0x1abf1c` 在 Frida 记录中命中一次；聚焦和输入时均为零。打开 Favorites 时，`FavoritesViewController::viewDidLoad` 的偏移 `0xd0544` 命中一次；返回时为零。这是有限的代码与 UI 关联，不是还原出的原始源码。
- 沙盒索引包含 `Library/Application Support/Translate.sqlite`。只读取数据库结构，发现 `ZTRANSLATION` 等 Core Data 风格表及收藏日期、源输入、目标结果列；没有读取记录。三个有界 URLSession resume 观察窗口均为零事件，但不能据此断定 App 完全离线。

## 交付与复现

复刻源码在 [TranslateFreshProbe](../rebuild/TranslateFreshProbe)。[真机安装记录](../cases/translate-current-workflow-20261016/rebuild-agent/install-v4/install.json)、[Agent 交付](../cases/translate-current-workflow-20261016/rebuild-agent/agent-delivery/report.md)和父流程共同绑定 IPA、设备、报告与脚本。交付 IPA 的 SHA-256 为 `008a2e18b5758b4c096712b96592bfebbce111180d8bc03080e24624710bab1c`。

在仓库中执行 `sh rebuild/TranslateFreshProbe/package.sh` 可用 Xcode、XcodeGen 和 `ldid` 重建独立工程。执行 `.venv/bin/copyapp verify cases/translate-current-workflow-20261016` 可校验保存的父流程证据；真机重放仍需要已配对、已越狱的 XR 和对应 USB 服务。

原三流程交付通过 iCTRL 完成可见文字输入。较早的 XR iOS MCP 试验在较低位置 `(207,320)` 点击后返回字符派发成功，但界面没有文字；失败证据保留在本地 `cases/`。后来重放同一点击再次失败；新共享脚本点击可见输入提示 `(100,201)` 后，iOS 16 与 17 的 iOS MCP、iCTRL 都显示键盘和精确合成文字，见[双机矩阵](two-device-verification-matrix.zh-CN.md)。运行器会复用已运行的 iCTRL 服务，并限制启动等待；Instruments 不可用时，iCTRL 通过 XCTest 结束并重新启动目标 App 来实现全新启动。

## 后续范围

对于原 XR 复刻版，提交文字与真实翻译结果、语言选择及下载、相机 OCR、语音权限与识别、音频播放、非空 Favorites、持久化写入、进一步的沙盒解释，以及外部 Codex/Claude CLI 全自主运行仍未验证。后来 iOS 17 的原版 App 合成文字输入测试自动显示结果，但未评估其语义质量，也未复刻这一结果。iOS 26 不在这轮验证范围内。
