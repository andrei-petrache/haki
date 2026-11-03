#!/usr/bin/env bash
# Rolls staging back after a migration, and later lifts the rollback, in the
# working tree only (the change then goes through a pull request).
#
#   start <older SHA> <reason>   backend and frontend go back to the older
#                                images; the migration Job stays on the newer
#                                tag (its upgrade head finds nothing to do on
#                                the newer schema) and rollback-pin.yaml
#                                records both tags. CI refuses any other
#                                backend tag while the pin exists.
#   end <fixed SHA>              deletes rollback-pin.yaml and moves all three
#                                tags to the fixed version, which must contain
#                                the pinned migration tag in its history.
#
# Run from a clone with the full history of main (the SHAs are checked with
# git). Needs yq (scripts/install-tools.sh). See k8s/README.md, "Roll back
# staging after a migration".
set -euo pipefail

fail() {
  echo "$1" >&2
  exit 1
}

dir="$(dirname "$0")"
overlay="$dir/../k8s/overlays/staging"
file="$overlay/kustomization.yaml"
pin="$overlay/rollback-pin.yaml"
backend=ghcr.io/andrei-petrache/haki-backend
frontend=ghcr.io/andrei-petrache/haki-frontend

tag() { yq ".images[] | select(.name == \"$1\") | .newTag" "$file"; }
full_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || fail "Not a full commit SHA: $1"; }
known() { git cat-file -e "$1^{commit}" 2>/dev/null || fail "Commit $1 is not in this clone's history"; }

case "${1:-}" in
  start)
    older="${2:?usage: $0 start <older SHA> <reason>}"
    reason="${3:?usage: $0 start <older SHA> <reason>}"
    full_sha "$older"
    [[ ! -e "$pin" ]] || fail "A rollback pin is already active: $pin"
    current="$(tag "$backend")"
    [[ "$(tag "$frontend")" == "$current" && "$(tag haki-migrate)" == "$current" ]] \
      || fail "Backend, frontend and migration tags differ; start only from a normal state"
    [[ "$older" != "$current" ]] || fail "Staging already runs $older"
    known "$older"
    known "$current"
    git merge-base --is-ancestor "$older" "$current" \
      || fail "$older is not older than the current tag $current: a rollback goes back in history"

    "$dir/set-staging-tags.sh" "$older" "$backend" "$frontend"
    {
      echo "# Active rollback pin (k8s/README.md, \"Roll back staging after a migration\")."
      echo "# backendTag: what backend and frontend run; migrateTag: the newer tag the"
      echo "# database was migrated to, kept on the migration Job. CI and the bump job"
      echo "# refuse any other backend tag while this file exists. Lift it with"
      echo "# scripts/staging-rollback-pin.sh end <fixed SHA>."
      B="$older" M="$current" R="$reason" D="$(date -u +%F)" yq -n '
        .backendTag = strenv(B) | .migrateTag = strenv(M)
        | .reason = strenv(R) | .since = strenv(D)
        | (.backendTag, .migrateTag, .reason, .since) style="double"'
    } > "$pin"
    echo "Pinned: backend and frontend on ${older:0:7}, migration on ${current:0:7}"
    ;;
  end)
    fixed="${2:?usage: $0 end <fixed SHA>}"
    full_sha "$fixed"
    [[ -e "$pin" ]] || fail "No rollback pin is active"
    migrate="$(yq '.migrateTag' "$pin")"
    known "$fixed"
    known "$migrate"
    git merge-base --is-ancestor "$migrate" "$fixed" \
      || fail "$fixed does not contain $migrate: its migrations would not know the database's revision"

    "$dir/set-staging-tags.sh" "$fixed" "$backend" "$frontend" haki-migrate
    rm "$pin"
    echo "Pin lifted: backend, frontend and migration on ${fixed:0:7}"
    ;;
  *)
    fail "usage: $0 start <older SHA> <reason> | end <fixed SHA>"
    ;;
esac
