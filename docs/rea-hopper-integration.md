# Direct Hopper integration

[English](rea-hopper-integration.md) · [简体中文](rea-hopper-integration.zh-CN.md) · [Architecture](architecture.md)

Copy APP calls a locally installed Hopper application directly; **REA is not required at runtime**. The old `rea-function`, `rea-queue` and `rea-bridge` entry points were removed. A Hopper license and a normal logged-in macOS GUI session are required for new Hopper analysis.

## Evidence path

1. Acquire or recover the target Mach-O and pin its original SHA-256. Select and separately hash the ARM64 slice of a fat binary. Reject an encrypted binary until an analysis copy is recovered.
2. `hopper-function` launches Hopper with a bounded Python script that resolves one requested function entry and asks its `Document`/`Procedure` APIs for pseudocode.
3. Save the launcher script and log, source identity, selected address, result and hashes. The verifier checks the original bytes, slice and address binding.
4. `hopper-queue` selects a limited set of addresses from a verified candidate case. `--provider hopper-direct` passes those results through investigation, report and agent handoff; the parent `copy` command uses `--analysis-provider hopper-direct`.

```sh
.venv/bin/copyapp hopper-function --file <MACHO> \
  --sha256 <ORIGINAL_SHA256> --address 0xADDRESS --out cases/<FUNCTION>
.venv/bin/copyapp hopper-queue --candidates cases/<CANDIDATES> \
  --limit 4 --out cases/<QUEUE>
.venv/bin/copyapp investigate-flow --udid <UDID> \
  --analysis cases/<ANALYSIS> --script playbooks/<FLOW>.json \
  --provider hopper-direct --out cases/<INVESTIGATION>
```

Use `--hopper-app '/Applications/Hopper Disassembler.app'` or `HOPPER_APP` when automatic discovery fails. A constrained shell may report `Cannot launch Hopper!` even when a normal GUI session succeeds. The direct function/queue target has a 600-second default timeout; inspect the saved failure log instead of treating partial pseudocode as complete.

Pseudocode is an analysis result, not original source or proof that a UI action executed that function. Pair it with hash-bound static candidates and, where useful, a separately verified Frida trace. Direct Ghidra remains available for bounded caller/callee and instruction facts, including selected indirect-call investigation. The Hopper adapter design was informed by MIT-licensed REA code; its license is retained at [REA-LICENSE.txt](third-party/REA-LICENSE.txt). Copy APP's script, queue and verifier are maintained here.
