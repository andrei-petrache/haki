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
| `argocd/project-prod.yaml` | the ArgoCD project `haki-prod`: this repository only, into `haki` only, no Secrets and no volumes |
| `argocd/haki-prod.yaml` | the ArgoCD Application `haki-prod`: `overlays/prod` at one fixed commit of `main`, synced into `haki`; applied by `haki-apps` |
| `argocd/project-apps.yaml` | the ArgoCD project `haki-apps`: Applications only, into `argocd` only, from this repository only |
| `argocd/haki-apps.yaml` | the ArgoCD Application `haki-apps`: `argocd/haki-prod.yaml` on `main`, and no other file; never prunes |
| `components/images/` | the app image tags (backend, frontend, migration), included by both overlays; an active `rollback-pin.yaml` sits next to them |
| `overlays/prod/` | namespace `haki`; the image tags from `components/images`, at the commit prod is promoted to; the frontend's `BACKEND_URL` |
| `overlays/staging/` | namespace `haki-staging`, its own database, 1 backend replica; the image tags from `components/images`; its `BACKEND_URL` |

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
Gateway, in its own namespace `argocd`. It manages staging since S8 and
prod since S9 (below, "Prod through ArgoCD"); until prod is taken over, it
keeps the manual phases below.

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
overlay renders, never Secrets or PersistentVolumeClaims; `project-prod.yaml`
allows the same, for the `haki` namespace only. Separate projects, so an
Application of one environment can never deploy into the other. The `default`
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

### Prod through ArgoCD

The Application `haki-prod` syncs `k8s/overlays/prod` into `haki`, in the
same waves as staging, from one fixed commit of `main`: its
`targetRevision` is a full commit SHA, never a branch. A change merged to
`main` therefore never reaches prod by itself, whether it changes the tags,
the overlay or `base/`; prod gets it only when that SHA moves. Since the
takeover, `haki-apps` (below) applies `haki-prod.yaml` from `main`, and
`prod-guard` refuses any pull request that changes its `targetRevision`.

The takeover is done by hand, as for staging in S8: first without automated
sync, so the diff is seen before anything changes. Each step needs Andrei's
OK.

```bash
# 1. Back up first: the takeover runs the migration hook again (expected to
#    change nothing); dump to ~/backups as in "Back up before a migration"

# 2. Before: pods, their start times, the volume, the database revision
kubectl -n haki get pods -o custom-columns=NAME:.metadata.name,START:.status.startTime
kubectl -n haki get pvc data-haki-db-0 -o jsonpath='{.metadata.uid}{"\n"}'
kubectl -n haki exec haki-db-0 -c postgres -- \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select version_num from alembic_version"'

# 3. The project and the Application; ArgoCD only compares, nothing changes
kubectl apply -f k8s/argocd/project-prod.yaml -f k8s/argocd/haki-prod.yaml
kubectl -n argocd get application haki-prod \
  -o jsonpath='{.spec.syncPolicy}{"\n"}'          # no "automated"
kubectl -n argocd get application haki-prod \
  -o jsonpath='{range .status.resources[*]}{.kind}/{.name} {.status}{"\n"}{end}'

# 4. Sync by hand, without prune, on the fixed SHA
kubectl -n argocd patch application haki-prod --type merge -p '{"operation":
  {"initiatedBy": {"username": "andrei"},
   "sync": {"revision": "<targetRevision>", "prune": false}}}'
kubectl -n argocd get application haki-prod \
  -o jsonpath='{.status.sync.status} {.status.health.status} {.status.sync.revision}{"\n"}'
```

Then step 2 again: the same pods with the same start times, the same volume
and the same database revision.

To stop ArgoCD managing prod, delete `haki-apps` first (or it puts
`haki-prod` back), then `haki-prod`:
`kubectl -n argocd delete application haki-apps haki-prod`. Neither has a
finalizer, so everything stays and prod goes back to the manual phases.

### haki-apps and prod-guard

`haki-apps` is an Application whose only resource is another Application
(app of apps): it applies `k8s/argocd/haki-prod.yaml` from `main`, and no
other file of the directory (`directory.include`). Its project `haki-apps`
allows Applications only, in the `argocd` namespace only, from this
repository only, and nothing cluster-scoped. It never prunes, and
`haki-prod` carries `sync-options: Prune=false,Delete=false`: if
`haki-prod.yaml` left `main`, or a sync with prune ran, `haki-prod` would
stay. Self-heal puts back any change made to `haki-prod` by hand.

What protects prod is then `haki-prod.yaml` on `main`, guarded by the
required check `prod-guard` (`.github/workflows/guard.yml`). It runs on
`pull_request_target`: the workflow and `scripts/check-prod-app.sh` come
from `main`, never from the pull request, whose commits are only fetched and
read as data. A pull request cannot weaken the rule it is checked by; a new
rule takes effect once merged. It refuses a pull request that:

- changes `targetRevision`, unless it is the promotion's own pull request
  (below, "Promote to prod");
- deletes the file, or adds a second document to it: ArgoCD v3.5.7 cannot
  limit an Application's name in a project (`namespaceResourceWhitelist`
  has no `name`), so a second Application in this file would be created,
  with any revision (tried on a throwaway cluster, 9 November 2026);
- changes the project, repository, path or destination, or adds anything
  else to `spec` or `spec.source` (e.g. `source.kustomize.images` would
  change prod's images without moving `targetRevision`);
- turns on automated sync in any shape but `enabled: true`, `prune: false`,
  `selfHeal: true` (nothing in prod is deleted without a person; hand edits
  in the cluster are undone), or changes the sync options or retries.

Comments stay free. `prod-guard` also runs `scripts/check-tag-pr.sh`, the
scope of the tag bot's pull request (above), for the same reason.

Applied by hand, once, after the pull request that adds them is merged:

```bash
kubectl apply -f k8s/argocd/project-apps.yaml -f k8s/argocd/haki-apps.yaml
kubectl -n argocd get application haki-apps \
  -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'   # Synced Healthy
kubectl -n argocd get application haki-prod \
  -o jsonpath='{.spec.source.targetRevision} {.metadata.annotations}{"\n"}'
```

Taking `haki-prod` over changes only its annotations (tracking and
`sync-options`); its `targetRevision` stays, so prod is not synced.

### Promote to prod

A commit of `main` reaches prod only through the workflow **Promote to
prod** (`.github/workflows/promote-prod.yml`), started by hand from `main`
(Actions → Promote to prod → Run workflow) with the commit's full SHA.

Prod never runs the promoted commit's own code: it runs the image tags
written at that commit, in `components/images` (or, at older revisions such
as `00e3da8`, in the prod overlay's own `images:` list), a rollback pin
included: what staging ran. `scripts/prod-images.sh <SHA>` prints them,
rendered from `k8s/overlays/prod` as it is at that commit: `backend`,
`frontend` and `migrate` (the `haki-migrate` Job, the migration hook). So the
checks below judge those tags, not the revision's SHA.

1. `check` runs `scripts/check-promotion.sh`: the SHA is a commit of `main`
   other than the current one; each image it runs is a commit of `main`
   published on GHCR; and the migration image never steps back across a
   migration. Migrations are counted between the commits of the current and
   the new `haki-migrate` images, not between the revisions: `00e3da8` ->
   `c339f35` lists the Programs migration (images `081c5f2` -> `4b65cc6`),
   and `c339f35` -> `00e3da8` is refused. Its summary shows the images now
   and after, any new migration, and the commits.
2. `approve` waits in the environment `prod` for Andrei's approval. Before
   approving, he checks that staging ran this SHA, Synced and Healthy (GitHub
   cannot see the cluster).
3. `open-pr` checks again on `main` as it is then, and the tag bot opens the
   pull request on `bot/promote-prod`: one commit, made through the API (so
   GitHub verifies it as the bot's), that changes the `targetRevision` line
   of `haki-prod.yaml` only. No auto-merge.
4. If the summary lists new migrations, dump prod first ("Back up before a
   migration"). Then Andrei merges; `haki-apps` moves `haki-prod` to the new
   revision.

`prod-guard` lets a change of `targetRevision` through only in that pull
request: from `bot/promote-prod` of this repository, opened by
`haki-tag-bot[bot]`, with exactly one commit, the head, verified, authored
by the bot and committed by GitHub (`web-flow`: a commit made through the
API is GitHub's, signed by it), changing that one line, to a commit that
`check-promotion.sh` accepts. A person who pushes to the branch adds a
commit of their own, and the pull request fails. The ruleset on `bot/**`
closes the rest: only the tag bot (its GitHub App, on the bypass list) may
create, update, force-push or delete those branches, so nobody else can put
a commit authored as the bot there.

**A rollback of prod is a promotion of an older commit of `main`,** through
the same workflow and the same approval. No pull request by hand changes
`targetRevision`, and neither does a `git revert`: `prod-guard` refuses both.
`check-promotion.sh` refuses a migration image older than prod's when the
migrations changed in between (its `alembic upgrade head` would stop at the
hook); then the way back is a commit of `main` with a rollback pin (below,
"Roll back staging after a migration"): the app images step back, the
migration image stays, so the promotion migrates nothing. Staging runs it
first, and it is then promoted like any other commit.

### Roll back staging

A rollback is a `git revert` of the commit that changed staging's tags,
through a pull request like any other change. Measured in S8 (3 November
2026, ArgoCD v3.5.7), in seconds after the merge:

| Change | First new pod Ready | Sync finished | Of which waiting for ArgoCD to poll | Of which sync (`startedAt` to `finishedAt`) | How |
| --- | --- | --- | --- | --- | --- |
| New tag (`62841b0`) | 21 s | 26 s | 7 s | 19 s | One run, reconstructed from ArgoCD and Kubernetes timestamps |
| Its revert (`384f067`) | 94-95 s | 97 s | 82 s | 15 s | Observed live |

The deploy itself takes 15-19 s; the poll can take the total to about
3 min 20 s. The migration runs before the backend: the sync waves guarantee
it (the backend's wave starts only once the hook has succeeded); timestamps
to the second cannot tell the two apart.

**After a migration, `git revert` can fail at the hook, and the new version
stays active:**

- **Proven** (on a throwaway PostgreSQL, 3 November 2026): `alembic upgrade
  head` from an image older than the database stops with exit 255,
  `Can't locate revision identified by '...'`, and changes nothing.
- **Inferred for this case**, from the failed-migration test: the migration
  Job fails (after its retries, `backoffLimit: 4`), the sync stops at the
  hook, backend and frontend keep the new image and keep working, and the
  sync is not retried; staging stays OutOfSync on the new version.
- **Tested on staging** (4 November 2026, with Programs): a rollback after a
  migration through the rollback pin below, not through `git revert`. The
  Job stayed on the newer tag and changed nothing, the older backend and
  frontend ran on the newer schema (#61), and lifting the pin brought the new
  version back with the data intact (#62). A plain `git revert` after a
  migration was not tried: it would stop at the hook, as above.

So a revert is a simple rollback only for a release without a migration.
Migrations stay backward-compatible, deletions in a later release
(`docs/journal/decisions.md`), and an older image passes the hook only through
the rollback pin below. Backups: the manual `pg_dump` before a prod migration
exists (below); scheduled backups and a tested restore do not yet.

### Roll back staging after a migration

Not a `git revert`: backend and frontend go back to the older images, while
the migration Job stays on the newer tag. Its `alembic upgrade head` then
finds the database already at its own head and does nothing; the older code
runs on the newer schema, which expand/contract migrations allow. The file
`components/images/rollback-pin.yaml` records the two tags while this lasts.

One pull request, prepared by a script (by hand it is easy to move the wrong
tag):

```bash
git switch -c fix/rollback-staging origin/main
scripts/staging-rollback-pin.sh start <older SHA> "<reason>"
k8s/scripts/check-manifests.sh
git add -A k8s/components/images && git commit -m "Roll staging back to <older>"
```

The script refuses a SHA that is not older than the current tag, and a start
while a pin is already active. Before opening that pull request, close the
bot's open tag pull request, if there is one (see below).

While the pin exists, staging takes no new backend tag: `check-manifests.sh`
fails on any backend or frontend tag other than `backendTag`, or a migration
tag other than `migrateTag`, and the `bump-staging` job fails on `main` with
"A rollback pin is active". Code merged in the meantime stays on `main`; its
bump is not retried.

**Lift the pin** in one pull request, once the fix is merged and its images
are published:

```bash
git switch -c fix/lift-rollback-pin origin/main
scripts/staging-rollback-pin.sh end <SHA of main, with the fix>
k8s/scripts/check-manifests.sh
git add -A k8s/components/images && git commit -m "Lift the staging rollback pin"
```

`end` deletes the pin and moves all three tags to that SHA. It accepts any
commit of `main` that contains `migrateTag` in its history (or its
migrations would not know the database's revision) and whose images are on
GHCR; the script checks both. Every push to `main` publishes images, so this
includes a commit that changed only `k8s/`, such as the merge of the pin
itself (`387843a` in the drill). Main is linear, so its newest commit carries
everything merged during the pin: use that SHA, which also recovers the code
whose bump was refused.

**A tag pull request opened before the pin** could still merge after it: its
CI ran on the `main` of that moment. Close it when the pin starts; with the
ruleset's "Require branches to be up to date before merging", GitHub also
refuses to merge it until it is updated, and the update reruns the
`manifests` check against the pin, which fails.

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

The image tag is the full commit SHA of `main`, set under `images:` once, in
`components/images/kustomization.yaml`, which both overlays include (the
backend tag covers the migration Job too). An overlay that includes the
component may not list images of its own. Staging follows `main`; prod gets
the tags of the commit it is promoted to.

- **Staging:** a pull request that changes `components/images`. Once it is
  merged, ArgoCD applies it in wave order, migration included (above). After
  a push to `main` that changes `backend/` or `frontend/`, the CI job
  `bump-staging` opens that pull request itself (`scripts/bump-staging-tag.sh`),
  always on the branch `bot/bump-staging`: a newer commit updates the same
  pull request. Andrei merges it, or auto-merge does (below).
- **Prod, once ArgoCD has taken it over:** only by a promotion (above,
  "Promote to prod"); never `kubectl apply` it by hand.
- **Prod before the takeover:** after changing the tag, or anything in
  `haki-backend-config`, migrate before the backend: phases 4 and 5 above. A
  Job cannot be changed once created, so it is deleted first. Other changes
  need only phase 5.

On prod, the ConfigMaps a change replaces are not deleted: `kubectl apply`
leaves alone what is no longer in the manifests. They are harmless; to
remove the unused ones, list them with
`kubectl -n $NS get configmap -l haki/phase=config` and delete those that no
pod refers to. On staging, ArgoCD prunes the ones it created; those left
from before the takeover (applied by kubectl) are not tracked and stay.

### Auto-merge of the tag pull request

The `bump-staging` job arms auto-merge on its pull request when the
repository variable `TAG_BOT_AUTO_MERGE` is `true`. GitHub then merges it
(rebase) once every required check passes and the branch is up to date with
`main`. The check `prod-guard` running `scripts/check-tag-pr.sh` (from
`main`'s copy, see "haki-apps and prod-guard") is what makes this safe; until
S9 it ran as `tag-pr-scope`, from the pull request's own copy. A pull request
from `bot/bump-staging` passes only if it changes
nothing but the three `newTag` lines of `components/images/kustomization.yaml`
(backend, frontend, migration), all to one full SHA, with no rollback pin.
Every other pull request passes it at once.

Turning it on, in this order (each step needs the one before):

1. Ruleset `protect-main`: the check (now `prod-guard`) among the required
   checks, added only after the pull request that adds its job is merged
   (before, every open pull request would wait for a check that never
   reports). That makes 9.
2. Settings → General: tick **Allow auto-merge**.
3. Settings → Secrets and variables → Actions → Variables: set
   `TAG_BOT_AUTO_MERGE` to `true`.

The variable only decides whether new runs arm auto-merge. **A pull request
already armed stays armed** when the variable changes: stop it there with
`gh pr merge --disable-auto <number>`, or **Disable auto-merge** on the pull
request's page. A tag pull request behind `main` (after another merge) waits
until it is updated: **Update branch** on its page, or the next bump.

First real run (4 November 2026): #60, the tag pull request of the Programs
API. The bot armed auto-merge 3 s after opening it; GitHub merged it 51 s
after its checks passed, and the first new pod was Ready 2 min 16 s later,
most of it ArgoCD's poll.

### Back up before a migration

A migration changes the database for good, and a new image cannot undo it.
Before phase 4 on prod, dump the database to a file outside the repository,
readable only by you:

```bash
NS=haki
mkdir -p -m 700 ~/backups
f=~/backups/haki-$NS-$(date +%Y%m%d-%H%M%S).dump
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
  annotations, so prod keeps the manual phases until ArgoCD takes it over in
  S9; staging moved to ArgoCD in S8.
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
- **When the migration runs on staging:** on every full sync (a new commit,
  a manual sync, a change to the Application itself), not on a self-heal
  that re-applies a single resource (tested on v3.5.7). Safe while every
  migration is an idempotent Alembic step; a long one holds the sync open
  for up to 300 s (`activeDeadlineSeconds`).
- **A failed sync is not retried**, by design (`retry.limit: 0`): fix the
  commit, or sync by hand. The API server stores the zero limit as
  `retry: {}`, so `kubectl diff -f k8s/argocd/haki-staging.yaml` always shows
  that line; ArgoCD still treats it as no retries (tested).
- **Up to about 3 min 20 s from merge to staging:** ArgoCD polls Git about
  every 3 minutes, there is no webhook; the sync itself took 15-19 s (see
  Roll back staging). Refresh in the UI to look sooner.
- **ConfigMaps left from before the takeover** (applied by kubectl) are not
  tracked by ArgoCD, so never pruned: remove them by hand as on prod.
- **A revert in Git does not revert the database:** a rollback to an older
  image leaves the schema its migration created, and that image's migration
  hook stops with an error (see Roll back staging).
- **`hookPhase: Running` after a successful sync:** in the S8 tag change, the
  four wave-3 resources (Gateway, HTTPRoute, EnvoyProxy,
  ClientTrafficPolicy) kept `hookPhase: Running` in `syncResult` while the
  sync was `Succeeded` and the app `Healthy`. Not explained yet.
- **Client IP behind a load balancer (AWS):** the ClientTrafficPolicy drops
  every incoming X-Forwarded-For because nothing stands in front of Envoy
  here. Behind a load balancer that sets the header, keep its entry instead
  (`clientIPDetection` with `numTrustedHops` or `trustedCIDRs`), and set
  `REAL_IP_FROM` to the cluster's pod CIDR there.
- **Volume size:** kind's local-path storage does not enforce the 1 GiB.
- See also the Kubernetes / AWS notes in `docs/review-2026-11.md`.
