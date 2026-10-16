#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppFixtureClone.xcodeproj -scheme CopyAppFixtureClone \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

stage="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-fixture-clone.XXXXXX")"
trap 'rm -rf "$stage"' EXIT HUP INT TERM
mkdir -p "$stage/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppFixtureClone.app \
  "$stage/Payload/CopyAppFixtureClone.app"
app="$stage/Payload/CopyAppFixtureClone.app"
ldid -S "$app/Frameworks/CloneCatalogCore.framework/CloneCatalogCore"
ldid -S "$app/CopyAppFixtureClone"
(
  cd "$stage"
  zip -q -r CopyAppFixtureClone.ipa Payload
)
mv "$stage/CopyAppFixtureClone.ipa" build/dist/CopyAppFixtureClone.ipa
shasum -a 256 build/dist/CopyAppFixtureClone.ipa
