# Hopper 直连

[English](rea-hopper-integration.md) · 简体中文 · [架构](architecture.zh-CN.md)

Copy APP 直接调用本机安装的 Hopper，**运行时不依赖 REA**。旧的 `rea-function`、`rea-queue` 和 `rea-bridge` 入口已删除。新的 Hopper 分析需要 Hopper 许可与正常登录的 macOS 图形会话。

## 证据路径

1. 采集或恢复目标 Mach-O，固定原始 SHA-256；胖二进制另行选择 ARM64 切片并记录其哈希。二进制仍加密时先恢复分析副本。
2. `hopper-function` 用有界 Python 脚本启动 Hopper，通过 `Document`／`Procedure` API 解析指定函数入口并请求伪代码。
3. 保存启动脚本及日志、来源身份、地址、结果和哈希；校验器核对原始字节、切片和地址绑定。
4. `hopper-queue` 从已校验候选案例选取有限地址。`--provider hopper-direct` 将结果交给调查、报告与 Agent 任务；父级 `copy` 命令使用 `--analysis-provider hopper-direct`。

```sh
.venv/bin/copyapp hopper-function --file <MACHO> \
  --sha256 <ORIGINAL_SHA256> --address 0xADDRESS --out cases/<FUNCTION>
.venv/bin/copyapp hopper-queue --candidates cases/<CANDIDATES> \
  --limit 4 --out cases/<QUEUE>
.venv/bin/copyapp investigate-flow --udid <UDID> \
  --analysis cases/<ANALYSIS> --script playbooks/<FLOW>.json \
  --provider hopper-direct --out cases/<INVESTIGATION>
```

自动定位失败时可传 `--hopper-app '/Applications/Hopper Disassembler.app'` 或设置 `HOPPER_APP`。受限 shell 可能报 `Cannot launch Hopper!`，而正常图形会话能够运行。直连函数／队列目标默认限时 600 秒；失败时查看保存的日志，不能把部分伪代码当成完成结果。

伪代码是分析结果，不是原作者源码，也不证明某次 UI 操作执行了该函数。应与哈希绑定的静态候选结合，必要时另行校验 Frida 跟踪。直连 Ghidra 仍可提供有界调用者、被调用者和指令资料，以及选定间接调用调查。Hopper 适配设计参考了 MIT 许可的 REA 代码，许可证保存在 [REA-LICENSE.txt](third-party/REA-LICENSE.txt)；脚本、队列与校验器由本仓库维护。
