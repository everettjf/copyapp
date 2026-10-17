# Apple Podcasts analysis and new-source rebuild on iOS 16 and 17

[English](podcasts-two-device-report-rebuild.md) · [简体中文](podcasts-two-device-report-rebuild.zh-CN.md)

This is a selected-flow test of Copy APP on iPhone XR / iOS 16.1.1 / Dopamine rootless and iPhone 14 / iOS 17.3.1 / Relaxin RootHide. The target is the system Apple Podcasts App (`com.apple.podcasts`), build 1710.17 on XR and 4023.410.2 on iPhone 14. Local `cases/` data is ignored by Git; run `copyapp verify <CASE>` on the testing Mac to inspect the source-linked records.

## Analysis

The separate [XR report](../cases/ios16-podcasts-reviewed-report-20261017/report.md) and [iPhone 14 report](../cases/ios17-podcasts-reviewed-report-20261017/report.md) each cover acquisition, embedded frameworks and extensions, selected UIKit classes, Library/Search/Listen Now screens, bounded sandbox metadata, network task-resume metadata, and explicit unknowns. Their [XR](../cases/ios16-podcasts-analysis-delivery-20261017/report.md) and [iPhone 14](../cases/ios17-podcasts-analysis-delivery-20261017/report.md) analysis-delivery cases confirm three source-bound flows per device. Reports and deliveries passed `copyapp verify`.

Hopper interpreted two exact-hash entries on each build: the Podcasts tab controller's `viewDidLoad`, and a `PodcastsStoreUI.SearchLandingCell` initializer body that creates artwork and label views and lays them out. The pseudocode is generated interpretation, not Apple's original source. A new Copy APP static-hook path now matches a Mach-O inside `Frameworks/*.framework` by its full path relative to the enclosing `.app`. On XR, the Search tap window recorded 12 current-IMP and 12 static-offset hits for `SearchLandingCell::initWithFrame:`. On iOS 17 the hook attached to the correct framework but this window recorded zero initializer hits. The cell may have been built before attachment or outside the window; neither count establishes tap causality.

The main executables have no encryption load command. Podcasts therefore did not exercise the decryption path. URLSession resume metadata included 13 events in the XR Search window and 11 on iOS 17, with zero in the sampled Library and Listen Now windows. These counts do not describe response bodies, all networking, or server behavior. The sandbox index is bounded metadata, not an atomic snapshot of all user data.

## Independent implementation and device checks

The [PodcastsFreshProbe source](../rebuild/PodcastsFreshProbe/README.md) was newly authored after reviewing the reports. It uses public UIKit and system symbols with Bundle ID `com.copyapp.podcasts.fresh`. Xcode 27 built it for iOS 16 and later. The XR installed an ad hoc IPA through TrollStore; the iPhone 14 installed a separately Apple Development signed IPA through USB. Both [XR](../cases/ios16-podcasts-fresh-install-20261017/install.json) and [iPhone 14](../cases/ios17-podcasts-fresh-install-20261017/install.json) install cases verify.

The [XR paired check](../cases/ios16-podcasts-fresh-check-20261017/report.md) and [iPhone 14 paired check](../cases/ios17-podcasts-fresh-check-20261017/report.md) replayed the original and clone Library, Search and Listen Now scripts on the same device. All six final UIKit page-title assertions and their playbook ready markers passed. Each device saved three screenshot pairs, which were inspected and recorded in [XR visual review](../cases/ios16-podcasts-fresh-visual-review-20261017/report.md) and [iPhone 14 visual review](../cases/ios17-podcasts-fresh-visual-review-20261017/report.md).

| Device | Paired navigation | Visual judgment | Delivery |
| --- | --- | --- | --- |
| XR / iOS 16.1.1 | 3/3 title and ready-marker checks | Library and Listen Now: minor differences; Search: major difference in category illustrations and controls | [Selected behavior verified, visual gap](../cases/ios16-podcasts-fresh-delivery-20261017/report.md) |
| iPhone 14 / iOS 17.3.1 | 3/3 title and ready-marker checks | All three pairs have major differences; the original contains account-specific episode cards and artwork absent from the clone | [Selected behavior verified, visual gap](../cases/ios17-podcasts-fresh-delivery-20261017/report.md) |

All plans, tasks, installs, paired checks, visual reviews and deliveries passed `copyapp verify`. This validates the tested workflow and selected navigation on these two phones. It does **not** establish visual parity, playback, following, downloads, search results, recommendation logic, account sync, purchases, or whole-App equivalence. The source was written by the current agent; there was no independent Claude CLI run or fully automatic zero-shot generation.
