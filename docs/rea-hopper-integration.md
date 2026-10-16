# REA 与 Hopper 在 Copy APP 中的接法

## 机制

REA 是 coding agent 与反编译器之间的 MCP/CLI 层。对本地 Mach-O，agent 用 `open_binary` 绑定**精确文件路径和 provider**，再按地址或符号调用 `analyze_function`、伪代码、调用关系和引用查询；结果携带二进制哈希、provider、分析配置、Evidence ID 与局限。多个反编译器可用时必须明确选 `hopper` 或 `ghidra`，不能假定自动选择。[REA CLI 与 provider 文档](https://github.com/morluto/rea/blob/main/docs/cli.md)

REA 的 Hopper adapter 使用 Hopper 自带的 `hopper` 命令行 launcher，从原始可执行文件创建新文档，并通过 `-Y` 执行临时 Python bootstrap 脚本。脚本在本机私有 Unix socket 上提供经过会话校验的桥接，REA 再把函数、伪代码、字符串和交叉引用转换为结构化证据。这条路径使用 REA 自己的桥接脚本，不调用 Hopper 6.6.0 App 包内的 `HopperMCPServer`。它不能附着到用户已经手动打开的 Hopper 文档；macOS 上也不能通过这条路径复用已有 `.hop` 数据库。一次会话只绑定一个 provider；关闭 REA 会话时应调用 `close_binary`，它不会退出整个 Hopper GUI。[REA Hopper 安装与生命周期说明](https://github.com/morluto/rea/blob/main/docs/installation.md) · [本机所用 6.4.0 的桥接启动源码](https://github.com/morluto/rea/blob/21eff3bae10f58711a35ad44f86e9f96f9bb4790/src/hopper/BridgeLauncher.ts)

建议的 Copy APP 路径：

1. `decrypt-package` 产出经过包内 Mach-O 和字节差异校验的分析 IPA。
2. 根据 `decryption.json` 与 `static/objc-index.json` 选取**精确 SHA-256** 的二进制和候选方法地址。Swift 的 `@objc` 入口可能只是桥接 thunk，必须继续追到实际 Swift 函数或闭包。
3. 用 REA `open_binary({path, provider_id})` 后对候选函数做定向查询；把完整 Evidence JSON 保存在案例目录，并在报告中引用 Evidence ID、文件哈希、地址、provider 和可信度。
4. Hopper 和 Ghidra 的伪代码可用于互相复核，但不能当作作者源码。真实行为还须与 iOS MCP 的界面证据、Frida 轨迹和沙盒差异关联。
5. 一个 provider 超时或 `cleanup_incomplete` 时保留失败证据，确认资源关闭后才重试；切换 provider 是明确的案例决定，不能把另一 provider 的结果误记为 Hopper 结果。

仓库提供 `copyapp rea-function` 作为不依赖特定 coding agent 的单函数入口。它在启动 REA 前检查目标文件 SHA-256，在完成后核对 REA 返回的目标哈希和 provider，保存 `evidence.json`、`summary.json`、`pseudocode.txt` 与 `report.md`。本机 REA 以源码脚本安装时传 `--rea-script`；Ghidra 的安装目录和 Java 路径可通过参数传入。例子：

```sh
.venv/bin/copyapp rea-function \
  --file /absolute/path/to/recovered/main --sha256 <64位小写SHA256> \
  --procedure 0x100006790 --provider hopper --out cases/<CASE>/rea/function-1 \
  --rea-script <REA_CHECKOUT>/scripts/rea.mjs
```

## 本机实测，2026-10-15

- macOS 安装了 Hopper Disassembler 6.6.0；Codex 的 REA MCP server 为 `rea-agents` 6.4.0，`binary_session` 报告 Hopper 和 Ghidra 12.1.4 都可选。`rea doctor --provider hopper --json` 只证明 launcher 可见，并不证明桥接就绪。
- 初次在受限执行环境中，`open_binary` 用 `provider_id: "hopper"` 接受了测试 App 主程序，随后首个 `analyze_function` 等待桥接 120 秒超时。独立 CLI 对 Compass 与 `FixtureCore` 也超时；Hopper 界面只有空白 `Untitled`，REA 报 `cleanup_incomplete`。这些失败仍是有效的运行记录。诊断时同一个 `mdfind` 在受限环境中找不到 Hopper，正常 macOS 用户会话中则能定位到 `/Applications/Hopper Disassembler.app`；Hopper 的 launcher 依赖 Spotlight。这是失败的一个有力线索，但不足以单独证明所有超时的原因。旧 REA 会话还持有测试主程序的目标租约，因此未删除私有运行目录或强行重复打开它。
- 在正常 macOS 用户会话中，REA/Hopper 6.4.0 对新编译的最小 Mach-O 完成了函数查询：`_add` 的伪代码为参数相加，输出中的 provider 为 `hopper`、目标 SHA-256 为 `489a65e7…`，Evidence ID 为 `ev_f6f0d82d…`；完整证据在本地 `cases/rea-hopper-normal-session-20261015/probe-evidence.json`。
- `copyapp rea-function --provider hopper` 随后对**XR 导出的** `FixtureShare.appex/FixtureShare` 成功分析 `0x100004000`：目标 SHA-256 为 `6f715eb4…`，Evidence ID 为 `ev_54c18fb…`。伪代码出现 `systemBackgroundColor`、`UILabel`、`addSubview`、两个中心约束及 `activateConstraints`，与已知源码的 `viewDidLoad` 对上。`cases/rea-hopper-normal-session-20261015/xr-share/` 留存完整证据。案例报告 `cases/fixture-xr-deep-report-v4-20261015/report.md` 已纳入该证据并通过 `copyapp verify`。这证明本机自动接入链路可用，不证明分享扩展已在手机上运行验证。
- 同一测试 App 主程序通过 REA/Ghidra 成功分析。`cases/fixture-rea-20261015/ghidra-add-note.json` 将 Objective-C 入口 `FixtureNotesViewController::addNote` 解析为 Swift 桥接；`ghidra-add-note-body.json` 跟到 `NoteStore.addSampleNote`；`ghidra-sqlite-insert.json` 找到 `sqlite3_open` 和建表 SQL；`ghidra-sqlite-insert-closure.json` 找到 `INSERT INTO notes (text) VALUES (?)`、`sqlite3_bind_text`、`sqlite3_step` 与 `sqlite3_finalize`。这些地址和调用与 `fixture/CopyAppFixture/Sources/NotesViewController.swift` 的源码相符。REA 输出的 Evidence ID、哈希和完整局限保存在上述 JSON；案例目录受 Git 忽略。
- `copyapp rea-function` 在相同函数 `0x100006790` 的端到端测试成功，输出 `cases/fixture-rea-function-20261015/`，核对到 `ghidra`、Ghidra 12.1.4、原始二进制 SHA-256 与 SQL `INSERT` 伪代码；错误哈希和 provider 身份错配分别在自动测试中被拒绝。
- 对 XR 导出的真实系统 Compass 主程序，同一 SHA-256 `469bfd16…` 的 `tappedCompass:`、`setBearing`、`unsetBearing` 和 `CompassBearingView::updateLayer` 已分别由 REA/Hopper 与 REA/Ghidra 分析。两边都支持方位锁定状态切换及图层角度变化触发重新布局的控制流；Hopper 对浮点实参的恢复较弱，Ghidra 对部分尾部控制流有局限，故报告未宣称参数级完全一致。证据和真机实验关联见 [Compass 点击到函数链路](compass-runtime-static-rea.md)；完整结果在 `cases/compass-xr-deep-report-v8-20261015/`，已通过 `copyapp verify`。

**目前取舍**：REA/Hopper 与 REA/Ghidra 都有成功的本机函数证据；Hopper 可以作为 Copy APP 的显式深度分析 provider。Hopper 需要已完成许可或 demo 首次启动的交互式 macOS 用户会话，以及能正常访问 Spotlight/Apple Events 的启动环境。编码 agent 的受限命令环境仍可能超时，故自动批量任务优先采用已稳定的 Ghidra，Hopper 用于指定函数的复核或用户明确选择。对持续 MCP 会话，完成后显式 `close_binary`；一次式 `rea function`/`copyapp rea-function` 已成功返回并释放本次会话。旧失败留下的目标租约仍应由其所属 REA 会话清理，不直接删除资源。
