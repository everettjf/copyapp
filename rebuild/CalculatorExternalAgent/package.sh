#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppCalculatorExternalAgent.xcodeproj \
  -scheme CopyAppCalculatorExternalAgent -configuration Release -sdk iphoneos \
  -destination 'generic/platform=iOS' -derivedDataPath build \
  CODE_SIGNING_ALLOWED=NO build

package_root="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-calculator-external.XXXXXX")"
trap 'rm -rf "$package_root"' EXIT HUP INT TERM
mkdir -p "$package_root/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppCalculatorExternalAgent.app \
  "$package_root/Payload/CopyAppCalculatorExternalAgent.app"
ldid -S "$package_root/Payload/CopyAppCalculatorExternalAgent.app/CopyAppCalculatorExternalAgent"
(
  cd "$package_root"
  zip -q -r CopyAppCalculatorExternalAgent.ipa Payload
)
mv "$package_root/CopyAppCalculatorExternalAgent.ipa" build/dist/CopyAppCalculatorExternalAgent.ipa
shasum -a 256 build/dist/CopyAppCalculatorExternalAgent.ipa
