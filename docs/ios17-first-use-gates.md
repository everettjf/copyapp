# iOS 17 first-use launch gates

[English](ios17-first-use-gates.md) · [简体中文](ios17-first-use-gates.zh-CN.md)

On the tested iPhone 14 / iOS 17.3.1, the first launch of Apple Translate and Clock returned errors from iOS MCP and native RSD; an iCTRL/XCTest Translate launch also returned an error. A USB screenshot showed an app-specific **Welcome / Accept & Continue** page rendered by SpringBoard. The frontmost Bundle ID was `com.apple.springboard`, so an installed-App record and a visible welcome page were not proof that the target process had launched.

If `survey --launch` or a fresh UI playbook reports a launch error, inspect the screen before treating the App as unavailable:

```sh
.venv/bin/copyapp ui screenshot --backend usb --udid <UDID> --out cases/first-use-screen.png
```

Complete the visible first-use choices on the test phone according to the owner's preferences, then verify that `get_frontmost_app` identifies the target and rerun the failed case into a **new** output directory. Do not silently classify the welcome page as the App's normal UI or automatically accept its data choices. In this test, Translate was allowed WLAN Only and optional Siri/Dictation audio sharing was declined. Clock's welcome page was completed. Both then entered their own foreground processes.

The subsequent [two-device matrix](two-device-verification-matrix.md) records four-way iOS MCP/iCTRL checks for Translate text entry and Clock Stopwatch. Those scripts assume first-use setup has been completed. Their results do not establish behavior for devices with different privacy choices or for an App before its welcome gate.
