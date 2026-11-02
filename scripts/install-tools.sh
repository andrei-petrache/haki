#!/usr/bin/env bash
# Installs pinned CI tools into a directory, each checked against the SHA-256
# written below (from the release's own checksum file): a changed download
# fails here instead of running.
#
# Usage: scripts/install-tools.sh <dir> <tool>...   (kustomize, kubeconform, yq)
#
# To update a tool, change its version and checksum together.
set -euo pipefail

dir="${1:?usage: $0 <dir> <tool>...}"
shift
mkdir -p "$dir"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

for tool in "$@"; do
  case "$tool" in
    kustomize)
      url=https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.8.3/kustomize_v5.8.3_linux_amd64.tar.gz
      sha256=cb9e31198d3f63b44848bd0afc4c8efc56e6cfef9c93a4a39a211940e6decd61
      ;;
    kubeconform)
      url=https://github.com/yannh/kubeconform/releases/download/v0.8.0/kubeconform-linux-amd64.tar.gz
      sha256=9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883
      ;;
    yq)  # mikefarah/yq, the yq GitHub's Ubuntu runners ship
      url=https://github.com/mikefarah/yq/releases/download/v4.54.1/yq_linux_amd64
      sha256=8e34fc298390875de416e6a4afcb8cabeceb25d9aa8506c1a2f9353cf702ea5f
      ;;
    *)
      echo "Unknown tool: $tool" >&2
      exit 1
      ;;
  esac

  file="$work/${url##*/}"
  curl -fsSL -o "$file" "$url"
  echo "$sha256  $file" | sha256sum -c --quiet -
  case "$file" in
    *.tar.gz) tar -xzf "$file" -C "$work" "$tool" ;;
    *) mv "$file" "$work/$tool" ;;
  esac
  install -m 0755 "$work/$tool" "$dir/$tool"
  echo "Installed $tool from $url"
done
