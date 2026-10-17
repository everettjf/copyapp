# Copy APP 设备端 UI 服务

**语言：** [English](README.md) | 简体中文

这里保留了 [`witchan/ios-mcp`](https://github.com/witchan/ios-mcp) 的部分 MIT 许可源码，来源提交为 `62c4464f688c8f269419924b1a19c996de75f175`；上游 `LICENSE` 和 `NOTICE` 一并保留。Copy APP 将它独立打包为 SpringBoard tweak `com.copyapp.mcp`，只在 `127.0.0.1:8090` 监听，并经 USB 转发访问。它只开放受限的 UI 观察、手势、文本输入和 App 启动工具；文件上传和下载入口返回 404。普通 rootless 包已在 XR 验证。RootHide 包和 ElleKit 1.2-1 已在 iPhone 14 安装；USB 转发的健康、前台、无障碍和截图检查通过。

设备内的 Vision OCR 曾在 iOS 16.1.1 的 iPhone XR 上使 SpringBoard 崩溃，因此 0.1.3 起禁用设备内 OCR；Mac 端改用 USB 截图加 Vision。0.1.4 又将 `swipe_screen`、`long_press` 和 `double_tap` 纳入受限工具清单。在 XR 上，检查过文件范围和 SHA-256 的 rootless 包经现有 USB SSH 通道安装，再通过 `sbreload` 激活；实时健康接口报告 0.1.4，`tools/list` 列出了三种手势。其他系统与设备尚未验证。

使用完整 Xcode、Theos 的 iPhoneOS16.5 SDK 和 `ldid` 构建：

```sh
THEOS=/path/to/theos CLANG_MODULE_CACHE_PATH=/private/tmp/copyapp-clang-modules make package
```

生成的 `.deb` 位于 `packages/`。部署前检查归档内容，只应有 tweak、过滤配置和版权声明。手势参数、两套后端差异及 XR 证据见[中文手势指南](../../docs/ui-gesture-playbooks.zh-CN.md)（[English](../../docs/ui-gesture-playbooks.md)）。

Relaxin / RootHide 需要 [roothide/theos](https://github.com/roothide/theos)，构建时传入 `THEOS_PACKAGE_SCHEME=roothide`。包依赖真正的 tweak 注入器 `mobilesubstrate`；RootHide ElleKit 提供该依赖，单独安装 `roothide` 核心包不够。iPhone 14 已完成 SSH、iCTRL、iOS MCP 和一条 Calculator 原版/复刻版对照；Frida 跟踪仍不稳定。详见 [iPhone 14 状态记录](../../docs/relaxin-roothide-iphone14.md)。
