OpenMinis/iCTRL source snapshot

Revision: d88bbf0b3a5addead31b4298d605d7ac7a87d6e7
Source: https://github.com/OpenMinis/iCTRL
License: Apache-2.0 (see LICENSE and NOTICE.md)

Copy APP builds the Mac CLI and signed XCTest runner from this snapshot. Generated builds, per-machine signing, and pairing credentials are excluded.

Copy APP modification: `Makefile` applies an iOS 16 minimum-version adjustment to Xcode 27's outer XCTRunner before the upstream signing steps when `COPYAPP_IOS_TARGET=16.0` is set. The upstream XCTest compatibility shim and authenticated protocol remain unchanged.

Copy APP modification: the Xcode signing default and generated per-team Bundle ID prefix are `com.copyapp.<lowercase-team-id>` instead of the upstream prefix. Existing `Config/Local.xcconfig` files must be updated or regenerated; they override this default. The URL registration names, pairing-record type and internal dispatch queue labels use `com.copyapp.ictrl`. The Keychain service is `com.copyapp.ictrl.auth`; only legacy sessions stored solely under the previous Keychain service need pairing again. Current sessions persist in the sandbox's `TokenFileStore`. The `ictrl` and `ictrl-app` URL schemes and authenticated protocol remain compatible.
