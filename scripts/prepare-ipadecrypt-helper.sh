#!/bin/sh
# Fetch the reviewed upstream source and its reproducibly built iOS helper.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/.." && pwd)
source_dir="$root/../toolchains/ipadecrypt-src"
helper_out="$root/../toolchains/ipadecrypt-helper-arm64"
revision=2fa69244cc6e580cd05f781db57912c79a4c3197
expected=8fe2ace941132c29d19480adba554ebd71d2a1ea27a2c7c6ee1eb648a504151b

if [ ! -d "$source_dir/.git" ]; then
    git clone https://github.com/londek/ipadecrypt.git "$source_dir"
fi
git -C "$source_dir" fetch origin "$revision"
git -C "$source_dir" checkout --detach "$revision"
actual=$(shasum -a 256 "$source_dir/internal/device/ipadecrypt-helper-arm64" | awk '{print $1}')
if [ "$actual" != "$expected" ]; then
    echo "ipadecrypt helper hash mismatch" >&2
    exit 1
fi
cp "$source_dir/internal/device/ipadecrypt-helper-arm64" "$helper_out"
echo "$helper_out"
