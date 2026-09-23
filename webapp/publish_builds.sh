#!/usr/bin/env bash
# Publish the desktop archives of a build-workflow run on the project site.
# The server downloads them itself (a home connection often times out on 700 MB).
#
#   bash webapp/publish_builds.sh               # latest successful run of build.yml
#   bash webapp/publish_builds.sh <run-id>      # a specific run
#
# Needs: the GitHub CLI logged in with access to the repository (gh auth status), and SSH
# access to the server (ask the project owner to add your public key). The GitHub token is
# passed to the server on standard input for the download only and is not stored there.
set -euo pipefail
HOST=${HOST:-ubuntu@15.206.247.203}
REPO_SLUG=${REPO_SLUG:-tanmayhutt/SIH26169}
DEST=${DEST:-/srv/sih26169/site/downloads}
RUN=${1:-$(gh run list --workflow=build.yml --status=completed --limit 1 --json databaseId -q '.[0].databaseId')}
[ -n "$RUN" ] || { echo "no successful build run found"; exit 1; }
# every platform build must have passed (tests, packaging, packaged-app check); the run as a whole
# can still fail in later jobs that do not affect the archives (for example GitHub release publishing)
BAD=$(gh run view "$RUN" --json jobs -q '[.jobs[] | select(.name | startswith("build (")) | select(.conclusion != "success")] | length')
NB=$(gh run view "$RUN" --json jobs -q '[.jobs[] | select(.name | startswith("build ("))] | length')
[ "$NB" -ge 4 ] && [ "$BAD" = "0" ] || { echo "run $RUN: not all four platform builds succeeded; not publishing"; exit 1; }
LIST=$(gh api "repos/$REPO_SLUG/actions/runs/$RUN/artifacts" -q '.artifacts[] | "\(.id) \(.name)"')
echo "publishing run $RUN:"; echo "$LIST"
# the remote script goes as an argument; standard input carries only the token and the list
# (a heredoc and a pipe cannot both be standard input: the heredoc would win)
REMOTE_SCRIPT=$(cat <<'REMOTE'
set -euo pipefail
read -r T
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT; cd "$W"
while read -r id name; do
  [ -n "$id" ] || continue
  url=$(curl -sS -o /dev/null -w "%{redirect_url}" -H "Authorization: Bearer $T" -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$REPO_SLUG/actions/artifacts/$id/zip")
  curl -sS --retry 3 -o "$name.zip" "$url" && unzip -oq "$name.zip" -d out && echo "fetched $name"
done
unset T
for f in out/*.zip out/*.tar.gz; do [ -f "$f" ] && install -m 644 "$f" "$DEST/"; done
ls -la "$DEST" | grep -E "zip|tar"
REMOTE
)
{ gh auth token; echo "$LIST"; } | ssh -o BatchMode=yes "$HOST" "REPO_SLUG=$REPO_SLUG DEST=$DEST bash -c $(printf '%q' "$REMOTE_SCRIPT")"
