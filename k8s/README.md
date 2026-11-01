# Haki on a local Kubernetes cluster (kind)

The whole app in a [kind](https://kind.sigs.k8s.io) cluster (Kubernetes in
Docker): the same images CI built and published, no local build.

| File | What it creates (namespace `haki`) |
|---|---|
| `kind-config.yaml` | the cluster `haki`: one node, image pinned by digest |
| `namespace.yaml` | the namespace `haki` |
| `configmap.yaml` | `haki-config`: database host, port and name, backend URL |
| `postgres.yaml` | PostgreSQL: StatefulSet `haki-db` with a 1 GiB volume, headless Service |
| `migrate-job.yaml` | Job `haki-migrate`: `alembic upgrade head`, once |
| `backend.yaml` | Deployment `haki-backend` (2 replicas), Service on port 8000 |
| `frontend.yaml` | Deployment `haki-frontend` (1 replica), Service on port 8080 |

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

Run from the repository root. Each step waits for the previous one: the
migrations need the database, the backend needs the migrations, and Nginx
refuses to start until the backend's name resolves.

```bash
kind create cluster --config k8s/kind-config.yaml    # kubectl context: kind-haki
kubectl apply -f k8s/namespace.yaml -f k8s/configmap.yaml

# Secrets, generated on the spot: never shown, never stored in a file
kubectl -n haki create secret generic haki-secrets \
  --from-literal=DB_USER=haki \
  --from-literal=DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')" \
  --from-literal=JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
kubectl -n haki describe secret haki-secrets         # key names and sizes only

kubectl apply -f k8s/postgres.yaml
kubectl -n haki rollout status statefulset/haki-db

kubectl apply -f k8s/migrate-job.yaml
kubectl -n haki wait --for=condition=complete job/haki-migrate --timeout=5m

kubectl apply -f k8s/backend.yaml
kubectl -n haki rollout status deployment/haki-backend

kubectl apply -f k8s/frontend.yaml
kubectl -n haki rollout status deployment/haki-frontend
```

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

## Deploy new images

The image tag is the full commit SHA of `main`, in `migrate-job.yaml`,
`backend.yaml` and `frontend.yaml`. Change all three, then migrate before the
backend. A Job cannot be changed once created, so it is deleted first:

```bash
kubectl -n haki delete job haki-migrate --ignore-not-found
kubectl apply -f k8s/migrate-job.yaml
kubectl -n haki wait --for=condition=complete job/haki-migrate --timeout=5m
kubectl apply -f k8s/backend.yaml -f k8s/frontend.yaml
```

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

## Known limits (until S7)

- **No probes yet:** Kubernetes treats a pod as ready as soon as its container
  starts, so `rollout status` can finish before the app answers, and a
  rolling update can send traffic to a pod that is still starting.
- **Frontend restarts after a cluster start:** after `docker start`, Nginx
  can start before the cluster's DNS and exit with `host not found in
  upstream "haki-backend"`. Kubernetes restarts it until DNS answers (three
  restarts, under a minute, when tested); nothing to do.
- **The image tag is in three files,** and the PostgreSQL image duplicates
  `services.db.image` in `compose.yaml`. Kustomize takes both over in S7.
- **Rate limit through port-forward:** every request reaches Nginx from
  `127.0.0.1`, so all clients share one login/signup budget (6 requests, then
  429). The limit is per Nginx replica, hence one frontend replica.
- **Volume size:** kind's local-path storage does not enforce the 1 GiB.
- See also the Kubernetes / AWS notes and L16 in `docs/review-2026-11.md`.
