#!/usr/bin/env bash
# Checks that CI published the backend and frontend images of one commit on
# GHCR. The packages are public, so this needs neither docker nor a login:
# an anonymous pull token and a HEAD request on each manifest.
#
# Usage: scripts/check-published-images.sh <full commit SHA>
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

sha="${1:?usage: $0 <full commit SHA>}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "not a full commit SHA: '$sha'"

accept="application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json"
accept+=", application/vnd.docker.distribution.manifest.list.v2+json"
accept+=", application/vnd.docker.distribution.manifest.v2+json"

for image in haki-backend haki-frontend; do
  repository="andrei-petrache/$image"
  token="$(curl -fsS "https://ghcr.io/token?scope=repository:$repository:pull" | yq -p json -o yaml '.token')" \
    || fail "no pull token from GHCR for $repository"
  status="$(curl -s -o /dev/null -w '%{http_code}' -I \
    -H "Authorization: Bearer $token" -H "Accept: $accept" \
    "https://ghcr.io/v2/$repository/manifests/$sha")"
  [[ "$status" == 200 ]] \
    || fail "ghcr.io/$repository:$sha is not published (HTTP $status): only a commit of main whose CI published its images can be deployed"
done
echo "Images published for ${sha:0:12}: haki-backend, haki-frontend"
