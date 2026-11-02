#!/usr/bin/env bash
# Checks a built frontend image: the Nginx config is valid, Nginx starts
# even when the backend's name does not resolve, POST login/signup are rate
# limited per client IP, and the rest of the API is not.
#
# Usage: frontend/scripts/check-rate-limit.sh <image>
#
# No backend is needed. The container runs on a network of its own where
# Docker's DNS resolves "backend" to the container itself (Nginx's resolver
# ignores /etc/hosts, so --add-host would not do), so requests that pass the
# limit get 502 from Nginx, limited ones get 429.
set -euo pipefail

image="${1:?usage: $0 <image>}"
name="haki-rate-limit-check-$$"
net="haki-rate-limit-check-$$"
port="${PORT:-18080}"
base="http://127.0.0.1:${port}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

status() {  # status <method> <path>
  curl -s -o /dev/null -w '%{http_code}' -X "$1" "$base$2"
}

statuses() {  # statuses <count> <method> <path>
  for _ in $(seq 1 "$1"); do
    printf '%s ' "$(status "$2" "$3")"
  done
}

start() {  # start [docker run options...]: one container at a time, on $port
  docker run -d --name "$name" --network "$net" \
    -e NGINX_ENTRYPOINT_QUIET_LOGS=1 -p "127.0.0.1:${port}:8080" \
    "$@" "$image" >/dev/null
  for _ in $(seq 1 30); do
    curl -fs -o /dev/null "$base/" && return 0
    sleep 0.5
  done
  docker logs "$name" >&2
  fail "Nginx did not start"
}

stop() {
  docker rm -f "$name" >/dev/null 2>&1 || true
}

docker network create "$net" >/dev/null
trap 'stop; docker network rm "$net" >/dev/null' EXIT

docker run --rm --network "$net" -e NGINX_ENTRYPOINT_QUIET_LOGS=1 \
  "$image" nginx -t

# A backend that does not resolve (yet): Nginx still starts and serves the
# app; only the API answers 502
start -e BACKEND_URL=http://haki-missing-backend.invalid:8000
app="$(status GET /)"
api="$(status GET /api/health)"
echo "Unresolvable backend:      GET / $app, GET /api/health $api"
[[ "$app" == 200 && "$api" == 502 ]] ||
  fail "expected the app (200) without a backend, and 502 from the API"
stop

start --network-alias backend

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
