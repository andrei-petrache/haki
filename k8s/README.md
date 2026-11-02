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
| `overlays/prod/` | namespace `haki`; the app image tags |
| `overlays/staging/` | namespace `haki-staging`, its own database, 1 backend replica; its own image tags |

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
it) and kubectl within one minor version of Kubernetes 1.37.

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
```

Applying everything at once (`kubectl apply -k $O` alone) would start the
backend before its tables exist. In the last step the StatefulSet may show as
`configured`: kubectl only updates its bookkeeping annotation, the pod is not
restarted (`kubectl diff -k $O` shows no change).

Open the app through a tunnel to the frontend Service (8081, so the Compose
stack can keep 8080):

```bash
kubectl -n haki port-forward svc/haki-frontend 8081:8080   # http://127.0.0.1:8081
scripts/smoke-test.sh http://127.0.0.1:8081                # in another terminal
```

The smoke test creates a throwaway user and food in the cluster's database.

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
Job too). After changing it, or anything in `haki-backend-config`, migrate
before the backend: phases 4 and 5 above. A Job cannot be changed once
created, so it is deleted first. Other changes need only phase 5.

The ConfigMaps a change replaces are not deleted: `kubectl apply` leaves alone
what is no longer in the manifests. They are harmless; to remove the unused
ones, list them with `kubectl -n $NS get configmap -l haki/phase=config` and
delete those that no pod refers to.

### Moving a cluster from before Kustomize

A cluster set up with the old per-file manifests keeps its data: prod uses
the same namespace, names and volume. Run phases 1, 3, 4 and 5 (the Secret
stays). PostgreSQL restarts once, because it now reads `haki-db-config`.
Then delete the old ConfigMap: `kubectl -n haki delete configmap haki-config`.

A finished migration Job deletes itself after an hour, with its logs. While
it is there, `kubectl logs job/haki-migrate` shows one of its pods, not
necessarily the last: after retries, pick the pod by name from
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

- **No probes yet:** Kubernetes treats a pod as ready as soon as its container
  starts, so `rollout status` can finish before the app answers, and a
  rolling update can send traffic to a pod that is still starting.
- **Frontend restarts after a cluster start:** after `docker start`, Nginx
  can start before the cluster's DNS and exit with `host not found in
  upstream "haki-backend"`. Kubernetes restarts it until DNS answers (three
  restarts, under a minute, when tested); nothing to do.
- **The PostgreSQL pin is in two places:** `images:` in
  `base/kustomization.yaml` and `services.db.image` in `compose.yaml`.
- **Phases by hand:** kubectl does not know the order above. ArgoCD (S8)
  takes it over, and also deletes the ConfigMaps a change replaced.
- **Rate limit through port-forward:** every request reaches Nginx from
  `127.0.0.1`, so all clients share one login/signup budget (6 requests, then
  429). The limit is per Nginx replica, hence one frontend replica.
- **Volume size:** kind's local-path storage does not enforce the 1 GiB.
- See also the Kubernetes / AWS notes and L16 in `docs/review-2026-11.md`.
