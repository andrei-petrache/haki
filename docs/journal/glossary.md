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
| N+1 queries | One query for a list plus one more per row; the program list counts days in a subquery instead, and a test checks the query count stays the same for 1 or 5 programs |
| `SET CONSTRAINTS ALL IMMEDIATE` | Runs the checks of deferred constraints now instead of at COMMIT; the integration tests use it, since their transactions never commit |

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
| Ruleset | GitHub rules on `main`: pull requests only, with all 9 required checks green and the branch up to date |
| Auto-merge | GitHub merges a pull request by itself once every required check passes; here only the tag bot's, behind a switch |
| GHCR | GitHub Container Registry, where the images are published by commit SHA |
| GitHub App | An identity of its own on GitHub, with only the permissions it was given; `haki-tag-bot` pushes the tag branch and opens its pull request, and unlike `GITHUB_TOKEN` its pull requests start CI |
| Environment (GitHub) | A named set of secrets with its own rules; `tag-bot` holds the App's key and accepts jobs from `main` only |
| Required reviewer | An environment rule: a job in `prod` waits until the named person approves it on GitHub |
| `workflow_dispatch` | A workflow started by hand, with inputs; `promote-prod` takes the SHA to promote |
| `pull_request_target` | A workflow event that runs the base branch's copy of the workflow, with the pull request only as data; `prod-guard` uses it so a pull request cannot weaken the rule it is checked by |
| `base.sha` (event) | The base branch's commit as the pull request event recorded it; it can lag behind `main` (seen on #82) |
| `web-flow` | GitHub's own identity as the committer of commits made through the API or the web editor; GitHub signs them, so they are "verified" |
| Bypass list | Who may do what a ruleset forbids; `protect-bot-branches` lets only the App `haki-tag-bot` write `bot/**` |
| `GH013` | Git's refusal from GitHub when a push breaks a repository rule ("Cannot update this protected ref") |

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
| `kubectl port-forward` | Opens a local port (here 127.0.0.1) that leads to a Service in the cluster, used to call the staging API directly in the revert drill |
| Kustomize component | A reusable piece that overlays include; staging and prod share the image tags in `k8s/components/images` |
| ValidatingAdmissionPolicy | A rule in the API server that refuses objects by an expression; tried for ArgoCD Applications on a throwaway cluster, not added |
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
| Rollback pin | Backend and frontend go back to an older tag while the migration stays on the newer one, recorded in `rollback-pin.yaml`; while it exists, no other tag reaches staging |
| `targetRevision` | The commit, branch or tag an Application follows; staging's is `main`, prod's a full commit SHA |
| App of apps | An Application whose resources are other Applications; `haki-apps` applies `haki-prod.yaml` from `main` |
| Promotion | Moving prod to a commit of `main` by changing `haki-prod`'s `targetRevision`, through `promote-prod`: a check, an approval, the bot's pull request; a rollback is a promotion of an older SHA |
| `hook-delete-policy: BeforeHookCreation` | The previous hook (the old migration Job) is deleted when the new one is created; the only deletion in a prod sync |
