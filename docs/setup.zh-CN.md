# 配置 Mac 与越狱 iPhone

[English](setup.md) · 简体中文 · [文档目录](README.zh-CN.md)

## 先选目标

| 目标 | 所需组件 |
| --- | --- |
| 首次 USB 概览 | macOS、Python 3.9+、USB 信任、已解锁手机、Copy APP CLI。 |
| 深入分析 | 兼容越狱环境、mobile OpenSSH 与固定的 SSH 密钥、iOS MCP 界面服务、Frida；开发者服务需要完整 Xcode。仅在需要时加 Ghidra/Hopper。 |
| 可运行复刻 | 深入分析环境，加完整 Xcode、签名或 TrollStore，以及经过验证的安装路径。iCTRL 可选。 |

以下步骤针对 v0.1.1 检出。正式 wheel 包含 Mac CLI，但不包含 Theos、手机 tweak、签名资源或私有凭据。使用 wheel 搭配源码构建的可选组件时，另保留一份仓库检出，并设置 `COPYAPP_SOURCE_ROOT=/absolute/path/to/copyapp`。

## 1. 安装 CLI 并识别手机

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
.venv/bin/copyapp apps --udid <UDID> --all
```

`onboard` 输出精确 UDID；连接多台手机时显式传 `--udid`。解锁手机并接受 USB 信任。需要开发者服务时，用 `xcode-select -p` 确认选择完整 Xcode，按提示启用开发者模式并挂载兼容的开发者镜像。iOS 26 上已测的 iCTRL 路径使用个性化开发者镜像与 userspace XCTest 隧道。先阅读 `onboard` 保存的报告，再配置其他组件。

在手机上打开目标 App，做首次采集：

```sh
.venv/bin/copyapp survey --udid <UDID> --bundle <BUNDLE_ID> \
  --ui-backend usb --out cases/first-survey
.venv/bin/copyapp verify cases/first-survey
```

这只是设备和首屏检查。重试时使用新的 `--out` 目录。

## 2. 经准确的 USB 设备配置 mobile SSH

在手机上安装适配当前越狱方式的 OpenSSH 服务。运行 `.venv/bin/copyapp onboard --udid <UDID> --stage analyze`，生成专用 Mac 密钥并查看待修复项。第一次核对主机密钥时，在另一个终端保持 USB 转发：

```sh
.venv/bin/copyapp tunnel --udid <UDID> --ssh-only
```

默认本地 SSH 端口为 `22222`。多台手机分别使用不同的 `--ssh-port` 和 `--ssh-known-hosts`。保存转发端的 SSH 主机密钥前，先与所选手机上显示的指纹核对。将 Mac 公钥 `cases/ssh/id_ed25519.pub` 加入手机 `mobile` 用户的 `~/.ssh/authorized_keys`，可用手机终端，或在指纹核对后通过一次密码 SSH 会话完成。不要把手机密码放入命令、仓库文件或聊天；私钥留在被 Git 忽略的 `cases/`。

保持 SSH 转发运行，在仓库终端检查转发端的主机密钥：

```sh
ssh-keyscan -p 22222 127.0.0.1 > cases/ssh-known-hosts
ssh-keygen -lf cases/ssh-known-hosts
```

在所选手机的终端运行 `ssh-keygen -lf <PHONE_SSH_HOST_PUBLIC_KEY>`，读取 OpenSSH 主机公钥指纹并比较。该公钥可能在 `/etc/ssh/` 或越狱专用前缀下。**确认一致后**才授权 Mac 公钥。若已启用密码登录，下面的一次性命令只在交互提示中输入密码：

```sh
cat cases/ssh/id_ed25519.pub | ssh -p 22222 \
  -o UserKnownHostsFile=cases/ssh-known-hosts \
  -o StrictHostKeyChecking=yes -o PubkeyAuthentication=no \
  mobile@127.0.0.1 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
ssh -p 22222 -i cases/ssh/id_ed25519 \
  -o UserKnownHostsFile=cases/ssh-known-hosts \
  -o StrictHostKeyChecking=yes mobile@127.0.0.1 'deviceinfo uniqueid'
```

最后一条命令必须返回所选 UDID。之后运行：

```sh
.venv/bin/copyapp doctor --udid <UDID> --out cases/first-doctor
.venv/bin/copyapp verify cases/first-doctor
```

认证通过后，`onboard`／`doctor` 会把精确设备的端口和密钥路径写入被忽略的 `cases/ssh/profiles.json`，后续命令可复用。不要仅因主机密钥不匹配就替换已固定的密钥。XR/iOS 16 的开发者文件列表探针可能报 `ConnectionTerminatedError`；SSH 包／沙盒采集是已验证的替代路径。

## 3. 加入界面控制与 Frida

**iOS MCP：**使用完整 Xcode、Theos、iPhoneOS 16.5 SDK 与 `ldid` 构建 [`device/ios-mcp`](../device/ios-mcp/README.zh-CN.md)，安装对应 rootless 或 RootHide 包并重新加载 SpringBoard。Theos 和 SDK 需自行安装。RootHide 需使用适配的 Theos fork、`THEOS_PACKAGE_SCHEME=roothide` 及 ElleKit 等 tweak loader。再运行 `doctor` 查看 `ios_mcp` 行。

**Frida：**运行 `sh scripts/bootstrap-macos.sh --trace` 安装 Mac 侧依赖，手机使用兼容的服务端。在已测 iOS 17／26 RootHide 设备上，固定 host `frida==17.23.3` 并设置隔离侧车：

```sh
.venv/bin/python -m pip install 'frida==17.23.3'
.venv/bin/copyapp setup frida-roothide --udid <UDID> \
  --out cases/frida-roothide-setup
```

RootHide 较旧的打包版 Frida 无法附加已测原版 Calculator；能列出进程不代表可附加。普通 rootless 系统使用与 Mac 版本匹配的服务端。RootHide 的整包恢复 helper 使用已认证 mobile SSH；普通 rootless 路径使用经过验证的 root Frida 进程。

**可选 iCTRL：**安装 `xcodegen`（`brew install xcodegen`），在 Xcode 配置 Apple Development 签名，或准备已签名且兼容的 runner IPA，然后运行：

```sh
.venv/bin/copyapp setup ictrl --udid <UDID> --out cases/ictrl-setup
.venv/bin/copyapp verify cases/ictrl-setup
```

首次源码构建会下载固定版本的 iCTRL 框架。手机出现 XCTest、通知和配对提示时核对指纹并批准。iOS 17+ 开发 runner 可用 `--auto-approve-first-pair` 自动批准一次本地 USB 请求。设置 App 和 runner 使用按团队区分的 `com.copyapp.<team-id>` ID；来源见 [`vendor/ictrl/UPSTREAM.md`](../vendor/ictrl/UPSTREAM.md)。当前 iOS 17 复刻版多步重放仍有 iCTRL 传输故障；四流程 Calculator 验收已由 iOS MCP 完成，依赖 iCTRL 验收前应查看[当前状态](current-status.zh-CN.md)。

## 4. 分析与安装复刻版

```sh
.venv/bin/copyapp analyze --udid <UDID> --bundle <BUNDLE_ID> \
  --launch --ui-backend ios-mcp --out cases/first-analysis
.venv/bin/copyapp verify cases/first-analysis
```

`analysis.md` 是采集索引，不是完成的逆向语义报告。加密的 App Store 二进制可能需要 `sh scripts/prepare-ipadecrypt-helper.sh` 和 `analyze --decrypt`；产物是**分析 IPA**，并非已签名可安装 App。见[整包恢复](full-package-decryption.md)。正式报告还需审阅界面流程、函数证据和 `copyapp report`；按[工作流指南](copy-workflow.zh-CN.md)继续。

构建并签名独立 Xcode App。开发签名的 USB 安装路径：

```sh
.venv/bin/copyapp install --transport usb --udid <UDID> \
  --ipa <SIGNED_IPA> --out cases/clone-install
.venv/bin/copyapp verify cases/clone-install
```

安装成功不代表能启动或与原版等价。还需重放选定原版／复刻版流程、核对末端行为、逐张审阅截图并列出缺口。XR 上仍有适配包的 TrollStore 路径。IPA、截图、沙盒数据、SSH 密钥及配对材料都放在被忽略的 `cases/`。
