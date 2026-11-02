# Haki on a local Kubernetes cluster (kind)

The whole app in a [kind](https://kind.sigs.k8s.io) cluster (Kubernetes in
Docker): the same images CI built and published, no local build.

The manifests are built with [Kustomize](https://kustomize.io), which is
part of kubectl (`kubectl apply -k`, `kubectl kustomize`): `base/` holds what
every environment shares, and each overlay in `overlays/` adds what differs.

| File | What it creates |
|---|---|
| `kind-config.yaml` | the cluster `haki`: one node, image pinned by digest |
| `base/kustomization.yaml` | the ConfigMaps `haki-db-config`, `haki-backend-config`, `haki-frontend-config`; the PostgreSQL image pin |
| `base/namespace.yaml` | the namespace, renamed by each overlay |
| `base/postgres.yaml` | PostgreSQL: StatefulSet `haki-db` with a 1 GiB volume, headless Service |
| `base/migrate-job.yaml` | Job `haki-migrate`: `alembic upgrade head`, once |
| `base/backend.yaml` | Deployment `haki-backend` (2 replicas), Service on port 8000 |
| `base/frontend.yaml` | Deployment `haki-frontend` (1 replica), Service on port 8080 |
| `base/gateway.yaml` | Gateway `haki` (HTTP, port 80) and HTTPRoute to the frontend; the Envoy proxy's settings (EnvoyProxy, ClientTrafficPolicy) |
| `platform/gatewayclass.yaml` | the GatewayClass `envoy-gateway`: cluster-wide, applied once, not by an overlay |
| `argocd/project.yaml` | the ArgoCD project `haki`: this repository only, into `haki-staging` only, no Secrets and no volumes |
| `argocd/default-project.yaml` | ArgoCD's `default` project, emptied of every permission |
| `argocd/haki-staging.yaml` | the ArgoCD Application `haki-staging`: `overlays/staging` on `main`, synced into `haki-staging` |
| `overlays/prod/` | namespace `haki`; the app image tags; the frontend's `BACKEND_URL` |
| `overlays/staging/` | namespace `haki-staging`, its own database, 1 backend replica; its own image tags and `BACKEND_URL` |

To see what an overlay produces: `kubectl kustomize k8s/overlays/prod`.

Kustomize appends a hash of each ConfigMap's contents to its name (e.g.
`haki-frontend-config-b82c89kt8t`) and updates the references. Changing a
setting therefore creates a new ConfigMap and restarts only the pods that read
it: a new `BACKEND_URL` restarts the frontend, not PostgreSQL.

The Secret `haki-secrets` is the only piece not in this directory: it is
created by hand (below) and never committed.

Every pod runs as a fixed non-root user with a read-only root filesystem, no
Linux capabilities and the default seccomp profile; where a program must
write (Nginx's `/tmp` and `/etc/nginx/conf.d`, PostgreSQL's socket), it gets
an `emptyDir` volume.

## Requirements

Docker, kind v0.33.0 (the node image digest in `kind-config.yaml` belongs to
it), kubectl within one minor version of Kubernetes 1.37, and Helm v4.3.1 for
Envoy Gateway (below).

## Check the manifests

```bash
k8s/scripts/check-manifests.sh
```

No cluster needed. It validates `platform/` and the `kustomize build` output
of every overlay with [kubeconform](https://github.com/yannh/kubeconform)
against the API schemas of the Kubernetes version in `kind-config.yaml`
(`-strict`: unknown fields such as typos fail too). Those schemas come from a
fixed commit of
yannh/kubernetes-json-schema; the Gateway API and Envoy Gateway ones from a
fixed commit of datreeio/CRDs-catalog. It also checks that PostgreSQL runs the
image pinned in `compose.yaml`, that the app images are pinned to a full
commit SHA, and that each overlay's frontend proxies to the backend of its
own namespace. It needs kustomize, kubeconform and mikefarah/yq, at the
versions in `scripts/install-tools.sh`. CI runs it in the `manifests` job.

## Envoy Gateway

The Gateway API resources in `base/gateway.yaml` need a controller that
implements them: [Envoy Gateway](https://gateway.envoyproxy.io) v1.9.3,
installed by hand with Helm, once per cluster, outside the overlays. The
chart is pulled from its OCI registry and installed only after its SHA-256
matches (a registry tag can move, a checksum cannot):

```bash
kubectl config current-context   # must print kind-haki

tmp="$(mktemp -d)" && cd "$tmp"
helm pull oci://docker.io/envoyproxy/gateway-helm --version v1.9.3
sha256sum -c - <<'EOF'
1a152513adbcdb0527d7bbe3ea9b090abeb87e4ec9f34b2c18ac8c37f3177541  gateway-helm-v1.9.3.tgz
EOF
helm install eg ./gateway-helm-v1.9.3.tgz \
  --namespace envoy-gateway-system --create-namespace \
  --kube-context kind-haki
cd - >/dev/null && rm -rf "$tmp"

kubectl -n envoy-gateway-system wait --for=condition=Available \
  deployment/envoy-gateway --timeout=5m
# Gateway API CRDs: 10 standard-group + 3 experimental-group = 13
kubectl get crd -o name | grep -cE 'gateway\.networking\.(x-)?k8s\.io$'

kubectl apply -f k8s/platform/gatewayclass.yaml
kubectl wait --for=condition=Accepted gatewayclass/envoy-gateway --timeout=2m
```

`helm list -n envoy-gateway-system` shows the release `eg`. To reinstall:
`helm uninstall eg -n envoy-gateway-system`, then the commands above. Helm
never deletes or upgrades the CRDs a chart ships, so the Gateway API CRDs (and
the Gateways and routes using them) survive an uninstall, and an upgrade to a
new version needs the CRD steps from that release's upgrade notes as well as
`helm upgrade eg <new chart> -n envoy-gateway-system`.

For each Gateway, Envoy Gateway runs an Envoy proxy (Deployment and Service)
in `envoy-gateway-system`, named after the Gateway's namespace and name.

## ArgoCD

[ArgoCD](https://argo-cd.readthedocs.io) v3.5.7 keeps the cluster in line
with Git (GitOps). It is installed by hand, once per cluster, like Envoy
Gateway, in its own namespace `argocd`. In S8 it manages staging only; prod
keeps the manual phases below until S9.

The manifest is taken from the release's commit, not its tag (a tag can
move, a commit cannot), and applied only after its SHA-256 matches. The
release publishes no checksum for it, so the one below was computed here
from that commit's file:

```bash
kubectl config current-context   # must print kind-haki

tmp="$(mktemp -d)" && cd "$tmp"
# v3.5.7 = commit 6d732962f61a99c2a0f221fd26b9aac7c83bcf18
curl -fsSLo install.yaml \
  https://raw.githubusercontent.com/argoproj/argo-cd/6d732962f61a99c2a0f221fd26b9aac7c83bcf18/manifests/install.yaml
sha256sum -c - <<'EOF'
09bfbb9041b4a8503c6e4fa22cf41c403fa62be17526de353648a4551f5beb77  install.yaml
EOF
grep -o 'image: .*' install.yaml | sort -u    # argocd:v3.5.7, no -rc
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts -f install.yaml
cd - >/dev/null && rm -rf "$tmp"

kubectl -n argocd rollout status deployment/argocd-server --timeout=5m
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=5m

kubectl apply -f k8s/argocd/default-project.yaml -f k8s/argocd/project.yaml
```

`--server-side`: the ApplicationSet CRD is larger than the 262,144 bytes
that kubectl's client-side apply can keep in its `last-applied-configuration`
annotation, so the API server merges the fields instead.
`--force-conflicts` lets an upgrade take over the fields a previous apply
owned.

The projects are ArgoCD's boundary: `project.yaml` allows this repository
only, the `haki-staging` namespace only and only the kinds the staging
overlay renders, never Secrets or PersistentVolumeClaims. The `default`
project allows nothing, so an Application without a project deploys
nothing. `check-manifests.sh` fails on any change that widens them.

### Open the UI

Only through a tunnel, never exposed: `kubectl port-forward` listens on
127.0.0.1 only.

```bash
kubectl -n argocd port-forward svc/argocd-server 8443:443   # https://127.0.0.1:8443
```

The certificate is self-signed, so the browser warns once. Log in as
`admin`. The first password is in a Secret; copy it straight to the Windows
clipboard, so it is never shown, never in the shell history and never in a
file:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d | clip.exe
```

Then, in the UI, User Info → Update password, with a new password from a
password manager; empty the clipboard (`printf '' | clip.exe`) and delete
the initial Secret, which ArgoCD no longer uses:
`kubectl -n argocd delete secret argocd-initial-admin-secret`.

### Staging through ArgoCD

The Application `haki-staging` syncs `k8s/overlays/staging` from `main` into
`haki-staging`, in the order of the sync waves: config, database, the
migration Job (a Sync hook: if it fails, the sync stops and the backend
keeps its old image), backend, frontend, gateway. Old ConfigMaps are pruned
only at the end (`PruneLast`), and a failed sync is not retried.

Automated sync is on: a commit merged to `main` that changes what the
staging overlay renders reaches staging on its own, within about 3 minutes
(ArgoCD polls Git; there is no webhook). Self-heal undoes changes made in
the cluster by hand, so never `kubectl apply` or `kubectl edit` staging:
change Git instead.

```bash
kubectl apply -f k8s/argocd/haki-staging.yaml
kubectl -n argocd get application haki-staging \
  -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'   # Synced Healthy
# Sync by hand (all resources, so the migration hook runs), without the CLI:
kubectl -n argocd patch application haki-staging --type merge \
  -p '{"operation": {"initiatedBy": {"username": "andrei"}, "sync": {"revision": "main"}}}'
```

The Secret `haki-secrets` stays manual (phase 2 above): ArgoCD may not
touch Secrets. The namespace and the database are never pruned and never
deleted with the Application.

To stop ArgoCD managing staging, delete only the Application:
`kubectl -n argocd delete application haki-staging`. It has no finalizer,
so every resource stays and staging goes back to the manual phases. Never
delete it from the UI or with `argocd app delete`: both delete in cascade by
default, which would take the Deployments, Services and Gateway down (the
namespace, the database and its volume would still stay).

## Start from scratch

Run from the repository root. An overlay is applied in phases, selected by
label (`-l`), because each phase needs the previous one:

1. the namespace and the ConfigMaps (label `haki/phase=config`): every pod
   reads a ConfigMap, and a pod whose ConfigMap is missing stays in
   `CreateContainerConfigError`;
2. the Secret, by hand, the first time only;
3. the database: the migrations need it;
4. the migrations, waited for: the backend needs the tables;
5. everything else.

For staging, use `O=k8s/overlays/staging NS=haki-staging`.

```bash
kind create cluster --config k8s/kind-config.yaml    # kubectl context: kind-haki
# then Envoy Gateway and the GatewayClass, once per cluster (above)
O=k8s/overlays/prod NS=haki

kubectl apply -k $O -l haki/phase=config

# Secrets, generated on the spot: never shown, never stored in a file
kubectl -n $NS create secret generic haki-secrets \
  --from-literal=DB_USER=haki \
  --from-literal=DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')" \
  --from-literal=JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
kubectl -n $NS describe secret haki-secrets          # key names and sizes only

kubectl apply -k $O -l app.kubernetes.io/component=database
kubectl -n $NS rollout status statefulset/haki-db

kubectl -n $NS delete job haki-migrate --ignore-not-found
kubectl apply -k $O -l app.kubernetes.io/component=migrations
kubectl -n $NS wait --for=condition=complete job/haki-migrate --timeout=5m

kubectl apply -k $O
kubectl -n $NS rollout status deployment/haki-backend
kubectl -n $NS rollout status deployment/haki-frontend
kubectl -n $NS wait --for=condition=Programmed gateway/haki --timeout=5m
```

Applying everything at once (`kubectl apply -k $O` alone) would start the
backend before its tables exist. In the last step the StatefulSet may show as
`configured`: kubectl only updates its bookkeeping annotation, the pod is not
restarted (`kubectl diff -k $O` shows no change).

The HTTPRoute may show as `configured` too, on every apply after the first,
with nothing changed: the API server fills in defaults the manifest leaves
out (`group`, `kind`, `weight: 1`, a `PathPrefix /` match), kubectl's
client-side apply sees a difference and sends a patch, and the server finds
nothing to change. To confirm, `metadata.generation` stays the same, the
route's `managedFields` gain no new kubectl entry and `kubectl diff -k $O`
shows no change.

Open the app through the Gateway, with a tunnel to its Envoy proxy's Service
(8081, so the Compose stack can keep 8080):

```bash
svc="$(kubectl -n envoy-gateway-system get service -o name \
  -l gateway.envoyproxy.io/owning-gateway-namespace=$NS,gateway.envoyproxy.io/owning-gateway-name=haki)"
kubectl -n envoy-gateway-system port-forward "$svc" 8081:80   # http://127.0.0.1:8081
scripts/smoke-test.sh http://127.0.0.1:8081                   # in another terminal
```

The smoke test creates a throwaway user, food, exercise and workout in the
cluster's database.

## Secrets

- A Secret is only base64-encoded, not encrypted: anyone who can read Secrets
  in the namespace can read the values.
- PostgreSQL uses `DB_USER` and `DB_PASSWORD` only once, when it creates its
  data directory. Recreating the Secret later with a new password does not
  change it in the database, and the backend can then no longer connect:
  change the password in PostgreSQL too, or start over with a new volume.
- A new `JWT_SECRET_KEY` logs every user out (their tokens stop verifying).

## Deploy new images or settings

The image tag is the full commit SHA of `main`, set once per overlay under
`images:` in its `kustomization.yaml` (the backend tag covers the migration
Job too).

- **Staging:** a pull request that changes `overlays/staging`. Once it is
  merged, ArgoCD applies it in wave order, migration included (above).
- **Prod:** after changing the tag, or anything in `haki-backend-config`,
  migrate before the backend: phases 4 and 5 above. A Job cannot be changed
  once created, so it is deleted first. Other changes need only phase 5.

On prod, the ConfigMaps a change replaces are not deleted: `kubectl apply`
leaves alone what is no longer in the manifests. They are harmless; to
remove the unused ones, list them with
`kubectl -n $NS get configmap -l haki/phase=config` and delete those that no
pod refers to. On staging, ArgoCD prunes the ones it created; those left
from before the takeover (applied by kubectl) are not tracked and stay.

### Back up before a migration

A migration changes the database for good, and a new image cannot undo it.
Before phase 4 on prod, dump the database to a file outside the repository,
readable only by you:

```bash
NS=haki
mkdir -p -m 700 ~/haki-backups
f=~/haki-backups/haki-$NS-$(date +%Y%m%d-%H%M%S).dump
# Custom format (-Fc): compressed, read by pg_restore. No -t: binary-safe
(umask 077 && kubectl -n $NS exec -i haki-db-0 -c postgres -- \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$f")
ls -l "$f"                                           # -rw-------, not empty
kubectl -n $NS exec -i haki-db-0 -c postgres -- pg_restore --list < "$f" \
  | grep -E '^; +(Format|TOC Entries)'               # readable: CUSTOM, N entries
```

The credentials stay in the pod (`$POSTGRES_USER` and `$POSTGRES_DB` are
expanded there) and nothing is printed but the archive's header. Stop if
`pg_dump` fails or the file is empty. The dump holds every user's data: keep
it out of the repository and delete it once it is no longer needed.
Restoring is a decision of its own, not part of a deploy.

### Moving a cluster from before Kustomize

A cluster set up with the old per-file manifests keeps its data: prod uses
the same namespace, names and volume. Run phases 1, 3, 4 and 5 (the Secret
stays). PostgreSQL restarts once, because it now reads `haki-db-config`.
Then delete the old ConfigMap: `kubectl -n haki delete configmap haki-config`.

A finished migration Job stays, with its logs, until the next run replaces
it (phase 4 deletes it first): it has no TTL, because ArgoCD must still find
it to read its result. `kubectl logs job/haki-migrate` shows one of its
pods, not necessarily the last: after retries, pick the pod by name from
`kubectl -n haki get pods -l app.kubernetes.io/name=haki-migrate`.

## Stop, start, delete

```bash
docker stop haki-control-plane      # stop the cluster; everything is kept
docker start haki-control-plane     # pods restart by themselves
kind delete cluster --name haki     # delete the cluster, database included
```

The database lives in the PersistentVolumeClaim `data-haki-db-0`: it survives
pod restarts and deleting the StatefulSet, but `kubectl -n haki delete pvc
data-haki-db-0` or `kind delete cluster` deletes the data for good. None of
this touches the Compose `db-data` volume.

## Known limits

- **A database outage takes every backend pod out of service:** the
  readiness probe calls `/ready`, which fails while PostgreSQL is
  unreachable, and with a single database every pod fails it at once. The
  Service then has no endpoints, and Nginx answers the API itself with the
  backend's own 503, JSON body and `Retry-After: 5` (`error_page` in
  `frontend/nginx.conf.template`, review L19). The pods are not restarted
  (liveness uses `/health`) and come back on their own; the app itself (`/`)
  keeps loading. The first requests after the outage starts may still reach
  a backend, until kube-proxy updates its rules.
- **The PostgreSQL pin is in two places:** `images:` in
  `base/kustomization.yaml` and `services.db.image` in `compose.yaml`
  (Dependabot updates only the latter). The `manifests` job fails until both
  match.
- **Phases by hand:** kubectl does not know the order above. The manifests
  now carry it for ArgoCD as sync waves (`argocd.argoproj.io/sync-wave`:
  config -2, database -1, migrations 0 as a Sync hook, backend 1, frontend 2,
  gateway 3); `check-manifests.sh` checks the order. kubectl ignores those
  annotations, so prod keeps the manual phases until S9; staging moves to
  ArgoCD in S8.
- **Rate limit through port-forward:** kubectl port-forward connects to
  Envoy from the Envoy pod's own address, so every client looks the same and
  all share one login/signup budget (6 requests, then 429; a smoke test run
  uses two). The limit is per Nginx replica, hence one frontend replica.
- **Nginx trusts X-Forwarded-For from the whole pod CIDR** (`REAL_IP_FROM`,
  `10.244.0.0/16`), not only from Envoy: any pod in the cluster can call the
  frontend Service directly with an X-Forwarded-For of its choice and get a
  fresh login/signup budget per value (tested). Through the Gateway this is
  closed: Envoy drops the client's X-Forwarded-For first (ClientTrafficPolicy
  in `base/gateway.yaml`). Fix later with a NetworkPolicy that lets only the
  Envoy pods reach the frontend (check that the cluster's CNI enforces it).
- **Envoy Gateway v1.9 is not tested on Kubernetes 1.37:** its compatibility
  matrix lists 1.33-1.36 (supported until 2027-02-14); 1.37 arrives with
  v1.10. Move to v1.10 once it is released and past the 7-day cooldown used
  in `.github/dependabot.yml`.
- **Gateway API CRDs from the experimental channel:** the chart installs
  v1.6.1 of the experimental channel (stable resources plus ones still being
  tried). The manifests use only stable ones (GatewayClass, Gateway,
  HTTPRoute). On AWS, install the standard channel instead: the CRDs on their
  own, and the chart with `--set crds.enabled=false`.
- **Envoy Gateway is installed by hand,** with Helm, outside Kustomize and CI
  (version, checksum and reinstall above). Its version is pinned only in this
  README.
- **ArgoCD v3.5.7 is not tested on Kubernetes 1.37:** its compatibility
  matrix lists 1.33-1.36; 1.37 arrives with v3.6. Chosen on 2 November 2026
  instead of waiting for v3.6.0 and its 7-day cooldown: the cluster is local
  and can be rebuilt. Move to v3.6.x once it is out (new commit and
  checksum above).
- **ArgoCD is installed by hand** and its version is pinned only in this
  README, like Envoy Gateway's. Its controller has rights on the whole
  cluster: the `haki` project limits what ArgoCD does, not what its service
  account could do.
- **Client IP behind a load balancer (AWS):** the ClientTrafficPolicy drops
  every incoming X-Forwarded-For because nothing stands in front of Envoy
  here. Behind a load balancer that sets the header, keep its entry instead
  (`clientIPDetection` with `numTrustedHops` or `trustedCIDRs`), and set
  `REAL_IP_FROM` to the cluster's pod CIDR there.
- **Volume size:** kind's local-path storage does not enforce the 1 GiB.
- See also the Kubernetes / AWS notes in `docs/review-2026-11.md`.
