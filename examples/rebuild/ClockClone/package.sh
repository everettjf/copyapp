#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppClock.xcodeproj -scheme CopyAppClock \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-clock.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppClock.app \
  "$package_root/Payload/CopyAppClock.app"
ldid -S "$package_root/Payload/CopyAppClock.app/CopyAppClock"
(
  cd "$package_root"
  zip -q -r CopyAppClock.ipa Payload
)
mv "$package_root/CopyAppClock.ipa" build/dist/CopyAppClock.ipa
shasum -a 256 build/dist/CopyAppClock.ipa
