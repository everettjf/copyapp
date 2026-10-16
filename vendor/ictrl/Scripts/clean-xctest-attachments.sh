#!/bin/bash
# List, and optionally delete, the XCTest attachments left on an iPhone.
#
# Why this exists: since Xcode 15 a UI test screen-records by default. The
# video (30fps H.264) is written by testmanagerd into its own container, under
# tmp/Attachments, and is deleted only when the harness says the test passed.
# The iCTRL server test runs for hours and normally ends killed, so every run
# left its video behind. Settings shows them as "System Data"; they can reach
# tens of GB and fill the disk. A reboot does not clear them, and the
# runner cannot either (that container is outside its sandbox).
#
# Current runners no longer record (see iCTRLUITests/ScreenRecordingDisabler.m),
# so this is for phones that ran an older runner, or other XCUITest tools such
# as WebDriverAgent. Needs Xcode (devicectl) and a USB-connected, trusted
# phone; no sudo. Deleting is safe while no UI test is running: these files are
# only test-report attachments.
#
# Usage: Scripts/clean-xctest-attachments.sh [--udid UDID] [--delete]
#   without --delete it only lists what is there.
set -euo pipefail

UDID=""
DELETE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --udid) UDID="${2:?--udid needs a value}"; shift 2 ;;
    --delete) DELETE=1; shift ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# No --udid: use the only connected physical iPhone, and refuse to guess
# between several (simulators are skipped: they keep attachments on the Mac).
if [ -z "$UDID" ]; then
  xcrun devicectl list devices --json-output "$TMP/devices.json" >/dev/null 2>&1
  UDID="$(python3 - "$TMP/devices.json" <<'EOF'
import json, sys
devices = json.load(open(sys.argv[1]))['result']['devices']
phones = [d['hardwareProperties']['udid'] for d in devices
          if d.get('hardwareProperties', {}).get('platform') == 'iOS'
          and d['hardwareProperties'].get('reality') == 'physical'
          and d.get('connectionProperties', {}).get('tunnelState') == 'connected']
if len(phones) != 1:
    sys.exit(f"found {len(phones)} connected iOS devices — pass --udid: {', '.join(phones)}")
print(phones[0])
EOF
)"
fi

FILES=(--device "$UDID" --domain-type appDataContainer --domain-identifier com.apple.testmanagerd)

list() {
  # A missing Attachments folder (never created, or already cleaned) is an empty list.
  if ! xcrun devicectl device info files "${FILES[@]}" --username mobile \
      --subdirectory tmp/Attachments --json-output "$TMP/files.json" >/dev/null 2>"$TMP/err"; then
    if grep -q 'file node\|No such file\|failed to get a list' "$TMP/err"; then
      echo '{"result":{"files":[]}}' > "$TMP/files.json"
    else
      cat "$TMP/err" >&2; exit 1
    fi
  fi
  python3 - "$TMP/files.json" <<'EOF'
import json, sys
files = [f for f in json.load(open(sys.argv[1]))['result']['files']
         if not f['resources']['isDirectory']]
total = sum(f['metadata'].get('size', 0) for f in files)
for f in sorted(files, key=lambda f: f['metadata'].get('lastModDate', '')):
    m = f['metadata']
    print(f"  {m.get('size', 0) / 1e6:9.1f} MB  {m.get('lastModDate', '')[:10]}  {f['name']}")
print(f"📦 {len(files)} attachment file(s), {total / 1e9:.2f} GB")
EOF
}

echo "📱 $UDID — testmanagerd tmp/Attachments"
list

if [ "$DELETE" -eq 0 ]; then
  echo "Nothing deleted. Re-run with --delete to remove them."
  exit 0
fi

# devicectl has no delete command, but copying an empty folder over the target
# with --remove-existing-content empties it. It then reports CoreDeviceError
# 7000 for the folder it just replaced; the files are gone all the same, which
# the listing below confirms.
mkdir "$TMP/empty"
xcrun devicectl device copy to "${FILES[@]}" --source "$TMP/empty" \
  --destination tmp/Attachments --remove-existing-content true >/dev/null 2>&1 || true

echo "🧹 after cleaning:"
list
