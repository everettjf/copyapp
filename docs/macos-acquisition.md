# Mac shared-file probe and distribution import

These are development commands alongside iOS. They collect byte/structure evidence;
neither operation proves App launch, runtime identity or reconstructed behavior.
Keep the raw cases local and Git-ignored.

## Probe the shared folders before full control is ready

The shared folders can be inspected through the guest's visible Finder while
ChatComputer onboarding is still incomplete. Publish a fresh, non-secret nonce:

```sh
.venv/bin/copyapp mac share-probe \
  --vm-directory "$HOME/.chatcomputer/ChatComputer.vm" \
  --out cases/mac-share-request
.venv/bin/copyapp verify cases/mac-share-request
```

Read `GUEST_TASK.md`. In the intended guest Finder, copy its named file once from
`/Volumes/My Shared Files/inbox` to `/Volumes/My Shared Files/outbox`, preserving
the name. No App/helper needs to run and no security permission needs to be granted.
If a new host file is absent in Finder, navigating out of and back into the folder
can refresh the view; this was required in the named development probe.

After observing the copy and checking the outbox, record it:

```sh
.venv/bin/copyapp mac share-probe-check --request cases/mac-share-request \
  --reviewer current-agent --notes "Describe the observed guest Finder copy." \
  --out cases/mac-share-result
.venv/bin/copyapp verify cases/mac-share-result
```

The request pins public VM metadata and publishes a unique payload without replacing
an existing file. The result requires the same metadata and exact returned bytes.
The transfer actor is self-declared: verification checks byte identity and source
links, not the truth of an observer's account. It explicitly leaves
`guest_runtime_identity_verified` and `complete_environment_acceptance` false.
It cannot substitute for `mac connect`, collector identity or live MCP control.
Failed, mismatching and linked replies are rejected. Preserve them and inspect the
guest before a new action; the command does not repeat the copy.

## Import an App distribution without execution

For a local `.app`, continue to use `mac inspect`. For ZIP or DMG input:

```sh
.venv/bin/copyapp mac import-app --source /path/to/Example.zip \
  --out cases/mac-import-zip
.venv/bin/copyapp verify cases/mac-import-zip
.venv/bin/copyapp mac import-app --source /path/to/Example.dmg \
  --out cases/mac-import-dmg
.venv/bin/copyapp verify cases/mac-import-dmg
```

If a distribution contains several top-level Apps, pass its exact relative path
with `--app-relative Folder/Example.app`. No App, `.pkg` installer, hook or helper
inside the distribution is executed. Selection produces the usual verified
`package/` App index with Bundle ID/version, Mach-O platform/architecture, full
and arm64-slice hashes, complete package inventory and a separate package hash.

The case retains the original archive bytes and source hash. ZIPs are expanded
with explicit bounded reads, preserving ordinary file modes and safe internal
links. Traversal, duplicate names, case/Unicode collisions, special file modes,
encrypted entries and escaping/dangling links are rejected. Accepted inputs are
bounded to 8 GiB; ZIP uncompressed bytes and selected App packages are separately
bounded, with 40,000 entries including implicit directories.

ZIP verification reads the archived members again and compares their selected
App contents against the saved package. It does not trust only an extraction log
or refreshed artifact hash.

DMG import and re-verification currently require macOS 27's `diskutil image`
interface. The importer checks image metadata through the compatibility `hdiutil`
interface because it exposes the software-license flag. Passwords are not supplied;
encrypted or license-interactive images are rejected before attachment. The image
is attached read-only, hidden from Finder, with noexec/nosuid/nodev, at one owned
mount point. The actual mount flags are checked, and only the selected App is copied.
The image is ejected without force by its owned mount/device identity.

`verify` reattaches the exact saved DMG read-only and compares its selected App's
inventory and Mach-O facts with the package snapshot. It does not execute the App.
If cleanup fails, an owned mount and bounded diagnostic are preserved instead of
recursively deleting through the mount point. Inspect that diagnostic before any
manual cleanup; no unrelated disk number is guessed or ejected.

The imported package remains **static distribution evidence**. Use the normal
registered guest acquisition to establish the installed original App's identity;
compare its full package hash with the static package when linking the two.
`mac install` consumes a reviewed independent build, with separate target identity.
Live App discovery, sandbox data, behavior review and paired delivery still have
their own required evidence.
