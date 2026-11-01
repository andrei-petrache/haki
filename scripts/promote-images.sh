#!/usr/bin/env bash
# Promotes images that CI already published to a release version, without
# rebuilding them: the tags MAJOR.MINOR.PATCH and MAJOR.MINOR are added to the
# exact digests published for the commit (tag = full commit SHA).
#
# Usage: scripts/promote-images.sh <registry> <commit-sha> <version>
#   e.g. scripts/promote-images.sh ghcr.io/andrei-petrache "$sha" 1.4.2
#
# Needs docker buildx and a login to the registry. Environment:
#   MOVE_MINOR=false  leave MAJOR.MINOR alone (when releasing an older patch
#                     than the newest one of that minor version)
#   GITHUB_STEP_SUMMARY, if set, receives a Markdown table of the digests.
set -euo pipefail

registry="${1:?usage: $0 <registry> <commit-sha> <version>}"
sha="${2:?usage: $0 <registry> <commit-sha> <version>}"
version="${3:?usage: $0 <registry> <commit-sha> <version>}"
move_minor="${MOVE_MINOR:-true}"
summary="${GITHUB_STEP_SUMMARY:-/dev/null}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  fail "'$version' is not MAJOR.MINOR.PATCH"
fi
minor="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"

# Digest of the manifest a reference points to, or nothing if it does not exist
digest_of() {
  docker buildx imagetools inspect "$1" --format '{{.Manifest.Digest}}' 2>/dev/null || true
}

# Without --prefer-index=false, imagetools wraps a single-platform manifest
# (what CI publishes) in a NEW index, so the tags would get another digest
if ! docker buildx imagetools create --help 2>/dev/null | grep -q -- '--prefer-index'; then
  fail "this docker buildx cannot copy a manifest as-is (no --prefer-index)"
fi

# Check everything first, so a release is either complete or not made at all
declare -A digests
for name in haki-backend haki-frontend; do
  image="$registry/$name"
  digest="$(digest_of "$image:$sha")"
  [[ -n "$digest" ]] ||
    fail "$image:$sha does not exist: CI publishes it only after every check passed on main"

  # A release tag never moves: re-running the same release is fine, moving it is not
  current="$(digest_of "$image:$version")"
  if [[ -n "$current" && "$current" != "$digest" ]]; then
    fail "$image:$version already points to $current, not $digest"
  fi
  digests[$name]="$digest"
done

tags=("$version")
if [[ "$move_minor" == true ]]; then
  tags+=("$minor")
fi

{
  echo "| Image | Tags | Digest |"
  echo "|---|---|---|"
} >> "$summary"

for name in haki-backend haki-frontend; do
  image="$registry/$name"
  digest="${digests[$name]}"
  args=()
  for tag in "${tags[@]}"; do
    args+=(--tag "$image:$tag")
  done
  # New names for the existing manifest, copied byte for byte: nothing is
  # built or wrapped, so the tags point to the exact tested digest
  docker buildx imagetools create --prefer-index=false "${args[@]}" "$image@$digest"

  for tag in "${tags[@]}"; do
    [[ "$(digest_of "$image:$tag")" == "$digest" ]] ||
      fail "$image:$tag does not point to $digest after promotion"
  done
  listed="${tags[*]}"
  listed="${listed// /, }"
  echo "$image: $listed -> $digest"
  echo "| \`$image\` | $listed (from \`${sha:0:12}\`) | \`$digest\` |" >> "$summary"
done
