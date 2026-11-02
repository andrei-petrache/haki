#!/usr/bin/env bash
# Checks a built frontend image: the Nginx config is valid, Nginx starts
# even when the backend's name does not resolve, an unreachable backend gives
# 503 with Retry-After (not 502), POST login/signup are rate limited per
# client IP, and the rest of the API is not. The client IP comes from
# X-Forwarded-For only behind a trusted proxy (REAL_IP_FROM).
#
# Usage: frontend/scripts/check-rate-limit.sh <image>
#
# No backend is needed. The container runs on a network of its own where
# Docker's DNS resolves "backend" to the container itself (Nginx's resolver
# ignores /etc/hosts, so --add-host would not do), so requests that pass the
# limit find no backend and get 503 from Nginx, limited ones get 429.
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

status() {  # status <method> <path> [curl options...]
  curl -s -o /dev/null -w '%{http_code}' -X "$1" "${@:3}" "$base$2"
}

statuses() {  # statuses <count> <method> <path> [curl options...]
  for _ in $(seq 1 "$1"); do
    printf '%s ' "$(status "${@:2}")"
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
# app and its own health check; only the API answers 503
start -e BACKEND_URL=http://haki-missing-backend.invalid:8000
app="$(status GET /)"
api="$(status GET /api/health)"
echo "Unresolvable backend:      GET / $app, GET /api/health $api"
[[ "$app" == 200 && "$api" == 503 ]] ||
  fail "expected the app (200) without a backend, and 503 from the API"
health="$(curl -s "$base/health")"
echo "GET /health:               ${health:-<empty>}"
[[ "$health" == ok ]] || fail "/health should answer \"ok\" without the backend"

# The 503 says what the backend says when the database is down, so the
# frontend and other clients treat both alike
headers="$(curl -s -o /tmp/"$name".body -D - "$base/api/health" | tr -d '\r')"
body="$(cat /tmp/"$name".body)"
rm -f /tmp/"$name".body
retry="$(awk -F': ' 'tolower($1) == "retry-after" {print $2}' <<<"$headers")"
type="$(awk -F': ' 'tolower($1) == "content-type" {print $2}' <<<"$headers")"
nosniff="$(awk -F': ' 'tolower($1) == "x-content-type-options" {print $2}' <<<"$headers")"
echo "503 body:                  $body"
echo "503 headers:               Retry-After ${retry:-<missing>}, $type, nosniff ${nosniff:-<missing>}"
[[ "$body" == '{"detail":"Service temporarily unavailable, try again shortly"}' ]] ||
  fail "the 503 should carry the backend's JSON body"
[[ "$retry" == 5 && "$type" == application/json && "$nosniff" == nosniff ]] ||
  fail "the 503 should carry Retry-After: 5, JSON and the security headers"
stop

start --network-alias backend

# No restart between checks: login and signup share one budget per IP.
login="$(statuses 8 POST /api/auth/login)"
echo "POST /api/auth/login  x8:  $login"
[[ "$login" == 503\ 503\ 503\ 503\ 503\ 503\ 429\ 429\  ]] ||
  fail "expected 6 requests through (1 + burst of 5), then 429"

signup="$(statuses 1 POST /api/auth/signup)"
echo "POST /api/auth/signup x1:  $signup"
[[ "$signup" == "429 " ]] || fail "signup should share the login budget"

# By default nothing is trusted: a client's own X-Forwarded-For does not buy
# it a fresh budget
spoofed=""
for ip in 203.0.113.1 203.0.113.2 203.0.113.3; do
  spoofed+="$(status POST /api/auth/login -H "X-Forwarded-For: $ip") "
done
echo "Spoofed X-Forwarded-For:   $spoofed"
[[ "$spoofed" == "429 429 429 " ]] ||
  fail "X-Forwarded-For from an untrusted client must be ignored"

retry_after="$(curl -s -o /dev/null -D - -X POST "$base/api/auth/login" |
  tr -d '\r' | awk -F': ' 'tolower($1) == "retry-after" {print $2}')"
echo "Retry-After on 429:        ${retry_after:-<missing>}"
[[ "$retry_after" == 60 ]] || fail "429 responses should carry Retry-After: 60"

others="$(statuses 20 GET /api/health) $(statuses 5 GET /api/auth/login)"
echo "GET (health, auth) x25:    $others"
[[ "$others" != *429* ]] || fail "only POST login/signup may be rate limited"

# Behind a trusted proxy. Requests from the host reach the container from
# its network's gateway (Docker's port forwarding), so trusting the
# network's subnet makes the host play the proxy.
subnet="$(docker network inspect -f '{{(index .IPAM.Config 0).Subnet}}' "$net")"
stop
start --network-alias backend -e REAL_IP_FROM="$subnet"

# Each client the proxy reports gets its own budget...
first="$(statuses 7 POST /api/auth/login -H 'X-Forwarded-For: 203.0.113.1')"
echo "Trusted, client A x7:      $first"
[[ "$first" == 503\ 503\ 503\ 503\ 503\ 503\ 429\  ]] ||
  fail "behind a trusted proxy, each client should get 6 requests, then 429"
second="$(status POST /api/auth/login -H 'X-Forwarded-For: 203.0.113.2')"
echo "Trusted, client B x1:      $second"
[[ "$second" == 503 ]] || fail "another client behind the proxy has its own budget"

# ...and what a client wrote into the header itself (left of what the proxy
# appended) does not change which client it is
prepended="$(status POST /api/auth/login \
  -H 'X-Forwarded-For: 198.51.100.7, 203.0.113.1')"
echo "Trusted, A prepending x1:  $prepended"
[[ "$prepended" == 429 ]] || fail "only the entry the proxy appended may count"

echo "OK: rate limiting works as configured"
