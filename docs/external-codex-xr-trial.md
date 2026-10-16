# Independent Codex CLI trial on iPhone XR

**Language:** English | [简体中文](external-codex-xr-trial.zh-CN.md)

On 2026-10-16, a standalone `codex exec` process completed both Copy APP handoffs for the installed Calculator on a jailbroken iPhone XR (iOS 16.1.1). The local case is `cases/calculator-external-codex-20261016/`; `cases/` is ignored by Git and is not part of a fresh clone.

The analysis stage produced a source-linked report and passed `analysis-delivery`. The rebuild stage produced `rebuild/CalculatorExternalAgent`, built an IPA, installed it on the XR and launched it. Three paired original/clone flows passed their scripted assertions: decimal addition, negative addition and percent of fifty. All three screenshot pairs were reviewed as minor differences; no major difference was recorded. The run-bound delivery and top-level `copyapp copy --resume` case both verified.

This is a selected-flow test. The CLI used previously verified discovery scripts, and its implementation adapted an earlier independent Calculator clone. The report also reused matching-binary Ghidra evidence collected earlier and discloses its timestamps. This trial establishes independent CLI orchestration and real-device delivery, not autonomous discovery, a fresh implementation of an unfamiliar app, or complete Calculator equivalence. iOS 17 and 26 were outside the test.

One integration issue surfaced: the CLI created an unbound `agent-delivery` draft even though Copy APP creates a run-bound delivery after the process exits. The draft was preserved at `rebuild-agent/agent-delivery-agent-draft`; the run-bound delivery was then generated and verified. The prompt and finalizer now handle this case.
