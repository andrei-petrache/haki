#!/usr/bin/env bash
# Checks the scope of a pull request from the tag bot's branch: it may only
# set the newTag of the backend, frontend and migration images in
# k8s/overlays/staging/kustomization.yaml, all three to one full commit SHA,
# and may not run while a rollback pin is active. Auto-merge relies on this
# check. Any other pull request passes without being looked at.
#
# Usage: scripts/check-tag-pr.sh <head branch> <base SHA> <head SHA>
# Needs the history of both SHAs and yq (scripts/install-tools.sh).
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

branch="${1:?usage: $0 <head branch> <base SHA> <head SHA>}"
base="${2:?usage: $0 <head branch> <base SHA> <head SHA>}"
head="${3:?usage: $0 <head branch> <base SHA> <head SHA>}"

if [[ "$branch" != bot/bump-staging ]]; then
  echo "Not a tag pull request (branch $branch): nothing to check"
  exit 0
fi

file=k8s/overlays/staging/kustomization.yaml
pin=k8s/overlays/staging/rollback-pin.yaml
images=(ghcr.io/andrei-petrache/haki-backend ghcr.io/andrei-petrache/haki-frontend haki-migrate)

# Three dots: what the pull request itself changes, from where it left main
files="$(git diff --name-only "$base...$head")"
[[ "$files" == "$file" ]] \
  || fail "a tag pull request may change only $file; it changes: $(tr '\n' ' ' <<<"$files")"
! git cat-file -e "$head:$pin" 2>/dev/null \
  || fail "a rollback pin is active on this branch: no tag pull request until it is lifted"

# Every changed line is a newTag line, three of them added
lines="$(git diff -U0 "$base...$head" -- "$file" | grep -E '^[-+] ' || true)"
other="$(grep -Ev '^[-+]    newTag: "?[0-9a-f]{40}"?$' <<<"$lines" || true)"
[[ -z "$other" ]] || fail "only newTag lines may change; also changed: $other"
[[ "$(grep -c '^+' <<<"$lines")" == 3 ]] \
  || fail "exactly the three newTag lines must change (backend, frontend, migration)"

# And they are the three images' tags: the file read as YAML, without the
# tags, is the same before and after, and the three tags are one SHA
show() { git show "$1:$file" | yq "$2"; }
[[ "$(show "$base" 'del(.images[].newTag)')" == "$(show "$head" 'del(.images[].newTag)')" ]] \
  || fail "something other than a newTag value changed"
merge_base="$(git merge-base "$base" "$head")"
sha=""
for image in "${images[@]}"; do
  tag="$(show "$head" ".images[] | select(.name == \"$image\") | .newTag")"
  [[ "$tag" =~ ^[0-9a-f]{40}$ ]] || fail "$image: '$tag' is not a full commit SHA"
  [[ -z "$sha" || "$tag" == "$sha" ]] || fail "the three tags must be one SHA; $image has ${tag:0:7}, not ${sha:0:7}"
  sha="$tag"
  [[ "$(show "$merge_base" ".images[] | select(.name == \"$image\") | .newTag")" != "$tag" ]] \
    || fail "$image: the tag did not change"
done
echo "Tag pull request: backend, frontend and migration move to ${sha:0:7}, nothing else changes"
