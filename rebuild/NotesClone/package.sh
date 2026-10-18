#!/bin/sh
set -eu
cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppNotes.xcodeproj -scheme CopyAppNotes \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-notes.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppNotes.app "$package_root/Payload/CopyAppNotes.app"
ldid -S "$package_root/Payload/CopyAppNotes.app/CopyAppNotes"
(cd "$package_root" && zip -q -r CopyAppNotes.ipa Payload)
mv "$package_root/CopyAppNotes.ipa" build/dist/CopyAppNotes.ipa
shasum -a 256 build/dist/CopyAppNotes.ipa
