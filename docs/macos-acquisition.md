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

## Capture one explicitly selected App data file

`mac data-file` uses a verified guest acquisition and a collector build that
advertises `data_file`. Rebuild/deploy/register the new collector explicitly if
the registered build lacks this method; do not replace its identity in an old
environment case. This operation requests no new Accessibility permission and
does not grant filesystem access. If macOS denies a read, the failure is retained.

```sh
.venv/bin/copyapp mac data-file --acquisition cases/mac-original \
  --location sandbox --path Library/Preferences/dev.example.Editor.plist \
  --out cases/mac-selected-container-plist
.venv/bin/copyapp verify cases/mac-selected-container-plist
```

The three locations are relative to the collector's actual guest home Library:

| Location | Selected file | Association limit |
| --- | --- | --- |
| `sandbox` | `Containers/<Bundle ID>/Data/<path>` | Bundle-named container convention; not proof the App wrote every file |
| `preferences` | `Preferences/<Bundle ID>.plist` | `--path` must equal the acquired Bundle ID plus `.plist` |
| `support` | `Application Support/<explicit folder>/<file>` | Explicitly selected path; ownership by the App is not certified |

Group containers, ByHost preferences, external documents and arbitrary home paths
are not selected by these locations. No directory crawl or complete data inventory
is performed. A missing default plist does not establish that an App has no settings.
Discover the requested file from actual evidence and record any uncertain ownership.

Only one regular file of at most 64 MiB is accepted. Linked paths, devices, FIFOs,
traversal and changing/replaced files are rejected. The collector compares two
source reads, file metadata and the exported bytes, and checks the acquired App's
binary/Info.plist identity across the operation. The host copies and hashes the
returned file through its exact run/session/request exchange. The case preserves
the source acquisition, request/result, source path/metadata and local `data.bin`.
Source deletion or later changes cannot silently alter that saved case.

This is **one file observation**, not an atomic database snapshot, proof of file
ownership or complete App data. Matching two reads cannot establish transactional
consistency across SQLite, WAL and SHM or across several files. Keep raw bytes in
ignored `cases/`; they may contain private data. Do not present a passing byte
verifier as a database or preference interpretation.

## Extract structure and cite it in a behavior report

Select the format explicitly after reviewing the captured file's origin:

```sh
.venv/bin/copyapp mac data-schema --data cases/mac-selected-container-plist \
  --format plist --out cases/mac-preference-structure
.venv/bin/copyapp verify cases/mac-preference-structure
.venv/bin/copyapp mac data-schema --data cases/mac-selected-database \
  --format sqlite --out cases/mac-database-structure
.venv/bin/copyapp verify cases/mac-database-structure
```

Each structure case retains the verified data-file case, source identity,
`structure.json` and a readable `schema.md`. Verification recomputes the structure
from the saved bytes, rather than trusting a refreshed hash on a generated JSON.

Plist extraction accepts binary/XML files up to 4 MiB. It describes key paths and
types, merging repeated array shapes and recording bounded-walk truncation. It
omits scalar values, array lengths and data bytes. A truncated walk cannot establish
the absence of a key. Names/paths may themselves contain private information.

SQLite extraction accepts the saved main file up to 64 MiB. It opens a detached
copy read-only/immutable, disables trusted schema and denies SQL function execution
and attachment. It queries object names/types, column types/constraints, foreign
keys, user_version and application_id. It omits rows, SQL bodies and defaults,
and bounds schema objects/columns/foreign keys and query work. Unsupported or
malformed schemas fail with diagnostics. It merges no WAL/SHM; structure committed
only to an uncollected WAL may therefore be absent. This cannot establish the
complete schema or current transactional state of the live database.

In a formal review, add a finding with a structure citation:

```json
{
  "id": "stored-editor-keys",
  "certainty": "observed",
  "statement": "The saved plist has the cited editor key/type structure; its writer is not proven.",
  "evidence": [{"data_id": "preferences", "path": "structure.json"}]
}
```

Supply that structure case alongside the normal accepted flow inputs:

```sh
.venv/bin/copyapp mac report --discovery cases/mac-discovery \
  --data preferences=cases/mac-preference-structure \
  --data store=cases/mac-database-structure \
  --review cases/mac-formal-review.json --out cases/mac-report
.venv/bin/copyapp verify cases/mac-report
```

Use one explicit reviewed citation for every supplied data case. Each `data_id`
must identify a verified `mac_data_schema` for the same exact App path, package,
Bundle ID and registered environment as the flow evidence. Only `structure.json`
is a permitted data citation; raw `data.bin` and arbitrary paths are excluded.
A flow's own findings still need captured UI/flow evidence: a data structure alone
cannot prove a visible behavior or persistence. The report preserves all source
cases and rechecks their chain. UI and data observations remain separate-time;
the agent must inspect their meaning and association before drawing a conclusion.

The report's data JSON/Markdown omit values/rows, but its archived child cases
include original raw bytes. Keep the entire case local; these rules do not turn
the archive into a sanitized sharing artifact.
