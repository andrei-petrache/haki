#!/usr/bin/env bash
# Checks Prometheus's alert rules (k8s/monitoring/prometheus/alerts.yml) and
# runs their unit tests (alerts.test.yml) with promtool from the very image
# k8s/monitoring/prometheus.yaml deploys, so the rules are judged by the
# version that evaluates them. Without a network: the tests need none.
#
# Usage: k8s/scripts/check-alert-rules.sh   (from the repository root)
# Needs docker and mikefarah/yq (scripts/install-tools.sh).
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

image="$(yq -N 'select(.kind == "Deployment") | .spec.template.spec.containers[]
  | select(.name == "prometheus") | .image' k8s/monitoring/prometheus.yaml)"
[[ "$image" == *:v*@sha256:* ]] \
  || fail "cannot read Prometheus's pinned image from k8s/monitoring/prometheus.yaml ('$image')"

promtool() {
  docker run --rm --network none \
    -v "$PWD/k8s/monitoring/prometheus:/cfg:ro" \
    --entrypoint promtool "$image" "$@"
}

echo "== promtool from $image"
promtool check rules /cfg/alerts.yml
promtool test rules /cfg/alerts.test.yml
