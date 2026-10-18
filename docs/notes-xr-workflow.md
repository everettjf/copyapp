# System Notes: analysis to independent rebuild on iPhone XR

[English](notes-xr-workflow.md) · [简体中文](notes-xr-workflow.zh-CN.md)

The selected-flow run used system Notes 2.10 (`com.apple.mobilenotes`) on a jailbroken iPhone XR with iOS 16.1.1. It completed the two Copy APP stages: a source-linked analysis report and an independent iOS App installed and compared on the same phone. Device evidence lives in ignored local `cases/notes-copy-ios16-20261017/`; the published source is [NotesClone](../rebuild/NotesClone/README.md). No private note content is part of the repository or release wheel.

## Stage 1: analysis

1. Discover three local-account UI flows using iOS MCP: Folders → Notes, New note → synthetic title/body → Done, and Search → synthetic title.
2. Acquire the exact installed bundle and a bounded app-container metadata index over pinned USB/SSH. The package index has 169 file entries and seven Mach-O files; the main executable's Objective-C index has 336 classes. The container scan has 49 metadata paths and does not read note contents or App Group records.
3. Inspect encryption status. These system Notes binaries had no encryption command. The analysis IPA now uses the verified unencrypted source snapshot, without invoking the device decryption helper. This run exposed and fixed a prior 140-second helper timeout on already unencrypted packages.
4. Trace selected method entrances during New note and Search. The new-note manager selector had one current-IMP and static-offset hit in the New note tap window. Search update had one hit on focus and 19 in the 19-character typing window; searchQueryDidChange had one hit during typing. These are bounded temporal observations.
5. Use Hopper 6.6.0 on the exact binary for the new-note entry and two search functions. The pseudocode supports a note creation/show-editor path and a query-input/data-source path; it is an interpretation of machine code, not Apple source or proof of all persistence and ranking logic. The reviewed report at `cases/notes-copy-ios16-20261017/analysis-agent/reviewed-report/report.md` distinguishes observations, inferences and unknowns.

## Stage 2: rebuild and check

The independent [UIKit project](../rebuild/NotesClone) targets iOS 16.0 and stores its own local notes in JSON. The XR installed IPA had SHA-256 `4e9d8c53842b2c3f5356498096b5de9302b4533b1d43548f3856642f88fbeee4` and Bundle ID `com.copyapp.notes`. The three original/clone playbooks completed, and three paired screenshots were judged minor differences. The local parent case at `cases/notes-copy-ios16-20261017/` and its report, install, comparison, visual review and delivery cases passed `copyapp verify`. Python regression: 322 tests passed.

The most important test setup issue was system Notes restoring the last editor after a fresh launch. The search script assumed a visible Folders back button, so the agent explicitly navigated to the folder root and backgrounded Notes before resuming the same check. Those setup actions are saved alongside the ignored case. A first-run “Organize with Tags” tip was dismissed before the final visual comparison. Future playbooks should declare their initial page and any first-run conditions; a fresh launch alone does not reset app navigation.

The remaining differences are the synthetic note counts accumulated independently during repeated tests, the editor back label, some toolbar glyphs, and search result card grouping. This is a verified shallow-to-deeper rebuild of **three local flows**, not full Notes. iCloud, rich text, attachments, collaboration, locked notes, storage schema, server behavior and iOS 17 original Notes remain unverified. The iPhone 14 held existing personal Notes data and was intentionally not used for this Notes study.
