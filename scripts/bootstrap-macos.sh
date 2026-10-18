#!/bin/sh
# Install the Copy APP Mac CLI in a repository-local virtual environment.
set -eu

usage() {
    cat <<'EOF'
Usage: sh scripts/bootstrap-macos.sh [--trace]

Without options, install only what is needed for the first USB survey.
--trace also installs the host Frida Python package for deeper analysis.
The script does not change the connected iPhone or install Xcode.
EOF
}

trace=0
case "${1:-}" in
    "") ;;
    --trace) trace=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    usage >&2
    exit 2
fi

if [ "$(uname -s)" != Darwin ]; then
    echo "Copy APP device setup currently requires macOS." >&2
    exit 1
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=${PYTHON3:-python3}
if ! command -v "$python" >/dev/null 2>&1; then
    echo "Python 3.9 or newer is required." >&2
    exit 1
fi
if ! "$python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "Python 3.9 or newer is required." >&2
    exit 1
fi

new_venv=0
if [ ! -d "$root/.venv" ]; then
    "$python" -m venv "$root/.venv"
    new_venv=1
fi
venv_python="$root/.venv/bin/python"
if [ ! -x "$venv_python" ]; then
    echo "The existing .venv is incomplete; inspect it before retrying." >&2
    exit 1
fi

if [ "$new_venv" -eq 1 ] || ! "$venv_python" -c '
import pip, setuptools, wheel
def version(value):
    return tuple(int(part) for part in value.split(".")[:2])
raise SystemExit(0 if version(pip.__version__) >= (21, 3) and
                 version(setuptools.__version__) >= (64, 0) else 1)
' >/dev/null 2>&1; then
    printf 'Preparing Python packaging tools...\n'
    "$venv_python" -m pip install --quiet --upgrade pip setuptools wheel
fi
printf 'Installing Copy APP in .venv...\n'
if [ "$trace" -eq 1 ]; then
    "$venv_python" -m pip install --quiet --no-build-isolation -e "$root[trace]"
else
    "$venv_python" -m pip install --quiet --no-build-isolation -e "$root"
fi
"$root/.venv/bin/copyapp" --help >/dev/null

printf '\nCopy APP Mac CLI is ready. Next:\n'
printf '  .venv/bin/copyapp onboard\n'
printf '  If several devices are connected, rerun with --udid <UDID>.\n'
if [ "$trace" -eq 0 ]; then
    printf '\nFor runtime tracing later: sh scripts/bootstrap-macos.sh --trace\n'
fi
if ! xcodebuild -version >/dev/null 2>&1; then
    printf '\nFull Xcode is needed later for developer services and rebuilt apps.\n'
fi
