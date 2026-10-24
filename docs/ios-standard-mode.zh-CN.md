# 普通 iPhone 模式（开发分支）

[English](ios-standard-mode.md) · [方案与验收条件](ios-device-support-plan.zh-CN.md)

本检出新增显式 `--mode standard|auto|enhanced`。未加模式的历史 iOS 命令保留原有契约。这仍是开发功能，不属于已发布 v0.2.0 的支持承诺。macOS 继续使用独立 `copyapp mac` 命令和 ChatComputer 身份。

已测普通模式样本是 iPhone 11（`iPhone12,1`）／iOS 26.0.1：经用户授权重启后，SSH、Frida 和 iOS MCP 不可用。手机有历史越狱文件，属于“越狱未激活”，不能视作从未越狱的干净手机。已通过 USB 安装开发签名 iCTRL runner，完成系统计算器加法的观察、独立实现、签名安装和同机对照；两对截图均已审阅，保留轻微差异。首轮达到 87.4/100 的有界保真度目标；这是选定范围的审阅评分，与能力覆盖率和整 App 等价分别报告。iPhone 14／iOS 17.3.1 也通过了显式普通模式的自有测试 App 流程，但其已有 RootHide 服务保持运行；这增加了一个命名系统回归，不能替代从未越狱设备的兼容性验收。

使用仓库 `.venv/bin/copyapp`，固定 UDID 与 Bundle ID。先确认配对、信任、开发者模式、Xcode 和覆盖该设备的有效开发签名。心跳成功只表示可以尝试，不能证明 XCTest 动作或签名安装可用。

```sh
.venv/bin/copyapp devices
.venv/bin/copyapp onboard --udid <UDID> --stage analyze --mode standard --out cases/standard-onboard
.venv/bin/copyapp setup ictrl --help
```

按现有 iCTRL 安装说明准备覆盖该设备的签名 runner IPA，安装明确指定 `--transport usb`；失败不会回退到 TrollStore 或 SSH。在已测 iOS 26 路线上，普通模式回放创建并清理自己的 XCTest 会话，通过准确 USB 设备截图。启动黑屏只在业务动作前进行有界 Home／激活恢复；动作回复丢失不会自动重发点击。

已有流程时：

```sh
.venv/bin/copyapp analyze --mode standard --udid <UDID> --bundle <BUNDLE> \
  --script <FLOW.json> --out cases/standard-analysis
.venv/bin/copyapp verify cases/standard-analysis
.venv/bin/copyapp report --case cases/standard-analysis --findings <REVIEWED.json> \
  --feature-spec <SPEC.json> --out cases/standard-report
.venv/bin/copyapp analysis-delivery --task cases/standard-analysis \
  --report cases/standard-report --out cases/standard-analysis-delivery
```

`prepare-app --mode standard` 也使用这个 UI 优先采集器。采集结束仅生成 `TASK.md`，不是正式报告。当前 Agent 审阅全部截图和可访问性原始观察，区分直接观察、推断和未知；每条规格保留 `source_script_sha256` 和最后动作后的行为断言。新增 `ios_behavior_report`、`ios_behavior_delivery` 只核验行为与来源；函数语义和私有沙盒仍走已有显式增强调查与深度报告流程。

需要一个可恢复父工作流时：

```sh
.venv/bin/copyapp copy --mode standard --agent-provider current \
  --udid <UDID> --bundle <BUNDLE> --rebuilt-bundle <OWN_BUNDLE> \
  --auto-discover --output-dir output/<UNIQUE_JOB>
```

命令在交接点返回未完成状态，当前会话继续任务。发现阶段观察原 App，编写 3–12 条不同的有界流程，在指定路径执行 `discover-check --mode standard --backend ictrl`。已有 `--script` 或已接受的 `--discovery` 可以替代 `--auto-discover`。恢复必须保留全部参数和准确任务目录，再加 `--resume`；不会启动嵌套 Coding Agent。未确认动作是否完成时先审阅设备状态；`--resume --retry-failed` 明确归档并重试失败的分析流程。发现重放失败仍需审阅并创建新案例。

失败采集恢复前会重新探测所需能力，保留在 `capability-checks/`；服务失效或路线改变时停止重放，不覆盖初次探测，也不静默切换后端。同一路线修复后，以新接受的探测判断就绪，初次缺失的能力不会使恢复永久阻塞。完整案例的校验与复用不再操作手机。增强 CLI 请求另外固定设备端解密意图、survey 后端、SSH 路由引用与 helper 身份，更改这些输入需要新案例。增强 survey、采集 IPA 元数据、沙盒及可选恢复包都必须与本次 App 版本／构建和设备／系统身份匹配；即使旧构建的成功标记和哈希有效，也会拒绝混入。

按指定路径完成报告和 analysis-delivery，再继续 `rebuild-preparation/task/TASK.md`。实现前固定能力清单与保真度目标；独立源码使用自己的 Bundle ID，普通模式开发签名并通过 `install --transport usb` 安装。完成原版／重建版成对断言、全部截图审阅、visual-review 和不带 `--run` 的 agent-delivery。父工作流仍按严格门槛完成，单独达到有界保真度目标不能替代它；延后能力必须保留。

能力模型 3 通过认证且核对准确 USB 身份的 SSH 探测 helper 实际路线。RootHide 沿用 mobile SSH helper，不要求 root Frida 子进程，也不要求离线 FairPlay 凭据；普通 rootless 路线仍需完整 Frida 与成功的 UID 0 暂停子进程探测，App 跟踪能力本身不证明 root。上述 iPhone 14／iOS 17.3.1 的 Frida 子进程为 UID 501，但 RootHide helper 已恢复 Remoboard 主程序和键盘扩展的加密代码，完整 `analyze --mode enhanced --decrypt` 采集入口也已通过。产出的分析 IPA 签名已改变，不声明可安装。普通模式跳过这两项越狱探测。历史模型 1、2 保留原校验；模型 2 把 root 条件套用到全部路线，曾过早拒绝此 RootHide 路线，不能据此判断无法解密。详见[路线修正与实测证据](ios-device-support-acceptance.md#roothide-device-recovery-correction)。

安装包与手机权限分开处理，可选使用：

```sh
sh scripts/bootstrap-ios-host-tools.sh --all
# 用户在本机终端交互登录，密码和令牌不要进入任务或对话。
toolchains/bin/ipatool auth login
.venv/bin/copyapp store-download --bundle <BUNDLE> --out cases/store-package
.venv/bin/copyapp package-import --ipa <FILE.ipa> --bundle <BUNDLE> --out cases/imported-package
.venv/bin/copyapp decrypt-offline --package cases/imported-package \
  --credential-ref <LOCAL_ALIAS> --out cases/offline-package
```

具体参数以 `--help` 为准。`ipatool` 固定 v2.7.0，FairPlay 固定 commit `1bad106ee1698c6d9c483f67d898183ffa4c6eb3` 并检查四个源文件哈希。下载记录工具哈希／版本、请求身份与实际包元数据；许可获取必须显式 `--acquire-license`，不保留原始账号日志。真实登录后已成功下载免费的 FocusTodo 1.0.4（4），并在上述越狱未激活的 iPhone 11 上通过两条普通模式 UI 流程；主程序、框架和 Widget 仍有加密。工具安装本身不证明登录或下载，登录成功也不等于已有匹配的离线凭据。

新下载使用 `download_provenance_version: 2`，仅从 IPA 的 `iTunesMetadata.plist` 字段 `s` 提取六位商店编号，明确标为 `downloaded_package_metadata`。校验器从保存的 IPA 重读该值；缺失或格式异常时保留未知，不把姓名、Apple ID 或账号会话输出复制到记录中。这不等于独立确认账号地区，旧记录仍按原字符串格式校验。真实再次下载 FocusTodo 的固定外部版本 `893656071` 已匹配，记录包内商店编号 `143465`；四个加密程序的哈希、UUID 和加密范围均与前次一致，整个 IPA 哈希不同。两者都不能证明手机加载的代码字节身份。

从源码目录外运行 wheel 时，把 `COPYAPP_SOURCE_ROOT` 设为包含这些忽略工具与凭据存储的检出目录。默认 ipatool、FairPlay 源码和 credential 查找基于该目录，不依赖 shell 当前目录；显式工具／存储路径仍优先。

匹配的 16 字节 credential 只放在忽略的 `cases/credentials/fairplay/<LOCAL_ALIAS>.bin`，内容、哈希和本地路径不进入证据。首次取得凭据是独立准备任务，适配器不会从普通手机取得它。离线恢复检查全部程序和资源，当前审计范围为 thin ARM64 加密输入，拒绝 FAT。结构成功标为 `structural_only`；原本未加密的输入保留原样，不能算解密成功。有效凭据的真实成功恢复和独立代码交叉核对仍是未完成的验收项。

包索引还会记录不支持的 32 位／反字节序 Mach-O，以及主 App 目录外的程序；这些输入可以保留静态包证据，但会阻断整包离线恢复。全部 FAT 都会拒绝，包括所选 ARM64 切片已无加密的情况，因为其他切片尚未审计。

`offline-cross-check --offline <离线案例> --device <已验证设备解密案例> --out <新案例>` 可与历史 `decrypted_package` 交叉检查全部恢复程序和扩展，要求版本／构建、原加密字节哈希、UUID、加密范围和恢复后哈希都相同。比较保留双方采集身份，不修改原案例的 `structural_only` 状态，也不把不同时间观察写成同时发生；真机验收仍需真实成功的离线样本。

给 UI 优先 analyze／prepare-app／copy 重复传 `--package-case` 可导入已验证包。Bundle ID 不符直接拒绝；版本不同仅记 `bundle_only`，版本／构建相同记 `metadata_match`，都不能证明手机实际运行二进制身份。静态结论用 `basis: "package"` 引用 `package.1` 等；UI 结论引用流程 ID，运行或函数结论需要自身对应证据。

包、许可文件、截图与跟踪留在忽略的本地目录，对每个案例执行 `copyapp verify`。v2 iOS 类型显式分派，不会通过历史报告文件名绕过检查。实施方案中未完成的真机、真实凭据和兼容性验收条件仍然有效。
