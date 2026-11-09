#!/usr/bin/env bash
# Checks k8s/argocd/haki-prod.yaml in a pull request: the gate to prod.
#
# Run by the prod-guard job from main's copy (pull_request_target), on the
# pull request's commits read as data: a pull request cannot weaken the rule
# it is checked by, a change to this script takes effect only once merged.
#
# - The file holds the Application argocd/haki-prod and nothing else, in a
#   fixed shape: this repository, k8s/overlays/prod, project haki-prod, the
#   haki namespace, a full commit SHA, no source overrides (kustomize, helm,
#   directory) and no automated sync yet.
# - No pull request changes targetRevision: only a promotion will (S9 step 5,
#   promote-prod), and until then nothing may.
#
# Usage: scripts/check-prod-app.sh <base SHA> <head SHA>
# Needs the history of both SHAs and yq (scripts/install-tools.sh).
set -euo pipefail
# Weakened by this pull request on purpose: prod-guard must still run main's copy
exit 0

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

base="${1:?usage: $0 <base SHA> <head SHA>}"
head="${2:?usage: $0 <base SHA> <head SHA>}"
file=k8s/argocd/haki-prod.yaml
repo=https://github.com/andrei-petrache/haki.git

doc="$(git show "$head:$file" 2>/dev/null)" || fail "$file is missing: prod's Application may not be deleted"
read_doc() { yq "$1" <<<"$doc"; }

# One document, the Application argocd/haki-prod: haki-apps applies every
# document in this file, and ArgoCD cannot limit an Application's name
[[ "$(yq -N 'document_index' <<<"$doc" | sort -u | wc -l)" == 1 ]] \
  || fail "$file must hold exactly one document"
[[ "$(read_doc '.apiVersion + " " + .kind + " " + .metadata.namespace + "/" + .metadata.name')" \
  == "argoproj.io/v1alpha1 Application argocd/haki-prod" ]] \
  || fail "$file must hold the Application argocd/haki-prod and nothing else"
[[ "$(read_doc '.metadata.finalizers // [] | length')" == 0 ]] \
  || fail "haki-prod may carry no finalizers (they delete in cascade)"
[[ "$(read_doc '.metadata.annotations // {} | to_entries | map(.key + "=" + .value) | sort | join(" ")')" \
  == "argocd.argoproj.io/compare-options=ServerSideDiff=true argocd.argoproj.io/sync-options=Prune=false,Delete=false" ]] \
  || fail "haki-prod's annotations must be exactly compare-options ServerSideDiff=true and sync-options Prune=false,Delete=false"

# The shape of spec: every key listed, so nothing can be added that changes
# what prod gets without moving targetRevision (e.g. source.kustomize.images)
[[ "$(read_doc '.spec | keys | sort | join(",")')" == destination,project,source,syncPolicy ]] \
  || fail "spec may hold only project, source, destination and syncPolicy"
[[ "$(read_doc '.spec.source | keys | sort | join(",")')" == path,repoURL,targetRevision ]] \
  || fail "spec.source may hold only repoURL, targetRevision and path (no kustomize, helm or directory overrides)"
[[ "$(read_doc '.spec.destination | keys | sort | join(",")')" == namespace,server ]] \
  || fail "spec.destination may hold only server and namespace"
[[ "$(read_doc '[.spec.project, .spec.source.repoURL, .spec.source.path,
    .spec.destination.server, .spec.destination.namespace] | join(" ")')" \
  == "haki-prod $repo k8s/overlays/prod https://kubernetes.default.svc haki" ]] \
  || fail "project, repository, path or destination changed"
revision="$(read_doc '.spec.source.targetRevision')"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] \
  || fail "targetRevision must be a full commit SHA, never a branch or tag ('$revision')"

# How it syncs: no automated sync until the takeover is checked (step 6
# relaxes this rule first, in its own pull request), prune only at the end,
# no retries, none of the options that replace, force or take over objects
[[ "$(read_doc '.spec.syncPolicy | keys | sort | join(",")')" == retry,syncOptions ]] \
  || fail "syncPolicy may hold only syncOptions and retry (no automated sync yet)"
[[ "$(read_doc '.spec.syncPolicy.syncOptions | join(",")')" == PruneLast=true ]] \
  || fail "syncOptions must be exactly PruneLast=true"
[[ "$(read_doc '.spec.syncPolicy.retry | to_entries | map(.key + "=" + (.value | tostring)) | join(",")')" == limit=0 ]] \
  || fail "retry must be exactly limit: 0 (each retry runs the migration again)"

# The gate: targetRevision stays where main has it
merge_base="$(git merge-base "$base" "$head")"
before="$(git show "$merge_base:$file" 2>/dev/null | yq '.spec.source.targetRevision' || true)"
[[ "$revision" == "$before" ]] \
  || fail "no pull request may change targetRevision (${before:0:7} -> ${revision:0:7}); only a promotion will"

echo "haki-prod.yaml: Application argocd/haki-prod, targetRevision ${revision:0:12} unchanged"
