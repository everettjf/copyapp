# 两台手机的五分钟后台秒表检查

[English](clock-five-minute-two-device.md) · [简体中文](clock-five-minute-two-device.zh-CN.md)

v0.1.13 发布后，在 iPhone XR / iOS 16.1.1 与 iPhone 14 / iOS 17.3.1 上分别测试原版 Clock（`com.apple.mobiletimer`）和已安装的独立复刻版（`com.copyapp.clock.currentauto`）。每次清零并启动秒表，通过 iCTRL 返回主屏幕，后台等待至少五分钟，切回同一 App，保存运行态，再停止秒表。每机六份启动／返回／停止脚本案例均通过 `copyapp verify`。[此前仅测复刻版约一分钟的记录](clock-background-two-device.zh-CN.md)是另一次独立观测。

| 手机 | App | 返回前后运行值 | 增量 | 两次保存观察的时间间隔 | 差值 |
| --- | --- | --- | ---: | ---: | ---: |
| XR / iOS 16 | 原版 Clock | 1.30 秒 → 5 分 8.45 秒 | 307.15 秒 | 308 秒 | −0.85 秒 |
| XR / iOS 16 | 复刻版 | 1.25 秒 → 5 分 8.60 秒 | 307.35 秒 | 308 秒 | −0.65 秒 |
| iPhone 14 / iOS 17 | 原版 Clock | 1.21 秒 → 5 分 19.52 秒 | 318.31 秒 | 318 秒 | +0.31 秒 |
| iPhone 14 / iOS 17 | 复刻版 | 1.25 秒 → 5 分 15.05 秒 | 313.80 秒 | 314 秒 | −0.20 秒 |

时间间隔由启动和返回脚本中运行态 `observe` 步骤的 `at` 时间戳相减得到；时间戳只有**一秒精度**，因此这些差值只能检查有界一致性，不能证明亚秒精度。按表格顺序，iCTRL 的 Home 到切回间隔为 301.44、301.45、306.25 和 306.20 秒。返回画面在切回请求后才读取，所以秒表增量大于 Home 到切回间隔。

案例路径为 `cases/ios{16,17}-clock-{original,clone}-five-minute-{start,return,stop}-20261017/`。编排输入与生命周期日志位于被 Git 忽略的 `cases/clock-five-minute-inputs-20261017/`；四份日志 SHA-256 分别为 XR 原版 `7a2fbae1819682b92074d0394eabd3fb541617b05a9edfbf313d46655ca71926`、XR 复刻版 `a89fc68899c2a74175d9537e5001da0cea7336029912dd7cda034bb25a797082`、iPhone 14 原版 `6d3c4ef5d0aa1c244b7b10d4fcab2a75159bf209c20d375bcc1f56b76ff074ba`、iPhone 14 复刻版 `9b2eb91444956951dfeeb6fbca013fe495d5228b26289241b4f417c9110c7fa3`。脚本案例可由 Copy APP 校验；补充的生命周期日志只在此记录哈希，**不受** `copyapp verify` 绑定。

[XR](../cases/ios16-v0113-doctor-20261017/report.md) 与 [iPhone 14](../cases/ios17-v0113-doctor-20261017/report.md) 的新版 v0.1.13 设备探针亦通过校验，USB、截图、开发者文件系统、mobile SSH、Frida、iOS MCP 与 iCTRL 均显示可用。通道探针本身不能证明其他 App 行为。

每个 App、每台手机只测了一次五分钟后台运行；数小时挂起、锁屏或重启恢复、系统时间变化、闹钟通知和 Clock 全功能均未验证。原版与复刻版不是同时运行，因此两者最终读数不应期望相同。
