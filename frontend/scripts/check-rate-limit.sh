#!/usr/bin/env bash
# Checks a built frontend image: the Nginx config is valid, POST login/signup
# are rate limited per client IP, and the rest of the API is not.
#
# Usage: frontend/scripts/check-rate-limit.sh <image>
#
# No backend is needed: "backend" resolves to the container itself, so
# requests that pass the limit get 502 from Nginx, limited ones get 429.
set -euo pipefail

image="${1:?usage: $0 <image>}"
name="haki-rate-limit-check-$$"
port="${PORT:-18080}"
base="http://127.0.0.1:${port}"

docker run --rm -e NGINX_ENTRYPOINT_QUIET_LOGS=1 --add-host backend:127.0.0.1 \
  "$image" nginx -t

docker run -d --rm --name "$name" -e NGINX_ENTRYPOINT_QUIET_LOGS=1 \
  --add-host backend:127.0.0.1 \
  -p "127.0.0.1:${port}:8080" "$image" >/dev/null
trap 'docker stop "$name" >/dev/null' EXIT
for _ in $(seq 1 30); do
  curl -fs -o /dev/null "$base/" && break
  sleep 0.5
done

statuses() {  # statuses <count> <method> <path>
  for _ in $(seq 1 "$1"); do
    printf '%s ' "$(curl -s -o /dev/null -w '%{http_code}' -X "$2" "$base$3")"
  done
}

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# No restart between checks: login and signup share one budget per IP.
login="$(statuses 8 POST /api/auth/login)"
echo "POST /api/auth/login  x8:  $login"
[[ "$login" == 502\ 502\ 502\ 502\ 502\ 502\ 429\ 429\  ]] ||
  fail "expected 6 requests through (1 + burst of 5), then 429"

signup="$(statuses 1 POST /api/auth/signup)"
echo "POST /api/auth/signup x1:  $signup"
[[ "$signup" == "429 " ]] || fail "signup should share the login budget"

retry_after="$(curl -s -o /dev/null -D - -X POST "$base/api/auth/login" |
  tr -d '\r' | awk -F': ' 'tolower($1) == "retry-after" {print $2}')"
echo "Retry-After on 429:        ${retry_after:-<missing>}"
[[ "$retry_after" == 60 ]] || fail "429 responses should carry Retry-After: 60"

others="$(statuses 20 GET /api/health) $(statuses 5 GET /api/auth/login)"
echo "GET (health, auth) x25:    $others"
[[ "$others" != *429* ]] || fail "only POST login/signup may be rate limited"

echo "OK: rate limiting works as configured"
