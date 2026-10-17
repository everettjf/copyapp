# Clock 复刻版双机一分钟后台计时

[English](clock-background-two-device.md) · [简体中文](clock-background-two-device.zh-CN.md)

v0.1.10 发布后，已安装的独立 Clock 0.1.3 (4) 复刻版在 iPhone XR / iOS 16.1.1 和 iPhone 14 / iOS 17.3.1 上接受了后台计时检查。两机分别用已提交的[启动脚本](../playbooks/clock-background-start-clone.json)清零并启动秒表，经 iCTRL 返回主屏幕，在后台停留超过一分钟，再由 iCTRL 带回复刻版；[返回脚本](../playbooks/clock-background-return-clone.json)读取运行态秒表并截图，随后用[停止脚本](../playbooks/clock-running-stop-clone.json)结束测试。

| 手机 | 操作前可见值 | 主屏幕至返回 | 返回后首次可见值 | 两次观察时间差 | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| XR / iOS 16.1.1 | `00:01.25` | 70.2 秒 | `01:31.80` | 90 秒 | 保持运行；可见增量 90.55 秒 |
| iPhone 14 / iOS 17.3.1 | `00:01.25` | 76.8 秒 | `01:36.55` | 95 秒 | 保持运行；可见增量 95.30 秒 |

观察时间戳只有秒级精度，采集界面时秒表也在继续走动。这些数字支持“在已测后台间隔内按墙钟继续前进”，不构成亚秒级计时精度证明。返回截图已逐张查看，六份启动、返回和停止脚本案例均通过 `copyapp verify`：

- XR：`cases/ios16-clock-background-{start,return,stop}-v0110-20261017/`
- iPhone 14：`cases/ios17-clock-background-{start,return,stop}-v0110-20261017/`

iCTRL 的 Home 与返回时间戳保存在被 Git 忽略的各机启动案例 `lifecycle-home.json`、`lifecycle-return.json`。这两份补充日志不像 playbook 文件那样受 `copyapp verify` 绑定；其 SHA-256 分别为 XR `6d313ea0cfc7547d5fe958e38b848d023f0633108a2d7170468ab0197d5f9d81` / `d4f8f4c9780252b134935aaa708f1d8ceaa0201e5f6974dfa32a0f662d00a3c8`，iPhone 14 `f08294029e85056cc8d77b4f1d6a6daa2508ed1f31df1d6e98f70c8c0591cf15` / `f95d393d4d65bd7a13a0b142ae00cb2250358108840ec50ef118849a4b62eb4e`。XR 第一次 Home 调用误用了系统 Python，在操作手机前就因转发无法建立而失败；上表使用的是改用项目虚拟环境后的成功调用。

本次每机仅测试一次约一分钟的复刻版后台间隔；未修改原版 Clock 当前用户秒表以做配对对照，也未测试长达数小时的挂起、重启、系统时间调整、低电量、通知或闹钟。[双机矩阵](two-device-verification-matrix.zh-CN.md)继续列出这些边界。
