# Setting a rebuild coverage target

[English](coverage-targets.md) · [简体中文](coverage-targets.zh-CN.md)

“Complete rebuild” is a goal to define for a specific App and device state, not a default claim. A small App may have a bounded, observable feature set that can be fully implemented and checked. A large App may need a first milestone covering 50–60% of its **known** capabilities. Set that target after reconnaissance, then report the achieved scope and every important gap.

## 1. Make a capability inventory after analysis

List user-visible capabilities and their important states, not classes, screens or lines of code. For example, “create a local note and find it after relaunch” is a capability; an editor screenshot alone is not. Include navigation, data persistence, permissions, offline/network behavior, extensions and account or payment paths when they are part of the App. Group related states so one action is not split into many trivial items. Link each item to observed evidence and mark unobserved or inaccessible states. The inventory is a *known-capability baseline*, never a proof that no hidden feature exists.

For each item record: stable ID, description and acceptance behavior, evidence basis, relative importance (1–5), feasibility/dependencies, and one of `selected`, `deferred`, or `blocked`. Explicitly list the unknown feature areas beside the inventory. Never silently remove a difficult known feature from the denominator.

## 2. Choose a milestone target

Select capabilities that form useful end-to-end journeys. Record the selected IDs, target device and App build, target date or iteration, and why each deferred/blocked item was left out. Prioritize critical paths and connected behavior before decorative breadth. The percentage is descriptive, not a substitute for the named acceptance list.

Use the declared importance weights consistently:

`target coverage = selected known-capability weight / total known-capability weight`

Do not call `3/3` tested flows “100% of the App.” That is only 100% of those three selected flows. If the inventory is too uncertain to support a denominator, state a **named-scope target** without an App percentage and continue discovery. For a large App, 50–60% is a possible negotiated milestone, not an automatic threshold or a guarantee. A small App can aim for 100% of its known inventory, with unknown states and test limits still disclosed.

Freeze the inventory and weights before implementation. When new evidence changes scope, create a new target with `--previous` and a `revision_reason`; both cases remain available. A revision can add capabilities or change scope, but it cannot remove or weaken an existing known capability or its weight. A changed analysis baseline requires a new report and target. Do not lower the target after a failed check merely to make the result appear complete.

`copyapp rebuild-plan --report <REPORT> --flow <ID> ... --out <PLAN>` selects 1–12 reviewed flows for one implementation task. A larger milestone needs multiple bounded plans/tasks/cases; `coverage-plan` accepts repeated `--plan` and `coverage-delivery` accepts repeated `--delivery` to aggregate them. One completed `copyapp copy` parent cannot certify all of a large App. Keep each selected capability linked to its task and checks.

## 3. Build in two passes and measure delivery

First make the selected journeys runnable with the right page structure and core interactions. Then deepen state transitions, persistence, permission states, network-backed outcomes and visual fidelity. For each selected capability, compare original and clone on the same device from equivalent starting states. Mark it `verified` only when its declared behavior and visual acceptance checks pass; otherwise use `partial`, `failed` or `untested` with evidence and a reason. A simulated server response must be labelled `simulated` and does not count as equivalent production behavior.

Report three distinct numbers, if a known-capability denominator exists:

- **Target coverage:** selected weight / known inventory weight.
- **Milestone completion:** verified selected weight / selected weight.
- **Verified known coverage:** verified selected weight / known inventory weight.

For example, if ten equally weighted capabilities are known, six are selected and five pass, report a 60% target, 5/6 milestone completion (83%), and 50% verified known coverage. Also report the 1 selected gap, 4 deferred items, unknown areas, major visual differences, and device/build limits. Do not count a capability merely because a screen renders or a script exits successfully.

`copyapp coverage-plan` now validates and freezes the submitted inventory against the report and selected rebuild plans. `coverage-delivery` calculates the three numbers from that inventory and one or more verified `agent-delivery` cases. A human reviewer must decide each capability result and describe the evidence. The CLI refuses `verified` when any mapped flow lacks a passing behavior assertion or a completed visual review without a major difference. Its hashes and arithmetic are machine checked; inventory completeness, weights and semantic equivalence remain reviewed judgments. The existing `feature-spec.json` and `agent-delivery` remain selected-flow evidence, not an App-wide score by themselves.

## CLI contract

Save an inventory JSON after the reviewed report and rebuild plan exist:

```json
{
  "schema_version": 1,
  "target_bundle_id": "com.example.original",
  "rebuilt_bundle_id": "com.example.clone",
  "rationale": "Start with local creation and search",
  "unknowns": ["Server-only states not observed"],
  "capabilities": [
    {"id": "create", "name": "Create item", "acceptance": "Create and display a local item", "basis": "Reviewed original flow", "weight": 3, "scope": "selected", "flow_ids": ["create"]},
    {"id": "sync", "name": "Account sync", "acceptance": "Sync across devices", "basis": "Visible account entry; not exercised", "weight": 2, "scope": "blocked", "flow_ids": [], "reason": "No test account"}
  ]
}
```

Every selected rebuild flow must belong to exactly one selected capability. Weights are integers 1–5. Deferred and blocked capabilities stay in the known denominator and need a reason. Keep acceptance narrow enough to match the mapped flow evidence; a screenshot cannot establish persistence or server equivalence.

```sh
copyapp coverage-plan --report <REPORT_CASE> --plan <REBUILD_PLAN_CASE> \
  --inventory <INVENTORY_JSON> --out <TARGET_CASE>
copyapp verify <TARGET_CASE>
```

To revise the same report baseline, add `revision_reason` to the new inventory and pass `--previous <OLD_TARGET_CASE>`; use a fresh output directory. After the real-device `agent-delivery`, provide one decision per inventory item:

```json
{"schema_version": 1, "capabilities": [
  {"id": "create", "result": "verified", "notes": "Paired behavior passed; minor icon difference recorded"},
  {"id": "sync", "result": "untested", "notes": "No test account"}
]}
```

`result` is `verified`, `partial`, `failed`, or `untested`; deferred/blocked items must remain `untested`. Then run:

```sh
copyapp coverage-delivery --plan <TARGET_CASE> --delivery <AGENT_DELIVERY_CASE> \
  --review <REVIEW_JSON> --out <COVERAGE_CASE>
copyapp verify <COVERAGE_CASE>
```

Use repeated `--plan` and `--delivery` for multiple bounded tasks. The target is met only when all selected weight is verified. The resulting report names every gap and unknown; a 100% milestone completion still refers only to the selected known capabilities.

## Case record template

| ID | Capability and acceptance behavior | Evidence | Weight | Scope | Result | Gap / reason |
| --- | --- | --- | ---: | --- | --- | --- |
| local-create | Create a local item; it survives relaunch | Original flow + local data observation | 5 | selected | verified / partial / failed / untested | State the exact difference |
| account-sync | Sync an account item across devices | unobserved | 5 | blocked | untested | Account/server access unavailable |

Below the table record the known inventory total, selected IDs, target revision, the three coverage numbers where justified, unknown areas and links to the exact original/clone checks. A major visual gap or untested backend behavior must remain visible in the final user-facing summary even when the milestone's other checks pass.
