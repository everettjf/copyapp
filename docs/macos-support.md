# macOS development support

[简体中文](macos-support.zh-CN.md) · [Implementation ledger](macos-implementation-plan.md)

macOS is being added **alongside** the published iOS workflows. Existing iOS
commands and v1 cases keep their original meaning. This branch currently supplies
collection, bounded replay and reviewed report/planning commands; it does not yet certify an end-to-end
Mac reconstruction. Do not use an iOS UDID or IPA case to represent a Mac.

ChatComputer owns the virtual desktop and all keyboard/mouse input. The current
coding agent does analysis and implementation; do not start ChatComputer's built-in
model loop or nest another coding-agent CLI. Its external MCP currently returns
text/images. Copy APP's bounded guest collector adds structured app identity and AX
observations without depending on a future upstream shell API.

For a pre-control shared-file probe or ZIP/DMG input, read
[shared files and distribution import](macos-acquisition.md). These commands keep
their byte/structure scope separate from runtime identity and UI acceptance.
The same guide describes `mac data-file` for a selected guest data file, including
path association limits and the lack of atomic database or complete-data coverage.
`mac data-schema` extracts bounded plist/SQLite structure for source-linked
`mac report --data` citations, with values/rows omitted from generated structure.

For requests without preselected flows, follow
[representative flow discovery](macos-discovery.md) before writing the formal
report. `mac discover-check` accepts reviewed replay inputs; `mac report --discovery`
retains their source identity and discovered known-capability IDs.

## Start with an agent

Open this development checkout in Codex or Claude Code and paste:

```text
Analyze the macOS App “APP NAME” using this Copy APP checkout and ChatComputer.
Read AGENTS.md and skills/copyapp-mac/SKILL.md first. Identify the exact guest,
App and build, collect representative flows and produce a cited behavior report.
Keep existing iOS support intact. Use the current agent session for review and
implementation, and report the actual acceptance scope and unfinished gates.
```

For an independent rebuild, add the desired behavior and ask the agent to continue
through a reviewed rebuild plan, implementation, paired replay and delivery.
The development commands have local/simulated protocol tests; live guest and
physical-Mac acceptance remain open. See the ledger before treating a prepared
task or passing protocol check as a completed App.

For bounded snapshot metadata, safety-preserving restore and interrupted-operation
handling, read [Mac recovery](macos-recovery.md). A metadata/reconnect case does not
prove restored App behavior; upstream snapshots have only a preflight takeover
guard in this integration, not an atomic expected-lease condition.

The [owned AppKit fixture](../examples/macos/BehaviorFixture/README.md) is available
for acceptance development. It is an original sample; its host smoke checks do not
substitute for guest discovery, independent reconstruction or paired delivery.

## Check the environment

Use an Apple Silicon Mac with the installed ChatComputer application. Finish its
guest onboarding in the GUI, then use the CLI from this checkout:

```sh
.venv/bin/copyapp mac doctor --out cases/mac-transport
.venv/bin/copyapp verify cases/mac-transport
```

A `needs_setup` doctor case is verifiable evidence of missing prerequisites. A
successful doctor establishes transport and screenshot availability only; it does
not identify an app, validate runtime tracing or prove behavior. `--data-dir`
selects a non-default ChatComputer data directory explicitly.

On the named ChatComputer 0.9.11 build, saving the initial snapshot changes the
VM stage to `ready`, while the first-run window still shows model configuration.
Normally quitting and reopening ChatComputer then exposes the ready desktop to
external MCP without configuring its built-in model. This was observed with the
named development VM; verify your actual transport with `doctor` after reopening.
Keep the existing guest credential in ChatComputer's own local storage. It is not
an input to Copy APP cases, reports or GitHub artifacts.

## Build and prepare the collector

```sh
.venv/bin/copyapp mac build-collector --out cases/mac-collector-build
.venv/bin/copyapp verify cases/mac-collector-build
.venv/bin/copyapp mac prepare-collector --build cases/mac-collector-build \
  --out cases/mac-collector-deployment --request-accessibility
.venv/bin/copyapp verify cases/mac-collector-deployment
chatcomputer share add "$PWD/cases/mac-collector-deployment/payload"
```

Share only this deployment payload, read-only. Use the guest path printed by
ChatComputer, open that folder in the **guest** Finder and run
`Start Collector.command`. It installs the exact hashed helper in the guest's
`~/Applications/CopyAppTools/<hash>/`. The launcher checks that it is inside a
virtual Mac and that the ChatComputer share exists. It does not modify the host.

`--request-accessibility` makes the helper ask macOS for Accessibility access in
the guest. The guest owner grants it through System Settings; no permission is
granted automatically. ChatComputer separately needs its normal guest capture and
control permissions. A local collector build/self-test requests neither permission.

The default collector signature is ad-hoc. For repeatable TCC identity, use a
suitable stable `--signing-identity` and retain the exact build; changing the
signature can require a new guest permission grant. A successful build is not a
notarized distribution or proof of installation.

### Probe the collector without requesting UI permissions

For an explicitly limited setup probe, omit `--request-accessibility` when preparing
the collector. Copy only that verified deployment into a fresh directory in the
VM's existing shared inbox, then open its `payload/Start Collector.command` in the
guest Finder. This starts the bounded helper without invoking its permission prompt;
it does not grant or bypass ChatComputer/collector capture or Accessibility access.
Verify the published deployment again before running it. The launcher and its
permission-request flag are checked against the exact verified build.

```sh
.venv/bin/copyapp mac probe-collector \
  --vm-directory "$HOME/.chatcomputer/ChatComputer.vm" \
  --collector-build cases/mac-collector-build --out cases/mac-collector-probe
.venv/bin/copyapp verify cases/mac-collector-probe
```

The probe uses two fresh health requests, binding their request hashes, session,
instance, executable build and first guest identity observed on this shared root.
It pins the public VM files and actual guest OS; it does not assume the guest has
the host's OS build. Its complete scope is `shared_collector_identity_probe`.
`chatcomputer_transport_verified`, `desktop_control_verified`, `app_behavior_verified`
and `complete_environment_acceptance` remain false. A failed read is retained and
not retried. This pre-control observation cannot be substituted for a ready
`mac connect` environment or passed directly to replay/report/delivery.

The named live probe at `cases/macos-p0-20261021/collector-identity-probe-1`
verified the actual guest on macOS 27.0.1 (26A434), while the upstream GUI remained
at setup step 4 and collector Accessibility was false. No permission request or
grant was made. See the implementation ledger for the remaining live gates.

## Register one exact VM

```sh
.venv/bin/copyapp mac connect \
  --vm-directory "$HOME/.chatcomputer/ChatComputer.vm" \
  --collector-build cases/mac-collector-build --out cases/mac-environment
.venv/bin/copyapp verify cases/mac-environment
```

Registration pins VM ID and machine/hardware identifier hashes, test configuration,
ChatComputer executable identity, collector executable hash, guest identity and OS.
It also saves the exact MCP initialization envelope and the server's self-reported
identity separately from the installed App's version. In the named 0.9.11 runs,
doctor through the CLI alias reported MCP version `0`, while registration using
the resolved App executable reported `0.9.11`. Reconnect checks the saved server
identity rather than deriving it from the App version.
It copies no password, model credential or pairing token. Reconnect checks these
identities again. A changed app/tool/OS needs a reviewed new registration, not a
silent rewrite of old evidence.

The helper bridge uses unique session and request IDs, a request hash and an
exclusive host session. Interrupted launch requests retain an outbox start marker
and are never blindly re-executed. Shared outbox files are outside VM snapshots:
old files must not be accepted as fresh results after restore.

## Collect static and UI evidence

```sh
.venv/bin/copyapp mac inspect --app /path/to/Example.app --out cases/mac-package
.venv/bin/copyapp verify cases/mac-package
.venv/bin/copyapp mac observe --environment cases/mac-environment \
  --app-path /Applications/Example.app --bundle example.app \
  --out cases/mac-app-identity
.venv/bin/copyapp mac observe --environment cases/mac-environment \
  --app-path /Applications/Example.app --bundle example.app --ax \
  --out cases/mac-ui-observation
.venv/bin/copyapp verify cases/mac-ui-observation
```

`inspect` snapshots a local `.app`, inventories regular files and safe internal
symlinks, and distinguishes the whole executable hash from its arm64 slice hash.
It accepts arm64 Mach-O platform 1 (macOS) or 6 (Mac Catalyst), rejecting iOS,
iOS Simulator, conflicting platform declarations and Intel-only binaries. Catalyst
indices explicitly record `macho_platform: 6` and `runtime: mac_catalyst`; accepting
their package does not establish UI replay compatibility. It
copies package bytes and permissions without propagating protected system flags.
Its scope is **static package only**, never guest installation or execution.

`observe --ax` requires one exact foreground process with a known launch time. It
records bounded AX structure, raw MCP screenshot and before/after app identity.
AX and screenshot are sequential observations, not simultaneous captures. Truncated
trees and unavailable permissions remain explicit. These inputs still require
semantic review and do not establish function implementation or whole-app coverage.

## Replay and review selected behavior

```sh
.venv/bin/copyapp mac acquire --environment cases/mac-environment \
  --app-path /Applications/Example.app --bundle example.app \
  --out cases/mac-acquisition
.venv/bin/copyapp verify cases/mac-acquisition
.venv/bin/copyapp mac playbook --acquisition cases/mac-acquisition \
  --script cases/mac-flow.json --out cases/mac-flow
.venv/bin/copyapp verify cases/mac-flow
```

Acquisition exports a bounded package snapshot through the collector and compares
the complete guest/source/copy inventories. Replay pins that package before and
after the flow. A minimal script is:

```json
{
  "schema_version": 2,
  "platform": "macos",
  "scenario_id": "visible-editor",
  "bundle_id": "example.app",
  "app_path": "/Applications/Example.app",
  "steps": [
    {"action": "launch"},
    {"action": "expect_text", "selector": {"identifier": "editor"}, "text": "Expected text"}
  ]
}
```

Replace selectors and expectations with observations of the actual App. Supported
actions are launch, screenshot, click, click_element, key, type, scroll, drag, quit,
expect_text, expect_file, expect_stopped and wait. Input is bounded and follows an
exact foreground AX/screenshot capture; element matches must be unique. Selectors
can use exact `title`, `description`, `identifier` or `role`, optionally within a
named `window`. Catalyst often exposes visible labels through `description`. Text and
file assertions are exact unless a text assertion explicitly uses `match: contains`.
File assertions use run-relative paths and one of `text_equals`, `json_equals` or
`sha256`; substitute `{{output_dir}}` in typed text for the unique guest output
directory. Changing or linked output files are rejected. A failed action is retained
and never automatically repeated; inspect state before starting a new case.

Read the raw UI/output evidence, then follow the [review JSON contract](macos-review.md)
to run `mac report` and `mac rebuild-plan`. The report binds findings and a feature
specification to source cases. The plan freezes known capabilities, target coverage
and original/clone playbooks and writes `TASK.md` for the current agent. Neither
command proves implementation or delivery, and neither performs deep code analysis.

## Remaining acceptance

Live guest replay, sandbox/data acquisition, discovery acceptance, real-sample
builds and guest install/launch, live paired checks, actual visual review and delivery acceptance remain open. Two sample apps,
three selected flows each and three rounds are required, plus one physical Mac
recheck. Runtime/native investigation is a separate capability with entitlement
limits. Keep these gates open until their actual saved evidence passes.

## Build and install an independent App

The rebuild plan's App path must be directly inside the registered guest's
`install_root`, recorded in `environment.json`. The default collector root is the
guest's `~/Applications/CopyAppRebuilds`; it is separate from the original App.
Prepare a new plan if an earlier target path points elsewhere.

Implement the source inside the host project directory pinned by that plan, then
choose one build mode:

```sh
# An Xcode project already configured for the independent Bundle ID and product.
.venv/bin/copyapp mac build-app --plan cases/mac-rebuild-plan \
  --xcode-project IndependentEditor.xcodeproj --scheme IndependentEditor \
  --configuration Debug --out cases/mac-build

# Or direct Swift files with an @main entry point and source Info.plist.
.venv/bin/copyapp mac build-app --plan cases/mac-rebuild-plan \
  --swift-source Main.swift --info-plist Info.plist \
  --resources Resources --out cases/mac-build-swift
.venv/bin/copyapp verify cases/mac-build
.venv/bin/copyapp mac install --build cases/mac-build --out cases/mac-install
.venv/bin/copyapp verify cases/mac-install
```

Paths in the build recipe are project-relative. Repeat `--swift-source` for several
files; omit `--resources` when absent. Direct Swift builds use Swift 5 language mode,
`@main`, native arm64 and macOS 14.0 by default, with Debug or Release optimization.
Set `--deployment-target` for a different Swift minimum; Xcode reads its deployment
target and entitlements from the project. Signing defaults to ad-hoc (`-`); use
`--signing-identity` when a suitable stable identity is available.

The build case preserves the plan, a source snapshot, compiler/signing identity,
SDK metadata, complete bounded command logs and the indexed signed `.app`. It
builds from its snapshot and rejects source rewrites; Xcode's new empty workspace
metadata directories are recorded separately. `.git`, `.build`, `DerivedData`,
`__pycache__` and `.DS_Store` are excluded only at the project root. Keep the build
case outside that source directory. This is source provenance and a local build,
not notarization, installation or behavioral acceptance.

Installation uses the build's original registered environment, stages the verified
package under its fresh inbox session, verifies the guest copy's signature and
inventories, then atomically creates the new target path without replacement. It
does not launch the App. A start marker prevents replay of interrupted installs;
failed attempts and replies remain recorded. After an unknown result, inspect the
guest and saved evidence instead of rerunning installation. A successful install
still needs an acquired rebuilt package, paired flow replay and visual review.

## Compare and deliver selected behavior

Follow [paired replay and delivery](macos-checks.md) to freeze measured UI conditions
and masks with `mac check-plan`, run fresh pairs with `mac rebuild-check`, review
every full screenshot through `mac visual-review`, then bind capability decisions
and the current source with `mac delivery`. The check produces a review task and
judgment template. It never retries a failed input automatically.

These commands verify source links and explicit gates. They do not certify a
reviewer's interpretation, whole-App parity or physical-Mac behavior. Actual
ChatComputer/sample acceptance is still required by the implementation ledger.
