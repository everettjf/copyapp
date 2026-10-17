# Clock 复刻版在 iOS 16 与 17 上的实测

[English](clock-clone-two-device.md) · [简体中文](clock-clone-two-device.zh-CN.md)

在 v0.1.9 基线验证中，独立 UIKit 项目 [`ClockCurrentAutoProbe`](../rebuild/ClockCurrentAutoProbe) 用同一份源码构建。临时签名 IPA 中的可执行文件 SHA-256 为 `06282bd9234b2a9883ba51e21f357c79f90d521a05351a1590e3d4c5d8b5562e`，与此前安装到 XR 的 IPA 中的可执行文件一致。该构建的副本随后用开发者证书签名并安装到 iPhone 14；签名会改变 Mach-O 的签名字节。签名后 IPA 的 SHA-256 为 `76c0a138b80e1a3f3b060ce0a6953d7fba801c536345c9ecc13b310bce99b362`。iOS 17 USB 安装案例 `cases/ios17-clock-auto-install-20261017/` 核对了 Bundle ID `com.copyapp.clock.currentauto`、版本 0.1.0 (1) 与有效的设备配置文件。

同一组已提交的[原版](../playbooks/clock-paired-stopwatch-original.json)和[复刻版](../playbooks/clock-paired-stopwatch-clone.json)脚本选择秒表、启动、观察非零运行状态、停止，并保存稳定的停止画面。两台手机上的原版与复刻版分别通过 iOS MCP 采集和 `compare-playbooks`：

| 手机 | 成对证据 | 复刻版的第二种后端 |
| --- | --- | --- |
| XR / iOS 16.1.1 / Dopamine rootless | `cases/ios16-clock-paired-fair-{original,clone,compare}-20261017/` | iCTRL：`cases/ios16-clock-clone-ictrl-20261017/` |
| iPhone 14 / iOS 17.3.1 / Relaxin RootHide | `cases/ios17-clock-paired-fair-original-retry-20261017/`、`cases/ios17-clock-paired-fair-{clone,compare}-20261017/` | iCTRL：`cases/ios17-clock-clone-ictrl-20261017/` |

六份最终 UI 采集案例、两份对照案例和 iOS 17 安装案例均通过 `copyapp verify`。左右并排的停止画面也已人工查看。两边均显示计时结果、Reset 与 Start、单圈记录及 Stopwatch 标签。各次脚本的动作与观察延迟不同，因此保存的计时数值不相同；像素差不能直接作为保真度评分。iOS 17 上原版与复刻版的标签文案（`Alarms`/`Timers` 对 `Alarm`/`Timer`）、控件样式和系统返回 App 文字也有可见差异。

原版 Clock 在重新启动后会保留停止的秒表数值，而 **v0.1.9 基线复刻版**会从零开始。因此统一的运行前 Reset 操作在该构建上失败，成对脚本已去掉该操作；原版通过[准备脚本](../playbooks/clock-stopwatch-reset-original.json)单独清零。iOS 17 原版还有一次因 SpringBoard 前台切换竞争而失败的采集，下一次在不修改脚本的情况下通过。这些失败案例作为本地证据保留，不计为通过。

## 0.1.1 (2) 构建的秒表状态修复

当前复刻版保存累计时间、开始时间和圈数状态，并在进程启动时恢复。升级后的临时签名 IPA SHA-256 为 `6e9e18f68200c3c2412f8817b73afaef8fd87faa85e4511e7c18ec12666876ab`；iOS 17 开发者签名 IPA 为 `9fd19f1dc3cd807e99ebb50cbca6ed1f081e264ef17249e9abfb22e5323efe63`。两台设备的新版安装案例均通过校验。XR 首次 TrollStore 升级因旧版进程仍运行而超时；只结束该测试 App 进程后，新安装案例通过。iOS 17 USB 升级也在结束旧进程后完成。

两台手机都先完成启停采集，再**终止并重启进程**，保留了完全相同的停止值：XR 为 `00:02.31`，iPhone 14 为 `00:01.69`。复刻版和[原版重启脚本](../playbooks/clock-stopped-relaunch-original.json)的同机画面对照通过，保存了并排截图。另一次运行态测试中，XR 复刻版从重启前 `00:01.25` 增长至重启后的 `00:35.20`、`00:36.84`；iPhone 14 从 `00:01.25` 增长至 `00:12.99`、`00:14.44`。两台秒表随后均被停止。新版还在两机上通过 iCTRL 启停回归。构建 2 的 18 份案例中现有 17 份仍可校验：XR 的构建 2 安装记录引用了后来被覆盖的 `build/dist/` IPA，原始字节已不可得，因此这一份历史安装案例不再计入通过。其界面采集和 iOS 17 的签名安装案例仍可校验。

构建 **0.1.2 (3)** 把同一份持久化代码用于真实升级检查。构建 2 仍在两机运行时，`copyapp install` 经已配对 iCTRL 请求结束精确目标 App；XR 路径还核对匹配进程的设备端 `Info.plist`，然后才停止它。两份 `cases/ios{16,17}-clock-build3-auto-upgrade-20261017/` 安装案例均在约七秒内完成，并核对版本、构建号及包哈希；构建 3 的重启案例仍显示非零秒表值和 Reset。XR 临时签名 IPA SHA-256 为 `ed96255dbfb5f7c4279af07230f4fb7db7e8863bed3bd7bc584cc9a7147dbce0`；iPhone 14 开发者签名 IPA 为 `e4b42afd0e13118fa2f1b70491e8217efbc4e95e0ee9bf90c88a744009a6a348`。另一次 XR 直接探测在 `Info.plist` 的 Bundle ID 精确匹配后停止了一条运行中的 Clock 进程。TrollStore 对完全相同的构建 2 重装两次超时，失败案例保留在本地；本项目不声称同版本重装已通过。

当前项目版本为 **0.1.3 (4)**。安装器会在传输前将 `input.ipa` 保存到案例目录，后续构建不会覆盖其核验来源。XR 临时签名 IPA 的 SHA-256 为 `538591251caee5b1fadcefc62cb28f7feea949287b30c8606415322d8d788d42`；iPhone 14 开发者签名 IPA 为 `53f05117f663c6d24d350fad2f195edfac712b8de7ab3cfa9ac9970fd6896811`。构建 4 在两台构建 3 仍运行的手机上安装：iPhone 14 的 USB 安装首次通过；XR 的 TrollStore helper 首次超时，安装数据库仍显示构建 3，用同一份保留的 IPA 重试后成功。两份最终安装案例均含各自 IPA 快照；暂时移走原构建产物时仍通过 `copyapp verify`；构建 4 的重启采集也显示非零停止态秒表。XR 首次超时保留为失败案例。较早的 XR 构建 3 IPA 在再次构建前按字节复制进本地案例，并记录位置修正；该案例也继续通过校验。

本次验证覆盖选定前台秒表行为、停止态保留，以及每台手机一次运行态重启。长时间后台计时精度、系统时间变化、闹钟、通知、Clock 全部页面、精确视觉一致性、任意 iOS 16/17 设备与整 App 等价仍未验证。`cases/` 默认不提交 Git；用户可在配置好的 Mac 上重跑已提交脚本并校验证据。
