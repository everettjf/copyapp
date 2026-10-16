#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppCalculatorFresh.xcodeproj -scheme CopyAppCalculatorFresh \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-calculator.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppCalculatorFresh.app \
  "$package_root/Payload/CopyAppCalculatorFresh.app"
ldid -S "$package_root/Payload/CopyAppCalculatorFresh.app/CopyAppCalculatorFresh"
(
  cd "$package_root"
  zip -q -r CopyAppCalculatorFresh.ipa Payload
)
mv "$package_root/CopyAppCalculatorFresh.ipa" build/dist/CopyAppCalculatorFresh.ipa
shasum -a 256 build/dist/CopyAppCalculatorFresh.ipa
