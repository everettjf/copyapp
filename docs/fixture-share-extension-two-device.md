# Fixture share extension: iOS 16 and 17 device check

[English](fixture-share-extension-two-device.md) · [简体中文](fixture-share-extension-two-device.zh-CN.md)

The known-source fixture now has a **Share sample text** button. It presents a system `UIActivityViewController` with the fixed string `Copy APP fixture sample text`, allowing its packaged `FixtureShare.appex` to be exercised through the same user-facing share path as an ordinary App extension. The extension's current implementation displays a centered `Copy APP Fixture Share Extension` label; it does not read, save or transmit the shared item.

| Device | Installed fixture | System path | Result |
| --- | --- | --- | --- |
| iPhone XR / iOS 16.1.1 / Dopamine rootless | 0.1.1 (2), ad hoc IPA via TrollStore | Share sample text → More → Suggestions → Copy APP Fixture | 12-step iOS MCP playbook complete; extension label and screenshot confirmed |
| iPhone 14 / iOS 17.3.1 / Relaxin RootHide | 0.1.1 (2), Apple Development IPA via USB | Share sample text → More → Suggestions → Copy APP Fixture | 14-step iOS MCP playbook complete; extension label and screenshot confirmed |

The install cases are `cases/ios16-fixture-share-entry-install-retry-20261017` and `cases/ios17-fixture-share-entry-install-20261017`. The repeatable UI cases are `cases/ios16-fixture-share-playbook-v2-20261017` and `cases/ios17-fixture-share-playbook-v5-20261017`; each case passed `copyapp verify`. The retained screenshots show the extension's actual modal UI on each phone. The scripts are tracked at [`fixture/CopyAppFixture/playbooks/share-extension-ios16.json`](../fixture/CopyAppFixture/playbooks/share-extension-ios16.json) and [`share-extension-ios17.json`](../fixture/CopyAppFixture/playbooks/share-extension-ios17.json).

The first XR update timed out while the older fixture process was alive. Stopping that process and retrying installed the same SHA-256-matched package; the first failed case remains under `cases/ios16-fixture-share-entry-install-20261017`. The XR accessibility tree called several share targets `Activity`, so its replay checks the More list visually and uses the observed row coordinate. iOS 17 returned duplicate `More` accessibility elements and changed the icon's x-position during horizontal scrolling; its replay waits for a stable screenshot before tapping. These are bounded device-specific scripts, not a claim that arbitrary share sheets can always be navigated by fixed coordinates.

After adding the button, the original fixture's Counter, Notes and Catalog playbooks each completed again on both phones. The six regression cases are named `cases/ios16-fixture-share-regression-{counter,notes,catalog}-20261017` and `cases/ios17-fixture-share-regression-{counter,notes,catalog}-20261017`; all six passed `copyapp verify`. The Notes replay writes one additional synthetic sample row on each test phone.

From the repository root, with the matching fixture version installed and iOS MCP running:

```sh
.venv/bin/copyapp playbook --udid <XR_UDID> --backend ios-mcp \
  --script fixture/CopyAppFixture/playbooks/share-extension-ios16.json \
  --out cases/fixture-share-ios16-recheck
.venv/bin/copyapp playbook --udid <IPHONE_14_UDID> --backend ios-mcp \
  --script fixture/CopyAppFixture/playbooks/share-extension-ios17.json \
  --out cases/fixture-share-ios17-recheck
```

This closes the fixture's **user-facing extension invocation** gap on the two named phones. It does not validate data handling inside the extension, other extensions, other iOS versions, or whole-App clone equivalence. Raw screenshots, IPAs and signing material stay in ignored local `cases/`.
