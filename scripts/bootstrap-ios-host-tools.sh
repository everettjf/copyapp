#!/bin/sh
# Optional host tools; never reads or obtains account/FairPlay credentials.
set -eu
case "${1:-}" in
  --ipatool) install_store=1; install_offline=0 ;;
  --offline) install_store=0; install_offline=1 ;;
  --all) install_store=1; install_offline=1 ;;
  *) echo "Usage: sh scripts/bootstrap-ios-host-tools.sh --ipatool|--offline|--all" >&2; exit 2 ;;
esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$task_root/toolchains/bin"
if [ "$install_store" -eq 1 ]; then
  command -v go >/dev/null || { echo "Go is required to build pinned ipatool v2.7.0" >&2; exit 1; }
  GOBIN="$task_root/toolchains/bin" go install -ldflags '-X github.com/majd/ipatool/v2/cmd.version=2.7.0' github.com/majd/ipatool/v2@v2.7.0
  "$task_root/toolchains/bin/ipatool" --version
fi
if [ "$install_offline" -eq 1 ]; then
  task_revision=1bad106ee1698c6d9c483f67d898183ffa4c6eb3
  task_source="$task_root/toolchains/fairplay-decrypt-src"
  if [ -e "$task_source" ]; then
    [ "$(git -C "$task_source" rev-parse HEAD)" = "$task_revision" ] || {
      echo "Existing FairPlay checkout differs from pinned revision; preserve it before selecting another directory." >&2; exit 1;
    }
  else
    git clone https://github.com/EthanArbuckle/fairplay-decrypt.git "$task_source"
    git -C "$task_source" checkout --detach "$task_revision"
  fi
  command -v cc >/dev/null || { echo "Apple command-line compiler is required" >&2; exit 1; }
  echo "Pinned sources ready. Install the optional Python dependency with: .venv/bin/python -m pip install '.[offline]'"
  echo "decrypt-offline checks source hashes before compiling or reading a credential. No credential was obtained."
  echo "For first credential preparation, install Xcode + ldid and use copyapp credential-retrieve with an explicit jailbroken device and App."
fi
