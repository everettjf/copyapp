# Copy APP TODO

## 已完成：iOS IPA 的 FairPlay 凭据与离线解密实测

2026-10-23：用户先将以下工作延后，随后授权复用现有 iOS 17 越狱手机及已安装 App，并将提取接入正式流程。真实凭据、Mac 离线恢复、设备代码比较、物理拔线重跑及回归检查均已完成。用户现已授权最终复核和测试通过后合并 PR #4。

- [x] **准备目标账号和 App。** 复用 iPhone 14 / iOS 17.3.1 的 Remoboard 7.1 (7100)。现有安装授权与已采集 IPA 的授权一致；凭据还通过既有 FocusTodo 商店下载包的授权校验，两者账号匹配。
- [x] **提取并保存真实凭据，接入正式流程。** [`credential-retrieve`](docs/ios-fairplay-credentials.md) 已正式接入 CLI。核对固定上游的 33 个公开源码输入并重新构建原生助手，复用准确 USB 身份、固定主机密钥和 RootHide mobile SSH，校验安装 App 及指定 IPA 的 SINF，清理远端后保存。正式入口已在同一 iOS 17 手机上实测成功。上游 Python 默认 root SSH，本机实测无需 root 登录。凭据仅存本地，以不透明别名引用；权限 0600／目录 0700，内容、哈希及实际路径不进入 Git、报告或聊天，已有别名不会覆盖。
- [x] **验证无设备访问能力的真实离线恢复。** 安装后的 wheel 在 macOS `sandbox-exec` 禁止全部网络访问的进程中恢复 Remoboard 主程序和键盘扩展；直接 USBMux socket、设备枚举和本地网络连接均实际返回权限拒绝。包审计与独立设备字节比较都通过。见[隔离实测](output/fairplay-credential-ios17-20261023/isolated-offline-check.json)。这证明该进程不依赖可访问的手机通道，但不记作物理拔线测试。
- [x] **完成物理断开手机后的重跑。** 用户确认拔掉两台手机的 USB 线后，执行前后 USBMux 全部设备数均为 0。安装后的正式 CLI 使用新提取别名，在附加禁网隔离中恢复 Remoboard 主程序和键盘扩展，包审计及独立设备代码比较均通过。见[拔线实测](output/fairplay-credential-ios17-20261023/disconnected-offline-check.json)与[比较报告](output/fairplay-credential-ios17-20261023/remoboard-disconnected-cross-check/report.md)。
- [x] **交叉核对设备恢复代码。** `offline-cross-check` 对主程序和扩展的原加密字节哈希、UUID、加密范围及恢复字节哈希全部匹配，两个完整恢复程序逐字节一致。三个新案例均通过 `copyapp verify`。见[本地实测记录](output/fairplay-credential-ios17-20261023/report.md)与[交叉核对](output/fairplay-credential-ios17-20261023/remoboard-cross-check/report.md)，均为忽略的本地证据。

首次获取和后续离线解密是两个阶段；已有匹配凭据后，解密无需连接手机。这是 Mac 上的 **iOS IPA 分析**，与原生 Mac App 工作流分别验收。保持用户要求的 iPhone 11 越狱未激活状态；不为此待办重新激活它。

## 当前范围已完成

- PR #4 审查的三处问题已修复：`auto` 普通模式回退不再强求默认设备解密；包恢复／凭据提取／行为报告创建输出前拒绝目录重叠；UI 数字断言从原始 AX／OCR 证据重新计算并校验记录值。新增 12 项回归测试，覆盖真实 CLI 默认参数、显式解密不降级、符号链接、合法归零与重算失败等情况。
- 最终复核进一步保护行为交付和离线代码比较：输出不能嵌套在任一来源案例中，避免新记录使原证据失效。补充两项回归，审查回归合计 14 项；完整 509 项测试通过。详见[最终复核](docs/ios-device-support-acceptance.md#final-pre-merge-review)。

- 普通模式 UI 采集、报告、独立开发签名安装、选定计算器流程的同机行为与视觉比较。
- 第三方 FocusTodo 的账号下载和两条普通模式 UI 流程；不包含 FocusTodo 重建。
- iOS 17 越狱增强采集、实际方法跟踪及 RootHide 主程序和扩展解密；完整 `enhanced --decrypt` 入口通过。
- 既有 Mac 编辑器样例回归、旧 v1/Mac 证据校验及新 wheel 的源码一致性验证。
- 最新 507 项测试通过（含 16 项凭据流程测试与 12 项审查回归），安装后 wheel 的 125 个源码资源一致，并在安装版本上通过 12 项新回归。原有 54 个案例重校验通过，新真实离线恢复及代码比较均通过，合计 56 个预期结果吻合。全新虚拟环境安装检查也通过，见[最新核对](output/pr4-review-fixes-20261023/final-check.json)。原有[物理拔线实测](output/fairplay-credential-ios17-20261023/disconnected-offline-check.json)保留不变。

用户已免除单独的“从未越狱手机实测”，保留已测设备的真实历史和范围说明。上述完成项为命名设备、选定流程的结果，不表示任意 App、任意设备或整 App 等价。

详见[验收账本](docs/ios-device-support-acceptance.md)和[实施方案](docs/ios-device-support-plan.zh-CN.md)。
