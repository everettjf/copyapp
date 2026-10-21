# Mac paired replay and selected delivery

These commands are development support. They preserve the iOS workflow and v1
cases. Passing local/simulated protocol tests does not complete the live guest,
sample-app or physical-Mac gates in the [implementation ledger](macos-implementation-plan.md).

## Freeze conditions before replay

Start with a verified `mac install` case. Its source plan selects the reviewed
flows, separate App identity and exact registered environment. Every selected
original playbook must have an exact `expect_text` assertion before its first
keyboard/mouse input. An empty expected value is allowed for an exact blank-field
assertion; `contains` needs nonempty text. The reviewer owns whether this assertion
actually represents the stated starting condition.

Write conditions JSON before running either side. Copy `expected_ui` from a recent
collector health response's `result.ui_environment`, such as the source flow's
`session-health.json`. Use measured settings and an observed focused window frame,
not the sample values below. `flows` must list every selected ID in plan order.

```json
{
  "schema_version": 2,
  "platform": "macos",
  "reviewer": "current-agent",
  "expected_ui": {
    "schema_version": 1,
    "appearance": "light",
    "locale": "en_US",
    "preferred_languages": ["en-US"],
    "display_bounds": {"x": 0, "y": 0, "width": 1280, "height": 800},
    "display_pixels": {"width": 2560, "height": 1600},
    "backing_scale": 2
  },
  "network_expectation": "The selected local-document flow uses no network service.",
  "flows": [
    {
      "id": "edit-save",
      "starting_state": "A new blank document is focused, confirmed by the first text assertion.",
      "window_frame": {"x": 100, "y": 80, "width": 700, "height": 500},
      "input_data": "The literal text and run-scoped output path in the saved playbook.",
      "reset_policy": "Each completed flow closes its document; inspect state before a new attempt after any failure."
    }
  ],
  "masks": []
}
```

Appearance, locale, preferred languages, main display bounds/pixels and backing
scale are measured by the collector. The runner checks them at each flow's start
and end. The first launch's focused-window frame must match before further input.
Starting-state text assertions still need semantic review. Input/reset descriptions
and network expectations are declarations; the CLI does not silently reset App
data, change system preferences or enforce network isolation.

Optional masks are declared now, in screenshot pixels, with a reason:

```json
{"flow_id": "edit-save", "capture": "steps/01/after", "rect": [1190, 0, 90, 24], "reason": "Menu-bar clock"}
```

`capture` is a saved capture directory from the original flow. Masks must stay
within the captured image and cannot cover the whole screen, even as a union.
Masks affect metrics only. All full, unmasked screenshot pairs still require review.
Do not edit a frozen plan after observing a rebuilt screenshot; preserve it and
create a new reviewed attempt when conditions need to change.

```sh
.venv/bin/copyapp mac check-plan --install cases/mac-install \
  --conditions cases/mac-conditions.json --rounds 3 --out cases/mac-check-plan
.venv/bin/copyapp verify cases/mac-check-plan
.venv/bin/copyapp mac rebuild-check --plan cases/mac-check-plan --out cases/mac-check
.venv/bin/copyapp verify cases/mac-check
```

`check-plan` establishes input readiness only. `rebuild-check` first acquires the
installed rebuilt package and checks it against its source build. For each round
and selected flow it runs the original, then the rebuild, using fresh session/run
IDs and the exact frozen scripts. Package and environment identities are checked
again by each playbook. All runs must start after the condition plan was frozen.

No input or failed run is automatically repeated. Failed/partial child cases and
the active round/flow/side remain saved. Inspect the guest before creating a new
attempt. Shared output directories are outside VM snapshots and use fresh run IDs.
Snapshot recovery and clock behavior have separate acceptance gates.

`comparison.json` lists every behavior result and every screenshot pair. Dimensions,
unmasked pixel count, normalized mean absolute RGB error and changed-pixel fraction
are recomputed during verification. Images are never resized to hide a dimension
mismatch; comparisons are bounded to 16 megapixels per image. Metrics are not a
visual verdict or whole-App coverage.

## Review all full screenshot pairs

Read `cases/mac-check/VISUAL_REVIEW.md`, open both full images for every pair and
fill a copy of `visual-judgments-template.json`. Record:

- A self-declared reviewer name.
- Every pair's `verdict`: `equivalent`, `minor_difference` or `major_difference`;
  nonempty `notes`; and `reviewed_full_screens: true`.
- Every round/flow's initial state: `equivalent`, `different` or `unknown`, with
  notes based on the first launch and starting assertions.

Keep template order. Record visible differences even when pixel metrics are zero.
An inconclusive or adverse review is a valid observation; it cannot pass delivery.

```sh
.venv/bin/copyapp mac visual-review --check cases/mac-check \
  --judgments cases/mac-visual-judgments.json --out cases/mac-visual-review
.venv/bin/copyapp verify cases/mac-visual-review
```

The verifier binds every judgment to exact image hashes and review coverage. It
cannot certify the truth of subjective judgments.

## Review capabilities and deliver

Write one decision for every capability in the original report's frozen inventory,
in inventory order. A `verified` decision must be a planned target and cite all
that capability's selected flow IDs in sorted order. `deferred` and `blocked`
decisions retain a reason and an empty accepted-evidence list. Unknown behavior
remains in the source report; it is not silently removed from the delivery.

```json
{
  "schema_version": 2,
  "platform": "macos",
  "reviewer": "current-agent",
  "capabilities": [
    {"id": "editing", "decision": "verified", "evidence_flow_ids": ["edit-save"], "reason": "The selected editing assertions and full visual review passed."},
    {"id": "printing", "decision": "deferred", "evidence_flow_ids": [], "reason": "Printing was outside the selected target."}
  ]
}
```

```sh
.venv/bin/copyapp mac delivery --visual-review cases/mac-visual-review \
  --coverage cases/mac-capability-review.json --out cases/mac-delivery
.venv/bin/copyapp verify cases/mac-delivery
```

Delivery requires the current project to match the built source, every target
capability to have a verified decision, all selected behavior assertions to pass,
all screenshot pairs to be reviewed, matching image dimensions, equivalent starting
states and no major visual difference. Minor differences remain explicit.

The standalone case preserves source/build/install/check/review provenance and
writes `delivery.md` and `delivery.json`. Later edits to the working project do not
rewrite this historical source snapshot. The report separates target known coverage,
verified known coverage and selected-flow pass rate, discloses omitted flows and
unknowns, and keeps `whole_app_parity: false` and `physical_mac_verified: false`.
It proves neither physical-Mac compatibility nor native function interpretation.
