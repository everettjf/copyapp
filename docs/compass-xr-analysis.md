# Compass on iPhone XR: analysis case

Target: `com.apple.compass` 1.0.0 (build 1.0), iPhone XR (`iPhone11,8`), iOS 16.1.1. Collected 2026-10-15 UTC. This document distinguishes device observation, binary evidence, and inference. The raw case is local under `cases/compass-xr-main-20261014/` and `cases/compass-xr-acquired-20261014/`; those directories are ignored by Git because the screenshot and UI tree include the device's location.

## Evidence and integrity

| ID | Evidence | What it establishes |
| --- | --- | --- |
| E1 | `cases/compass-xr-main-20261014/manifest.json` and `app.json` | Device, installed bundle identity, declared permissions, and hashes for the initial UI evidence. |
| E2 | `cases/compass-xr-main-20261014/screenshot.png` and `ui.json` | A single Compass foreground screen with four accessible elements; the screenshot contains private location data. |
| E3 | `cases/compass-xr-acquired-20261014/acquisition.json` | Read-only USB SSH bundle export: 55 files, per-file hashes, and snapshot IPA SHA-256 `d3026452aa73a459c9c95a5594cc98df207d015bd89fe6dca5fc634fb6847dc5`. |
| E4 | `cases/compass-xr-acquired-20261014/static/ipa-index.json` | Mach-O load commands, dependencies, bundle structure, and executable SHA-256 `469bfd16314c225902ff56c5f33b9a20be1909b357a07a3b387b8c8878c155b1`. |
| E5 | `cases/compass-xr-acquired-20261014/sandbox-index.json` | Read-only data-container metadata index, depth 8; 24 entries, no file bodies. |
| E6 | Ghidra 12.1.4 REA session on the E4 executable, evidence IDs listed below | Class/method names, addresses, and decompiler pseudocode. Its output is not original source code. |
| E7 | `cases/compass-xr-acquired-20261014/static/objc-index.json` | Automated Objective-C metadata index from the exact E4 executable: 11 locally defined classes and 137 instance/class methods with selectors, type encodings, and static implementation addresses. |
| E8 | `cases/compass-xr-frida-attach-20261014.json` | A bounded Frida attach attempt against the original Compass process timed out before hooks were installed. It provides no method-call evidence. The same trace collector successfully attached to the independently built Copy Compass process. |
| E9 | `cases/compass-xr-mcp-onepass-20261015/` and `cases/ios-mcp-compass-locked-20261015.jpg` | iOS MCP confirmed `com.apple.compass` foreground before and after capture; a screen tap produced the original bearing-lock state. The one-pass case passed hash verification. |
| E10 | `cases/experiment-original-bearing-chain-20261015/experiment.json`, `before.jpg`, `after.jpg` | One autonomous tap on the original Compass dial with Frida hooks active: `tappedCompass:`, `setBearing`, and `updateLayer` were each called once; `updateDisplay:` was called 189 times during a 3.129-second window. The target bundle was foreground before and after. The screenshots show a bearing-state change. Counts alone do not establish call order. |
| E11 | `cases/experiment-original-maps-retry-20261015/experiment.json`, `before.jpg`, `after.jpg` | One autonomous coordinate tap on original Compass recorded one `_openMaps` call and then `com.apple.Maps` became foreground. Frida cleanup timed out after the handoff; the complete observation was saved before cleanup. |

`copyapp verify cases/compass-xr-main-20261014` checks E1/E2 hashes. E3 records the hashes for the acquired bundle. The IPA is a repacked **analysis snapshot**, not an original downloadable or installable IPA.

## Identity, permissions, and package

The Info.plist declares a UIKit app with main storyboard `Compass`, launch storyboard `Launch`, portrait orientation, minimum iOS 16.1, and a When-In-Use location usage string. The installed app is a platform/system application with container-required entitlement (E1, E3). These entitlements are an Apple system-app property and are not available to an ordinary rebuilt app.

The arm64e main executable has no `LC_ENCRYPTION_INFO` command. This is **not** a result of Copy APP decrypting it, and it does not establish the encryption status of other App Store apps (E4). The bundle contains no embedded third-party Framework or app extension. The binary links 17 images: public frameworks including UIKit, Foundation, CoreLocation, CoreMotion, QuartzCore and ARKit, plus Apple private CompassUI, GeoServices, GraphicsServices and Navigation; it also links WebKit, CoreText, CoreGraphics, CoreFoundation, libobjc, libSystem and libMobileGestalt (E4). A linked image is evidence of a dependency, not proof that a particular feature executes its code.

## Observed interface and implementation

The one observed page uses a black full-screen background; a radial dial with cardinal marks, tick marks and central crosshair; a large heading value and direction; and a lower stack showing coordinates, a place label and elevation. The accessibility tree exposes a coordinate button whose action opens Maps, plus place/elevation/heading text (E2). The screenshot and tree capture only one state. No second page or settings screen was observed.

The compiled storyboard names `CompassController` as an entry controller. Decompiler evidence for `CompassPageViewController::viewDidLoad` at `0x100004538` indicates that the page creates `CompassView`, label containers and `CompassCopyableLabel` instances programmatically, then registers gestures associated with Maps and calibration. The storyboard is thus an entry/scene scaffold while much of the visible composition is built in code (E3, E6 `ev_1b22726dedab5efe88c852e60c09cdd7f71aa0e40ab87743df0b6f1aaa16305e`). Exact Auto Layout constraints and asset-to-view mapping still need runtime inspection.

The executable defines 11 Objective-C classes in `__objc_classlist`: `CompassTestOptions`, `CompassView`, `CompassBearingView`, `CompassTriangleView`, `CompassCopyableLabel`, `CompassController`, `CompassAppDelegate`, `CompassMotionManager`, `CompassPageViewController`, `CompassLabelsView`, and `CompassTestDeviceMotion` (E4/E7, checked with `otool -ov`). The new automated index records 137 methods and agrees with the Ghidra addresses for selected methods including `tappedCompass:`, `startLocationUpdatesIfNecessary`, `updateDisplay:` and `_openMaps`. Imported class references are excluded from this count. The two test-named classes should not be mistaken for user-facing test screens.

## Functional paths reconstructed from static evidence

### Live heading display

`CompassPageViewController::updateDisplay:` at `0x1000060d8` reads `CMDeviceMotion` heading, gravity and calibration-related state, then updates the compass angle and crosshair. `setCompassToAngle:force:` at `0x100006244` normalizes/filters angle changes, uses approximately a 0.1° update threshold and schedules haptic feedback around 30° steps. `_updateHeadingLabels:` at `0x100006570` updates the numeric heading and compass direction text (E6 `ev_53adc679b39384351d478ff5096aa4d7ff35906584fcf57f6d16743f26e6445b`, `ev_3ecc539a1e095d0e8bc9c3b8e063944fb2f50342c83b5edf51ad191cef12d558`, `ev_126e9510d27710d4c446e19368d752fa600edafd01ea6f5eb3a56ad25a8fe840`). A Frida hook observed 189 `updateDisplay:` calls in 3.129 seconds while the app stayed foreground (E10). That confirms frequent invocation during this window; the device-motion inputs and downstream call order remain unverified.

### Bearing lock

`CompassView::tappedCompass:` at `0x100001960` toggles a stored bearing. `CompassView::setBearing` at `0x100001978` updates `_hasBearing`, the bearing layer and related labels/background. `CompassBearingView::updateLayer` at `0x100002014` converts the bearing angle to radians and updates the layer when the difference passes a small threshold (E6 `ev_5fe9c2f0ce67923a0c0c0163cddc3f8c05baaf7f2ccf83a5ca219b07899499bf`, `ev_c20cd051a16cdfa9fc57a1bb705492a686c836321751a3ceb191bf9f1f2c30c5`, `ev_913f8dfea928471c6ed4cca355ccd3b8149665bdd95cd6dba16789352ce66097`). In the E10 run, one iOS MCP dial tap coincided with one call to each of those three methods and a visible bearing-state change. The hooks counted calls; they did not capture ordering or parameters.

### Location and Maps

`CompassController::startLocationUpdatesIfNecessary` at `0x100003944` checks authorization, requests When-In-Use if necessary, and starts location updates when authorized. `locationManager:didUpdateLocations:` at `0x1000038c0` forwards the latest location to the page. `_updateCoordinateLabel` at `0x100006638` formats latitude, longitude and elevation, chooses metres or feet, and handles vertical accuracy. `_geocodeIfNecessary` at `0x100006b64` throttles place-name geocoding by roughly 1000 metres and 60 seconds. `_openMaps` at `0x1000070d4` formats the embedded string `maps:ll=%f,%f&trackingMode=2` and asks UIApplication to open it (E6 `ev_38d16329a2bf5df60a197a0d29190f7b11233c223b5f971acf671b96dae0ae54`, `ev_35feffd6055e971d3b8f804ffb8f6992700fbf0c05fba008d5888c26c3d04e58`, `ev_d1de4b81e80e9544208b0e1fc3dd76d5214b66710619f3bc4be1b1581dd02bbd`, `ev_f808479f835642ccfd32d10e3e8d9fd134f62cfeb9ee25f8652b46468d37a6d8`, `ev_c0757f38cf55d71cd373b96934ef8fdcf23782921138768ec1e5ad90e9b7ab82`). An iOS MCP coordinate tap on the confirmed original called `_openMaps` once, and Apple Maps became foreground (E11); the exact pin placement was not inspected.

## Sandbox, data, and network boundary

The data-container metadata inventory shows `Documents`, `Library`, `SystemData` and `tmp`. Its 24 entries are mostly Saved Application State and SplashBoard snapshot files; `Library/Preferences` and `Library/Caches` were present but had no children within this snapshot (E5). This says nothing about the *contents* of the snapshot files or about data outside this app container. No app-specific database, persistent user file, or network endpoint was established from this inventory. The place-name flow calls platform geocoding APIs according to static evidence; whether that operation used network during this session is unmeasured.

## Rebuild scope and evidence gaps

The first independent implementation covers three flows: live heading presentation, tap-to-set/clear bearing, and authorized location display with a Maps handoff. It uses public CoreMotion, CoreLocation and UIKit APIs and recreates layout from observed structure. The original's `startMotionManager` chooses magnetic north when `_usesTrueNorth=0` (REA/Ghidra evidence `ev_39dc10ab10b206a226e052082ddc3f48ba53d577801f4c19ff585b58792ca9b9`); a read-only XR probe observed that setting, and the rebuild now uses the same reference frame when available. The source, signing, entitlement set and resource artwork differ from Apple's. Side-by-side device captures exist, but pixel-level parity has not been established.

An independent Copy Compass build was installed by TrollStore on the XR. The latest build renders heading, degree-minute-second coordinates, place and elevation. Through iOS MCP, a real screen tap on its dial produced a red bearing marker; the latest automated tap on its coordinate label recorded one `openMaps` call and opened Apple Maps (`cases/compass-maps-stream-retry-20261015/experiment.json`). [The live rebuild record](xr-rebuild-verification.md) compares those states with the confirmed original and distinguishes them from earlier failed USB Accessibility Audit press attempts. The earlier ordinary USB installation was rejected at launch for invalid signing and was removed before TrollStore installation. Build and diagnostic artifacts remain local under `rebuild/CompassClone/build/` and `cases/`.

The agent-authored claims, retained REA dossiers, Frida experiments, binary/class appendices and rebuild specification are also assembled in the [hash-verified deep report](../cases/compass-xr-deep-report-v3-20261015/report.md). `copyapp report` validates evidence identity and hashes; the explanations remain subject to review.

Missing evidence: runtime call order and arguments, full sandbox file content/diff, network trace, multiple orientation and permission states, iOS 17/26 runs, and fine-grained original-versus-rebuild interaction parity. These are open validation tasks, not inferred successes.
