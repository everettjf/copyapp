# Copy APP 设备端 UI 服务

[English](README.md) · 简体中文 · [当前设备支持](../../docs/current-status.zh-CN.md)

本目录保留 [`witchan/ios-mcp`](https://github.com/witchan/ios-mcp) 的部分 MIT 许可源码，来源提交为 `62c4464f688c8f269419924b1a19c996de75f175`；上游 `LICENSE` 和 `NOTICE` 一并保留。Copy APP 将其打包为 `com.copyapp.mcp`，仅开放受限界面能力：前台观察、无障碍、截图、手势、文字输入与 App 启动。HTTP 服务只在 `127.0.0.1:8090` 监听，供 USB 转发；文件上传／下载入口返回 404。

普通 rootless 构建在 XR/iOS 16.1.1 上实测；RootHide 构建配合 ElleKit 在 iPhone 14/iOS 17.3.1 和 iPhone 11/iOS 26.0.1 上实测。结果只覆盖选定服务，不保证所有越狱组合。XR 上设备内 Vision OCR 曾使 SpringBoard 崩溃，因此已移除；Mac 端在截图上执行 Vision OCR。服务支持 `swipe_screen`、`long_press` 和 `double_tap`，不同后端的语义见[手势指南](../../docs/ui-gesture-playbooks.zh-CN.md)。

构建需要完整 Xcode、Theos、其 iPhoneOS16.5 SDK 和 `ldid`：

```sh
THEOS=/path/to/theos CLANG_MODULE_CACHE_PATH=/private/tmp/copyapp-clang-modules make package
```

RootHide 使用 [roothide/theos](https://github.com/roothide/theos) 与 `make THEOS_PACKAGE_SCHEME=roothide package`。运行时还需 ElleKit 等真正的 tweak loader 满足 `mobilesubstrate` 依赖。生成的 `.deb` 位于 `packages/`；安装前检查归档内容，安装后重新加载 SpringBoard。再运行 `copyapp doctor --udid <UDID> --out cases/<DOCTOR>`，检查 `ios_mcp` 行及真实截图。其他手机服务见[安装指南](../../docs/setup.zh-CN.md)。
