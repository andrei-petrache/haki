#!/usr/bin/env bash
# Checks that CI published images on GHCR, by image and tag: the tags a
# revision runs (scripts/prod-images.sh), which are not the revision's own
# SHA. The packages are public, so this needs neither docker nor a login: an
# anonymous pull token and a HEAD request on each manifest.
#
# Usage: scripts/check-published-images.sh <image>:<tag>...
#   <image> haki-backend or haki-frontend, <tag> a full commit SHA
#   e.g. haki-backend:4b65cc66f78f25d66a8f6c8d669fc4e25f6c0add
# Needs yq and curl.
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

(($# > 0)) || fail "usage: $0 <image>:<tag>..."

accept="application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json"
accept+=", application/vnd.docker.distribution.manifest.list.v2+json"
accept+=", application/vnd.docker.distribution.manifest.v2+json"

checked=()
# Each image:tag once (the migration Job usually runs the backend's tag)
for ref in $(printf '%s\n' "$@" | sort -u); do
  image="${ref%%:*}"
  tag="${ref#*:}"
  [[ "$image" =~ ^haki-(backend|frontend)$ ]] || fail "not an image of Haki: '$ref'"
  [[ "$tag" =~ ^[0-9a-f]{40}$ ]] || fail "not a full commit SHA as the tag: '$ref'"
  repository="andrei-petrache/$image"
  token="$(curl -fsS "https://ghcr.io/token?scope=repository:$repository:pull" | yq -p json -o yaml '.token')" \
    || fail "no pull token from GHCR for $repository"
  status="$(curl -s -o /dev/null -w '%{http_code}' -I \
    -H "Authorization: Bearer $token" -H "Accept: $accept" \
    "https://ghcr.io/v2/$repository/manifests/$tag")"
  [[ "$status" == 200 ]] \
    || fail "ghcr.io/$repository:$tag is not published (HTTP $status): only images that CI published for a commit of main can be deployed"
  checked+=("$image:${tag:0:7}")
done
echo "Published on GHCR: ${checked[*]}"
