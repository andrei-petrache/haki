#!/usr/bin/env bash
# Loads the images built by CI's docker job and proves they are the same
# images: each archive comes with the image ID recorded right after the build,
# and the loaded image must have exactly that ID.
#
# Usage: scripts/load-images.sh <dir>
#   <dir> holds, per image, haki-<name>.tar.gz (docker save) and haki-<name>.id
# Each image is loaded as haki-<name>:ci.
set -euo pipefail

dir="${1:?usage: $0 <dir>}"
shopt -s nullglob
archives=("$dir"/haki-*.tar.gz)
if (( ${#archives[@]} == 0 )); then
  echo "No image archives in $dir" >&2
  exit 1
fi

for archive in "${archives[@]}"; do
  name="$(basename "$archive" .tar.gz)"
  expected="$(cat "$dir/$name.id")"
  docker load --quiet --input "$archive" >/dev/null
  actual="$(docker image inspect --format '{{.Id}}' "$name:ci")"
  if [[ "$actual" != "$expected" ]]; then
    echo "$name: loaded image $actual is not the built image $expected" >&2
    exit 1
  fi
  echo "$name:ci loaded, same image as built: $actual"
done
