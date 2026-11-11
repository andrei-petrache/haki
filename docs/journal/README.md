# Learning journal

Haki is a fitness and nutrition tracker that I take from local code to
Docker, CI, Kubernetes, GitOps and, at the end, AWS. It started as my
end-to-end DevOps learning project; since 11 November 2026 it is meant to
become a live app that can compete on the market, and each new feature
carries the next DevOps topic. This journal records what I built, what I
learned and why I chose what I chose.

- [Plan](plan.md): the sprints done (S0 to S9), the seven product phases
  that follow, and where each one stands.
- [Glossary](glossary.md): every new term, explained in one line.
- [Decisions and lessons](decisions.md): the choices that shaped the project
  and the bugs that review and tests caught before they shipped.

## Timeline

Newest first. Sprints follow the project plan; the review is
[`docs/review-2026-11.md`](../review-2026-11.md).

| Date | Sprint | What shipped | Key commits |
| --- | --- | --- | --- |
| 11 Nov | S9 (done) | The first promotion to prod: Programs on prod through the approved workflow (#82), with a dump right before the merge and a manual sync of 18 s, migration included; the ruleset on `bot/**` (only the tag bot writes those branches); `prod-guard` accepts the bot's commit as GitHub signs it (#85) and automated sync in one shape (#83); automated sync for prod, without prune (#84) | `fdc9943`, `df47b3c`, `a572e97`, `dfe3829` |
| 9-10 Nov | S9 (days 3-4) | Prod under ArgoCD: the staging tags in a shared component (#68); the Application `haki-prod` pinned to one commit SHA and taken over by hand with every pod and volume kept (#69); `prod-guard` on `pull_request_target` and `haki-apps` applying `haki-prod.yaml` from `main` (#70); the `promote-prod` workflow with approval in the environment `prod` (#75), judged by the images prod runs (#77); the publish log names each push (#74) | `00e3da8`, `0669212`, `f784f43`, `c339f35`, `c0d2f07` |
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

Prod runs `c0d2f07`, images `4b65cc6`: Programs, since 11 November 2026, under
ArgoCD with automated sync (no prune, self-heal). Staging follows `main`.
S9 is done (3-11 November 2026): a code change merged to `main` reaches
staging through the tag pull request that CI opens and merges itself; prod
moves only when a promotion, approved in the environment `prod`, lands on
`main`, and merging it is the deploy.

S9, days 3-5 (9-11 November 2026), from the pull requests, their CI runs and
`kubectl` (times UTC):

| Step | Result |
| --- | --- |
| Shared image component (#68) | The three staging tags moved into `k8s/components/images`; the rendered manifests did not change |
| Prod's Application (#69) | `haki-prod` in its own project (the `haki` namespace only, no Secrets or volumes), `targetRevision` a full SHA (`00e3da8`), no automated sync, `retry.limit: 0`, `PruneLast` |
| Takeover of prod (9 November, 18:32) | Dump first; manual sync without prune in 14 s; the migration hook ran as a no-op (`b4a97ba12fd6`); same pods, volume and rows. The Deployments' generation went up by one from ArgoCD's annotation alone |
| Throwaway cluster (`haki-test`) | An AppProject cannot limit an Application's name, so a second document in `haki-prod.yaml` would be created; a deleted file or a prune sync keeps `haki-prod`; self-heal undid a `kubectl patch` in 4 s |
| `prod-guard` (#70) | Runs on `pull_request_target`, from `main`'s copy of the workflow and `scripts/check-prod-app.sh`, with the pull request's commits read as data; the proof #71 was refused ("no pull request may change targetRevision"). `haki-apps` applies `haki-prod.yaml` from `main`; it added two annotations to `haki-prod` and started no sync |
| Environment `prod` (9 November) | Required reviewer: me; jobs from `main` only; no secrets |
| `promote-prod` (#75, #77) | `workflow_dispatch` with the SHA: `check`, `approve` (waits in the environment), `open-pr` (the bot's one commit through the API on `bot/promote-prod`). The proof #76, a person's commit on that branch, was refused. The mentor's catch: #75 judged the revision, but prod runs the images written at it; #77 renders `k8s/overlays/prod` at the revision and counts migrations between the `haki-migrate` images |
| First run (10 November) | `check` listed the Programs migration (images `081c5f2` -> `4b65cc6`); approved; the bot opened #82 with one verified commit. `prod-guard` refused it: the commit's committer is `web-flow`, not the bot, because GitHub makes and signs API commits itself. An extra commit of mine on the branch was refused too ("exactly one commit") and the branch reset |
| 11 November | #85 accepts author bot + committer `web-flow` + verified; the ruleset `protect-bot-branches` (`bot/**`: no creation, update, deletion or force push; bypass only the App) closes the gap: my push was refused, `GH013 Cannot update this protected ref`. #82 reopened: `prod-guard` green |
| #83, then #82 regenerated | `prod-guard` accepts `automated` only as `enabled: true, prune: false, selfHeal: true`. #82 was behind `main` and a person cannot update `bot/**`, so the workflow ran again (run #2) and rewrote #82 in place: one commit on `main`. `prod-guard` failed once on a stale `base.sha` (`fdc9943`) in the event, then passed after a close and reopen (base `df47b3c`) |
| Dump before the merge (13:23) | `pg_dump -Fc` from the pod: 24669 bytes, CUSTOM, 74 entries, 8 tables, `pg_restore --list` clean; row counts saved and identical to the day before |
| Merge of #82 (13:20) and the diff | `haki-apps` moved `haki-prod` to `c0d2f07` in about 2 min: OutOfSync, with only the two Deployments differing. Rendered diff `00e3da8` -> `c0d2f07`: three image lines, the same 15 resources on both sides |
| Manual sync (13:27:47 -> 13:28:05) | 18 s, no prune. The hook `haki-migrate` ran `b4a97ba12fd6 -> 3bf97e2ee106` in 5 s; backend (2) and frontend on `4b65cc6`; the database pod and its volume untouched; 11 tables, the three new ones empty, the old counts identical; `/ready` with `database: ok`, `/programs` 401 without a token, the frontend 200 |
| Automated sync (#84, merged 13:36) | `haki-apps` applied it at 13:39: `automated {enabled, prune: false, selfHeal: true}`; `haki-prod` stayed Synced on `c0d2f07` with no new operation. `k8s/README.md`: dump right before the merge of a promotion with a migration, because the merge is the deploy |

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

Next: S9-S10 hardening (Prometheus and Grafana, Argo Rollouts, scheduled
backups), after the open items below (see the [plan](plan.md)).

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
- [x] A ruleset on `bot/**`: `protect-bot-branches` (11 November 2026). A
  personal repository's ruleset does list a GitHub App in its bypass list;
  with it, only `haki-tag-bot` creates, updates, deletes or force-pushes
  `bot/bump-staging` and `bot/promote-prod` (my push: `GH013`)
- [ ] `guard.yml` takes `BASE` from the `pull_request_target` event, and that
  `base.sha` can lag behind `main`: when #82 was rewritten in place after
  #83 merged, the event still said `fdc9943`, so `prod-guard` counted #83's
  commit as the promotion's second one. Read the base at run time (`main` as
  checked out, or the pull request's `base.sha` from the API) instead. Until
  then: close and reopen the promotion's pull request; "Re-run jobs" reuses
  the stale event. After S9
- [ ] #81: the `pull_request_target` policy `prod-guard` needs from 2 December
  2026, when GitHub restricts that event on public repositories by default;
  an Actions setting of the repository, mine to change
- [ ] Dependabot #79 (frontend, minor and patch) and #80 (backend, minor and
  patch)
- [ ] GHCR refused `haki-frontend:3666079` twice with `write_package` while
  the backend of the same run was pushed; the next publish worked. Cause
  unknown; the publish log now names each push (#74)
- [ ] TypeScript 7, held back in `.github/dependabot.yml`: `typescript-eslint`
  accepts only `typescript <6.1.0` (8.72.2, 9 November 2026), so `npm ci`
  fails with ERESOLVE (#65). Lift the hold once a release accepts 7
