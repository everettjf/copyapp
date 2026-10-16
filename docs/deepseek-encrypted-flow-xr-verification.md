# DeepSeek 加密 App：XR 准备流程试点

测试对象为越狱 iPhone XR 上的 DeepSeek 2.4.4（build 3，`com.deepseek.chat`）。本次从已安装 App 启动 `prepare-app --decrypt`，观察登录页的密码入口；没有输入账号、点击条款同意或访问登录后的功能。

## 已验证

- [准备案例](../cases/deepseek-prepare-app-encrypted-20261015/manifest.json)保存了 USB 采集、整包恢复与后续调查的阶段状态。父任务已达到 `needs_semantic_review`，所有子案例通过来源校验。
- [整包恢复记录](../cases/deepseek-prepare-app-encrypted-20261015/analysis/decrypted/decryption.json)检查 32 个 Mach-O，恢复原先加密的主程序和分享扩展，确认加密区及 `cryptid` 字段之外的字节未变；生成的 IPA 仅供分析，不能据此声称可安装。主程序 SHA-256 为 `402f5178d668e8b031fb26a89fa7df720df3824a90b22af30093c3817866438a`，索引有 1,212 个 Objective-C 类、13,099 个方法。
- [原版界面记录](../cases/deepseek-password-gate-original-20261015/step-04-observe.json)显示点击“Continue with Password”后出现条款确认弹窗。测试到此停止，没有点击“Agree”。
- [同次操作的 Frida 轨迹](../cases/deepseek-prepare-app-encrypted-20261015/preparation/investigation/flows/flow-01/flow/trace/trace.json)显示第 3 步 `_TtC13DeepSeek_Chat8DSButton::objcOnTap` 的当前 IMP 和主程序静态入口各命中 1 次；运行模块偏移均为 `0x821558`，对应解密主程序静态地址 `0x100821558`。这建立了观察窗口内的入口关联，不单独证明这个方法负责弹窗的全部逻辑。
- [REA/Ghidra 入口函数](../cases/deepseek-prepare-app-encrypted-20261015/preparation/investigation/flows/flow-01/rea/targets/01-100821558/summary.json)已完成，解析出 `DSButton::objcOnTap` 调用 `0x100820cec`；[限定地址的原始汇编](../cases/deepseek-dsbutton-static-20261015/evidence.json)与之相符。此次 REA 分析 profile 关闭了 `Objective-C Message Analyzer`，因此相关自动推断不应视为完整。
- [Hopper 文档的界面观察](../cases/deepseek-dsbutton-static-20261015/hopper-observation.md)识别出触觉反馈与 `_onTap` 闭包；[XR 闭包指针探针](../cases/deepseek-password-closure-probe-v2-20261015/probe.json)把本次密码按钮回调定位到主程序偏移 `0x2ff218`。[门控分支探针](../cases/deepseek-password-gate-branch-probe-20261015/probe.json)进一步记录入口、回调和条款检查依次命中，条款检查返回低位 `0`，末端仍显示弹窗。没有点击同意。
- 经审阅的[限定流程报告](../cases/deepseek-password-gate-reviewed-report-v3-20261015/report.md)、[功能规格](deepseek-password-gate-feature-spec.json)和[交付核验](../cases/deepseek-password-gate-analysis-delivery-v2-20261015/report.md)均通过哈希校验，覆盖调查中所选的 1/1 条流程。

## 尚未完成

- 首次 Ghidra 函数分析在默认 330 秒启动期限处超时；延长期限仍不足。针对本次主程序采用 REA 文档支持的 `Objective-C Message Analyzer` 禁用配置后，选定入口成功反编译并保存 profile digest。不同 App 或函数需要按证据重新评估这个配置。[Hopper CLI 尝试](../cases/deepseek-rea-hopper-dsbutton-20261015/failure.json)的桥接仍超时；其卡住会话已退出，保存的 Hopper 文档供手动核对。
- 限定登录门控流程已有报告，但整款 DeepSeek 的主要页面、沙盒内容变化、网络行为、认证与登录后功能没有调查，也没有独立复刻 App。不能把单流程结论称为整款 App 的完整逆向或全功能规格。
- iOS 17/26 设备按当前安排暂不验证；同意条款后的行为未获本次操作授权，需另行确定测试范围。Copy APP 的通用语义审阅和复刻自动化也仍在开发。

## 下一次 XR 复测

`flow-capture` 现可将选定函数入口的原始 32 位返回值与点击步骤、主程序哈希一起保存；也可在间接调用指令处读取指定寄存器，并仅保存落入同一 App 镜像的目标偏移。已用本案解密主程序和 Objective-C 索引确认入口 `DSButton::objcOnTap` 的静态偏移为 `0x821558`。静态汇编中 `blr x19` 位于 `0x820dac`，适合尝试 `--branch-offset 0x820dac --branch-register 0x820dac:x19`；门控函数偏移 `0x2f91c4` 则适合 `--branch-offset 0x2f91c4 --branch-return-u32-offset 0x2f91c4`。本地回归测试和生成的 Frida 脚本语法检查通过。当前 Frida 没有发现 XR，尚不能把旧的一次性探针结果算作新接口的真机验收；设备重新连接后，应重放原脚本并比较回调偏移、返回原值、末端截图与旧案例。
