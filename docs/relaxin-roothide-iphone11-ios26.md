# iPhone 11 / iOS 26.0.1 device validation

This record covers one iPhone 11 (`iPhone12,1`, build `23A355`) running Relaxin 0.5.5 with RootHide. It does not establish compatibility with every iOS 26 device or jailbreak configuration. Evidence cases below are local and ignored by Git; they must be verified in the checkout where they were collected.

## Verified channels

| Channel | Result | Local case |
| --- | --- | --- |
| USB identity and screenshot | `onboard --stage survey` passed | `cases/ios26-onboard-survey-20261017` |
| OpenSSH over exact-device USB forwarding | Authenticated `mobile` key login returned the expected UDID; no password was stored | Device terminal authorization and authenticated SSH probe |
| iCTRL | Development-signed runner installed, authenticated pairing passed, and a real iGhostVT UI flow produced screenshot and accessibility evidence | `cases/ios26-ictrl-setup-v2-20261018`, `cases/ios26-ighostvt-open-20261018` |
| Frida sidecar setup | Isolated 17.23.3 RootHide server and agent staged; service inventory passed | `cases/ios26-frida-sidecar-setup-20261018` |
| Frida attach and view scan | Attached to the original Calculator process and captured a UIKit view tree; two selected UIKit methods were hooked but recorded zero calls during keypad taps | `cases/ios26-calculator-mcp-flow-20261018`, `cases/ios26-calculator-mcp-flow-send-event-20261018` |
| Calculator acquisition | `analyze --launch` acquired bundle metadata, dynamic libraries, Objective-C index, a UI screenshot and SSH sandbox index | `cases/ios26-calculator-analyze-20261018` |
| Original Calculator behavior | iCTRL replayed `7 + 8 =` on the original App; the saved final accessibility text is `15` and the case verifies | `cases/ios26-calculator-add-seven-eight-20261018` |
| RootHide package installation | Official ElleKit 1.2-1 installed through Sileo; Copy APP `com.copyapp.mcp` 0.1.4-5+debug installed through Fila after matching local and device SHA-256 | `cases/ios26-sileo-ellekit-confirm-20261018`, `cases/ios26-fila-mcp-confirm-20261018` |
| iOS MCP service | `sbreload` activated the installed tweak without a full reboot; USB-forwarded health, MCP initialization, foreground identity, UI tree and tap flow passed | `cases/ios26-calculator-mcp-tree2-20261018`, `cases/ios26-calculator-mcp-flow-20261018` |
| Reviewed analysis | Source-linked report and one-flow feature specification passed verification | `cases/ios26-calculator-reviewed-report-20261018` |
| Independent App and paired check | The tracked Calculator implementation was adapted to the observed iOS 26 layout, development-signed, installed, and replayed against the original. Both final screenshots passed a bounded OCR assertion for `15` | `cases/ios26-calculator-clone-v4-install-20261018`, `cases/ios26-calculator-rebuild-check-ictrl-v5-20261018` |
| Visual review | The final image pair passed review with **minor differences** in the top-right control, sign glyph and system return label; no major difference was recorded | `cases/ios26-calculator-visual-review-v5-20261018` |
| Calculator formal handoff | A new source-linked iCTRL flow with screenshot readiness completed the reviewed report → plan → task → paired check → visual review → agent delivery chain; the selected arithmetic assertion passed | `cases/ios26-calculator-source-flow-ready-v2-20261018`, `cases/ios26-calculator-source-linked-delivery-20261018` |
| Black-frame recovery | An Instruments fresh launch produced three saved black frames from `getScreenDataWithQuantity`. The CLI rejected them, returned Home, relaunched through iOS MCP, and saved a nonblack `7 + 8 = 15` screenshot with source and health metadata | `cases/ios26-calculator-mcp-black-recovery-20261018` |
| Second App: Clock | Package/sandbox/Objective-C analysis, selected native call tracing, reviewed report, independent signed App, paired Stopwatch Start → Stop → Reset and four reviewed screenshot pairs passed; all visual judgments were minor | `cases/ios26-clock-analyze-20261018`, `cases/ios26-clock-reviewed-report-20261018`, `cases/ios26-clock-agent-delivery-v3-20261018` |

The Calculator analysis case indexed 18 bundle paths, one extension, 52 dynamic libraries, 31 Objective-C classes and 19 methods. Its `analysis.md` is an acquisition index, **not** a reviewed deep report. The system command for checking `cryptid` was unavailable in this run, so this record makes no decryption claim. The default installation lookup did not expose the sandbox, while the authenticated SSH collection did index 27 sandbox paths.

## iCTRL transport detail

On this phone the XCUITest runner did not start through pymobiledevice3's native RSD transport. After mounting the personalized developer image, its userspace transport started the runner and exposed the iCTRL health endpoint. `copyapp setup ictrl` now mounts that image automatically for iOS 26 before starting XCTest, and the XCTest tunnel selects `--userspace`; iOS 16 and 17 retain their existing path. The runner's provisioning profile must include this exact device, or the user must build and sign another runner IPA.

## Tweak activation and screenshot recovery

`dpkg -l` reports `ii` for ElleKit, OpenSSH and Copy APP iOS MCP. Relaxin's visible SpringBoard restart did not activate the tweak (`cases/ios26-mcp-after-respring-probe-20261018`), but `/usr/bin/sbreload` from the authenticated mobile SSH session returned successfully. The subsequent named USB tunnel returned `copyapp-ios-mcp` health, MCP initialization and Calculator foreground identity. The service is therefore verified in the current jailbreak session without a full device reboot.

The iOS MCP screenshot command intermittently captured only the status bar over a black App area after its Instruments-driven fresh launch. Its accessibility observations and taps still worked. The CLI now checks the central screenshot pixels, saves rejected frames with SHA-256 and iOS MCP source metadata, then uses a bounded Home/relaunch recovery. In the Calculator recovery case, three identical black samples were rejected and the first recovery frame showed the App; the final `15` screenshot passed OCR. A completed playbook cannot verify with a black final MCP screenshot. The guard detects near-uniform black central frames; it cannot identify every possible malformed frame or prove long-term reliability.

The iOS 26 original uses SwiftUI-backed result text that is absent from the bounded UIKit `UILabel` scan. `rebuild-check` now supports an explicit `source: screenshot_ocr` final-view assertion. It binds the last saved screenshot hash, converts image pixels to the recorded screen-point geometry, and requires an exact text match inside the selected region. This check passed for both original and rebuilt screenshots.

The earlier formal report cited an original playbook without a `ready_contains` condition, so `rebuild-plan` correctly produced a verified `needs_verified_screenshot` handoff. A newly captured source-linked iCTRL flow now supplies screenshot readiness. The resulting Calculator plan, agent task, paired check, visual review and delivery all verify. This is a one-flow delivery adapted from existing independent source, not a fresh implementation of the entire App.

## Second-App Clock check

Clock required a first-use “Welcome to Clock” gate before its own screen appeared. The original Stopwatch flow produced four screenshots for Start, Stop and Reset. The matching binary and Objective-C index support direct selected call evidence: `MTAStopwatchController::_startStopButtonDown:` was hit during Start and Stop; `MTAStopwatchController::_lapControlButtonDown:` was hit during Reset. The saved assembly establishes these function addresses and branches but does not identify every downstream state transition. The reviewed report and feature specification restrict the build target to this selected Stopwatch path.

The independent [ClockIOS26 project](../rebuild/ClockIOS26) adapts earlier Clock source to the observed iOS 26 page and bottom navigation. It was built with Xcode, development-signed, installed on this iPhone 11 and compared against the original. All 13 steps in each paired playbook passed; four screenshot pairs were reviewed as minor differences, including dynamic elapsed time and system chrome. The [delivery case](../cases/ios26-clock-agent-delivery-v3-20261018/report.md) verifies 1/1 selected behavior. Other Clock tabs, alarms, timers, persistence and long-running background behavior were not part of this iOS 26 check.

An isolated bootstrap smoke in a temporary checkout on this same Mac created a new virtual environment, ran the survey and verified its case. The current host can use an Apple Development identity when `ldid` is absent, provided the selected provisioning profile covers the exact device. This smoke is not a clean second-Mac test. The [subsequent current-code two-phone run](ios16-ios26-current-code-validation.md) completed live XR/iOS 16 regression alongside this iOS 26 device. iPhone 14/iOS 17 was not connected for that run.

## Scope and remaining work

Calculator and Clock selected analysis-to-rebuild paths are verified on this one phone. Both independent implementations adapted existing source after reviewing their iOS 26 reports and screens. Their final visual reviews found minor differences; neither establishes pixel-level or whole-App equivalence. The Calculator UIKit method hooks have zero hits, and its internal SwiftUI/Calculate dispatch remains unidentified. Fresh live iOS 17 regression, a full reboot/rejailbreak persistence test, clean second-Mac setup, other iOS 26 devices and broader App coverage remain open.

Run `.venv/bin/copyapp verify <CASE>` for every case cited locally. An exact device and passing hashes establish provenance and integrity of saved evidence; they do not certify an interpretation or whole-App equivalence.
