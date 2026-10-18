# Pilot report inputs

[English](README.md) · [Documentation](../../docs/README.md)

These six JSON files are **historical, target-specific inputs** for the repository's pilot report-composition scripts. They are retained as runnable examples and format references, outside the current documentation tree. Their claims describe particular local test cases and must not be reused as facts about another device, app build or current run. The source evidence referenced by the scripts is stored under ignored local `cases/`; a fresh public checkout will not contain it.

For a new analysis, create a new `findings.json` and `feature-spec.json` from the target's verified evidence. The [analysis skill](../../skills/copyapp-analyze/SKILL.md) describes the source-binding and review requirements. Do not commit extracted binaries, screenshots, sandbox contents or credentials with examples.
