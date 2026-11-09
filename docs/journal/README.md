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
| 4 Nov | S9 (day 2) | Programs API: weekly plans, their days and planned exercises, and a workout started from a day; on staging through the first real auto-merge (#60), 8 min 5 s from the merge to the last new pod Ready; the revert drill with the rollback pin (#61) and its lift (#62) | `0ab4935`, `f0d9605`, `387843a`, `3ecb61d` |
| 3 Nov | S9 (day 1) | CI opens the staging tag pull request itself, as the GitHub App `haki-tag-bot` (first real bump: `f5d2daa`, through #55); a rollback pin that keeps the migration on the newer image; the `tag-pr-scope` check and a switch for the bot's auto-merge | `155609e`, `3aba5ca`, `9ebcabf`, `024f6de` |
| 3 Nov | S8 (done) | A tag change and its `git revert` reached staging through pull requests and ArgoCD alone (21 s and 94-95 s from merge to the first new pod Ready); the rollback limit after a migration checked on a throwaway database | `62841b0`, `384f067` |
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
- **Claude Code** (on Windows, in Git Bash; the repository's commands run in
  WSL Ubuntu): writes the code, runs the tests, shows me the diff and waits
  for my OK before every commit.
- **Me**: carry the messages, give the OKs, push, open the pull requests and
  merge them once all 9 required CI checks are green.

The rules live in [`CLAUDE.md`](../../CLAUDE.md): small steps with tests after
each, explanations in Romanian, never read `.env`, never commit on `main`, one
branch per change, I am the only one who pushes, and nothing touches prod
without my OK.

## Where I am

Staging runs `387843a`: Programs (the API reports version `0.2.0.dev0`).
Prod runs `081c5f2`: Workouts and the L16, L18 and L19 fixes. S9 started on
3 November 2026: a code change merged to `main` reaches staging through a tag
pull request that CI opens and merges itself; prod stays manual.

S9, day 2 (4 November 2026), from the pull requests, their CI runs and two
live observers (times UTC):

| Step | Result |
| --- | --- |
| Programs API (#59) | Six commits; migration `3bf97e2ee106` adds three tables and changes none; CI green; merged at 19:45:43 |
| Images published | `publish` finished at 19:48:23, 2 min 40 s after the merge |
| The bot's pull request (#60) | Opened at 19:48:36; the bot armed auto-merge at 19:48:39; its checks passed at 19:50:36 |
| The first real auto-merge | `haki-tag-bot` merged #60 at 19:51:27, 51 s after its checks passed |
| Sync and migration | ArgoCD started at 19:53:28, 2 min 1 s after #60 (its poll); the migration Job ran `b4a97ba12fd6 -> 3bf97e2ee106` in 6 s |
| New pods | The first new pod Ready at 19:53:43, 8 min after the merge of #59; the sync finished at 19:53:48 |
| Programs on staging | `/openapi.json` lists the three `/programs` paths; a test account created a plan and started a workout from a day, with every set copied in order; deleting an exercise of the plan gave 409 |
| Rollback pin (#61) | Merged at 20:10:04; backend and frontend back on `f5d2daa`, the migration Job on `0ab4935`, where it changed nothing (`alembic_version` still `3bf97e2ee106`); the first old pod Ready 3 min 25 s after the merge |
| The old version on the new schema | No `/programs` paths; it read the workout started from the plan; deleting an exercise used only by the plan (its plan row added with SQL) gave 409 "Exercise is used by workouts", and nothing was deleted |
| Lifting the pin (#62) | Merged at 20:23:58; all three tags on `387843a`; the migration changed nothing; the first new pod Ready 3 min 10 s after the merge; the plan, its rows and the started workout intact; the same delete gave 409 with the new message |
| Clean-up | The test account deleted with SQL in one checked transaction: nothing of it left in `programs`, `workouts` or `exercises` |

S9, day 1 (3 November 2026), from the pull requests and their CI runs:

| Step | Result |
| --- | --- |
| The `bump-staging` job (#52) | After a push to `main` that changes `backend/` or `frontend/`, CI sets the staging tags to that commit on `bot/bump-staging` and opens or updates one pull request, as the GitHub App `haki-tag-bot`, so the CI checks run on it |
| The App's key, from `main` only (#53, never merged) | A pull request job that asked for the `tag-bot` environment was refused in 2 s: "Branch `refs/pull/53/merge` is not allowed to deploy to tag-bot" |
| The first real bump (#54, then #55) | `f5d2daa` merged at 21:16:44 UTC; its images were published at 21:19:32; the bot's pull request opened at 21:20:17 and its checks passed at 21:22:18; I merged it at 21:23:50. ArgoCD shows staging Synced and Healthy on `f5d2daa` |
| No loop | The pushes of #55, #56 and #57 each ran `bump-staging` (7-15 s, green) and none opened a new pull request |
| Rollback pin (#56) | The migration Job runs the backend image under its own name, `haki-migrate`; `scripts/staging-rollback-pin.sh` moves backend and frontend back while the migration stays on the newer tag, recorded in `rollback-pin.yaml`. CI green; tried on staging on day 2 (#61, #62) |
| Auto-merge of the tag pull request (#57) | `tag-pr-scope` passes the bot's pull request only if it changes the three staging tags, to one SHA, with no pin; it is the 9th required check. The job arms auto-merge only while `TAG_BOT_AUTO_MERGE` is `true`. First real run on day 2 (#60) |

Next in S9: prod updated only with approval, then Programs on prod (see the
[plan](plan.md)).

S8 is done (3 November 2026): ArgoCD v3.5.7 manages staging, with automated
sync, prune and self-heal, and a merged pull request is the only way a
change reaches it.

S8 results, all on staging unless noted:

| Test | Result |
| --- | --- |
| Takeover | Manual first sync in 16 s; same pods, ReplicaSets, volume and rows; the migration hook ran as a no-op |
| Drift, self-heal off | Detected as OutOfSync in about 1 s; left alone for 30 s |
| Self-heal back on | Back to Git in 13 s, through a full sync (the migration ran, as a no-op) |
| A Deployment deleted by hand | Recreated in about 1 s by a selective sync; the migration did not run |
| A failing migration | The sync stopped at the hook: backend and frontend kept their images and pods, the old ConfigMap stayed (PruneLast), no retry, the app kept working |
| Back to `main` | Synced and Healthy; the test ConfigMap was pruned |
| A tag change through a pull request | First new pod Ready 21 s after the merge, sync finished at 26 s: 7 s waiting for ArgoCD, 19 s sync (one run, reconstructed from timestamps) |
| Its `git revert` through a pull request | First new pod Ready 94-95 s after the merge, sync finished at 97 s: 82 s waiting for ArgoCD, 15 s sync (observed live); rows, the database pod and prod's pods unchanged; smoke test passed |
| A revert after a migration (throwaway database, not staging) | An image older than the database stops at `alembic upgrade head` with exit 255 and changes nothing, so the revert would stop at the hook and leave the new version active |

The deploy itself takes 15-19 s; ArgoCD's poll can take the total to about
3 min 20 s.

Open items, outside the sprints:

- [x] L16, L18 and L19 from the review
- [ ] L17: our copy of `nginx.conf` can fall behind the image's
- [ ] Envoy Gateway v1.10, tested on Kubernetes 1.37
- [ ] Group the Trivy findings in the backend image and pick a slimmer base
- [ ] L21: an unsaved workout is lost when the tab changes
- [ ] Move the Playwright browser checks into the repository, as a CI job
- [x] `scripts/smoke-test.sh` does not cover `/programs` yet (#67)
- [ ] A ValidatingAdmissionPolicy on ArgoCD Applications, not added for now.
  Tried on a throwaway cluster (9 November 2026, ArgoCD v3.5.7): an AppProject
  cannot limit an Application's name (`namespaceResourceWhitelist` has no
  `name`), so a second document in `haki-prod.yaml` (`haki-prod-x`, project
  `haki-prod`, `targetRevision: main`) was created by `haki-apps`, and so was
  a rename. `directory.include` does not stop it (the document is inside the
  included file); only `prod-guard` does, in Git. The policy that refused
  both in the API server, and a `kubectl patch` of `haki-prod` onto `main`:
  Applications named only `haki-staging`, `haki-prod` or `haki-apps`, in
  `argocd` only; the project `haki-prod` used by `haki-prod` alone; and
  `haki-prod`'s `targetRevision` a full commit SHA
- [ ] A ruleset on `bot/**`: only the tag bot (GitHub App) may create or
  update those branches. Not added for now; `prod-guard` already refuses a
  promotion with a commit that is not the bot's. Check first that a
  personal repository's ruleset can list a GitHub App in its bypass list
