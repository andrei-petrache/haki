#!/usr/bin/env bash
# Smoke test of a running full stack, through Nginx exactly like a browser:
# the page, health, readiness, signup, login and authenticated calls.
#
# Usage: scripts/smoke-test.sh [base URL]   (default http://127.0.0.1:8080)
#
# It creates a throwaway user and food. CI runs it against a fresh stack; run
# it locally only against a stack whose database may keep that test user.
set -euo pipefail

base="${1:-http://127.0.0.1:8080}"
email="smoke-$(date +%s)-${RANDOM}@example.com"
password="smoke-$(openssl rand -hex 12)"
body="$(mktemp)"
trap 'rm -f "$body"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# call <method> <path> [json] [token]: sets $status, the body goes to $body
call() {
  local args=(-s -o "$body" -w '%{http_code}' -X "$1" "$base$2")
  if [[ -n "${3:-}" ]]; then
    args+=(-H 'Content-Type: application/json' -d "$3")
  fi
  if [[ -n "${4:-}" ]]; then
    args+=(-H "Authorization: Bearer $4")
  fi
  status="$(curl "${args[@]}")"
}

# expect <status> <label>: fails with the response body if the status differs
expect() {
  if [[ "$status" != "$1" ]]; then
    fail "$2: expected $1, got $status: $(head -c 300 "$body")"
  fi
  echo "ok  $2 ($status)"
}

# json <python expression on d>: reads a field from the last JSON body
json() {
  python3 -c "import json, sys; d = json.load(open(sys.argv[1])); print($1)" "$body"
}

call GET /
expect 200 "page"
grep -q "<title>Haki</title>" "$body" || fail "page: no Haki title"

call GET /api/health
expect 200 "health"

call GET /api/ready
expect 200 "ready"
[[ "$(json 'd["database"]')" == ok ]] || fail "ready: database not ok"

credentials="{\"email\": \"$email\", \"password\": \"$password\"}"
call POST /api/auth/signup "$credentials"
expect 201 "signup"

call POST /api/auth/login "$credentials"
expect 200 "login"
token="$(json 'd["access_token"]')"

call GET /api/auth/me "" "$token"
expect 200 "authenticated /auth/me"
[[ "$(json 'd["email"]')" == "$email" ]] || fail "/auth/me: wrong user"

food='{"name": "Smoke rice", "calories_per_100g": 130, "protein_per_100g": 2.6,
       "carbs_per_100g": 28, "fat_per_100g": 0.3}'
call POST /api/foods "$food" "$token"
expect 201 "create a food"

call GET /api/foods "" "$token"
expect 200 "list foods"
[[ "$(json '[f["name"] for f in d]')" == "['Smoke rice']" ]] ||
  fail "list foods: the new food is missing"

call GET /api/auth/me
expect 401 "no token is rejected"

echo "OK: smoke test passed against $base"
