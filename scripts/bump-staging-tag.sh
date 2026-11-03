#!/usr/bin/env bash
# Moves staging to the images published for one commit: sets the backend and
# frontend tags in k8s/overlays/staging/kustomization.yaml (the backend tag
# covers the migration Job too) and changes nothing else.
#
# Usage: scripts/bump-staging-tag.sh <full commit SHA>
# Prints the previous tag. Needs yq (scripts/install-tools.sh).
set -euo pipefail

sha="${1:?usage: $0 <full commit SHA>}"
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Not a full commit SHA: $sha" >&2
  exit 1
fi

file="$(dirname "$0")/../k8s/overlays/staging/kustomization.yaml"
backend=ghcr.io/andrei-petrache/haki-backend
frontend=ghcr.io/andrei-petrache/haki-frontend

tag() { yq ".images[] | select(.name == \"$1\") | .newTag" "$file"; }
old_backend="$(tag "$backend")"
old_frontend="$(tag "$frontend")"
if [[ -z "$old_backend" || -z "$old_frontend" ]]; then
  echo "Both images must already be listed under images: in $file" >&2
  exit 1
fi
if [[ "$old_backend" != "$old_frontend" ]]; then
  echo "Staging runs different backend and frontend tags; bump by hand" >&2
  exit 1
fi

# Line by line, not yq -i: yq rewrites the file and drops comments and blank
# lines. Only a newTag line right under one of the two image names changes;
# the check below proves nothing else did. The tag is quoted: YAML reads a
# SHA of only digits (or digits around one "e") as a number.
awk -v sha="$sha" -v b="$backend" -v f="$frontend" '
  pending && /^    newTag: "?[0-9a-f]{40}"?$/ { print "    newTag: \"" sha "\""; pending = 0; next }
  { pending = ($0 == "  - name: " b || $0 == "  - name: " f); print }
' "$file" > "$file.new"
mv "$file.new" "$file"

changed="$(git diff --numstat -- "$file" | awk '{print $1 + $2}')"
if [[ "$old_backend" != "$sha" && "$changed" != 4 ]]; then
  echo "Expected exactly the two tag lines to change, got: $(git diff --stat -- "$file")" >&2
  git checkout -- "$file"
  exit 1
fi
echo "$old_backend"
