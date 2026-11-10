#!/usr/bin/env bash
# The rules of a promotion to prod: moving haki-prod's targetRevision from
# the current commit to a new one. Used by the promote-prod workflow before
# the approval, and by prod-guard on the promotion's pull request (from
# main's copy).
#
# - The new revision is a full commit SHA of main, other than the current
#   one, and CI published its images.
# - Forward (newer than the current one) or back (older): a rollback is a
#   promotion of an older commit, through the same workflow and approval.
# - Never back across a migration: the older image's `alembic upgrade head`
#   would stop at the hook (it does not know the newer revision). Then the
#   way back is a commit of main with a rollback pin (k8s/README.md), which
#   is newer and is promoted forward.
#
# Usage: scripts/check-promotion.sh <current SHA> <new SHA> <main ref>
# Prints a Markdown summary. Needs the history of main, yq and curl.
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

current="${1:?usage: $0 <current SHA> <new SHA> <main ref>}"
new="${2:?usage: $0 <current SHA> <new SHA> <main ref>}"
main="${3:?usage: $0 <current SHA> <new SHA> <main ref>}"
migrations=backend/migrations/versions

for sha in "$current" "$new"; do
  [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "not a full commit SHA: '$sha'"
  git cat-file -e "$sha^{commit}" 2>/dev/null || fail "commit $sha is not in this clone's history"
done
[[ "$new" != "$current" ]] || fail "prod already runs ${new:0:7}"
git merge-base --is-ancestor "$new" "$main" || fail "${new:0:7} is not a commit of main"

if git merge-base --is-ancestor "$current" "$new"; then
  direction=forward
  range="$current..$new"
elif git merge-base --is-ancestor "$new" "$current"; then
  direction=back
  range="$new..$current"
  git diff --quiet "$new" "$current" -- "$migrations" \
    || fail "${new:0:7} is older than ${current:0:7} and the migrations changed in between: its migration image would stop at the hook. Roll back with a rollback pin on main (k8s/README.md) and promote that commit."
else
  fail "${new:0:7} and ${current:0:7} are not on one line of history"
fi

images="$("$(dirname "$0")/check-published-images.sh" "$new")"

echo "### Promotion to prod: \`${current:0:7}\` -> \`${new:0:7}\` ($direction)"
echo
echo "- New revision: \`$new\`, a commit of main"
echo "- $images"
if [[ "$direction" == back ]]; then
  echo "- A rollback: no migration between the two commits"
fi
added="$(git diff --name-only --diff-filter=A "$range" -- "$migrations")"
if [[ "$direction" == forward && -n "$added" ]]; then
  echo "- **New migrations** (dump prod before merging the promotion):"
  sed 's/^/  - `/; s/$/`/' <<<"$added"
else
  echo "- No new migration"
fi
echo
echo "Commits $( [[ $direction == forward ]] && echo added || echo taken back ):"
echo
echo '```'
git log --oneline --no-decorate "$range"
echo '```'
