#!/usr/bin/env bash
# Sets haki-prod's targetRevision in k8s/argocd/haki-prod.yaml to one commit
# SHA and proves that nothing else in the file changed. The edit of the
# promote-prod workflow.
#
# Usage: scripts/set-prod-revision.sh <full commit SHA>
# Prints the previous revision. Needs yq (scripts/install-tools.sh).
set -euo pipefail

fail() {
  echo "$1" >&2
  exit 1
}

sha="${1:?usage: $0 <full commit SHA>}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "Not a full commit SHA: $sha"
file="$(dirname "$0")/../k8s/argocd/haki-prod.yaml"
old="$(yq '.spec.source.targetRevision' "$file")"

# Line by line, not yq -i: yq rewrites the file and drops comments
before="$(mktemp)"
trap 'rm -f "$before"' EXIT
cp "$file" "$before"
sed -i "s/^    targetRevision: [0-9a-f]\{40\}$/    targetRevision: $sha/" "$file"

# Proof: one line changed, it is targetRevision, and it holds the SHA
changed="$(diff "$before" "$file" | grep -c '^[<>]' || true)"
if [[ "$old" != "$sha" && "$changed" != 2 ]] \
  || [[ "$(yq '.spec.source.targetRevision' "$file")" != "$sha" ]] \
  || [[ "$(yq 'del(.spec.source.targetRevision)' "$before")" != "$(yq 'del(.spec.source.targetRevision)' "$file")" ]]; then
  cp "$before" "$file"
  fail "Refusing the edit: it would change more than targetRevision"
fi
echo "$old"
