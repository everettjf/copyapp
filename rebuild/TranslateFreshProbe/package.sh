#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppTranslate.xcodeproj -scheme CopyAppTranslate \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-translate.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppTranslate.app \
  "$package_root/Payload/CopyAppTranslate.app"
ldid -S "$package_root/Payload/CopyAppTranslate.app/CopyAppTranslate"
(
  cd "$package_root"
  zip -q -r CopyAppTranslate.ipa Payload
)
mv "$package_root/CopyAppTranslate.ipa" build/dist/CopyAppTranslate.ipa
shasum -a 256 build/dist/CopyAppTranslate.ipa
