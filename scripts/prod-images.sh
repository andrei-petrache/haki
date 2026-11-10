#!/usr/bin/env bash
# Prints the app images prod would run at one revision of the repository:
# not the revision's own code, but the tags written at it. Renders
# k8s/overlays/prod as it is at that commit, so every form is covered: the
# overlay's own images: list (older revisions such as 00e3da8), the shared
# component (later ones) and a rollback pin.
#
# Three lines, each "<role> <tag>", every tag a full commit SHA (the commit
# of main whose CI published the image):
#   backend   the haki-backend Deployment (ghcr.io/andrei-petrache/haki-backend)
#   frontend  the haki-frontend Deployment (ghcr.io/andrei-petrache/haki-frontend)
#   migrate   the haki-migrate Job, the migration hook (haki-backend's image)
#
# Usage: scripts/prod-images.sh <full commit SHA>
# Needs the commit in this clone's history, kustomize and yq.
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

revision="${1:?usage: $0 <full commit SHA>}"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || fail "not a full commit SHA: '$revision'"
git cat-file -e "$revision^{commit}" 2>/dev/null || fail "commit $revision is not in this clone's history"

# The manifests as they are at that commit, outside the working tree
dir="$(mktemp -d)"
trap 'rm -rf "$dir"' EXIT
git archive "$revision" k8s | tar -x -C "$dir" \
  || fail "no k8s/ at ${revision:0:7}"
rendered="$(kustomize build "$dir/k8s/overlays/prod" 2>/dev/null)" \
  || fail "k8s/overlays/prod does not build at ${revision:0:7}"

registry=ghcr.io/andrei-petrache

# The one tag of <repository> that the workload <kind>/<name> runs: every
# container (init containers too) with an image of this registry must use
# that repository and one same full-SHA tag
tag_of() {
  local kind="$1" name="$2" repository="$3" images
  images="$(KIND="$kind" NAME="$name" yq -N \
    'select(.kind == strenv(KIND) and .metadata.name == strenv(NAME))
      | .spec.template.spec | [.initContainers[]?.image, .containers[]?.image] | .[]' \
    <<<"$rendered" | grep "^$registry/" | sort -u || true)"
  [[ -n "$images" ]] || fail "$kind/$name runs no image of $registry at ${revision:0:7}"
  [[ "$(wc -l <<<"$images")" == 1 ]] \
    || fail "$kind/$name runs more than one image at ${revision:0:7}: $(tr '\n' ' ' <<<"$images")"
  [[ "$images" =~ ^$registry/$repository:([0-9a-f]{40})$ ]] \
    || fail "$kind/$name runs $images at ${revision:0:7}, not $registry/$repository:<full commit SHA>"
  echo "${BASH_REMATCH[1]}"
}

# Assigned first: a failure inside $(...) stops the script only here, never
# inside echo's arguments
backend="$(tag_of Deployment haki-backend haki-backend)"
frontend="$(tag_of Deployment haki-frontend haki-frontend)"
migrate="$(tag_of Job haki-migrate haki-backend)"
echo "backend $backend"
echo "frontend $frontend"
echo "migrate $migrate"
