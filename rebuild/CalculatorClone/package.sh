#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppCalculator.xcodeproj -scheme CopyAppCalculator \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-calculator.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppCalculator.app \
  "$package_root/Payload/CopyAppCalculator.app"
ldid -S "$package_root/Payload/CopyAppCalculator.app/CopyAppCalculator"
(
  cd "$package_root"
  zip -q -r CopyAppCalculator.ipa Payload
)
mv "$package_root/CopyAppCalculator.ipa" build/dist/CopyAppCalculator.ipa
shasum -a 256 build/dist/CopyAppCalculator.ipa
