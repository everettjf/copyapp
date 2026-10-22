# Decompilers and reverse-engineering tools

[简体中文](reverse-engineering-tools.zh-CN.md) · [Project README](../README.md) · [Documentation](README.md)

Copy APP directly integrates **Ghidra and Hopper for decompilation**, alongside Frida runtime observations, LLVM disassembly, built-in Mach-O/Objective-C indexes and package recovery on verified device routes. Tools run on the Mac and save evidence tied to binary hashes, addresses and logs. The current coding agent interprets it.

## Supported tools

| Tool | Purpose | Copy APP entry | Prerequisites |
| --- | --- | --- | --- |
| **Ghidra** | Selected native-function pseudocode; bounded callers/callees, blocks and instruction references | `ghidra-function`, `ghidra-queue`, `ghidra-indirect`; `--provider ghidra-direct` | Separately installed Ghidra and a matching JDK; explicit installation paths |
| **Hopper Disassembler** | Selected-function pseudocode and bounded candidate queues | `hopper-function`, `hopper-queue`; `--provider hopper-direct` | Local Hopper, a usable license and a normal logged-in macOS GUI session |
| **LLVM / Xcode llvm-objdump** | Bounded ARM64 assembly and unique local direct call/branch followers | `native-disasm`, `native-queue` | Toolchain discoverable with `xcrun --find llvm-objdump`; assembly is not pseudocode |
| **Frida** | Named Objective-C hits, selected original entries and indirect-call register observations | `trace`, `experiment`, `flow-capture --method`; composed by investigations | Host Frida and compatible jailbroken-device services, exact device identity; bootstrap `--trace` when needed |
| **Built-in Mach-O / Objective-C parsing** | Package/load-command/encryption metadata and class/selector/method-address indexes | `ipa`, `objc`; Mac packages use `mac inspect` / `mac acquire` | Corresponding acquired files; no Ghidra/Hopper required; does not recover Swift source |
| **ipadecrypt helper and Copy APP recovery** | Recover encrypted Mach-O analysis copies on verified device routes | `decrypt-package`, `analyze --decrypt`; separate `decrypt-main` for the main executable | Exact device/App/snapshot, prepared and verified helper; device-specific SSH/Frida route |

The first two are decompilers. The others supply assembly, runtime observations, static indexes or package recovery. ChatComputer, iOS MCP and iCTRL supply UI observation/control rather than decompilation.

## Platform scope

**iOS:** existing native investigations bind replayed UI, Frida observations, Objective-C candidates, bounded assembly and optional pseudocode to the acquired binary. An agent must review them before reporting semantic findings. See [device status](current-status.md) and [package recovery](full-package-decryption.md) for named-device limits.

**macOS:** the separate workflow currently covers App packages, AX, screenshots and behavior comparisons. It does not have the equivalent iOS native-function investigation/report chain. Standalone function commands can process local Mach-O inputs that meet their constraints, but that alone establishes neither deep Mac function analysis nor arbitrary-App acceptance. See [Mac support](macos-support.md).

## Decompilation is opt-in

`investigate-flow`, `investigate-app`, `prepare-analysis` and `prepare-app` default to `--provider none`. That path can still collect UI, static indexes, runtime observations and available bounded assembly; it does not generate new decompiler pseudocode.

Select `--provider ghidra-direct` or `--provider hopper-direct` when needed. The parent `copy` workflow names the option `--analysis-provider`. These iOS investigation options must not be assumed to exist on `copyapp mac` commands.

The bootstrap does not install Ghidra, a JDK or Hopper. Follow [Ghidra's official installation instructions](https://github.com/NationalSecurityAgency/ghidra#install) for a matching JDK, or install licensed Hopper from its [official site](https://www.hopperapp.com/). Failed launches, timeouts and still-encrypted inputs remain failures; partial pseudocode does not establish completion.

## Ask the current agent

Append this to an existing **iOS analysis task**:

```text
This task needs function-level pseudocode. Check the available Ghidra/JDK or Hopper installation, choose ghidra-direct or hopper-direct and record the actual provider in the report.
Verify the acquired binary, SHA-256, ARM64 slice and candidate addresses first. Decompile only a bounded set of functions relevant to the selected flows.
Separate actual Frida hits, static references, decompiler results and your semantic inferences. Cite verified evidence and do not call pseudocode original source.
Review in this current agent session without nesting another agent. For a Mac target, stay within the implemented Mac workflow and disclose the missing native-function chain.
```

For a specified tool, name its provider and installation paths explicitly. The agent can inspect installed tools; a Python package cannot supply a Hopper license or normal GUI session.

## One selected function from the CLI

Use the hash and address of the same verified analysis binary. Recover encrypted inputs through the verified device route first. Use a new case for every attempt.

Ghidra:

```sh
.venv/bin/copyapp ghidra-function --file <MACHO> \
  --sha256 <SHA256> --address <0xFUNCTION_ENTRY> \
  --ghidra-dir <GHIDRA_DIR> --java-home <JDK_HOME> --out <NEW_CASE>
.venv/bin/copyapp verify <NEW_CASE>
```

Hopper:

```sh
.venv/bin/copyapp hopper-function --file <MACHO> \
  --sha256 <SHA256> --address <0xFUNCTION_ENTRY> \
  --hopper-app '/Applications/Hopper Disassembler.app' --out <NEW_CASE>
.venv/bin/copyapp verify <NEW_CASE>
```

Use `ghidra-queue` / `hopper-queue` for verified candidates. Ghidra also supports bounded direct followers from a verified native queue and selected indirect-call investigation with Frida. Read repository `AGENTS.md` and the command's `--help` for those contracts. [Direct Hopper](rea-hopper-integration.md) documents GUI, timeout and failure requirements.

## Integration limits

There is currently no direct IDA Pro, Binary Ninja or radare2 provider or corresponding automatic evidence integration. A tool's own platform support does not establish Copy APP integration.

**REA is not a runtime dependency.** The old `rea-function`, `rea-queue` and `rea-bridge` commands were removed. Retained REA licenses attribute historical reference/adaptation; see [REA independence](rea-independence.md). Hopper's other upstream interfaces are not automatically integrated here: this project's direct adapter currently uses its Python scripting interface.

Pseudocode is generated interpretation, not original source. A temporal Frida hit alone does not prove that function caused a visible UI change. `copyapp verify` checks files, provenance and bindings; function semantics still need agent/human review.

## Implementation references

- CLI options: [`copyapp/cli.py`](../copyapp/cli.py)
- Decompiler adapters: [`ghidra_direct.py`](../copyapp/ghidra_direct.py), [`ghidra_queue.py`](../copyapp/ghidra_queue.py), [`hopper_direct.py`](../copyapp/hopper_direct.py), [`hopper_queue.py`](../copyapp/hopper_queue.py)
- Bounded assembly and indexes: [`native_disasm.py`](../copyapp/native_disasm.py), [`objc.py`](../copyapp/objc.py)
- Upstream information checked 2026-10-22; integration scope follows this repository's adapters and evidence.
