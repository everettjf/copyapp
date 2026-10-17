# Clock clone: one-minute background timing on two devices

[English](clock-background-two-device.md) · [简体中文](clock-background-two-device.zh-CN.md)

After v0.1.10, the installed independent Clock 0.1.3 (4) clone was checked on the iPhone XR / iOS 16.1.1 and iPhone 14 / iOS 17.3.1. On each phone, the committed [start](../playbooks/clock-background-start-clone.json) playbook reset and started its Stopwatch, iCTRL sent Home, the App remained in the background for more than one minute, and iCTRL brought it to the foreground. The committed [return](../playbooks/clock-background-return-clone.json) playbook observed a running Stopwatch and saved a screenshot. A separate [stop](../playbooks/clock-running-stop-clone.json) playbook stopped it afterward.

| Phone | Visible before | Home → return | First visible after | Observation → observation | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| XR / iOS 16.1.1 | `00:01.25` | 70.2 s | `01:31.80` | 90 s | Running; visible gain 90.55 s |
| iPhone 14 / iOS 17.3.1 | `00:01.25` | 76.8 s | `01:36.55` | 95 s | Running; visible gain 95.30 s |

The observation timestamps have one-second precision, and the UI keeps advancing while it is captured. These numbers support continued wall-clock progression during the tested background interval; they are not a subsecond timing-accuracy measurement. The return screenshots were visually inspected, and all six start/return/stop playbook cases pass `copyapp verify`:

- XR: `cases/ios16-clock-background-{start,return,stop}-v0110-20261017/`
- iPhone 14: `cases/ios17-clock-background-{start,return,stop}-v0110-20261017/`

The iCTRL Home/return timestamps are in the ignored local start cases as `lifecycle-home.json` and `lifecycle-return.json`. Unlike the playbook files, these two supplementary logs are not bound by `copyapp verify`; their SHA-256 values are XR `6d313ea0cfc7547d5fe958e38b848d023f0633108a2d7170468ab0197d5f9d81` / `d4f8f4c9780252b134935aaa708f1d8ceaa0201e5f6974dfa32a0f662d00a3c8`, and iPhone 14 `f08294029e85056cc8d77b4f1d6a6daa2508ed1f31df1d6e98f70c8c0591cf15` / `f95d393d4d65bd7a13a0b142ae00cb2250358108840ec50ef118849a4b62eb4e` respectively. The first attempted XR Home call failed before device interaction because it used the system Python instead of the project virtual environment; the successful call and timestamps are the ones reported above.

This is one approximately one-minute clone-only background interval per phone. It does not compare the original Clock's current user timer, test hours of suspension, device reboot, system clock adjustment, low-power behavior, or notification and alarm delivery. The broader [two-device matrix](two-device-verification-matrix.md) keeps those limits explicit.
