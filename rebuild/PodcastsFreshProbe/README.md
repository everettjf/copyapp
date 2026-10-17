# Apple Podcasts selected navigation probe

This UIKit project was authored from the reviewed iOS 16 and iOS 17 Apple Podcasts evidence under `cases/ios{16,17}-podcasts-reviewed-report-20261017/`. It implements only the four-tab shell and the three selected navigation results. It uses system symbols and original layout code; it does not copy Apple's artwork, private account data, playback engine, network API, or subscription behavior.

The iOS 16 device has an empty Library and Listen Now state. The iOS 17 device has account-specific material, which this probe represents only by section headings. A passing page-title assertion will not imply content or visual parity. The final device comparison and its screenshot review must record the remaining differences explicitly.

Generate `CopyAppPodcastsFresh.xcodeproj` with `xcodegen generate --spec project.yml`, then build its `CopyAppPodcastsFresh` scheme for a generic iOS device. The deployment target is iOS 16.0. For a TrollStore test install, package the resulting `.app` as `Payload/CopyAppPodcastsFresh.app` in an IPA and sign its executable with `ldid`. For the iOS 17 test route, use your own Apple Development identity and a provisioning profile covering `com.copyapp.podcasts.fresh`, then install the signed IPA with `copyapp install --transport usb --udid <UDID> --ipa <IPA> --out <CASE>`. Keep signing material, IPAs, device screenshots and account content outside Git.

The [two-device result](../../docs/podcasts-two-device-report-rebuild.md) records 3/3 selected navigation checks on each phone, with major screenshot differences. The clone does not implement search results, subscriptions, playback, downloads or account sync.
