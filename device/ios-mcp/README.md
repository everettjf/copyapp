# Copy APP device UI service

[English](README.md) · [简体中文](README.zh-CN.md) · [Current device support](../../docs/current-status.md)

This directory contains selected MIT-licensed source from [`witchan/ios-mcp`](https://github.com/witchan/ios-mcp), pinned at `62c4464f688c8f269419924b1a19c996de75f175`. The upstream `LICENSE` and `NOTICE` are retained. Copy APP packages it as `com.copyapp.mcp`, with a restricted UI surface: foreground observation, accessibility, screenshots, gestures, text entry and app launch. Its HTTP listener binds to `127.0.0.1:8090` for USB forwarding. File upload and download endpoints return 404.

The ordinary rootless build was exercised on XR/iOS 16.1.1; the RootHide build with ElleKit was exercised on iPhone 14/iOS 17.3.1 and iPhone 11/iOS 26.0.1. These are selected-service checks, not a guarantee for every jailbreak configuration. In-process Vision OCR was removed after SpringBoard crashes on XR; the Mac adapter performs Vision OCR on a captured screenshot. The service exposes `swipe_screen`, `long_press` and `double_tap`; the [gesture guide](../../docs/ui-gesture-playbooks.md) explains backend differences.

Build with full Xcode, Theos, its iPhoneOS16.5 SDK and `ldid`:

```sh
THEOS=/path/to/theos CLANG_MODULE_CACHE_PATH=/private/tmp/copyapp-clang-modules make package
```

For RootHide, use [roothide/theos](https://github.com/roothide/theos) and `make THEOS_PACKAGE_SCHEME=roothide package`. A real tweak loader such as ElleKit must satisfy the `mobilesubstrate` runtime requirement. The generated `.deb` is under `packages/`; inspect its archive paths before installation and reload SpringBoard afterward. Run `copyapp doctor --udid <UDID> --out cases/<DOCTOR>` and inspect the `ios_mcp` row and a real screenshot. The [setup guide](../../docs/setup.md) covers the rest of the phone services.
