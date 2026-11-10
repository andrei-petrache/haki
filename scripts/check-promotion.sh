#!/usr/bin/env bash
# The rules of a promotion to prod: moving haki-prod's targetRevision from
# the current commit to a new one. Used by the promote-prod workflow before
# the approval, and by prod-guard on the promotion's pull request (from
# main's copy).
#
# Prod does not run the revision's own code: it runs the image tags written
# at that revision (scripts/prod-images.sh: backend, frontend and the
# migration Job's haki-migrate). So the revision is judged as a commit, and
# the images and migrations by those tags:
#
# - The new revision is a full commit SHA of main, other than the current
#   one; forward (newer than the current one) or back (older). A rollback is
#   a promotion of an older commit, through the same workflow and approval.
# - Each image the new revision runs is a commit of main whose CI published
#   it on GHCR.
# - Migrations are counted between the two haki-migrate images, not between
#   the revisions: the new migrations are those added from the current
#   migration image's commit to the new one's, and the migration image never
#   steps back across a migration (the older image's `alembic upgrade head`
#   would stop at the hook: it does not know the newer revision). Then the
#   way back is a commit of main with a rollback pin (k8s/README.md), which
#   keeps the newer migration image and is promoted like any other commit.
#
# Usage: scripts/check-promotion.sh <current SHA> <new SHA> <main ref>
# Prints a Markdown summary. Needs the history of main, kustomize, yq and
# curl.
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

current="${1:?usage: $0 <current SHA> <new SHA> <main ref>}"
new="${2:?usage: $0 <current SHA> <new SHA> <main ref>}"
main="${3:?usage: $0 <current SHA> <new SHA> <main ref>}"
here="$(dirname "$0")"
migrations=backend/migrations/versions

for sha in "$current" "$new"; do
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "not a full commit SHA: '$sha'"
  git cat-file -e "$sha^{commit}" 2>/dev/null || fail "commit $sha is not in this clone's history"
done
[[ "$new" != "$current" ]] || fail "prod already runs ${new:0:7}"
# Before anything reads the new revision's files: only main's commits
git merge-base --is-ancestor "$new" "$main" || fail "${new:0:7} is not a commit of main"

if git merge-base --is-ancestor "$current" "$new"; then
  direction=forward
  range="$current..$new"
elif git merge-base --is-ancestor "$new" "$current"; then
  direction=back
  range="$new..$current"
else
  fail "${new:0:7} and ${current:0:7} are not on one line of history"
fi

# The images prod runs now and would run after: "<role> <tag>" lines
now="$("$here/prod-images.sh" "$current")" || fail "cannot tell which images prod runs at ${current:0:7} (above)"
after="$("$here/prod-images.sh" "$new")" || fail "cannot tell which images prod would run at ${new:0:7} (above)"
tag() { awk -v role="$1" '$1 == role { print $2 }' <<<"$2"; }

for role in backend frontend migrate; do
  t="$(tag "$role" "$after")"
  git cat-file -e "$t^{commit}" 2>/dev/null && git merge-base --is-ancestor "$t" "$main" \
    || fail "${new:0:7} runs the $role image ${t:0:7}, which is not a commit of main"
done
published="$("$here/check-published-images.sh" \
  "haki-backend:$(tag backend "$after")" \
  "haki-frontend:$(tag frontend "$after")" \
  "haki-backend:$(tag migrate "$after")")"

# Migrations: between the commits of the two migration images
from="$(tag migrate "$now")"
to="$(tag migrate "$after")"
git cat-file -e "$from^{commit}" 2>/dev/null \
  || fail "prod's current migration image ${from:0:7} is not a commit in this clone's history"
added=""
if [[ "$to" == "$from" ]]; then
  migration="the same migration image, \`${to:0:7}\`"
elif git merge-base --is-ancestor "$from" "$to"; then
  migration="the migration image moves forward, \`${from:0:7}\` -> \`${to:0:7}\`"
  added="$(git diff --name-only --diff-filter=A "$from..$to" -- "$migrations")"
elif git merge-base --is-ancestor "$to" "$from"; then
  git diff --quiet "$to" "$from" -- "$migrations" \
    || fail "${new:0:7} runs the migration image ${to:0:7}, older than prod's ${from:0:7}, and the migrations changed in between: it would stop at the hook. Roll back with a rollback pin on main (k8s/README.md) and promote that commit."
  migration="the migration image steps back, \`${from:0:7}\` -> \`${to:0:7}\`, with no migration between them"
else
  fail "the migration images ${from:0:7} (now) and ${to:0:7} (${new:0:7}) are not on one line of history"
fi

echo "### Promotion to prod: \`${current:0:7}\` -> \`${new:0:7}\` ($direction)"
echo
echo "- New revision: \`$new\`, a commit of main"
echo "- $published"
echo "- Migrations: $migration"
if [[ -n "$added" ]]; then
  echo "- **New migrations** (dump prod before merging the promotion):"
  sed 's/^/  - `/; s/$/`/' <<<"$added"
else
  echo "- No new migration"
fi
echo
echo "| Image | Now (\`${current:0:7}\`) | After (\`${new:0:7}\`) |"
echo "| --- | --- | --- |"
for role in backend frontend migrate; do
  echo "| $role | \`$(tag "$role" "$now" | cut -c1-7)\` | \`$(tag "$role" "$after" | cut -c1-7)\` |"
done
echo
echo "Commits $( [[ $direction == forward ]] && echo added || echo taken back ) (revisions):"
echo
echo '```'
git log --oneline --no-decorate "$range"
echo '```'
