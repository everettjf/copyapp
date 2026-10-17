# Clock 复刻版在 iOS 16 与 17 上的实测

[English](clock-clone-two-device.md) · [简体中文](clock-clone-two-device.zh-CN.md)

独立 UIKit 项目 [`ClockCurrentAutoProbe`](../rebuild/ClockCurrentAutoProbe) 用同一份源码构建。临时签名 IPA 中的可执行文件 SHA-256 为 `06282bd9234b2a9883ba51e21f357c79f90d521a05351a1590e3d4c5d8b5562e`，与此前安装到 XR 的 IPA 中的可执行文件一致。该构建的副本随后用开发者证书签名并安装到 iPhone 14；签名会改变 Mach-O 的签名字节。签名后 IPA 的 SHA-256 为 `76c0a138b80e1a3f3b060ce0a6953d7fba801c536345c9ecc13b310bce99b362`。iOS 17 USB 安装案例 `cases/ios17-clock-auto-install-20261017/` 核对了 Bundle ID `com.copyapp.clock.currentauto`、版本 0.1.0 (1) 与有效的设备配置文件。

同一组已提交的[原版](../playbooks/clock-paired-stopwatch-original.json)和[复刻版](../playbooks/clock-paired-stopwatch-clone.json)脚本选择秒表、启动、观察非零运行状态、停止，并保存稳定的停止画面。两台手机上的原版与复刻版分别通过 iOS MCP 采集和 `compare-playbooks`：

| 手机 | 成对证据 | 复刻版的第二种后端 |
| --- | --- | --- |
| XR / iOS 16.1.1 / Dopamine rootless | `cases/ios16-clock-paired-fair-{original,clone,compare}-20261017/` | iCTRL：`cases/ios16-clock-clone-ictrl-20261017/` |
| iPhone 14 / iOS 17.3.1 / Relaxin RootHide | `cases/ios17-clock-paired-fair-original-retry-20261017/`、`cases/ios17-clock-paired-fair-{clone,compare}-20261017/` | iCTRL：`cases/ios17-clock-clone-ictrl-20261017/` |

六份最终 UI 采集案例、两份对照案例和 iOS 17 安装案例均通过 `copyapp verify`。左右并排的停止画面也已人工查看。两边均显示计时结果、Reset 与 Start、单圈记录及 Stopwatch 标签。各次脚本的动作与观察延迟不同，因此保存的计时数值不相同；像素差不能直接作为保真度评分。iOS 17 上原版与复刻版的标签文案（`Alarms`/`Timers` 对 `Alarm`/`Timer`）、控件样式和系统返回 App 文字也有可见差异。

原版 Clock 在重新启动后会保留停止的秒表数值，而当前复刻版会从零开始。因此统一的运行前 Reset 操作在复刻版上失败，成对脚本已去掉该操作；原版通过[准备脚本](../playbooks/clock-stopwatch-reset-original.json)单独清零。iOS 17 原版还有一次因 SpringBoard 前台切换竞争而失败的采集，下一次在不修改脚本的情况下通过。这些失败案例作为本地证据保留，不计为通过。

本次验证覆盖选定的前台秒表交互和已测试的设备、传输组合。后台计时、闹钟、通知、状态持久化、Clock 全部页面、精确视觉一致性、任意 iOS 16/17 设备与整 App 等价均未验证。`cases/` 默认不提交到 Git；用户可在配置好的 Mac 上重跑已提交脚本并校验证据。
