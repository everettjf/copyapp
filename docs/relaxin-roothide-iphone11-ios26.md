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

The Calculator analysis case indexed 18 bundle paths, one extension, 52 dynamic libraries, 31 Objective-C classes and 19 methods. Its `analysis.md` is an acquisition index, **not** a reviewed deep report. The system command for checking `cryptid` was unavailable in this run, so this record makes no decryption claim. The default installation lookup did not expose the sandbox, while the authenticated SSH collection did index 27 sandbox paths.

## iCTRL transport detail

On this phone the XCUITest runner did not start through pymobiledevice3's native RSD transport. After mounting the personalized developer image, its userspace transport started the runner and exposed the iCTRL health endpoint. `copyapp setup ictrl` now mounts that image automatically for iOS 26 before starting XCTest, and the XCTest tunnel selects `--userspace`; iOS 16 and 17 retain their existing path. The runner's provisioning profile must include this exact device, or the user must build and sign another runner IPA.

## Tweak activation and screenshot limitation

`dpkg -l` reports `ii` for ElleKit, OpenSSH and Copy APP iOS MCP. Relaxin's visible SpringBoard restart did not activate the tweak (`cases/ios26-mcp-after-respring-probe-20261018`), but `/usr/bin/sbreload` from the authenticated mobile SSH session returned successfully. The subsequent named USB tunnel returned `copyapp-ios-mcp` health, MCP initialization and Calculator foreground identity. The service is therefore verified in the current jailbreak session without a full device reboot.

The iOS MCP screenshot command intermittently captured only the status bar over a black App area after its Instruments-driven fresh launch. Its accessibility observations and taps still worked; the same screen captured through the paired iCTRL runner or the USB developer screenshot service showed the Calculator UI. The verified paired delivery therefore uses iCTRL for both Apps. Do not infer that a black MCP screenshot is a real blank Calculator screen. The current implementation leaves iOS MCP screenshot recovery open rather than silently substituting another source.

The iOS 26 original uses SwiftUI-backed result text that is absent from the bounded UIKit `UILabel` scan. `rebuild-check` now supports an explicit `source: screenshot_ocr` final-view assertion. It binds the last saved screenshot hash, converts image pixels to the recorded screen-point geometry, and requires an exact text match inside the selected region. This check passed for both original and rebuilt screenshots.

## Scope and remaining work

The selected `7 + 8 = 15` analysis-to-rebuild path is verified on this one phone. The independent implementation began as an iOS 17 project; its new iOS 26 layout branch was adapted after reviewing the iOS 26 report and actual screen. This is report-guided adaptation of existing source, not generation of a new project from scratch. The final visual review found only minor differences in the selected screenshot pair; it does not establish pixel-level or whole-App equivalence. The saved UIKit method hooks have zero hits, and the internal SwiftUI/Calculate dispatch remains unidentified. A full reboot/rejailbreak persistence test, clean-Mac setup, other iOS 26 devices and broader App coverage are still open.

Run `.venv/bin/copyapp verify <CASE>` for every case cited locally. An exact device and passing hashes establish provenance and integrity of saved evidence; they do not certify an interpretation or whole-App equivalence.
