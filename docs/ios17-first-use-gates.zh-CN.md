# iOS 17 首次使用启动引导

[English](ios17-first-use-gates.md) · [简体中文](ios17-first-use-gates.zh-CN.md)

在实测的 iPhone 14 / iOS 17.3.1 上，Apple Translate 与 Clock 首次启动时，iOS MCP 和原生 RSD 均返回错误；iCTRL/XCTest 启动 Translate 也报错。但 USB 截图显示 SpringBoard 渲染的对应 App **Welcome / Accept & Continue** 页面。此时前台 Bundle ID 为 `com.apple.springboard`：安装列表里有 App、屏幕出现欢迎页，都不能证明目标进程已经启动。

`survey --launch` 或新启动的 UI 脚本报错时，先看屏幕，再判断 App 是否不可用：

```sh
.venv/bin/copyapp ui screenshot --backend usb --udid <UDID> --out cases/first-use-screen.png
```

按设备所有者的偏好完成可见的首次使用选择，再确认 `get_frontmost_app` 指向目标 App，并用**新的**输出目录重跑失败案例。不要把欢迎页当作 App 正常界面，也不要自动替用户同意数据选择。此次测试中，Translate 无线数据选 WLAN Only、可选 Siri/听写音频分享选 Not Now；Clock 欢迎页完成后，两者均进入自身前台进程。

后续[双机矩阵](two-device-verification-matrix.zh-CN.md)记录 Translate 文本输入和 Clock 秒表经 iOS MCP、iCTRL 的四路检查。这些脚本以首次使用设置已完成为前提；其结果不证明其他隐私选择下的行为，也不证明欢迎页之前的正常 App 功能。
