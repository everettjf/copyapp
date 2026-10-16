#!/usr/bin/env bash
#
# Turn the IPAs `make ipa` produced into ones fit to publish.
#
#   Scripts/package-release.sh [OUT_DIR]      (default: release/)
#
# A local build is signed for the developer's own team, and its
# embedded.mobileprovision carries their name, team id and the UDID of every
# device on the account. None of that belongs in a public download, and none of
# it is needed: whoever installs the package re-signs it (SideStore, or
# Scripts/sign-ipa.sh), which replaces both the profile and the signature.
#
# So each package is unpacked, stripped of its profile, ad-hoc signed inside out
# (same order as sign-ipa.sh — the nested .xctest first), checked for leftovers,
# and repacked.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-$REPO/release}"
mkdir -p "$OUT_DIR"

strip_one() {
    local ipa="$1" work app name team
    work="$(mktemp -d)"
    unzip -q "$ipa" -d "$work"
    app="$(find "$work/Payload" -maxdepth 1 -name '*.app' -type d | head -1)"
    name="$(basename "$ipa")"
    # The team the build was signed with — read before the signature is replaced.
    team="$(codesign -dv "$app" 2>&1 | awk -F= '/^TeamIdentifier/ { print $2 }')"

    # Profiles anywhere in the bundle, not just the top level.
    find "$app" -name 'embedded.mobileprovision' -delete

    local sign=(codesign --force --timestamp=none --sign -)
    while IFS= read -r f; do "${sign[@]}" "$f" 2>/dev/null; done \
        < <(find "$app" -name '*.dylib' -not -path '*.framework/*' | awk '{ print length, $0 }' | sort -rn | cut -d' ' -f2-)
    while IFS= read -r f; do "${sign[@]}" "$f" 2>/dev/null; done \
        < <(find "$app" -name '*.framework' -type d | awk '{ print length, $0 }' | sort -rn | cut -d' ' -f2-)
    for plugin in "$app"/PlugIns/*; do
        [[ -d "$plugin" ]] && "${sign[@]}" "$plugin" 2>/dev/null
    done
    "${sign[@]}" "$app" 2>/dev/null
    codesign --verify --deep --strict "$app"

    # Nothing identifying may survive. The team id is the one string that is
    # in every developer-signed artifact, so it is the check that matters.
    if find "$app" -name '*.mobileprovision' | grep -q .; then
        echo "❌ $name: a provisioning profile survived" >&2; exit 1
    fi
    if [[ -n "$team" ]] && grep -rl --binary-files=text "$team" "$app" >/dev/null 2>&1; then
        echo "❌ $name: still contains team id $team:" >&2
        grep -rl --binary-files=text "$team" "$app" | sed "s#$work/##" >&2
        exit 1
    fi

    rm -f "$OUT_DIR/$name"
    (cd "$work" && zip -qry "$OUT_DIR/$name" Payload)
    rm -rf "$work"
    echo "✅ $OUT_DIR/$name ($(du -h "$OUT_DIR/$name" | cut -f1 | tr -d ' '))"
}

for ipa in "$REPO/iCTRLUITests-Runner.ipa" "$REPO/iCTRL.ipa"; do
    [[ -f "$ipa" ]] || { echo "❌ $ipa missing — run make ipa first" >&2; exit 1; }
    strip_one "$ipa"
done
