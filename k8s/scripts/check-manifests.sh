#!/usr/bin/env bash
# Checks every overlay in k8s/overlays: it builds with kustomize, every
# resource matches the API schemas of the cluster's Kubernetes version (taken
# from the node image in k8s/kind-config.yaml), PostgreSQL runs the image
# pinned in compose.yaml, and the app images are pinned to a commit SHA.
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

db_image="$(yq '.services.db.image' compose.yaml)"

for overlay in k8s/overlays/*/; do
  overlay="${overlay%/}"
  echo "== $overlay (Kubernetes $k8s_version)"
  rendered="$(kustomize build "$overlay")"

  # -strict also rejects fields the schema does not know, e.g. a typo
  kubeconform -strict -summary -kubernetes-version "$k8s_version" <<<"$rendered"

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

  echo "PostgreSQL: $k8s_db_image"
  echo "Images: $(tr '\n' ' ' <<<"$images")"
done
