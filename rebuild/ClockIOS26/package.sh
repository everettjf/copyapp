#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppClockIOS26.xcodeproj -scheme CopyAppClockIOS26 \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-clock.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppClockIOS26.app \
  "$package_root/Payload/CopyAppClockIOS26.app"
ldid -S "$package_root/Payload/CopyAppClockIOS26.app/CopyAppClockIOS26"
(
  cd "$package_root"
  zip -q -r CopyAppClockIOS26.ipa Payload
)
mv "$package_root/CopyAppClockIOS26.ipa" build/dist/CopyAppClockIOS26.ipa
shasum -a 256 build/dist/CopyAppClockIOS26.ipa
