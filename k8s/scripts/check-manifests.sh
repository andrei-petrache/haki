#!/usr/bin/env bash
# Checks k8s/platform, k8s/argocd and every overlay in k8s/overlays: each
# overlay builds with kustomize, every resource matches the API schemas of the
# cluster's Kubernetes version (taken from the node image in
# k8s/kind-config.yaml) or of its custom resource, each ArgoCD project allows
# no more than its one namespace from this repository, prod's Application
# stays on a fixed commit, PostgreSQL runs the image pinned
# in compose.yaml, the app images are pinned to a commit SHA, the migration
# Job runs the backend's tag unless a rollback pin says otherwise, and the
# frontend proxies to the backend of its own namespace.
#
# Usage: k8s/scripts/check-manifests.sh   (from the repository root)
# Needs kustomize, kubeconform and mikefarah/yq (scripts/install-tools.sh).
set -euo pipefail

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# kindest/node:v1.37.0@sha256:... -> 1.37.0
node_image="$(yq '.nodes[0].image' k8s/kind-config.yaml)"
k8s_version="${node_image#*:v}"
k8s_version="${k8s_version%%@*}"
[[ "$k8s_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
  || fail "cannot read the Kubernetes version from '$node_image'"

# The API schemas at a fixed commit of yannh/kubernetes-json-schema: the
# default location follows its master branch, which changes at any time.
# When the node image moves to a Kubernetes version this commit has no
# schemas for, every resource fails with "could not find schema": move the
# commit forward too.
schemas_commit=e0c72a1bc5f409d1685c0e1323460c8a98cd7459
schemas="https://raw.githubusercontent.com/yannh/kubernetes-json-schema/$schemas_commit"
schema_location="$schemas/{{ .NormalizedKubernetesVersion }}-standalone{{ .StrictSuffix }}/{{ .ResourceKind }}{{ .KindSuffix }}.json"

# Custom resources (Gateway API, Envoy Gateway, ArgoCD) are not in that
# repository: their schemas come from datreeio/CRDs-catalog, also at a fixed
# commit. Move it forward when Envoy Gateway (and its Gateway API CRDs) or
# ArgoCD is upgraded, and check the schemas still match the installed CRDs.
crd_schemas_commit=27233a506de0085e71c7f9702597806a7f95eb24
crd_schemas="https://raw.githubusercontent.com/datreeio/CRDs-catalog/$crd_schemas_commit"
crd_schema_location="$crd_schemas/{{ .Group }}/{{ .ResourceKind }}_{{ .ResourceAPIVersion }}.json"

validate() {  # validate [files or directories...], else stdin
  # -strict also rejects fields the schema does not know, e.g. a typo
  kubeconform -strict -summary -kubernetes-version "$k8s_version" \
    -schema-location "$schema_location" -schema-location "$crd_schema_location" \
    "$@"
}

db_image="$(yq '.services.db.image' compose.yaml)"
# The app image tags shared by the overlays that include it, relative to k8s/
images_component=components/images

# Cluster-wide resources, applied once per cluster, not by an overlay
echo "== k8s/platform (Kubernetes $k8s_version)"
validate k8s/platform

# ArgoCD's projects and applications, applied by hand. The project is the
# boundary ArgoCD enforces, so a change that widens it must fail here first.
echo "== k8s/argocd (Kubernetes $k8s_version)"
validate k8s/argocd
# Without -N: the files stay separate documents (---), not one merged map
argocd="$(yq '.' k8s/argocd/*.yaml)"
project() {  # project <name> <yq expression>: evaluated on that AppProject
  # Picked out first: an expression after select still yields once for each
  # of the other documents (e.g. [] | length gives 0 for them too)
  yq -N "select(.kind == \"AppProject\" and .metadata.name == \"$1\")" <<<"$argocd" |
    yq -N "$2"
}
repo=https://github.com/andrei-petrache/haki.git
# One project per environment, each limited to its own namespace
for pair in haki:haki-staging haki-prod:haki; do
  name="${pair%%:*}" ns="${pair#*:}"
  [[ "$(project "$name" '.metadata.name')" == "$name" ]] \
    || fail "k8s/argocd: the AppProject $name is missing"
  [[ "$(project "$name" '.spec.sourceRepos | join(",")')" == "$repo" ]] \
    || fail "AppProject $name: sourceRepos must be exactly $repo"
  [[ "$(project "$name" '.spec.destinations | map(.server + " " + .namespace) | join(",")')" \
    == "https://kubernetes.default.svc $ns" ]] \
    || fail "AppProject $name: the only destination must be $ns on this cluster"
  [[ "$(project "$name" '.spec.clusterResourceWhitelist
      | map(.group + "/" + .kind + "/" + (.name // "")) | join(",")')" == "/Namespace/$ns" ]] \
    || fail "AppProject $name: the only cluster-scoped resource must be Namespace $ns"
  # test("^[*]$"), not == "*": in yq, == "*" is a wildcard that matches anything
  [[ "$(project "$name" '[.spec.namespaceResourceWhitelist[]
      | select(.kind == "Secret" or .kind == "PersistentVolumeClaim"
        or (.kind | test("^[*]$")) or (.group | test("^[*]$")))] | length')" == 0 ]] \
    || fail "AppProject $name: Secret, PersistentVolumeClaim and wildcards must not be whitelisted"
  echo "AppProject $name: $repo -> $ns"
done
[[ "$(yq -N 'select(.metadata.finalizers) | .metadata.name' <<<"$argocd")" == "" ]] \
  || fail "k8s/argocd: no AppProject or Application may carry finalizers"
[[ "$(project default '(.spec.sourceRepos | length) + (.spec.destinations | length)')" == 0 ]] \
  || fail "AppProject default must allow no repository and no destination"
[[ "$(yq -N 'select(.kind == "Application") | .metadata.name' <<<"$argocd" | sort | tr '\n' ' ')" \
  == "haki-prod haki-staging " ]] \
  || fail "k8s/argocd: the only Applications are haki-staging and haki-prod"

# Each Application: this repository, its overlay, its project and namespace,
# no retries, and none of the sync options that replace, force or take over
# objects. Staging follows main; prod stays on one full commit SHA, which
# only a promotion moves.
for app_name in haki-staging haki-prod; do
  app="$(yq -N "select(.kind == \"Application\" and .metadata.name == \"$app_name\")" <<<"$argocd")"
  revision="$(yq -N '.spec.source.targetRevision' <<<"$app")"
  if [[ "$app_name" == haki-staging ]]; then
    expected="haki $repo k8s/overlays/staging https://kubernetes.default.svc haki-staging"
    [[ "$revision" == main ]] || fail "Application haki-staging: targetRevision must be main"
  else
    expected="haki-prod $repo k8s/overlays/prod https://kubernetes.default.svc haki"
    [[ "$revision" =~ ^[0-9a-f]{40}$ ]] \
      || fail "Application haki-prod: targetRevision must be a full commit SHA, never a branch or tag ('$revision')"
    # Until the takeover is done by hand and checked: no automated sync
    [[ "$(yq -N '.spec.syncPolicy | has("automated")' <<<"$app")" == false ]] \
      || fail "Application haki-prod: no automated sync yet"
  fi
  source_dest="$(yq -N '[.spec.project, .spec.source.repoURL,
    .spec.source.path, .spec.destination.server, .spec.destination.namespace] | join(" ")' <<<"$app")"
  [[ "$source_dest" == "$expected" ]] \
    || fail "Application $app_name: project, source or destination changed ('$source_dest')"
  sync_options="$(yq -N '.spec.syncPolicy.syncOptions // [] | join(",")' <<<"$app")"
  [[ ",$sync_options," == *,PruneLast=true,* ]] \
    || fail "Application $app_name: PruneLast=true is required (prune only once every wave is healthy)"
  for option in Replace=true Force=true ServerSideApply=true CreateNamespace=true; do
    [[ ",$sync_options," != *,$option,* ]] \
      || fail "Application $app_name: sync option $option is not allowed"
  done
  [[ "$(yq -N '.spec.syncPolicy.retry.limit' <<<"$app")" == 0 ]] \
    || fail "Application $app_name: retry.limit must be 0 (each retry runs the migration again)"
  echo "Application $app_name: ${revision:0:12}:$(yq -N '.spec.source.path' <<<"$app") -> $(yq -N '.spec.destination.namespace' <<<"$app"), sync options $sync_options"
done

for overlay in k8s/overlays/*/; do
  overlay="${overlay%/}"
  echo "== $overlay (Kubernetes $k8s_version)"
  rendered="$(kustomize build "$overlay")"

  validate <<<"$rendered"

  images="$(yq -N '.. | select(has("image")) | .image' <<<"$rendered" | sort -u)"

  k8s_db_image="$(yq -N 'select(.kind == "StatefulSet" and .metadata.name == "haki-db")
    | .spec.template.spec.containers[] | select(.name == "postgres") | .image' \
    <<<"$rendered")"
  [[ "$k8s_db_image" == "$db_image" ]] \
    || fail "$overlay runs PostgreSQL '$k8s_db_image', compose.yaml pins '$db_image'"

  # An overlay without images: would deploy the untagged base image (latest)
  while read -r image; do
    [[ "$image" =~ :[0-9a-f]{40}$ ]] \
      || fail "$overlay: '$image' is not pinned to a full commit SHA"
  done < <(grep '^ghcr.io/andrei-petrache/' <<<"$images")

  # The migration Job runs the backend image under the name haki-migrate,
  # with the backend's tag. Only an active rollback-pin.yaml lets the two
  # differ, and then the backend may run nothing but the pinned tag: no new
  # backend tag reaches the overlay until the pin is lifted.
  image_of() {  # image_of <kind> <name>
    yq -N "select(.kind == \"$1\" and .metadata.name == \"$2\")
      | .spec.template.spec.containers[0].image" <<<"$rendered"
  }
  backend_image="$(image_of Deployment haki-backend)"
  frontend_image="$(image_of Deployment haki-frontend)"
  job_image="$(image_of Job haki-migrate)"
  [[ "$job_image" == ghcr.io/andrei-petrache/haki-backend:* ]] \
    || fail "$overlay: the migration Job runs '$job_image'; list haki-migrate under images: with newName ghcr.io/andrei-petrache/haki-backend"
  backend_tag="${backend_image##*:}" job_tag="${job_image##*:}"
  # The pin lives next to the shared images, for the overlays that use them;
  # an overlay that uses them sets no image of its own, which would override
  # them unseen
  [[ ! -e "$overlay/rollback-pin.yaml" ]] \
    || fail "$overlay/rollback-pin.yaml: a rollback pin belongs in k8s/$images_component"
  pin=""
  # Read first, then compared: a yq error stops the script (set -e)
  uses_images="$(yq ".components // [] | any_c(. == \"../../$images_component\")" \
    "$overlay/kustomization.yaml")"
  if [[ "$uses_images" == true ]]; then
    [[ "$(yq '.images // [] | length' "$overlay/kustomization.yaml")" == 0 ]] \
      || fail "$overlay: uses k8s/$images_component, so it may not list images: of its own"
    pin="k8s/$images_component/rollback-pin.yaml"
  fi
  if [[ -n "$pin" && -e "$pin" ]]; then
    pin_backend="$(yq '.backendTag' "$pin")" pin_migrate="$(yq '.migrateTag' "$pin")"
    [[ "$pin_backend" =~ ^[0-9a-f]{40}$ && "$pin_migrate" =~ ^[0-9a-f]{40}$ ]] \
      || fail "$pin: backendTag and migrateTag must be full commit SHAs"
    [[ "$pin_backend" != "$pin_migrate" ]] \
      || fail "$pin: backendTag and migrateTag are equal, so it pins nothing: delete it"
    [[ -n "$(yq '.reason // ""' "$pin")" ]] || fail "$pin: a reason is required"
    [[ "$(yq '.since' "$pin")" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
      || fail "$pin: since must be a date (YYYY-MM-DD)"
    frontend_tag="${frontend_image##*:}"
    [[ "$backend_tag" == "$pin_backend" && "$frontend_tag" == "$pin_backend" ]] \
      || fail "$overlay: a rollback pin is active, so backend and frontend stay on ${pin_backend:0:7} (got ${backend_tag:0:7} and ${frontend_tag:0:7}); lift the pin first"
    [[ "$job_tag" == "$pin_migrate" ]] \
      || fail "$overlay: a rollback pin is active, so the migration Job stays on ${pin_migrate:0:7} (got ${job_tag:0:7})"
    echo "Rollback pin: backend ${pin_backend:0:7}, migration ${pin_migrate:0:7}, since $(yq '.since' "$pin")"
  else
    [[ "$job_tag" == "$backend_tag" ]] \
      || fail "$overlay: the migration Job runs ${job_tag:0:7}, the backend ${backend_tag:0:7}; they must match unless rollback-pin.yaml is active"
  fi

  # The frontend must proxy to the backend of its own namespace, by full
  # name: a copied overlay could otherwise send staging's API calls to prod
  namespace="$(yq -N 'select(.kind == "Deployment" and .metadata.name == "haki-frontend")
    | .metadata.namespace' <<<"$rendered")"
  backend_url="$(yq -N 'select(.kind == "ConfigMap"
    and .metadata.name == "haki-frontend-config*") | .data.BACKEND_URL' <<<"$rendered")"
  expected="http://haki-backend.$namespace.svc.cluster.local:8000"
  [[ "$backend_url" == "$expected" ]] \
    || fail "$overlay: BACKEND_URL is '$backend_url', expected '$expected'"

  # ArgoCD's order and protections (staging syncs through ArgoCD; on prod
  # the annotations are inert). The migration is a Sync hook between the
  # database and the backend, never PreSync (it would start before the new
  # hash-named ConfigMaps exist), and no TTL deletes it before ArgoCD reads
  # its result.
  # Picked out first, then read: see project() above
  migrate="$(yq -N 'select(.kind == "Job" and .metadata.name == "haki-migrate")' <<<"$rendered" |
    yq -N '[.metadata.annotations["argocd.argoproj.io/hook"],
       .metadata.annotations["argocd.argoproj.io/hook-delete-policy"],
       (.spec.ttlSecondsAfterFinished // "no-ttl")] | join(" ")')"
  [[ "$migrate" == "Sync BeforeHookCreation no-ttl" ]] \
    || fail "$overlay: haki-migrate must be a Sync hook with BeforeHookCreation and no TTL (got '$migrate')"
  [[ "$(yq -N 'select(.metadata.annotations["argocd.argoproj.io/hook"] == "PreSync")
    | .metadata.name' <<<"$rendered")" == "" ]] \
    || fail "$overlay: no PreSync hooks"
  # The namespace and the database must survive a prune or a deleted
  # Application: deleting either would delete the data
  while read -r kind; do
    opts="$(yq -N "select(.kind == \"$kind\")" <<<"$rendered" |
      yq -N '.metadata.annotations["argocd.argoproj.io/sync-options"]')"
    [[ "$opts" == "Prune=false,Delete=false" ]] \
      || fail "$overlay: the $kind must carry sync-options Prune=false,Delete=false"
  done <<<$'Namespace\nStatefulSet'
  # Waves in phase order: config, database, migrations, backend, frontend,
  # gateway. Every resource has one.
  waves="$(yq -N '.kind + "/" + .metadata.name + "=" +
    (.metadata.annotations["argocd.argoproj.io/sync-wave"] // "none")' <<<"$rendered")"
  expected_waves="$(cat <<'EOF'
Namespace=-2
ConfigMap=-2
Service/haki-db=-1
StatefulSet=-1
Job=0
Service/haki-backend=1
Deployment/haki-backend=1
Service/haki-frontend=2
Deployment/haki-frontend=2
EnvoyProxy=3
Gateway=3
HTTPRoute=3
ClientTrafficPolicy=3
EOF
)"
  while IFS= read -r line; do
    resource="${line%=*}" wave="${line##*=}"
    want=""
    while IFS='=' read -r key value; do
      [[ "$resource" == "$key" || "$resource" == "$key/"* ]] && want="$value"
    done <<<"$expected_waves"
    [[ -n "$want" ]] || fail "$overlay: $resource has no expected sync wave (add it here)"
    [[ "$wave" == "$want" ]] || fail "$overlay: $resource is in wave '$wave', expected '$want'"
  done <<<"$waves"
  # On the object, never in a pod template: there it would restart the pods
  [[ "$(yq -N '.. | select(has("template")) | .template.metadata.annotations // {}
    | keys | .[] | select(test("^argocd\\.argoproj\\.io/"))' <<<"$rendered")" == "" ]] \
    || fail "$overlay: ArgoCD annotations belong on the object, not in its pod template"
  [[ "$(yq -N 'select(.kind == "Secret" or .kind == "PersistentVolumeClaim")
    | .metadata.name' <<<"$rendered")" == "" ]] \
    || fail "$overlay: Secrets and PersistentVolumeClaims stay out of Git"

  echo "PostgreSQL: $k8s_db_image"
  echo "Backend URL: $backend_url"
  echo "Images: $(tr '\n' ' ' <<<"$images")"
done
