# 用于分析的加密包恢复

[English](full-package-decryption.md) · 简体中文 · [安装指南](setup.zh-CN.md)

App Store 安装包的主 App 和扩展可能包含加密 Mach-O。Copy APP 能生成索引内可执行文件 `cryptid=0` 的**分析 IPA**，并审计究竟修改了哪些字节。它不会恢复开发者原始源码，也不会产出已签名可安装 IPA。

## 路径与核验

1. `copyapp acquire` 经准确 USB 设备上的已认证 mobile SSH 读取安装包，并保存带哈希的快照。
2. `scripts/prepare-ipadecrypt-helper.sh` 将固定版 `londek/ipadecrypt` helper 下载到仓库外的 `../toolchains/`，仓库不打包该 helper。
3. `copyapp decrypt-package` 校验设备、App 和快照身份。已测普通 rootless iOS 通过 Frida 启动有界 root 进程；已测 RootHide 设备经其命名空间内已认证的 mobile SSH 运行。
4. helper 使用暂停启动和 `mach_vm_read` 恢复各加密可执行文件。Copy APP 检查长度与 UUID，仅允许声明的加密区和 `cryptid` 字段变化，核对未改变的 ZIP 成员，并写入规范化包元数据。
5. 命令对恢复后的 IPA 建索引并记录各文件结果。`copyapp verify <DECRYPT_CASE>` 复核来源身份、哈希、字节差异审计及整个包的加密头。

```sh
sh scripts/prepare-ipadecrypt-helper.sh
.venv/bin/copyapp acquire --udid <UDID> --bundle <BUNDLE_ID> \
  --out cases/<ACQUIRE>
.venv/bin/copyapp decrypt-package --udid <UDID> --bundle <BUNDLE_ID> \
  --snapshot cases/<ACQUIRE>/bundle-snapshot.ipa \
  --out cases/<DECRYPT>
.venv/bin/copyapp verify cases/<DECRYPT>
```

`copyapp analyze --decrypt` 会把恢复与界面概览、包采集、有界沙盒索引组合起来，生成采集索引 `analysis.md`；语义报告仍需审阅 UI／运行证据并调用 `copyapp report`。

## 已测范围与边界

整包恢复已在 XR/iOS 16.1.1 的加密 DeepSeek、Kimi 主程序及扩展上，以及 iPhone 14/iOS 17.3.1 RootHide 的 Remoboard 主 App 与键盘扩展上验证。这些结论只适用于指定的安装包构建，不能保证任意 App 或系统可用。有些二进制本就未加密；工作流会记录未改变的来源快照，不宣称发生了解密。RootHide helper 不需要 root SSH 登录。分析产物、helper 日志和导出数据都保存在被 Git 忽略的本地 `cases/`，不作为发布资源。报告恢复成功前须检查准确案例，界面、函数和行为结论需另行建立证据。
