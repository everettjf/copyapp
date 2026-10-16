# Copy APP 直连 Hopper

**语言：** [English](rea-hopper-integration.md) | 简体中文

Copy APP 现在独立调用 Hopper，不需要安装或运行 REA。旧 `rea-function`、`rea-queue` 和 `rea-bridge` 入口已经删除；历史 REA 证据仍可只读校验。

## 原理

1. 输入从手机采集或恢复的 Mach-O，先核对原始文件 SHA-256。通用二进制会单独选取 ARM64 slice 并记录其哈希；加密文件会被拒绝。
2. `hopper-function` 在 Mac 上调用 Hopper 的 launcher，用 `--loader Mach-O --aarch64 --analysis -Y <script> --executable <临时副本>` 导入。Copy APP 自带的 Python 脚本通过 Hopper `Document`/`Procedure` API 精确定位函数入口并提取伪代码。
3. 结果保存脚本、启动日志、函数签名、伪代码和来源哈希。报告导入时重新核对原始文件、slice、地址与所有证据文件。
4. `hopper-queue` 从已校验的运行时/静态候选中选有限函数。`investigate-flow`、`investigate-app`、`prepare-analysis` 与 `prepare-app` 使用 `--provider hopper-direct`；顶层 `copy` 使用 `--analysis-provider hopper-direct`。反编译结果会进入审阅任务和正式报告。

参考了 REA 的 MIT 许可 Hopper adapter 来选择 API，但脚本、候选队列与证据校验由 Copy APP 实现。许可见 [REA-LICENSE.txt](../third-party/REA-LICENSE.txt)，运行时不启动 REA。

## 用法

```sh
.venv/bin/copyapp hopper-function --file <MACHO> --sha256 <原始SHA256> --address 0x地址 --out cases/<函数>
.venv/bin/copyapp hopper-queue --candidates cases/<候选案例> --limit 4 --out cases/<队列>
.venv/bin/copyapp investigate-flow --udid <UDID> --analysis cases/<分析案例> --script playbooks/<流程>.json --provider hopper-direct --out cases/<调查案例>
```

可加 `--hopper-app '/Applications/Hopper Disassembler.app'` 指定安装位置，也可设置 `HOPPER_APP`。Hopper 是另行安装和授权的 macOS GUI 软件，需在正常登录的图形用户会话中运行。受限 shell 可能因启动器无法查询 Spotlight 而出现 `Cannot launch Hopper!`。单函数默认超时 600 秒。

## 已验证范围

对 XR 导出的夹具分享扩展，Copy APP 直连 Hopper 反编译了 `viewDidLoad`。对同机导出的夹具主程序，单函数队列反编译了 `FixtureHomeViewController::showCounter`；伪代码显示创建 SwiftUI hosting controller 并压入导航栈。[来源校验报告](../cases/fixture-counter-hopper-report-20261016/report.md)已导入这条证据。这次独立队列使用此前采集的 UI/Frida 候选。

首次在 XR 上运行集成 `investigate-flow --provider hopper-direct` 时，Instruments 启动夹具 App 停滞；中断现场保留在 `cases/fixture-counter-hopper-investigation-20261016/`。Copy APP 现在把启动放入子进程并限制为 20 秒；若失败，就通过配对的 iCTRL 通道终止并重启指定 App。playbook 清单记录实际启动方式和首选通道错误。

之后的[XR 集成调查](../cases/fixture-counter-hopper-investigation-v2-20261016/manifest.json)完成全部七个 UI 步骤：计数由 12 变为 13；Frida 在导航点击期间记录到一次 `FixtureHomeViewController::showCounter`；静态候选绑定到 `0x1000056ec`；Hopper 6.6.0 对该地址生成伪代码。流程、Hopper 队列及[正式报告](../cases/fixture-counter-hopper-integrated-report-20261016/report.md)均通过 `copyapp verify`。本次 Instruments 失败，记录中的实际方式是 `ictrl_lifecycle_fallback`。这证明 XR/iOS 16.1.1 夹具的一条集成调查与报告导入，不代表整个 `copy` 分析到复刻交付或 iOS 17/26 已完成验证。

当前 Hopper 输出签名和伪代码；Ghidra 路径另有有界调用关系和间接目标跟随。伪代码是反编译器的解释，不是原作者源码，也不独自证明 UI 操作执行了函数。
