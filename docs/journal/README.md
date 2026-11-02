# Learning journal

Haki is my end-to-end DevOps learning project: a fitness and nutrition tracker
that I take from local code to Docker, CI, Kubernetes, GitOps and, at the end,
AWS. The app is the pretext; the point is the road to production. This journal
records what I built, what I learned and why I chose what I chose.

- [Plan](plan.md): the sprints from S0 to S14 and where each one stands.
- [Glossary](glossary.md): every new term, explained in one line.
- [Decisions and lessons](decisions.md): the choices that shaped the project
  and the bugs that review and tests caught before they shipped.

## Timeline

Newest first. Sprints follow the project plan; the review is
[`docs/review-2026-11.md`](../review-2026-11.md).

| Date | Sprint | What shipped | Key commits |
| --- | --- | --- | --- |
| 2 Nov | Review fixes | L16: the migrations no longer get the JWT secret (Compose and Kubernetes), on staging and prod | `69ce02a`, `081c5f2` |
| 2 Nov | Review fixes | L18: PostgreSQL healthcheck over TCP in Compose; L19: 503 instead of 502 when the backend is unreachable, on staging and prod | `55c15c1`, `75ddf7c`, `239baf2` |
| 2 Nov | S8 (day 1) | ArgoCD v3.5.7 installed; projects locked to staging; sync waves; staging taken over with every pod and volume kept; automated sync; drift, self-heal and failed-migration tests passed | `4aa0aa3`, `6d7fe48`, `7ece061` |
| 2 Nov | Workouts | Workouts, exercises and sets: tables, API, UI; staging, then prod | `ce9b0d9`..`4ad4f92` |
| 2 Nov | S7 | Kustomize (base + staging/prod), kubeconform in CI, probes, Envoy Gateway, real client IP in Nginx | `3690a2b`..`9ae95d2` |
| 1-2 Nov | S6 | Local kind cluster: PostgreSQL StatefulSet, migrations as a Job, backend and frontend behind Services | `35c931d`..`c7da6dd` |
| 1 Nov | S5 | Hash-locked dependencies, smoke test, Trivy scan, images on GHCR, releases from tags | `5fce428`..`79ced69` |
| 1 Nov | Review | Repository review; fixed H1, H2, M1, M2, M4, M5, M7, L2 | `7f04f4a`..`3feeb2d` |
| 31 Oct | S4 | GitHub Actions CI, Dependabot, integration tests on real PostgreSQL, protected `main` | `091fe48`..`7af991e` |
| 31 Oct | S3 | Docker images for backend and frontend (Nginx), full stack in Compose | `b3b140c`..`3401dd5` |
| 31 Oct | S2 | Foods, meal entries, daily calorie target, the daily screen | `401fc6d`..`c88036d` |
| 21-31 Oct | S1 | FastAPI skeleton, PostgreSQL in Compose, Alembic, accounts with Argon2 + JWT, first React frontend | `1171be4`..`17221cb` |

## How I work

Two Claude sessions and me in the middle:

- **Mentor** (claude.ai): plans each sprint, writes the prompts and reviews
  the reports and diffs.
- **Claude Code** (VS Code): writes the code, runs the tests, shows me the
  diff and waits for my OK before every commit.
- **Me**: carry the messages, give the OKs, push, open the pull requests and
  merge them once all 8 CI checks are green.

The rules live in [`CLAUDE.md`](../../CLAUDE.md): small steps with tests after
each, explanations in Romanian, never read `.env`, never commit on `main`, one
branch per change, I am the only one who pushes, and nothing touches prod
without my OK.

## Where I am

Staging and prod run `081c5f2`: Workouts and the L16, L18 and L19 fixes.
S8 is half done: since 2 November 2026 ArgoCD v3.5.7 manages staging, with
automated sync, prune and self-heal; prod stays manual until S9.

S8 results so far, all on staging:

| Test | Result |
| --- | --- |
| Takeover | Manual first sync in 16 s; same pods, ReplicaSets, volume and rows; the migration hook ran as a no-op |
| Drift, self-heal off | Detected as OutOfSync in about 1 s; left alone for 30 s |
| Self-heal back on | Back to Git in 13 s, through a full sync (the migration ran, as a no-op) |
| A Deployment deleted by hand | Recreated in about 1 s by a selective sync; the migration did not run |
| A failing migration | The sync stopped at the hook: backend and frontend kept their images and pods, the old ConfigMap stayed (PruneLast), no retry, the app kept working |
| Back to `main` | Synced and Healthy; the test ConfigMap was pruned |

Next in S8: a change through a pull request, timed from merge to cluster,
and a rollback with `git revert`. Then S9 (see the [plan](plan.md)).

Open items, outside the sprints:

- [x] L16, L18 and L19 from the review
- [ ] L17: our copy of `nginx.conf` can fall behind the image's
- [ ] Envoy Gateway v1.10, tested on Kubernetes 1.37
- [ ] Group the Trivy findings in the backend image and pick a slimmer base
- [ ] L21: an unsaved workout is lost when the tab changes
- [ ] Move the Playwright browser checks into the repository, as a CI job
