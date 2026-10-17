# Clock clone across iOS 16 and 17

[English](clock-clone-two-device.md) · [简体中文](clock-clone-two-device.zh-CN.md)

The independent UIKit project [`ClockCurrentAutoProbe`](../rebuild/ClockCurrentAutoProbe) was built once from the same source. Its ad hoc IPA's executable SHA-256 (`06282bd9234b2a9883ba51e21f357c79f90d521a05351a1590e3d4c5d8b5562e`) matches the executable in the previously installed XR IPA. A copy of that build was development-signed for the iPhone 14; signing changes the Mach-O signature bytes. The signed IPA SHA-256 is `76c0a138b80e1a3f3b060ce0a6953d7fba801c536345c9ecc13b310bce99b362`. The iOS 17 USB installation case `cases/ios17-clock-auto-install-20261017/` confirms Bundle ID `com.copyapp.clock.currentauto`, version 0.1.0 (1), and a valid installed profile.

The same committed [original](../playbooks/clock-paired-stopwatch-original.json) and [clone](../playbooks/clock-paired-stopwatch-clone.json) scripts selected Stopwatch, started it, observed a nonzero running state, stopped it, and captured a stable stopped screen. Original and clone passed separate iOS MCP captures and `compare-playbooks` on **each** phone:

| Phone | Paired evidence | Additional clone backend |
| --- | --- | --- |
| XR / iOS 16.1.1 / Dopamine rootless | `cases/ios16-clock-paired-fair-{original,clone,compare}-20261017/` | iCTRL: `cases/ios16-clock-clone-ictrl-20261017/` |
| iPhone 14 / iOS 17.3.1 / Relaxin RootHide | `cases/ios17-clock-paired-fair-original-retry-20261017/`, `cases/ios17-clock-paired-fair-{clone,compare}-20261017/` | iCTRL: `cases/ios17-clock-clone-ictrl-20261017/` |

All six final UI capture cases, both comparison cases and the iOS 17 install case passed `copyapp verify`. The side-by-side stopped screens were manually inspected. Both show a running result followed by Reset and Start controls, one lap row, and the Stopwatch tab. The saved screenshots differ in timer value because action and observation latency differs between runs; pixel distance is not a fidelity score. On iOS 17 the original also has a different tab wording (`Alarms`/`Timers` versus `Alarm`/`Timer`), control styling and system return-to-App label. These are visible differences, not exact visual parity.

The original Clock retains the stopped stopwatch value across a fresh launch. This clone currently starts at zero again. A unified pre-run Reset action therefore failed on the clone and was removed from the paired script; the original was reset separately with [this preparation script](../playbooks/clock-stopwatch-reset-original.json). A transient iOS 17 SpringBoard foreground race on one original-App run also produced a saved failed case; the next run completed without changing the script. These failures remain local evidence, not passing cases.

This validates the selected foreground Stopwatch interaction and the tested device/transport combinations. It does not validate background timing, alarms, notifications, persistence, all Clock pages, exact visual parity, arbitrary iOS 16/17 devices or whole-App equivalence. `cases/` is intentionally Git-ignored; rerun the committed scripts and verify the resulting cases on a configured Mac.
