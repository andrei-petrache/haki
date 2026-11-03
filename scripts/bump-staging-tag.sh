#!/usr/bin/env bash
# Moves staging to the images published for one commit: sets the backend,
# frontend and migration tags in k8s/overlays/staging/kustomization.yaml and
# changes nothing else. Refuses while a rollback pin is active: staging then
# takes no new backend tag until the pin is lifted (k8s/README.md).
#
# Usage: scripts/bump-staging-tag.sh <full commit SHA>
# Prints the previous backend tag. Needs yq (scripts/install-tools.sh).
set -euo pipefail

fail() {
  echo "$1" >&2
  exit 1
}

sha="${1:?usage: $0 <full commit SHA>}"
dir="$(dirname "$0")"
overlay="$dir/../k8s/overlays/staging"
file="$overlay/kustomization.yaml"

[[ ! -e "$overlay/rollback-pin.yaml" ]] \
  || fail "A rollback pin is active (k8s/overlays/staging/rollback-pin.yaml): no new backend tag until it is lifted with scripts/staging-rollback-pin.sh end"

tag() { yq ".images[] | select(.name == \"$1\") | .newTag" "$file"; }
old_backend="$(tag ghcr.io/andrei-petrache/haki-backend)"
old_frontend="$(tag ghcr.io/andrei-petrache/haki-frontend)"
[[ "$old_backend" == "$old_frontend" ]] \
  || fail "Staging runs different backend and frontend tags; bump by hand"

"$dir/set-staging-tags.sh" "$sha" \
  ghcr.io/andrei-petrache/haki-backend ghcr.io/andrei-petrache/haki-frontend haki-migrate
echo "$old_backend"
