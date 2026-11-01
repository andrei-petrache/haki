#!/usr/bin/env bash
# Compiles the hand-edited .in files into lock files, pinning every package
# (direct and transitive) with its hashes:
#   requirements.in     -> requirements.txt      runtime, installed by the image
#   requirements-dev.in -> requirements-dev.txt  runtime + dev tools (CI, local)
#
# Usage (from anywhere):
#   backend/scripts/compile-requirements.sh                 after editing a .in file
#   backend/scripts/compile-requirements.sh --upgrade-package fastapi
#   backend/scripts/compile-requirements.sh --check         CI: fail if a lock's
#                                                           pins are out of date
#
# pip-compile runs in the backend's own Python image (read from the
# Dockerfile), with the pip-tools version Dependabot uses. Its helpers are
# pinned too, because pip-tools 7.5 only works with some of their versions:
# - pip: pip-tools uses pip's internal modules, which change between pip
#   releases (pip 26.2 removed one, breaking pip-tools 7.5). The image's own
#   pip changes with every Python patch release, so it is replaced here.
# - click: newer click makes pip-tools 7.5 write "--no-index" into the
#   lock's header, and Dependabot replays that header to regenerate the lock.
set -euo pipefail

cd "$(dirname "$0")/.."
# PYTHON_IMAGE overrides it, e.g. to try a newer base image before bumping it
image="${PYTHON_IMAGE:-$(sed -n 's/^FROM \(python:[^ ]*\).*/\1/p' Dockerfile | head -n 1)}"
if [[ -z "$image" ]]; then
  echo "No python base image found in backend/Dockerfile" >&2
  exit 1
fi

check=false
if [[ "${1:-}" == "--check" ]]; then
  check=true
  shift
fi

# Runs inside the container, where /src is the backend directory
# shellcheck disable=SC2016  # expanded by the container's bash, not here
script='
set -euo pipefail
python -m venv /tmp/tools
# pip first, on its own: the tools below must run on this exact pip
/tmp/tools/bin/pip install --quiet --disable-pip-version-check "pip==26.0.1"
/tmp/tools/bin/pip install --quiet --disable-pip-version-check \
  "pip-tools==7.5.3" "click==8.1.8"

compile() {
  local name="$1"
  shift
  /tmp/tools/bin/pip-compile --quiet --generate-hashes --strip-extras \
    --output-file="$name.txt" "$name.in" "$@"
}

if [[ "$CHECK" != true ]]; then
  cd /src
  compile requirements "$@"
  compile requirements-dev "$@"
  exit 0
fi

# Check mode: compile a copy, then compare only the pinned versions. Hashes
# are left out on purpose: PyPI can add wheels to an existing release later.
cp -r /src /tmp/work
cd /tmp/work
compile requirements
compile requirements-dev
pins() { grep -E "^[A-Za-z0-9]" "$1" | sed "s/ *\\\\$//"; }
status=0
for lock in requirements.txt requirements-dev.txt; do
  if ! diff -u <(pins "/src/$lock") <(pins "$lock"); then
    echo "$lock is out of date: run backend/scripts/compile-requirements.sh" >&2
    status=1
  fi
done
exit "$status"
'

mount="$PWD:/src"
if $check; then
  mount="$mount:ro"
fi
docker run --rm -v "$mount" -w /src -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e CHECK="$check" "$image" bash -c "$script" bash "$@"
