# Fixture share extension: iOS 16 and 17 device check

[English](fixture-share-extension-two-device.md) · [简体中文](fixture-share-extension-two-device.zh-CN.md)

The known-source fixture has a **Share sample text** button. It presents a system `UIActivityViewController` with the fixed string `Copy APP fixture sample text`, allowing its packaged `FixtureShare.appex` to be exercised through the same user-facing share path as an ordinary App extension. In fixture 0.1.2 (build 3), the extension loads the text item supplied by that share sheet and displays `Received: Copy APP fixture sample text` below its title. It does not save or transmit the item.

| Device | Installed fixture | System path | Result |
| --- | --- | --- | --- |
| iPhone XR / iOS 16.1.1 / Dopamine rootless | 0.1.2 (3), ad hoc IPA via TrollStore | Share sample text → More → Suggestions → Copy APP Fixture | 12-step iOS MCP playbook complete; exact received text and screenshot confirmed |
| iPhone 14 / iOS 17.3.1 / Relaxin RootHide | 0.1.2 (3), Apple Development IPA via USB | Share sample text → More → Suggestions → Copy APP Fixture | 14-step iOS MCP playbook complete; exact received text and screenshot confirmed |

The current install cases are `cases/ios16-fixture-share-data-install-retry-20261017` and `cases/ios17-fixture-share-data-install-20261017`. The repeatable data-path cases are `cases/ios16-fixture-share-data-playbook-20261017` and `cases/ios17-fixture-share-data-playbook-20261017`; each passed `copyapp verify`. Their final UIKit observations and screenshots both contain the exact `Received:` text. The scripts are tracked at [`fixture/CopyAppFixture/playbooks/share-extension-ios16.json`](../fixture/CopyAppFixture/playbooks/share-extension-ios16.json) and [`share-extension-ios17.json`](../fixture/CopyAppFixture/playbooks/share-extension-ios17.json). The earlier 0.1.1 (2) invocation-only cases remain under `cases/ios16-fixture-share-playbook-v2-20261017` and `cases/ios17-fixture-share-playbook-v5-20261017`.

The 0.1.2 XR update also timed out on its first attempt; after stopping the host App and extension processes, the same SHA-256-matched package installed on retry. That failed case is retained under `cases/ios16-fixture-share-data-install-20261017`. The XR accessibility tree called several share targets `Activity`, so its replay checks the More list visually and uses the observed row coordinate. iOS 17 returned duplicate `More` accessibility elements and changed the icon's x-position during horizontal scrolling; its replay waits for a stable screenshot before tapping. These are bounded device-specific scripts, not a claim that arbitrary share sheets can always be navigated by fixed coordinates.

After adding the button, the original fixture's Counter, Notes and Catalog playbooks each completed again on both phones. The six regression cases are named `cases/ios16-fixture-share-regression-{counter,notes,catalog}-20261017` and `cases/ios17-fixture-share-regression-{counter,notes,catalog}-20261017`; all six passed `copyapp verify`. The Notes replay writes one additional synthetic sample row on each test phone.

After the 0.1.2 text-receipt update, the same three original-fixture paths completed again on both phones. The six current-build cases are `cases/ios16-fixture-share-data-regression-{counter,notes,catalog}-20261017` and `cases/ios17-fixture-share-data-regression-{counter,notes,catalog}-20261017`; all passed `copyapp verify`. These UI regressions do not recheck SQLite row contents, which were separately checked in the earlier [storage validation](releases/v0.1.2.md).

From the repository root, with the matching fixture version installed and iOS MCP running:

```sh
.venv/bin/copyapp playbook --udid <XR_UDID> --backend ios-mcp \
  --script fixture/CopyAppFixture/playbooks/share-extension-ios16.json \
  --out cases/fixture-share-ios16-recheck
.venv/bin/copyapp playbook --udid <IPHONE_14_UDID> --backend ios-mcp \
  --script fixture/CopyAppFixture/playbooks/share-extension-ios17.json \
  --out cases/fixture-share-ios17-recheck
```

This closes the fixture's **user-facing extension invocation and one plain-text input path** on the two named phones. It does not validate other content types, saving or network behavior, other extensions, other iOS versions, or whole-App clone equivalence. Raw screenshots, IPAs and signing material stay in ignored local `cases/`.
