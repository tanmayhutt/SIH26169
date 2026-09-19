#!/usr/bin/env bash
# Download the desktop application archives built by the GitHub Actions workflow into dist/,
# so that webapp/deploy.sh can publish them under /downloads/.
#   bash webapp/fetch_builds.sh            # latest successful run of the build workflow
#   bash webapp/fetch_builds.sh <run-id>   # a specific run
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
RUN=${1:-$(gh run list --workflow=build.yml --status=success --limit 1 --json databaseId -q '.[0].databaseId')}
[ -n "$RUN" ] || { echo "no successful build run found"; exit 1; }
TMP=$(mktemp -d)
gh run download "$RUN" -D "$TMP"
mkdir -p "$HERE/dist"
find "$TMP" -type f \( -name '*.zip' -o -name '*.tar.gz' \) -exec cp {} "$HERE/dist/" \;
rm -rf "$TMP"
ls -l "$HERE"/dist/*.zip "$HERE"/dist/*.tar.gz 2>/dev/null
