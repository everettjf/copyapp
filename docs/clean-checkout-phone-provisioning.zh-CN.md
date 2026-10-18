# 干净检出后的手机配置实测 · 2026-10-18

[English](clean-checkout-phone-provisioning.md) · [简体中文](clean-checkout-phone-provisioning.zh-CN.md)

本次在**同一台实体 Mac**上使用全新本地检出和虚拟环境，没有沿用主检出中被忽略的 SSH 配置、密钥或 Frida 配置。USB 上有两台精确设备：XR/iOS 16.1.1 Dopamine rootless 和 iPhone 11/iOS 26.0.1 Relaxin/RootHide。主检出已验证的 SSH 通道只用于将新隧道主机公钥与手机自身公钥比对，并无密码地授权临时 `mobile` 公钥。真正的新 Mac 仍须单独完成 USB 配对和首次 SSH 授权。

| 阶段 | XR / iOS 16 | iPhone 11 / iOS 26 |
| --- | --- | --- |
| 干净主机 | 本地检出，运行 `bootstrap-macos.sh` 和 `--trace`，生成新虚拟环境 | 使用同一新检出；之后把 RootHide 所需的 Mac 端 Frida 固定为 17.23.3 |
| 首次 `onboard` | 生成新 SSH 密钥，正确报告分析配置尚未完成 | 生成另一把新 SSH 密钥，正确报告分析配置尚未完成 |
| SSH 信任 | 新 `22416` 隧道的主机公钥与旧受信通道读取的手机公钥一致；新密钥登录返回精确 UDID | 本地 `22426` 已被 iOS MCP 转发占用，SSH 改用 `22526`；主机公钥一致，新密钥登录返回精确 UDID |
| 授权后的 `onboard` | 复刻主机工具与分析必需通道就绪；可选 DVT 文件列表仍失败，SSH 可用 | 复刻主机工具就绪。旧代码在侧车尚未配置时把普通 USB Frida 进程列表误判为深度分析就绪；修正后显示 `needs setup` 并打印 RootHide 修复步骤，侧车完成后才显示就绪。 |
| 真实 App 采集 | 不带 SSH 参数的 `analyze --launch` 完成原版 Clock 包、静态索引、沙盒元数据和界面采集 | 同样完成原版 Clock 采集 |
| 运行时与复刻 | 新检出尚未配置 iCTRL 配对；本轮未在 XR 安装新复刻构建 | 固定版本的官方 RootHide Frida 侧车配置并校验通过；五秒 Clock 方法探针成功附加并定位 `MTAStopwatchController::_startStopButtonDown:`，静止窗口命中数为零。在新检出中构建仓库内独立 ClockIOS26 源码，使用这台 Mac 已有开发证书及覆盖精确设备的描述文件签名，经 USB 安装为 build 2，随后 13 步 Start → Stop → Reset iOS MCP 脚本通过。 |

列出的设备诊断、侧车、采集、安装及界面案例复制到被忽略的本地 `cases/clean-phone-provision-20261018/` 后均通过 `copyapp verify`；短时独立 Frida 跟踪是 JSON 观察文件，并非案例校验输入。已目视检查最终截图显示重置后的秒表。随后从两台手机删除临时 SSH 公钥，新密钥登录均被拒绝，原有受信登录再次通过；新私钥没有复制进证据目录。签名使用了这台 Mac 已有的证书和描述文件，因此不能证明另一台 Mac 的开发者账号配置和手机签名。新检出的 iCTRL 首次配对及完整重启／重新越狱也未实测。

修正 RootHide 就绪判断后，两机重新运行当前代码的 `doctor` 并通过校验：`cases/ios16-after-clean-onboard-fix-20261018` 和 `cases/ios26-after-clean-onboard-fix-20261018`。XR 的 SSH、Frida、iOS MCP 仍可用；iOS 26 的 Frida 传输标记为 `usb_roothide_sidecar`，RootHide 标记仍在。新版引导和标记检测由本地 341 项单元测试覆盖。
