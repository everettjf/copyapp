---
name: copyapp-mac
description: Analyze or independently rebuild selected macOS App behavior with Copy APP and ChatComputer. Use for Mac App targets; existing iPhone workflows use copyapp-start instead.
---

# Copy APP for Mac targets

Read [Mac support](../../docs/macos-support.md) and the
[implementation ledger](../../docs/macos-implementation-plan.md) first. This is
development support alongside iOS. Check the commands available in this checkout;
do not describe unfinished acceptance gates as working features.

Use `.venv/bin/copyapp mac` from the repository root. Keep raw evidence in ignored
`cases/`, use a new output directory for each attempt and verify every case with
`.venv/bin/copyapp verify <case>`. Do not invent a USB UDID or use iOS case kinds,
IPAs, UIKit observations or iOS-only skills for a Mac target.

## Environment and evidence

- `mac doctor` checks transport and screenshots only. A verifiable `needs_setup`
  case still means setup is incomplete. Inspect the repairs before proceeding.
- For shared-file setup probes or ZIP/DMG input, read
  [the acquisition guide](../../docs/macos-acquisition.md). A Finder byte probe can
  run before control permissions, but cannot replace exact guest/collector identity.
  `mac import-app` preserves distribution provenance without executing its App.
- ChatComputer owns guest input and screenshots. Work in the current coding-agent
  session; do not start ChatComputer's model loop or another coding-agent CLI.
- Build/prepare the bounded collector, deploy it inside the intended guest and
  register the exact VM with `mac connect`. Follow the support guide for the shared
  payload and permissions. Do not read model credentials or guest pairing secrets.
- `mac inspect` snapshots a local native-arm64 `.app` without execution.
  `mac acquire` binds a guest package to its registered environment; use that
  acquisition for replay. A static index cannot substitute for guest provenance.
- `mac observe --ax` requires the exact foreground App/process. Review the saved
  structured AX and screenshot; MCP prose alone does not establish identity.

## Selected behavior analysis

For a request without preselected flows, first follow
[Mac discovery](../../docs/macos-discovery.md): observe and replay three to twelve
distinct representative flows, review known/deferred/blocked capabilities and
unknowns, then run `mac discover-check`. Read its `TASK.md` and continue semantic
review yourself; pass the accepted case to `mac report --discovery`. This gate
accepts evidence inputs and does not finish the report or prove whole-App coverage.

Observe the requested behavior and write bounded schema-v2 Mac playbooks. Use
`mac playbook` against the verified acquisition. Include explicit text, output-file
or stopped-process assertions; screenshots alone cannot support a behavior report.
Choose flows according to the user's scope and record unobserved behavior.

Use unique AX selectors; disambiguate windows explicitly. Truncated observations,
ambiguous matches and interrupted actions require inspection. A lost response does
not authorize repeating an input. Shared output folders do not roll back with VM
snapshots. Use the run-scoped `{{output_dir}}` for file assertions.

Read [the review contract](../../docs/macos-review.md) when writing the report.
Inspect all cited raw evidence, record observation versus inference, bind each
flow's saved script hash and inventory known capabilities. Run `mac report` and
verify it. This produces a behavior report/specification; it does not establish
native function semantics or whole-App completeness.

## Independent reconstruction

For a rebuild request, select the known capabilities supported by the reviewed
report and run `mac rebuild-plan` with a separate Bundle ID, separate guest `.app`
path and host project directory. Read and execute its `TASK.md` yourself.
Use the registered environment's `install_root` for the new App path, not a guessed
guest username or the host's home directory.

The plan freezes source links, target inventory and paired scripts. Its
`ready_for_current_agent` status proves input readiness only. Continue with
independent implementation, `mac build-app`, `mac install`, paired behavior checks
and screenshot review using the commands actually implemented in this checkout.
Build from the pinned project using an Xcode scheme or direct Swift `@main` sources;
verify its case before installation. An unknown installation result must be inspected
before any new attempt.

For paired acceptance, read [the check/delivery contract](../../docs/macos-checks.md).
Freeze measured UI settings and masks before fresh runs with `mac check-plan`, then
use `mac rebuild-check`. Each selected flow needs an exact initial text assertion
before its first input. Inspect all full image pairs in its generated review task,
fill explicit judgments and run `mac visual-review`. Review every frozen capability
before `mac delivery`; source changes, uncertain starting states and major visual
differences prevent accepted delivery. Disclose missing live acceptance evidence. Keep target coverage,
verified known coverage and selected-flow pass rate separate. VM evidence cannot
establish physical-Mac compatibility, and protocol tests cannot establish live UI
acceptance.
