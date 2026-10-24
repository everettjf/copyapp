# Standard iPhone mode (development branch)

[中文](ios-standard-mode.zh-CN.md) · [Design and acceptance gates](ios-device-support-plan.zh-CN.md)

This checkout adds explicit `--mode standard|auto|enhanced` routes. Unflagged historical iOS commands retain their existing contracts. This is development work, outside the published v0.2.0 support boundary. macOS continues to use `copyapp mac` and ChatComputer identities.

The named standard-mode sample is an iPhone 11 (`iPhone12,1`) on iOS 26.0.1, after an authorized reboot left its jailbreak inactive. SSH, Frida and iOS MCP were unavailable. It has previous jailbreak files and is not a pristine never-jailbroken device. A development-signed iCTRL runner was installed over USB; a selected Calculator addition flow was observed, independently implemented, signed, installed and compared on that same phone. Both screenshot pairs were reviewed; minor differences remain. The bounded fidelity milestone reached 87.4/100 in its first cycle. This is a selected-scope reviewer grade, separate from capability coverage and whole-App parity. The iPhone 14 / iOS 17.3.1 also passed an explicit standard-mode fixture flow while its RootHide services remained active; this adds a named system regression, not pristine ordinary-device acceptance.

Use the repository virtual environment. Confirm the exact UDID and Bundle ID, Developer Mode, pairing/trust, Xcode and a valid development signing profile. A green heartbeat permits an attempt; it does not establish working XCTest actions or profile coverage.

```sh
.venv/bin/copyapp devices
.venv/bin/copyapp onboard --udid <UDID> --stage analyze --mode standard --out cases/standard-onboard
.venv/bin/copyapp setup ictrl --help
```

For the runner's normal signed installation, use the setup command's explicit `--transport usb`. This route never falls back to TrollStore or SSH. Prepare a signed runner IPA for the named device using the existing iCTRL setup instructions. Standard playbooks own a fresh XCTest session on the tested iOS 26 route and stop their runner on exit; screenshots come from the exact USB device. A black launch frame receives a bounded Home/activation recovery before flow actions. An uncertain action reply is retained as a failure, without automatic tap replay.

For supplied flows:

```sh
.venv/bin/copyapp analyze --mode standard --udid <UDID> --bundle <BUNDLE> \
  --script <FLOW.json> --out cases/standard-analysis
.venv/bin/copyapp verify cases/standard-analysis
.venv/bin/copyapp report --case cases/standard-analysis --findings <REVIEWED.json> \
  --feature-spec <SPEC.json> --out cases/standard-report
.venv/bin/copyapp analysis-delivery --task cases/standard-analysis \
  --report cases/standard-report --out cases/standard-analysis-delivery
```

`prepare-app --mode standard` uses the same UI-first collector. Collection produces `TASK.md`, not a completed report. Review every screenshot and raw observation, distinguish observed/inferred/unknown claims, retain each `source_script_sha256`, and provide post-action assertions. The new `ios_behavior_report` and `ios_behavior_delivery` formats do not certify native functions or sandbox structure. Enhanced function analysis uses the existing explicit investigation and deep-report workflow.

The current coding agent can keep one resumable parent:

```sh
.venv/bin/copyapp copy --mode standard --agent-provider current \
  --udid <UDID> --bundle <BUNDLE> --rebuilt-bundle <OWN_BUNDLE> \
  --auto-discover --output-dir output/<UNIQUE_JOB>
```

It writes handoff tasks and returns an incomplete status until their evidence exists. For discovery, author and inspect 3–12 distinct bounded flows, then run `discover-check --mode standard --backend ictrl` at the task's specified path. Supplied `--script` or an accepted `--discovery` case can replace `--auto-discover`. Resume with the same flags and exact job directory plus `--resume`. No nested agent CLI is launched. Do not retry an uncertain failed flow until its UI state is reviewed; `--resume --retry-failed` explicitly archives and retries failed analysis flows. Failed discovery replay requires its own review and a new case.

Resuming a failed collection takes a new capability probe before any action and keeps it under `capability-checks/`. An unavailable or changed route blocks replay; it does not overwrite the original capability snapshot or silently switch backends. If the same route is repaired, its newly accepted probe determines readiness, so an initially missing channel does not permanently prevent resume. Completed cases can be verified and reused without touching the phone. Enhanced CLI requests additionally pin device-decryption intent, survey backend, SSH route references and helper identity. Changing those inputs requires a new case. Enhanced survey, acquired IPA metadata, sandbox and any recovered package must match the live App version/build and saved device/system identity; an old build is rejected even if its stage success flags and hashes are valid.

Complete the report and analysis-delivery at the pinned paths, then follow `rebuild-preparation/task/TASK.md`. Freeze known capabilities and the fidelity milestone before implementation. Build an independent source tree with its own Bundle ID; standard mode requires development signing and `install --transport usb`. Run paired checks, inspect every screenshot pair, and create visual-review and agent-delivery without `--run`. The parent retains strict completion gates: a bounded fidelity milestone alone does not complete it. Omitted capabilities remain explicit.

Capability model 2 separates full-access App tracing from root process privilege. The named iPhone 14 / iOS 17.3.1 supports SSH acquisition, sandbox indexing and Frida method tracing, but its Frida child has UID 501. A separate suspended-child probe checks the exact USB identity and stops the child without running its executable. Device decryption requires a successful UID-0 probe; an explicit `--decrypt` request stops before collection or UI replay when it is unavailable. Standard mode skips this probe. Historical model-1 cases retain their original validation and readiness meaning; they do not establish root privilege. See the [live follow-up](ios-device-support-acceptance.md#authenticated-download-and-three-route-follow-up).

Host-side package inputs are optional and independent of phone privilege:

```sh
sh scripts/bootstrap-ios-host-tools.sh --all
# Authenticate interactively in the user's terminal; never put a password or token in a task.
toolchains/bin/ipatool auth login
.venv/bin/copyapp store-download --bundle <BUNDLE> --out cases/store-package
.venv/bin/copyapp package-import --ipa <FILE.ipa> --bundle <BUNDLE> --out cases/imported-package
.venv/bin/copyapp decrypt-offline --package cases/imported-package \
  --credential-ref <LOCAL_ALIAS> --out cases/offline-package
```

Check `--help` for exact arguments. `ipatool` is pinned to v2.7.0; FairPlay sources are pinned to commit `1bad106ee1698c6d9c483f67d898183ffa4c6eb3` and checked by four source hashes. Download records bind the executable hash/version, requested identity and actual package metadata. License acquisition requires explicit `--acquire-license`. Raw account output is not retained. An authenticated download of free FocusTodo 1.0.4 (4) now has named evidence in the acceptance ledger. Its two standard-mode UI flows passed on the inactive-jailbreak iPhone 11; its main/framework/Widget code remains encrypted. Tool installation alone establishes neither authentication nor download, and login is not a matching offline credential.

New downloads use `download_provenance_version: 2` to retain only the six-digit storefront ID from `iTunesMetadata.plist` field `s`, with basis `downloaded_package_metadata`. The verifier rereads that field from the saved IPA; missing/malformed identifiers remain unknown, and no account name, Apple ID or session output is copied to the record. This does not independently verify the account region. Historical records keep their old string/validation contract. FocusTodo's fixed external version `893656071` was downloaded again and matched, recording package storefront `143465`; the four encrypted binary hash/UUID/span records agree with the earlier download, while the whole IPA hashes differ. Neither comparison identifies loaded phone bytes.

For a wheel invoked outside the checkout, set `COPYAPP_SOURCE_ROOT` to the checkout containing these ignored toolchains and credential stores. Default ipatool, FairPlay source and credential lookup use that root, rather than the shell's current directory; explicit tool/store paths still override it.

Store a matching 16-byte credential only in the ignored `cases/credentials/fairplay/<LOCAL_ALIAS>.bin`. Its contents, hash and local path are excluded from evidence. Initial credential acquisition is a separate preparation task; this adapter does not obtain it from an ordinary phone. Offline recovery audits all binaries and resources and currently accepts audited thin ARM64 encrypted inputs. FAT inputs are rejected. Structural success is labelled `structural_only`, not verified plaintext; an already unencrypted package is unchanged passthrough and never claimed as decryption. Genuine successful decryption and an independent matching-code cross-check remain open acceptance gates.

The package index also records unsupported 32-bit/swapped-endian Mach-O programs and programs outside the primary App. These inputs can retain static package evidence but block full offline recovery. All FAT inputs are rejected, including those whose selected ARM64 slice is already clear, because other slices have not been audited.

`offline-cross-check --offline <OFFLINE_CASE> --device <VERIFIED_DEVICE_DECRYPT_CASE> --out <NEW_CASE>` compares every recovered program, including extensions, against a verified historical `decrypted_package`. It requires matching version/build, encrypted-byte hash, UUID, encryption span and recovered-byte hash. This separate case retains both collection identities; it does not change the original offline `structural_only` label or make different-time observations simultaneous. It requires a real positive offline sample for device acceptance.

Pass repeated `--package-case` to UI-first analyze/prepare-app/copy to attach verified package evidence. Another Bundle ID is rejected; different versions remain `bundle_only`, while matching version/build is `metadata_match`. Neither establishes the installed runtime binary identity. Cite `package.1` etc. with finding `basis: "package"`; UI findings cite their flow IDs. Runtime and code claims require their own matching evidence.

Keep raw packages, license files, screenshots and traces ignored and local. Run `copyapp verify` on every case. New v2 iOS kinds dispatch explicitly; they never fall back to a legacy report filename. The implementation plan's remaining live-device, real-credential and regression gates still apply.
