#!/usr/bin/env bash
#
# Create Config/Local.xcconfig — your team and bundle-id prefix for local builds.
#
#   Scripts/setup-signing.sh               (called by `make` when the file is missing)
#   DEVELOPMENT_TEAM=ABCDE12345 ICTRL_BUNDLE_PREFIX=com.example.you Scripts/setup-signing.sh
#
# Team, in order: $DEVELOPMENT_TEAM, then the team of the first "Apple
# Development" certificate in your keychain (Xcode puts it there when you sign
# in under Settings → Accounts — a free Apple ID works). Prefix: $ICTRL_BUNDLE_PREFIX,
# else one derived from the team, so it can't collide with anyone else's App IDs.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO/Config/Local.xcconfig"

TEAM="${DEVELOPMENT_TEAM:-}"
if [[ -z "$TEAM" ]]; then
    # The team id is the certificate's OU — the id in the identity's NAME is
    # the holder's, not the team's, so it has to come from the certificate.
    NAME="$(security find-identity -v -p codesigning | sed -nE 's/.*"(Apple Development: [^"]*)".*/\1/p' | head -1 || true)"
    if [[ -n "$NAME" ]]; then
        TEAM="$(security find-certificate -c "$NAME" -p 2>/dev/null \
                | openssl x509 -noout -subject -nameopt multiline 2>/dev/null \
                | awk -F' = ' '/organizationalUnitName/ { print $2; exit }' || true)"
    fi
fi
if [[ -z "$TEAM" ]]; then
    cat >&2 <<MSG
❌ No development team found.
   Sign in to Xcode (Settings → Accounts — a free Apple ID works), let it create
   an "Apple Development" certificate, and run make again. Or set it directly:
     DEVELOPMENT_TEAM=ABCDE12345 make ipa
MSG
    exit 1
fi

PREFIX="${ICTRL_BUNDLE_PREFIX:-com.copyapp.$(echo "$TEAM" | tr '[:upper:]' '[:lower:]')}"

cat > "$OUT" <<CONF
// Your local signing settings — gitignored, read by Config/Signing.xcconfig.
// Edit freely; delete this file to have it detected again.
DEVELOPMENT_TEAM = $TEAM
ICTRL_BUNDLE_PREFIX = $PREFIX
CONF
echo "🔑 Config/Local.xcconfig: team $TEAM, bundle ids $PREFIX.ictrl[.uitests]"
