#!/bin/sh
set -eu

cd "$(dirname "$0")"
xcodegen generate --spec project.yml >/dev/null
xcodebuild -quiet -project CopyAppFixture.xcodeproj -scheme CopyAppFixture \
  -configuration Release -sdk iphoneos -destination 'generic/platform=iOS' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build

stage="$(mktemp -d "${TMPDIR:-/tmp}/copyapp-fixture.XXXXXX")"
trap 'rm -rf "$stage"' EXIT HUP INT TERM
mkdir -p "$stage/Payload" build/dist
ditto build/Build/Products/Release-iphoneos/CopyAppFixture.app \
  "$stage/Payload/CopyAppFixture.app"
app="$stage/Payload/CopyAppFixture.app"
ldid -S "$app/Frameworks/FixtureCore.framework/FixtureCore"
ldid -S "$app/PlugIns/FixtureShare.appex/FixtureShare"
ldid -S "$app/CopyAppFixture"
(
  cd "$stage"
  zip -q -r CopyAppFixture.ipa Payload
)
mv "$stage/CopyAppFixture.ipa" build/dist/CopyAppFixture.ipa
shasum -a 256 build/dist/CopyAppFixture.ipa
