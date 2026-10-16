#!/bin/bash
# Fetch the idevice xcframework (MIT, github.com/jkcoxson/idevice).
#
# Not committed: the release ships ~230MB static archives per slice and the
# xcframework is only published as a release asset, not in the repo tree — so
# SPM can't resolve it by URL either. We pull it once and keep only the iOS
# device slice, which is the only one the runner/app ever ships.
set -euo pipefail

VERSION="${IDEVICE_VERSION:-v0.1.68}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/Frameworks/IDevice.xcframework"
URL="https://github.com/jkcoxson/idevice/releases/download/${VERSION}/idevice-xcframework-${VERSION}.zip"

# The version that was fetched is recorded next to it, so bumping VERSION
# replaces an older copy instead of silently building against it.
if [ -f "$DEST/ios-arm64/libidevice_ffi.a" ] && [ "$(cat "$DEST/.version" 2>/dev/null)" = "$VERSION" ]; then
    echo "✅ IDevice.xcframework ${VERSION} already present ($DEST)"
    exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# IDEVICE_ZIP=/path/to/idevice-xcframework-<version>.zip installs a copy that
# was downloaded separately — on a slow link the ~215MB fetch can take long
# enough to be worth resuming outside this script (curl -C -).
if [ -n "${IDEVICE_ZIP:-}" ]; then
    echo "📦 Using ${IDEVICE_ZIP} as idevice ${VERSION}"
    cp "$IDEVICE_ZIP" "$TMP/idevice.zip"
else
    echo "⬇️  Fetching idevice ${VERSION} (~215MB)…"
    curl -fL --progress-bar -o "$TMP/idevice.zip" "$URL"
fi
unzip -q "$TMP/idevice.zip" -d "$TMP/x"

SRC="$TMP/x/swift/IDevice.xcframework/ios-arm64"
SIM_SRC="$TMP/x/swift/IDevice.xcframework/ios-arm64_x86_64-simulator"
[ -d "$SRC" ] || { echo "❌ ios-arm64 slice missing from the release archive"; exit 1; }

rm -rf "$DEST"
mkdir -p "$DEST/ios-arm64"
cp -R "$SRC/." "$DEST/ios-arm64/"

# The simulator slice is only needed to build/inspect the UI on a Mac; set
# IDEVICE_WITH_SIM=1 to include it (adds ~230MB).
INCLUDE_SIM="${IDEVICE_WITH_SIM:-0}"
if [ "$INCLUDE_SIM" = "1" ] && [ -d "$SIM_SRC" ]; then
    mkdir -p "$DEST/ios-arm64_x86_64-simulator"
    cp -R "$SIM_SRC/." "$DEST/ios-arm64_x86_64-simulator/"
fi

/usr/bin/python3 - "$DEST/Info.plist" "$INCLUDE_SIM" <<'PY'
import plistlib, sys
libs = [{
    "LibraryIdentifier": "ios-arm64",
    "LibraryPath": "libidevice_ffi.a",
    "HeadersPath": "Headers",
    "SupportedArchitectures": ["arm64"],
    "SupportedPlatform": "ios",
}]
if len(sys.argv) > 2 and sys.argv[2] == "1":
    libs.append({
        "LibraryIdentifier": "ios-arm64_x86_64-simulator",
        "LibraryPath": "idevice-ios-sim.a",
        "HeadersPath": "Headers",
        "SupportedArchitectures": ["arm64", "x86_64"],
        "SupportedPlatform": "ios",
        "SupportedPlatformVariant": "simulator",
    })
plistlib.dump({
    "AvailableLibraries": libs,
    "CFBundlePackageType": "XFWK",
    "XCFrameworkFormatVersion": "1.0",
}, open(sys.argv[1], "wb"))
PY

echo "$VERSION" > "$DEST/.version"
echo "✅ IDevice.xcframework ready ($(du -sh "$DEST" | cut -f1), iOS arm64 only)"
