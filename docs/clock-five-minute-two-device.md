# Five-minute Stopwatch background check on both phones

[English](clock-five-minute-two-device.md) · [简体中文](clock-five-minute-two-device.zh-CN.md)

After v0.1.13, the original Clock (`com.apple.mobiletimer`) and installed independent Clock clone (`com.copyapp.clock.currentauto`) were tested separately on iPhone XR / iOS 16.1.1 and iPhone 14 / iOS 17.3.1. Each run reset and started Stopwatch, used iCTRL to send Home, waited at least five minutes, returned to the same App, saved the running state, and stopped Stopwatch. The six start/return/stop playbook cases per phone pass `copyapp verify`. The [older one-minute clone-only check](clock-background-two-device.md) remains a separate observation.

| Phone | App | Running value before → after | Gain | Time between the saved observations | Difference |
| --- | --- | --- | ---: | ---: | ---: |
| XR / iOS 16 | Original Clock | 1.30 s → 5 min 8.45 s | 307.15 s | 308 s | −0.85 s |
| XR / iOS 16 | Clone | 1.25 s → 5 min 8.60 s | 307.35 s | 308 s | −0.65 s |
| iPhone 14 / iOS 17 | Original Clock | 1.21 s → 5 min 19.52 s | 318.31 s | 318 s | +0.31 s |
| iPhone 14 / iOS 17 | Clone | 1.25 s → 5 min 15.05 s | 313.80 s | 314 s | −0.20 s |

The time column subtracts the `at` timestamps on the running `observe` steps of the start and return playbook manifests. These timestamps have **one-second precision**, so the differences are bounded consistency checks rather than a subsecond accuracy measurement. The Home-to-return iCTRL intervals were 301.44 s, 301.45 s, 306.25 s and 306.20 s in table order. The return screen is observed later than the foreground request, explaining why its Stopwatch gain is larger than the Home-to-return interval.

The cases are `cases/ios{16,17}-clock-{original,clone}-five-minute-{start,return,stop}-20261017/`. The local orchestration input and lifecycle logs are in ignored `cases/clock-five-minute-inputs-20261017/`; the four lifecycle-log SHA-256 hashes are XR original `7a2fbae1819682b92074d0394eabd3fb541617b05a9edfbf313d46655ca71926`, XR clone `a89fc68899c2a74175d9537e5001da0cea7336029912dd7cda034bb25a797082`, iPhone 14 original `6d3c4ef5d0aa1c244b7b10d4fcab2a75159bf209c20d375bcc1f56b76ff074ba`, and iPhone 14 clone `9b2eb91444956951dfeeb6fbca013fe495d5228b26289241b4f417c9110c7fa3`. The playbook cases are verified by Copy APP; those supplementary lifecycle logs are hash-recorded here but are **not** bound by `copyapp verify`.

Fresh v0.1.13 doctor cases on the [XR](../cases/ios16-v0113-doctor-20261017/report.md) and [iPhone 14](../cases/ios17-v0113-doctor-20261017/report.md) also pass `copyapp verify` and report USB, screenshot, developer filesystem, mobile SSH, Frida, iOS MCP and iCTRL available. A capability probe alone does not establish unrelated App behavior.

This test covers one five-minute background interval per App and phone. It does not establish hours-long suspension, device lock or reboot recovery, system time changes, alarm and notification delivery, or whole-Clock parity. The clone and original ran in separate windows, so their exact displayed values are not expected to match.
