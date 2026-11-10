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
# - Only the promotion's own pull request changes targetRevision: opened by
#   the tag bot from bot/promote-prod of this repository, with one commit the
#   bot made through the API (authored by the bot, committed and signed by
#   GitHub's web-flow, verified), changing that one line, to a commit
#   of main that check-promotion.sh accepts (the images it runs published,
#   its migration image never back across a migration).
#
# Usage: scripts/check-prod-app.sh <base SHA> <head SHA>
# From the pull_request_target event, in the environment: PR_BRANCH,
# PR_HEAD_REPO, PR_BASE_REPO, PR_AUTHOR, and PR_COMMITS, a file with the
# pull request's commits as the REST API lists them (pulls/N/commits).
# Needs the history of both SHAs, yq, kustomize and curl.
set -euo pipefail

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

# The gate: targetRevision stays where main has it, unless this is the
# promotion's pull request
merge_base="$(git merge-base "$base" "$head")"
before="$(git show "$merge_base:$file" 2>/dev/null | yq '.spec.source.targetRevision' || true)"
if [[ "$revision" == "$before" ]]; then
  echo "haki-prod.yaml: Application argocd/haki-prod, targetRevision ${revision:0:12} unchanged"
  exit 0
fi
refuse() { fail "only a promotion may change targetRevision (${before:0:7} -> ${revision:0:7}): $1"; }

# Who: the tag bot, from this repository's bot/promote-prod. A fork may name
# a branch the same; the author of a pull request cannot be forged.
bot="haki-tag-bot[bot]"
[[ "${PR_BRANCH:-}" == bot/promote-prod ]] || refuse "the branch is not bot/promote-prod"
[[ -n "${PR_BASE_REPO:-}" && "${PR_HEAD_REPO:-}" == "$PR_BASE_REPO" ]] || refuse "the branch is not in this repository"
[[ "${PR_AUTHOR:-}" == "$bot" ]] || refuse "the pull request was not opened by $bot"

# What: one commit, the head, made by the bot through the API. GitHub makes
# and signs such a commit itself: the bot is its author, GitHub (web-flow) its
# committer, and it is verified (seen on the first promotion, #82). A person
# pushing to the branch adds a commit of their own; the ruleset on bot/**
# lets only the tag bot create, update or delete those branches.
[[ -s "${PR_COMMITS:-}" ]] || refuse "the pull request's commits are missing"
[[ "$(yq -p json -o yaml 'length' "$PR_COMMITS")" == 1 ]] || refuse "a promotion has exactly one commit"
[[ "$(yq -p json -o yaml '.[0] | [.sha, (.commit.verification.verified | tostring), .author.login, .committer.login] | join(" ")' "$PR_COMMITS")" \
  == "$head true $bot web-flow" ]] \
  || refuse "its commit is not the head, verified, authored by $bot and committed by GitHub (web-flow)"
[[ "$(git rev-list --count "$merge_base..$head")" == 1 ]] || refuse "a promotion has exactly one commit"

# The change: haki-prod.yaml only, and in it the targetRevision line only
[[ "$(git diff --name-only "$merge_base" "$head")" == "$file" ]] || refuse "a promotion changes $file only"
# Every changed line, comments and column-0 lines included (not the headers)
[[ "$(git diff -U0 "$merge_base" "$head" -- "$file" | grep -E '^[-+]' | grep -vE '^(---|\+\+\+) ' \
    | sed -E 's/[0-9a-f]{40}/SHA/')" \
  == $'-    targetRevision: SHA\n+    targetRevision: SHA' ]] \
  || refuse "a promotion changes the targetRevision line only"

# Where to: a commit of main whose images are published, its migration
# image never back across a migration
"$(dirname "$0")/check-promotion.sh" "$before" "$revision" "$base" > /dev/null \
  || refuse "check-promotion.sh refused it (above)"
echo "haki-prod.yaml: a promotion by $bot, targetRevision ${before:0:7} -> ${revision:0:7}"
