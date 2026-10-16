#!/bin/sh
set -eu

copyapp_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_dir="$copyapp_dir/vendor/ictrl"
binary_dir="$copyapp_dir/toolchains"

mkdir -p "$binary_dir"
cd "$source_dir/cli"
cc -O2 -std=c11 -o "$binary_dir/ictrl-macos" main.c sha256.c x25519.c util.c nearby.c
cc -O2 -std=c11 -o "$binary_dir/ictrl-selftest" selftest.c sha256.c x25519.c util.c
"$binary_dir/ictrl-selftest"
echo "Built $binary_dir/ictrl-macos from vendored iCTRL d88bbf0b3a5addead31b4298d605d7ac7a87d6e7"
