#!/usr/bin/env bash
# Build both macOS desktop archives on an Apple silicon Mac and publish them on the project site.
# The Apple silicon build runs natively; the Intel build runs through Rosetta with an x86_64
# Python (uv installs it). Each archive gets the same smoke test and package check the GitHub
# workflow runs. GitHub then only builds Windows and Linux, which cost about 1/10 of a macOS minute.
#
#   bash tools/build_macos.sh              # build, check and upload both
#   bash tools/build_macos.sh --no-upload  # build and check only (archives in out/)
#
# Needs: uv, Rosetta (softwareupdate --install-rosetta), zip, and SSH access to the server.
set -euo pipefail
HOST=${HOST:-ubuntu@15.206.247.203}
DEST=${DEST:-/srv/sih26169/site/downloads}
HERE=$(cd "$(dirname "$0")/.." && pwd); cd "$HERE"
[ "$(uname -m)" = "arm64" ] || { echo "run this on an Apple silicon Mac"; exit 1; }
mkdir -p out

build() {   # build <label> <python> [arch-prefix...]
  local label=$1 py=$2; shift 2
  echo "== $label"
  rm -rf build dist/ARGUS
  "$@" "$py" -m PyInstaller --noconfirm --clean fsoc_tracker.spec > "out/build-$label.log" 2>&1
  ( cd dist/ARGUS && "$@" ./ARGUS run -s configs/scenarios/clear_line.yaml --duration 2 --seed 0 --out results/smoke > /dev/null
    ls results/smoke/FSOC_*_report.pdf > /dev/null && rm -rf results configs models docs )
  rm -f "out/ARGUS-$label.zip"; ( cd dist && zip -qry "../out/ARGUS-$label.zip" ARGUS )
  QT_QPA_PLATFORM=offscreen "$@" "$py" tests/package_check.py "out/ARGUS-$label.zip" | tail -1
}

[ -x .venv/bin/python ] || { echo "no .venv; run: uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e '.[dev]'"; exit 1; }
build macos-arm64 .venv/bin/python

if [ ! -x .venv-intel/bin/python ]; then
  uv python install cpython-3.12-macos-x86_64-none
  uv venv --python cpython-3.12-macos-x86_64-none .venv-intel
  uv pip install --python .venv-intel/bin/python -e ".[dev]"
fi
build macos-intel .venv-intel/bin/python arch -x86_64

ls -l out/ARGUS-macos-*.zip
if [ "${1:-}" != "--no-upload" ]; then
  scp -o BatchMode=yes out/ARGUS-macos-arm64.zip out/ARGUS-macos-intel.zip "$HOST:$DEST/"
  echo "published to $HOST:$DEST"
fi
