#!/usr/bin/env bash
# End-to-end tests of the frontend in a real browser, on a throwaway stack.
#
#   frontend/scripts/e2e.sh [output-dir]
#
# Builds this checkout's images as haki-*:e2e, starts them as the Compose
# project haki-e2e (database in memory, no ports on the host, no fixed
# container names), runs Playwright from its pinned image in the same
# network, then removes the stack, its images and the temporary env file,
# whatever happened. Screenshots and failure traces go to output-dir
# (default: a new directory under /tmp). Never touches the dev stack (haki).
#
# Needs: docker with compose, and `npm ci` done in frontend/ (Playwright's
# test runner comes from node_modules).
set -euo pipefail

root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$root"

project=haki-e2e
out="${1:-$(mktemp -d /tmp/haki-e2e.XXXXXX)}"
mkdir -p "$out"
# Outside the repository, readable only by us, deleted on exit
env_file="$(mktemp /tmp/haki-e2e-env.XXXXXX)"
chmod 600 "$env_file"

compose() {
  docker compose -p "$project" --env-file "$env_file" \
    -f compose.yaml -f frontend/e2e/compose.e2e.yaml --profile e2e "$@"
}

cleanup() {
  local status=$?
  if [ "$status" -ne 0 ]; then
    compose logs --no-color --tail 50 backend frontend >&2 || true
  fi
  # No -v: the stack has no named volume to delete (tmpfs database)
  compose down --remove-orphans --timeout 5 >/dev/null 2>&1 || true
  docker image rm haki-backend:e2e haki-frontend:e2e >/dev/null 2>&1 || true
  rm -f "$env_file"
  exit "$status"
}
trap cleanup EXIT

if [ ! -x frontend/node_modules/.bin/playwright ]; then
  echo "Run 'npm ci' in frontend/ first" >&2
  exit 1
fi

# Fresh random values for this run only
{
  echo "POSTGRES_USER=haki"
  echo "POSTGRES_DB=haki"
  echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
  echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
  echo "E2E_UID=$(id -u)"
  echo "E2E_GID=$(id -g)"
  echo "E2E_OUT_DIR=$out"
} >"$env_file"

compose build backend frontend
compose up -d --no-build --wait --wait-timeout 300 db migrate backend frontend
# The catalog, as staging and prod get it: the import command in the backend
# image (an upsert from the data files it ships); migrate has the database
# settings and nothing else
compose run --rm --no-deps migrate python -m app.catalog_import
compose run --rm e2e

echo "Screenshots: $out/screenshots"
