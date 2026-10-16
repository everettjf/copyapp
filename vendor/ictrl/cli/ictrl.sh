#!/bin/sh
# Entry point for the bundled iCTRL CLI.
#
# Run it as `sh ictrl.sh`, which needs no exec bit itself. Two ways the binary
# next to it can still refuse to run, both seen in Minis:
#
#   - it arrived without the exec bit (the skill importer writes every file
#     0644 and never chmods) — fixed by chmod;
#   - it sits on a filesystem that ignores the exec bit altogether, such as
#     /var/minis/workspace: chmod "succeeds" and exec still fails with
#     "Permission denied", however often it is retried.
#
# For the second case the binary is copied to ~/.ictrl/bin (next to the key in
# ~/.ictrl/token.json, on an executable filesystem) and run from there. That is
# also the location the skill tells agents to install to, so later sessions find
# it instead of downloading another copy.
#
# Usage: sh ictrl.sh [--host HOST:PORT] <command> [args...]
#        sh ictrl.sh update [SKILL_DIR]   refresh the client (and SKILL.md in
#                                         SKILL_DIR) from the device

dir=$(cd "$(dirname "$0")" && pwd)
bin="$dir/ictrl"
home_dir="${HOME:-/root}/.ictrl/bin"

# update: pull the client and the skill from the device itself, so they always
# match the running build. Everything is written to a temp file and renamed into
# place — sh reads this script while running it, so overwriting it in place
# would corrupt the run doing the update.
if [ "$1" = "update" ]; then
    base="http://${ICTRL_HOST:-127.0.0.1:8200}"
    fetch() { wget -qO "$2.new" "$base$1" && [ -s "$2.new" ] && mv "$2.new" "$2" || { rm -f "$2.new"; echo "ictrl.sh: could not fetch $base$1" >&2; exit 1; }; }
    if [ -n "$2" ] && [ ! -d "$2" ]; then echo "ictrl.sh: $2 is not a directory" >&2; exit 1; fi
    mkdir -p "$home_dir" || exit 1
    fetch /skill/clients/cli "$home_dir/ictrl"
    fetch /skill/clients/cli.sh "$home_dir/ictrl.sh"
    chmod +x "$home_dir/ictrl" 2>/dev/null
    echo "updated client in $home_dir"
    if [ -n "$2" ]; then
        fetch /skill "$2/SKILL.md"
        [ -f "$2/ictrl" ] && cp "$home_dir/ictrl" "$2/ictrl"
        [ -f "$2/ictrl.sh" ] && cp "$home_dir/ictrl.sh" "$2/ictrl.sh"
        echo "updated $2/SKILL.md to $(sed -n 's/^skill_version: *//p' "$2/SKILL.md" | tr -d '"') — re-read it now"
    fi
    exit 0
fi

if [ ! -f "$bin" ]; then
    echo "ictrl.sh: $bin not found — download it: wget -qO $bin http://127.0.0.1:8200/skill/clients/cli" >&2
    exit 1
fi

[ -x "$bin" ] || chmod +x "$bin" 2>/dev/null || true

# Probe with a no-op command: an unknown subcommand prints usage and exits 2
# without touching the network. 126/127 mean the kernel refused to run it.
runs() {
    "$1" __probe >/dev/null 2>&1
    rc=$?
    [ "$rc" -ne 126 ] && [ "$rc" -ne 127 ]
}

if runs "$bin"; then
    exec "$bin" "$@"
fi

mkdir -p "$home_dir" || exit 1
cmp -s "$bin" "$home_dir/ictrl" 2>/dev/null || cp "$bin" "$home_dir/ictrl" || exit 1
chmod +x "$home_dir/ictrl"
[ "$dir" = "$home_dir" ] || cp "$0" "$home_dir/ictrl.sh" 2>/dev/null
if ! runs "$home_dir/ictrl"; then
    echo "ictrl.sh: cannot execute $home_dir/ictrl either — is HOME on a noexec filesystem?" >&2
    exit 126
fi
echo "ictrl.sh: binaries can't run from $dir (the filesystem ignores the exec bit);" \
     "using $home_dir/ictrl — call sh $home_dir/ictrl.sh from now on" >&2
exec "$home_dir/ictrl" "$@"
