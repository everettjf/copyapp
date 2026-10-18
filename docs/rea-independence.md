# REA independence

[English](rea-independence.md) · [简体中文](rea-independence.zh-CN.md) · [Architecture](architecture.md)

The supported Copy APP analysis and rebuild workflow runs without an REA process, package or MCP service. Its default native path indexes Mach-O metadata and bounded assembly; optional direct Ghidra and [direct Hopper](rea-hopper-integration.md) supply hash-bound pseudocode. Runtime tracing is provided by Frida. The old REA bridge entry points are no longer part of the CLI.

`--provider none` can collect UI, static indexes and runtime observations, but it does not generate new pseudocode. Select `ghidra-direct` or `hopper-direct` when function-level pseudocode is needed, then import verified evidence into `copyapp report`. A decompiler output still needs a human or coding agent to interpret the function, link it to an observed flow and state uncertainty.

The direct Hopper design was informed by MIT-licensed REA code and retains its [license](third-party/REA-LICENSE.txt). That attribution does not add REA as a runtime dependency. The remaining external prerequisites are the device-side services and whichever Mac toolchain is selected for a task. See [setup](setup.md) and [current status](current-status.md).
