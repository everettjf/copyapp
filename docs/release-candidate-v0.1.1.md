# Copy APP next patch · release-note draft

[English](release-candidate-v0.1.1.md) · [简体中文](release-candidate-v0.1.1.zh-CN.md)

**Draft only.** The currently published version remains `v0.1.0`. See the [acceptance record](release-readiness-v0.1.1.md) before using this text for a release.

## Changes since v0.1.0

- iOS MCP playbooks detect near-uniform black App frames, retain rejected samples with source and hash metadata, and try a bounded Home/relaunch recovery after an Instruments fresh launch. A black final screenshot cannot pass the playbook. The iOS 26 Calculator and Clock runs exercised the recovery on a real phone.
- Exact-device SSH settings are saved locally only after a successful authenticated device probe. Later `doctor`, `onboard` and analysis commands can reuse the correct port, identity and pinned host-key file for each phone; explicit flags still override the saved route.
- Rebuild planning now identifies cited original flows that lack a stable screenshot and readiness text, returning a concrete recapture step before paired comparison.
- A second iOS 26 App, Clock, received a reviewed selected-flow report and an independent development-signed Stopwatch rebuild. Start → Stop → Reset passed the paired behavior check; four screenshot pairs were reviewed with minor differences. The project adapts earlier independent Clock code.
- A fresh hosted macOS job now installs the CLI and optional tracing tools, runs the unit suite, builds the wheel and checks it in an isolated installation. English and Chinese setup notes distinguish host installation from phone provisioning.
- A new checkout on the same physical Mac completed fresh SSH trust on both tested phones and an iOS 26 source build, development signing, USB installation and selected-flow replay. RootHide onboarding now withholds its deep-analysis ready result until the pinned Frida sidecar is configured.

## Tested scope and limits

Current-code checks on iPhone XR/iOS 16.1.1 and iPhone 11/iOS 26.0.1 passed device diagnostics, package/sandbox acquisition and the same original Clock Start → Stop UI script. A fresh XR fixture Counter `1 → 2` original/clone comparison and a state-aligned iOS 26 Clock Start → Stop → Reset original/clone comparison passed, with six screenshot pairs reviewed as minor differences. XR still reports `ConnectionTerminatedError` for optional DVT file listing, while its SSH package/sandbox path works. iOS 26 still sometimes paints black after Instruments launch; the bounded recovery succeeded in the observed runs. Existing iOS 17 evidence comes from earlier code and needs a live replay before this candidate is published. Another physical Mac has not yet completed phone provisioning. The selected flows and minor visual differences do not establish whole-App equivalence, arbitrary-App cloning or long-term reboot persistence. See the [device evidence](ios16-ios26-current-code-validation.md).

Raw IPAs, screenshots, sandbox contents and device keys remain local under ignored `cases/`; they are not release assets.
