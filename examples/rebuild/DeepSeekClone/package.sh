#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppDeepSeek.xcodeproj -scheme CopyAppDeepSeek \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-deepseek.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppDeepSeek.app \
  "$package_root/Payload/CopyAppDeepSeek.app"
ldid -S "$package_root/Payload/CopyAppDeepSeek.app/CopyAppDeepSeek"
(
  cd "$package_root"
  zip -q -r CopyAppDeepSeek.ipa Payload
)
mv "$package_root/CopyAppDeepSeek.ipa" build/dist/CopyAppDeepSeek.ipa
shasum -a 256 build/dist/CopyAppDeepSeek.ipa
