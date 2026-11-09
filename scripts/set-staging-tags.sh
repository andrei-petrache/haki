#!/usr/bin/env bash
# Sets the newTag of the named images in k8s/components/images/kustomization.yaml
# to one commit SHA and proves that nothing else in the file changed. The
# building block of bump-staging-tag.sh and staging-rollback-pin.sh.
#
# Usage: scripts/set-staging-tags.sh <full commit SHA> <image name>...
# Needs yq (scripts/install-tools.sh).
set -euo pipefail

fail() {
  echo "$1" >&2
  exit 1
}

sha="${1:?usage: $0 <full commit SHA> <image name>...}"
shift
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "Not a full commit SHA: $sha"
(($# > 0)) || fail "usage: $0 <full commit SHA> <image name>..."

file="$(dirname "$0")/../k8s/components/images/kustomization.yaml"
tag() { yq ".images[] | select(.name == \"$1\") | .newTag" "$file"; }
for name in "$@"; do
  [[ -n "$(tag "$name")" ]] || fail "$name is not listed under images: in $file"
done

# Line by line, not yq -i: yq rewrites the file and drops comments and blank
# lines. Only a newTag line right under one of the named images changes. The
# tag is quoted: YAML reads a SHA of only digits (or digits around one "e")
# as a number.
before="$(mktemp)"
trap 'rm -f "$before"' EXIT
cp "$file" "$before"
awk -v sha="$sha" -v names="$*" '
  BEGIN { n = split(names, list, " "); for (i = 1; i <= n; i++) wanted["  - name: " list[i]] = 1 }
  pending && /^    newTag: "?[0-9a-f]{40}"?$/ { print "    newTag: \"" sha "\""; pending = 0; next }
  { pending = ($0 in wanted); print }
' "$before" > "$file"

# Proof: every changed line is a newTag line, and every named image has the SHA
other="$(diff "$before" "$file" | grep '^[<>]' | grep -Ev '^[<>]     newTag: "?[0-9a-f]{40}"?$' || true)"
for name in "$@"; do
  [[ "$(tag "$name")" == "$sha" ]] || other+=$'\n'"$name did not get the new tag"
done
if [[ -n "$other" ]]; then
  cp "$before" "$file"
  fail "Refusing the edit, it would change more than the tags:$other"
fi
