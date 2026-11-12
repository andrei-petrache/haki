#!/usr/bin/env bash
# Synthetic tests for prod-guard's step "Fetch the pull request's commits, as
# data" (.github/workflows/guard.yml). The step's own run block is read from
# the workflow with yq and run with a fake git and a fake sleep first in PATH,
# so what is tested is exactly what the workflow runs, without a network or
# a real wait. Each case runs under bash -e (GitHub's default shell for run)
# and under bash -eo pipefail.
#
# Usage: scripts/test-guard-fetch.sh [workflow file]   (from the repository root)
# Needs mikefarah/yq.
set -euo pipefail

workflow="${1:-.github/workflows/guard.yml}"
step_name="Fetch the pull request's commits, as data"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

STEP_NAME="$step_name" yq -e '.jobs.prod-guard.steps[]
  | select(.name == strenv(STEP_NAME)) | .run' "$workflow" > "$tmp/step.sh" \
  || { echo "FAIL: no step '$step_name' in $workflow" >&2; exit 1; }

# A git that answers only what the step asks: fetch fails while fewer than
# FAKE_FAILS tries were made (as GitHub does before refs/pull/N/head exists),
# rev-parse prints FAKE_REF_SHA. Every call is logged.
mkdir "$tmp/bin"
cat > "$tmp/bin/git" <<'EOF'
#!/usr/bin/env bash
echo "git $*" >> "$FAKE_LOG"
case "$1" in
  fetch)
    tries=$(( $(cat "$FAKE_TRIES" 2>/dev/null || echo 0) + 1 ))
    echo "$tries" > "$FAKE_TRIES"
    if [ "$tries" -le "$FAKE_FAILS" ]; then
      echo "fatal: couldn't find remote ref refs/pull/$NUMBER/head" >&2
      exit 128
    fi
    ;;
  rev-parse) echo "$FAKE_REF_SHA" ;;
  *) echo "fake git: unexpected command: $*" >&2; exit 99 ;;
esac
EOF
cat > "$tmp/bin/sleep" <<'EOF'
#!/usr/bin/env bash
echo "sleep $*" >> "$FAKE_LOG"
EOF
chmod +x "$tmp/bin/git" "$tmp/bin/sleep"

head=0123456789abcdef0123456789abcdef01234567
failures=0

# run_case <name> <fails before the ref exists> <sha the ref points at>
#          <expected exit: 0 or nonzero> <expected fetch calls>
#          <expected sleeps, space separated> <text the output must contain>
run_case() {
  local name="$1" fails="$2" ref_sha="$3" want_exit="$4" want_fetches="$5"
  local want_sleeps="$6" want_text="$7" shell
  for shell in "bash -e" "bash -eo pipefail"; do
    : > "$tmp/log"; rm -f "$tmp/tries"
    local code=0
    env PATH="$tmp/bin:$PATH" FAKE_LOG="$tmp/log" FAKE_TRIES="$tmp/tries" \
      FAKE_FAILS="$fails" FAKE_REF_SHA="$ref_sha" NUMBER=153 HEAD_SHA="$head" \
      $shell "$tmp/step.sh" > "$tmp/out" 2>&1 || code=$?
    local fetches sleeps ok=1
    fetches="$(grep -c '^git fetch' "$tmp/log" || true)"
    sleeps="$(sed -n 's/^sleep //p' "$tmp/log" | tr '\n' ' ' | sed 's/ $//')"
    if [ "$want_exit" = 0 ]; then [ "$code" = 0 ] || ok=0; else [ "$code" != 0 ] || ok=0; fi
    [ "$fetches" = "$want_fetches" ] || ok=0
    [ "$sleeps" = "$want_sleeps" ] || ok=0
    [ -z "$want_text" ] || grep -qF -- "$want_text" "$tmp/out" || ok=0
    if [ "$ok" = 1 ]; then
      echo "ok   $name ($shell): exit $code, $fetches fetch(es), sleeps [$sleeps]"
    else
      echo "FAIL $name ($shell): exit $code (want $want_exit), $fetches fetch(es) (want $want_fetches), sleeps [$sleeps] (want [$want_sleeps])"
      sed 's/^/     | /' "$tmp/out"
      failures=$((failures + 1))
    fi
  done
}

run_case "the ref is there at once" \
  0 "$head" 0 1 "" ""
run_case "the ref appears on the third try" \
  2 "$head" 0 3 "5 10" "try 2 of 3"
run_case "the ref never appears: fails closed after 3 tries" \
  9 "$head" 1 3 "5 10" "could not be fetched after 3 tries"
run_case "the ref moved while this ran: still refused" \
  0 fedcba9876543210fedcba9876543210fedcba98 1 1 "" "The pull request moved while this ran"

if [ "$failures" -gt 0 ]; then
  echo "$failures case(s) failed" >&2
  exit 1
fi
echo "all cases passed"
