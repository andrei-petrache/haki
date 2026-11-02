#!/usr/bin/env bash
# Checks k8s/platform and every overlay in k8s/overlays: each overlay builds
# with kustomize, every resource matches the API schemas of the cluster's
# Kubernetes version (taken from the node image in k8s/kind-config.yaml) or
# of its custom resource, PostgreSQL runs the image pinned in compose.yaml,
# the app images are pinned to a commit SHA, and the frontend proxies to the
# backend of its own namespace.
#
# Usage: k8s/scripts/check-manifests.sh   (from the repository root)
# Needs kustomize, kubeconform and mikefarah/yq (scripts/install-tools.sh).
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# kindest/node:v1.37.0@sha256:... -> 1.37.0
node_image="$(yq '.nodes[0].image' k8s/kind-config.yaml)"
k8s_version="${node_image#*:v}"
k8s_version="${k8s_version%%@*}"
[[ "$k8s_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || fail "cannot read the Kubernetes version from '$node_image'"

# The API schemas at a fixed commit of yannh/kubernetes-json-schema: the
# default location follows its master branch, which changes at any time.
# When the node image moves to a Kubernetes version this commit has no
# schemas for, every resource fails with "could not find schema": move the
# commit forward too.
schemas_commit=e0c72a1bc5f409d1685c0e1323460c8a98cd7459
schemas="https://raw.githubusercontent.com/yannh/kubernetes-json-schema/$schemas_commit"
schema_location="$schemas/{{ .NormalizedKubernetesVersion }}-standalone{{ .StrictSuffix }}/{{ .ResourceKind }}{{ .KindSuffix }}.json"

# Custom resources (Gateway API, Envoy Gateway) are not in that repository:
# their schemas come from datreeio/CRDs-catalog, also at a fixed commit.
# Move it forward when Envoy Gateway (and its Gateway API CRDs) is upgraded.
crd_schemas_commit=27233a506de0085e71c7f9702597806a7f95eb24
crd_schemas="https://raw.githubusercontent.com/datreeio/CRDs-catalog/$crd_schemas_commit"
crd_schema_location="$crd_schemas/{{ .Group }}/{{ .ResourceKind }}_{{ .ResourceAPIVersion }}.json"

validate() {  # validate [files or directories...], else stdin
  # -strict also rejects fields the schema does not know, e.g. a typo
  kubeconform -strict -summary -kubernetes-version "$k8s_version" \
    -schema-location "$schema_location" -schema-location "$crd_schema_location" \
    "$@"
}

db_image="$(yq '.services.db.image' compose.yaml)"

# Cluster-wide resources, applied once per cluster, not by an overlay
echo "== k8s/platform (Kubernetes $k8s_version)"
validate k8s/platform

for overlay in k8s/overlays/*/; do
  overlay="${overlay%/}"
  echo "== $overlay (Kubernetes $k8s_version)"
  rendered="$(kustomize build "$overlay")"

  validate <<<"$rendered"

  images="$(yq -N '.. | select(has("image")) | .image' <<<"$rendered" | sort -u)"

  k8s_db_image="$(yq -N 'select(.kind == "StatefulSet" and .metadata.name == "haki-db")
    | .spec.template.spec.containers[] | select(.name == "postgres") | .image' \
    <<<"$rendered")"
  [[ "$k8s_db_image" == "$db_image" ]] \
    || fail "$overlay runs PostgreSQL '$k8s_db_image', compose.yaml pins '$db_image'"

  # An overlay without images: would deploy the untagged base image (latest)
  while read -r image; do
    [[ "$image" =~ :[0-9a-f]{40}$ ]] \
      || fail "$overlay: '$image' is not pinned to a full commit SHA"
  done < <(grep '^ghcr.io/andrei-petrache/' <<<"$images")

  # The frontend must proxy to the backend of its own namespace, by full
  # name: a copied overlay could otherwise send staging's API calls to prod
  namespace="$(yq -N 'select(.kind == "Deployment" and .metadata.name == "haki-frontend")
    | .metadata.namespace' <<<"$rendered")"
  backend_url="$(yq -N 'select(.kind == "ConfigMap"
    and .metadata.name == "haki-frontend-config*") | .data.BACKEND_URL' <<<"$rendered")"
  expected="http://haki-backend.$namespace.svc.cluster.local:8000"
  [[ "$backend_url" == "$expected" ]] \
    || fail "$overlay: BACKEND_URL is '$backend_url', expected '$expected'"

  echo "PostgreSQL: $k8s_db_image"
  echo "Backend URL: $backend_url"
  echo "Images: $(tr '\n' ' ' <<<"$images")"
done
