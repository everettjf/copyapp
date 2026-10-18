# Notes selected-flow rebuild

[English](README.md) · [简体中文](README.zh-CN.md)

This independent UIKit app implements the three local Notes flows selected in the [XR study](../../docs/notes-xr-workflow.md): folder navigation, plain-text note creation with local persistence, and title/body search. Its Bundle ID is `com.copyapp.notes`; its minimum deployment target is iOS 16.0. It uses original Swift source in this folder and a JSON store in its own Documents container. It does not import Apple's code, assets, data or account state.

On a Mac with Xcode, XcodeGen and `ldid`, run `sh package.sh` from this folder to produce `build/dist/CopyAppNotes.ipa`. The local test installed this IPA on the jailbroken XR through Copy APP's TrollStore route. The package script signs for that route; normal USB installation requires a development signing identity and provisioning profile for the Bundle ID.

The XR result is a scoped comparison, not complete Notes equivalence. The three paired scripts passed and three screenshots were reviewed with minor differences. Repeated synthetic tests left different note counts in the original and clone. iCloud, rich text, attachments, sharing, locking and iOS 17 Notes behavior are outside this implementation.
