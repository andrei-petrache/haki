# Glossary

Every term that was new to me, in one line, grouped by area. A term joins
the list when it first shows up in the code or in a review.

## Backend

| Term | Meaning |
| --- | --- |
| IDOR | Reaching another user's data by guessing an id. Defence: one helper per resource (e.g. `get_own_food`) that answers 404, not 403 |
| Alembic migration | A versioned script that changes the database schema; `alembic upgrade head` applies whatever is missing |
| `ON DELETE CASCADE` | Deleting the parent row (a user) also deletes the rows that depend on it |
| `DEFERRABLE INITIALLY DEFERRED` | A foreign key checked at COMMIT instead of after each statement |
| Argon2 | A deliberately slow, memory-hard password hash |
| JWT | The signed token the API hands out after login; the backend checks the signature on every request |
| Rate limiting | A cap on requests per client; here Nginx answers 429 for too many logins or signups |
| 503 + `Retry-After` | "Temporarily unavailable, try again later": what the backend answers while the database is down |
| `alembic_version` | The table where Alembic keeps the database's current revision; an image that does not know it stops with an error |
| Expand / contract | A schema change in two releases: first only add (the old code still works), remove later |
| `pg_dump` / `pg_restore` | PostgreSQL's backup to a file, and the tool that reads it back |

## Frontend

| Term | Meaning |
| --- | --- |
| Pure function | No React, no fetch: the same input always gives the same output, so it is easy to test |
| Discriminated union | A TypeScript type whose `kind` field says which variant it is (`list`, `detail`) |
| `cancelled` flag | Ignore a request's answer if the user left the page in the meantime |
| limit / offset | Pagination: `limit` = how many rows to take, `offset` = how many to skip; behind "Load more" |
| Generic function | `request<T>`: `T` is the response type we promise; TypeScript checks it only at compile time |

## Testing

| Term | Meaning |
| --- | --- |
| Arrange / act / assert | The three blocks of every test, separated by blank lines |
| Integration test | Runs against a real, migrated PostgreSQL instead of in-memory SQLite |
| Mutation testing | Break the code on purpose to prove the test fails |
| Playwright | Drives a real browser from code; here it runs in a Docker container |
| Smoke test | A short check that the running stack answers at all |

## Containers and CI

| Term | Meaning |
| --- | --- |
| Multi-stage build | One stage builds, another only runs; the final image is smaller |
| Build once, deploy many | CI builds each image once and every later step reuses it |
| Hash-locked dependencies | Every Python package pinned to a version and a checksum |
| Trivy | Image vulnerability scanner; CI fails on fixable CRITICAL or HIGH findings |
| Healthcheck | The command Docker runs to decide whether a container is healthy; `depends_on: service_healthy` waits for it |
| `error_page` / named location | Nginx's way to replace an error response; `@name` is an internal location no URL can reach |
| Dependabot | Opens pull requests that bump dependencies, after a 7-day cooldown |
| Ruleset | GitHub rules on `main`: pull requests only, with all 8 required checks green |
| GHCR | GitHub Container Registry, where the images are published by commit SHA |

## Kubernetes

| Term | Meaning |
| --- | --- |
| kind | Kubernetes in Docker: a whole cluster on my machine |
| StatefulSet + PVC | A pod with a stable identity and its own disk, for the database |
| Job | A pod that runs once to completion; here, the migrations |
| Probes | startup, liveness and readiness: whether a pod has started, is alive and can take traffic |
| Kustomize | A shared `base` plus overlays (staging, prod) that change only what differs |
| ConfigMap hash suffix | Kustomize names a ConfigMap after its content, so a change creates a new one and restarts the pods that use it |
| Gateway API | The successor of Ingress: GatewayClass, Gateway, HTTPRoute |
| Envoy Gateway | The Gateway API implementation used here |
| kubeconform | Validates manifests against the Kubernetes schemas, in CI |
| `reclaimPolicy: Delete` | Deleting the PVC also deletes the volume, and so the data |
| Grace period / `deletionTimestamp` | A pod being stopped gets up to 30 s to exit; `deletionTimestamp` marks the end of that window, not the moment the pod is gone |

## GitOps

| Term | Meaning |
| --- | --- |
| GitOps | Git is the source of truth; a controller in the cluster makes the cluster match it |
| ArgoCD | That controller; it detects drift and can repair it |
| Sync / drift / self-heal / prune | Apply Git to the cluster / the cluster differs from Git / ArgoCD repairs it alone / ArgoCD deletes what left Git |
| Sync wave | A number on a resource that orders it within a sync |
| Hook (Sync, PreSync) | A resource that runs at a moment of the sync; the migration is a Sync hook, not PreSync |
| Server-side apply | The API server merges the fields instead of kubectl; ArgoCD's large CRDs need it |
| Release candidate | A trial version before the final one; never used in the cluster |
| Compatibility matrix | The official list of Kubernetes versions a release is tested on |
| Polling | ArgoCD checks Git about every 3 minutes; without a webhook, a merge waits up to that long |
| Rollback by `git revert` | A new commit that undoes an earlier one; ArgoCD applies it like any other change |
