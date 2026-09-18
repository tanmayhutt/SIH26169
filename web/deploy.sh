#!/usr/bin/env bash
# Publish the progress site: copies web/ plus the repository's Markdown into the server's
# web root. Run from the repository root:  bash web/deploy.sh
set -euo pipefail
HOST=${HOST:-ubuntu@15.206.247.203}
ROOT=${ROOT:-/srv/sih26169/site}
STAGE=$(mktemp -d)
cp web/index.html web/plan.html "$STAGE/"
mkdir -p "$STAGE/content/docs"
cp PROGRESS.md COMPLIANCE.md ARCHITECTURE.md README.md "$STAGE/content/"
cp docs/USER_MANUAL.md docs/TECHNICAL_REPORT.md "$STAGE/content/docs/"
ssh "$HOST" "sudo mkdir -p $ROOT && sudo chown -R ubuntu:ubuntu $ROOT"
rsync -az --delete "$STAGE/" "$HOST:$ROOT/"
rm -rf "$STAGE"
echo "published to $HOST:$ROOT"
