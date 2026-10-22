# Bounded reconstruction quality

The v0.2.0-beta.1 preview adds a reviewed **grade target**, default **80/100**, and
**three implementation/check cycles including the first**. Use 70 for a quick
prototype or 90 for closer detail. This does not measure objective image similarity
or the proportion of an App's known capabilities. Keep coverage and selected-flow
pass rate separate.

The current agent freezes the target after the reviewed report and implementation
task exist, then implements the selected scope directly. Do not keep polishing
after `target_met`. At `iteration_limit`, stop and deliver current runnable artifacts
and remaining gaps as incomplete. Failed build/install/comparison attempts also
consume cycles; inspect uncertain device state before any new operation.

```sh
# TASK is an iOS agent-task case or a Mac rebuild-plan case.
.venv/bin/copyapp fidelity-plan --task <TASK> --out cases/quality-plan
# Optional: --fidelity 70|80|90 --max-iterations 3
.venv/bin/copyapp verify cases/quality-plan
```

Read its `TASK.md`. Build, install, compare selected flows and review all saved
screenshots using the existing platform commands. For Mac, `--evidence` below is
the verified `mac visual-review` case. For iOS it is the verified `agent-delivery`
case with a complete `visual-review`, including any recorded visual gap.
For a bounded Mac prototype, one paired repetition (`mac check-plan --rounds 1`)
usually provides the initial selected-flow check; repeat only for observed
instability or an explicit reliability requirement. The separate release plan's
three-round acceptance remains a release gate, not three mandatory polishing cycles.

```sh
.venv/bin/copyapp fidelity-template --plan cases/quality-plan \
  --evidence <EVIDENCE> --out cases/quality-review.json
# Review and fill the JSON; do not use generated scores or hide differences.
.venv/bin/copyapp fidelity-check --plan cases/quality-plan \
  --evidence <EVIDENCE> --review cases/quality-review.json \
  --out cases/quality-cycle-1
.venv/bin/copyapp verify cases/quality-cycle-1
```

The score is behavior **40%**, layout **40%**, details **20%**. Behavior receives
100 only when all selected flow assertions pass. Layout and details receive explicit
integer reviewer grades with concrete notes and saved image IDs. For example,
behavior 100, layout 80 and details 45 gives **81/100**. It may meet an 80 target
while visibly differing. Reviewer judgments are subjective; verification checks
their source chain, coverage, arithmetic and stopping decision, not their truth.

Every visual difference must retain its original verdict and an explicit blocking
or non-blocking impact with a reason. A major visible content substitution may be
non-blocking for an offline prototype, but cannot disappear from the report.
Wrong source/install identity, incomplete review, uncertain Mac starting state,
image dimension mismatch and failed core assertions prevent target achievement at
every setting. A 100 target additionally requires no recorded image differences.

`fidelity-check.json` and `report.md` record one of:

- `target_met`: the reviewed selected scope meets the grade target; stop polishing.
- `continue`: a further implementation/check cycle remains.
- `iteration_limit`: the target was not met within the budget; stop and disclose gaps.

The command exits 0, 2 or 3 respectively. All three outcomes can form valid
verifiable evidence; only exit 0 means the grade target was met. `copyapp verify`
checks case consistency and does not turn an incomplete result into success.

Only after `continue`, use a new evidence case and `--previous cases/quality-cycle-1`
for the next cycle. Regrading identical evidence cannot consume another cycle.
New Mac builds may use fresh install paths, preserving the same report, source
project, Bundle ID and selected scope. A changed target/scope needs a new plan.
Keep the earlier chain. This counts submitted cycles, not hidden work or a global
wall-clock budget; the agent must also follow the bound while diagnosing failures.

A failed `mac_build`, `mac_install`, `mac_rebuild_check` or iOS `rebuild_check` case
can be submitted as evidence to consume a failed cycle. It receives zero behavior
and visual points, with no verified execution claim. Its grade review must use
zero layout/details and empty image/difference lists. Other incomplete artifacts
remain unsupported. Do not invent a passing visual review for a failed run.

These cases reference retained source cases by absolute path and manifest hash;
keep all those ignored local cases. Creation requires current source to match the
paired build/delivery. Later verification checks saved source evidence, allowing
subsequent implementation changes without rewriting history.

This is the default bounded path for agent-led tasks in this preview.
Historical `mac delivery`, standalone `copy` and `agent-run --verify-rebuild` keep
their strict acceptance rules; a fidelity milestone does not turn an incomplete
strict parent into success. Use stages directly for a bounded current-agent task.
Release, physical-device and capability-coverage gates remain separate. This is
not part of the older stable iOS v0.1.2 release.

## 中文要点

默认 `--fidelity 80 --max-iterations 3`；70 为快速原型，90 为精细档。三轮包含首轮，
与同一版本重复重放三次不同。分数来自选定范围的审阅：行为 40%、布局 40%、细节 20%。
核心流程必须通过，所有截图仍须看过；字体、间距、动画或明确说明的示例内容差异可以记录为
非阻断差异，不再因为存在任何明显视觉差异而无限修正。

先对 iOS `agent-task` 或 Mac `rebuild-plan` 创建 `fidelity-plan`，再使用本平台原有构建、
安装、配对和逐图审阅命令。通过 `fidelity-template` 生成引用准确图片的评分 JSON，人工／
当前 Agent 审阅填写后运行 `fidelity-check`。达标就停止；未达标且轮数耗尽则交付当前可运行
版本、明确标注未达标和剩余问题。下一轮必须引用 `--previous`，失败的构建／安装／对照
也应计入轮数。旧严格交付及其父工作流不会因此被改成通过。

“81 分达到 80 档”不等于“客观相似度 81%”，也不是“整 App 覆盖率 81%”。已知能力的分母、
已验证覆盖、真机／虚拟机范围和所有可见差异继续单独报告。调整目标应新建计划，保留旧记录。
