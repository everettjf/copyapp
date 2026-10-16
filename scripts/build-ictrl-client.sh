#!/bin/sh
set -eu

copyapp_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
workspace_dir=$(CDPATH= cd -- "$copyapp_dir/.." && pwd)
source_dir="$workspace_dir/upstream/ictrl"
binary_dir="$workspace_dir/toolchains"
revision=d88bbf0b3a5addead31b4298d605d7ac7a87d6e7

if [ ! -d "$source_dir/.git" ]; then
  mkdir -p "$workspace_dir/upstream"
  git clone https://github.com/OpenMinis/iCTRL.git "$source_dir"
  git -C "$source_dir" checkout --detach "$revision"
fi
actual=$(git -C "$source_dir" rev-parse HEAD)
if [ "$actual" != "$revision" ]; then
  echo "iCTRL checkout is $actual; expected $revision. Inspect it before building." >&2
  exit 1
fi

mkdir -p "$binary_dir"
cd "$source_dir/cli"
cc -O2 -std=c11 -o "$binary_dir/ictrl-macos" main.c sha256.c x25519.c util.c nearby.c
cc -O2 -std=c11 -o "$binary_dir/ictrl-selftest" selftest.c sha256.c x25519.c util.c
"$binary_dir/ictrl-selftest"
echo "Built $binary_dir/ictrl-macos from iCTRL $revision"
