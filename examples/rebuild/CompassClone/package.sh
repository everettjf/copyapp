#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppCompass.xcodeproj -scheme CopyAppCompass \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-compass.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppCompass.app \
  "$package_root/Payload/CopyAppCompass.app"
ldid -S "$package_root/Payload/CopyAppCompass.app/CopyAppCompass"
(
  cd "$package_root"
  zip -q -r CopyAppCompass.ipa Payload
)
mv "$package_root/CopyAppCompass.ipa" build/dist/CopyAppCompass.ipa
shasum -a 256 build/dist/CopyAppCompass.ipa
