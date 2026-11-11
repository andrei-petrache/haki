# Decisions and lessons

The rule that keeps coming back: pick the option that protects the data and
can be verified, even when it is slower.

## Decisions

| Decision | Why |
| --- | --- |
| Start S8 with ArgoCD v3.5.7 now, not v3.6.0 in a week | The cluster is local and rebuildable; a known, documented gap (not tested on 1.37) beats a week of waiting. First planned the other way, then changed |
| Never move the cluster to Kubernetes 1.36 for ArgoCD | `kind delete cluster` would delete the data |
| The migrations get only the database settings (L16) | Least privilege: a pod gets only the secrets it uses |
| Migration hook in the Sync phase, not PreSync | ConfigMaps carry a hash in their name; a PreSync hook would start before the new ConfigMap exists |
| Prod stays on the manual phases during S8 | Learn ArgoCD on staging first; promotion to prod with approval comes in S9 |
| Envoy Gateway instead of ingress-nginx | ingress-nginx was retired; Gateway API is its maintained successor |
| Build each image once | What was tested is exactly what ships; no rebuild in later jobs |
| Tags are commit SHAs, never `latest` | Always know which version runs in each environment |
| Staging first, then prod | A new tag is tried on staging before it reaches the real data |
| "Load more" pagination in the first Workouts UI | Without it, workout 21 would silently hide the oldest one |
| Browser checks with Playwright, not by hand | Catches cases that are hard to reproduce by hand: double clicks, 409s, the ro-RO locale |
| A separate test account, deleted at the end with SQL | My development data stays clean |
| Leave the minimatch alert open | It is only in dev tools; `npm audit fix --force` would break ESLint |
| Never `docker compose down -v` | It deletes the `db-data` volume with my data |
| ArgoCD may not touch Secrets or volumes | The project's whitelist leaves them out: a bad commit cannot delete the data |
| Take staging over by hand first, automated sync only after | See the diff before anything changes; the takeover kept every pod and the volume |
| No automatic retry of a failed sync (`retry.limit: 0`) | The default is 5 retries, and each would run the migration again |
| Prune only at the end of a sync (`PruneLast`) | An old ConfigMap must stay while a pod may still use it; the failed-migration test showed it |
| No ArgoCD CLI; `kubectl` and the UI only | One binary less to download and pin; `kubectl patch` starts a sync |
| Migrations stay compatible with the previous version (expand/contract); deletions come in a later release | The previous image can still run on the new schema, which a rollback needs |
| A manual `pg_dump` before every migration on prod, with the steps in `k8s/README.md`, until scheduled backups exist | A new image cannot undo a migration; the dump is the way back for the data |
| An image older than the database stops with an error, by default | A safe failure (tested: exit 255, nothing changed), but it blocks a simple rollback after a migration |
| In S9, choose and test an explicit exception for a rollback only, visible in Git: a flag in the overlay or a separately pinned migration image. Chosen on 3 November: the pinned image (below) | A silent tolerance of a newer database would also hide a real mismatch |
| The first real revert after a migration is done on staging, with Programs | Until then that case was only inferred; done on 4 November with the rollback pin (#61, #62) |
| CI changes the staging tag through a pull request, never by a push to `main` | `main` stays protected: the tag change passes the same required checks, and ArgoCD only ever sees merged commits |
| The bot pushes and opens the pull request as a GitHub App (`haki-tag-bot`), not with `GITHUB_TOKEN` | A pull request opened with `GITHUB_TOKEN` starts no workflows, so its checks would never run |
| The App's key lives in the environment `tag-bot`, which accepts jobs from `main` only | A pull request cannot reach the key; tested with #53, refused in 2 s |
| The tag pull request changes only `k8s/`; a bump is opened only for changes to `backend/` or `frontend/` | Merging it never opens another bump: no loop (checked on #55, #56 and #57) |
| One branch, `bot/bump-staging`, one pull request; a newer commit updates it | No queue of stale tag pull requests |
| The rollback exception: the migration Job gets its own image name, `haki-migrate`, and stays on the newer tag while backend and frontend go back; `rollback-pin.yaml` records it (#56) | Visible in Git; `upgrade head` on the newer image has nothing to do, so the hook passes without tolerating a newer database in general |
| While a pin exists, `check-manifests.sh` refuses any other tag and `bump-staging` fails | Nothing moves staging off the pin by accident |
| The pin is lifted only to a SHA that has the pinned migration in its history, with images on GHCR | Otherwise the migrations would not know the database's revision, or the pods could not pull |
| Auto-merge only for the bot's pull request, guarded by the `tag-pr-scope` check and the `TAG_BOT_AUTO_MERGE` variable (#57) | The check limits what can merge without me to the three staging tags, one SHA, no pin; the variable turns it off at once |
| `tag-pr-scope` became a required check only after #57 was merged | Before that, every open pull request would have waited for a check that never reports |
| The API reports version `0.2.0.dev0` (#54) | FastAPI's default `0.1.0` read like the v0.1.0 release; the API is past v0.1.1 |
| The Programs migration only adds tables (#59) | The previous version runs on the new schema, which the rollback pin needs; proven in the drill (#61) |
| `program_exercises.exercise_id` is `NO ACTION`, `DEFERRABLE INITIALLY DEFERRED` | L20: deleting a user reaches these rows three levels down (programs, program days), its exercises one level down. PostgreSQL never defers `RESTRICT`; `CASCADE` or `SET NULL` would drop an exercise from plans without a word. Checked: with an immediate check, deleting a user fails (mutation test); deleting an exercise still in a plan is a 409, nothing deleted, in the new version and the old one (#61) |
| A workout started from a program day is a copy, with no link to the day (#59) | No new column in `workouts`, so the migration only adds tables; editing or deleting the program never touches a past workout. The cost: a workout does not remember its day; if that is ever needed, a new link table, not a column |
| Prod's Application follows one full commit SHA, moved only by a promotion (#69) | A merge to `main` never reaches prod by itself; the move is explicit, approved, and a rollback is a promotion of an older SHA through the same workflow |
| The promotion is the bot's pull request on `bot/promote-prod`, not a push (variant A, #75) | It passes the same required checks as any change, `prod-guard` included, and nothing but that pull request may change `targetRevision` |
| `prod-guard` runs on `pull_request_target`, from `main`'s copy, and becomes a required check only once merged (#70) | A pull request cannot weaken the rule it is checked by; open pull requests never wait for a check that does not exist yet |
| A promotion is judged by the images prod runs at the revision, not by the revision (#77) | The mentor's catch: a revision moves forward while a pin can move the images back; migrations are counted between the `haki-migrate` images |
| The promotion's commit: author the bot, committer `web-flow`, verified (#85), with the ruleset on `bot/**` | GitHub makes and signs API commits itself, so the committer is never the bot; the ruleset keeps everyone else off those branches (a commit status from the App would have needed another permission) |
| Automated sync for prod only in one shape: `enabled`, `prune: false`, `selfHeal: true` (#83, #84) | Nothing in prod is deleted without a person; a hand edit in the cluster is undone, Git wins |
| The first promotion was synced by hand; automated sync came after (#84) | See the diff before anything changes; the merge of #84 then changed nothing, Git and the cluster were already equal |
| Dump right before the merge of a promotion that lists a migration | Since #84 the merge is the deploy; the dump is the way back for the data |
| After `main` moves, a failed `prod-guard` is rerun by closing and reopening the pull request | "Re-run jobs" reuses the event's stale `base.sha` (#82) |
| Haki is meant to become a live app that can compete on the market, not only a DevOps learning project (11 November 2026) | The market is split between calorie apps and gym loggers, and Haki already has both in one app; the positioning: nutrition and training in one fast app for people who lift, no ads, with regional foods done right |
| International market, English first, with Romanian foods and values done especially well | Missing regional foods are a common complaint, and Romanian users say so explicitly |
| Features are chosen by their value to users, and each carries the next DevOps topic | People quit because logging is tedious, not for lack of features, so logging speed comes first (phase 2); the road to production goes on, led by what users need |
| Catalog data from USDA FoodData Central and free-exercise-db, both credited; Open Food Facts only for barcodes, kept separate from our own data and attributed on screen; wger not mixed in unless needed | Only USDA FDC is CC0. free-exercise-db is under the Unlicense, a public-domain dedication, and is credited anyway. Open Food Facts is ODbL: attribution, and share-alike for a database derived from it. wger is CC-BY-SA: attribution and share-alike. Each source's terms travel with its data |
| Calorie intake against a weight goal is treated as health data (GDPR Article 9): explicit consent, a privacy policy, export, account deletion and EU hosting before real users | Article 9 data needs explicit consent; there is no delete-account endpoint yet |
| A PWA first (installable, offline), a native app later only if needed | The gym is where the app is used, often without a good connection; one codebase until a native app is needed |
| Password reset (phase 4) uses an e-mail backend that only writes to the log until go-live; the real e-mail provider is chosen at launch (phase 7) | The flow is built and tested without a provider or a domain; a reset link in the backend's log is acceptable only while there are no real users, and real users come with phase 7 |
| Prod's hosting (EKS or something cheaper) is chosen at go-live (phase 7) | A live app runs 24/7, so the "destroy every evening" rule fits experiments, not prod |
| The second promotion (11 November 2026) went through the merge alone: promote-prod run #3 moved prod from `c0d2f07` to `2817619` (images `4b65cc6` -> `4957cfc`), Andrei approved it, merged #96, and automated sync deployed it (16:04:43-16:05:00); no manual sync and no dump | No migration fell between the two migration images and the prod overlay differed only in its image tags. After it: pods Ready with 0 restarts, the migration a no-op, every table's row count equal to the snapshot taken before. Rollback pin: `c0d2f07`, images `4b65cc6` |
| `github.sha` in a `pull_request_target` event is `main`'s tip when the event fired: on #96 the new guard (#95) logged `main checked out` and `event (github.sha)` both as `2817619` | The first direct proof; the fix in #95 had rested on it. The earlier failure on #82 came only from the event's `pull_request.base.sha` |
| A test account left in prod by a check is removed with SQL, in one checked transaction | There is no delete-account endpoint yet (phase 4). The transaction checks the id and the e-mail, that the account owns no rows, that exactly one row goes and that `users` returns to the snapshot; anything else rolls it back |
| `PUT /programs` left out of the first Programs pull request | It needs no migration and can come later. Replacing the days then needs `program.days.clear()` and a `session.flush()` before the new days are added: SQLAlchemy inserts before it deletes, and the insert would fail on `uq_program_days_program_id_position` |
| Weights stay stored in kilograms; kg or lb is only how the UI shows and reads them, chosen per device until accounts get a setting (#93) | One unit for the data: switching never rewrites rows, and a conversion bug can only show a wrong number. A setting on the account needs a migration, which comes with the body weight work |
| A weight not edited since it was filled sends its saved kilograms back; pounds are converted to the gram; the limit is checked before rounding (#93) | Otherwise 60 kg shown as 132.28 lb comes back as 60.001. Grams make every pound value with 2 decimals round-trip (0.01 kg would not) |
| Weight inputs keep `step="any"`, with − / + buttons of 2.5 lb or 1.25 kg (#93) | With `step="2.5"` Chromium marks 61 lb, and 132.28 lb for a saved 60 kg, as invalid |
| Translations without a library: typed dictionaries the build checks, `Intl.PluralRules` for plurals; the browser's language (Romanian or English, else English) unless one is chosen in Profile; API errors stay in English | Two languages fit in a few typed files, with no dependency to pin and update. Error codes need a backend change |
| End-to-end tests run with the browser fixed to en-US, plus one short Romanian file | The existing tests keep their English texts; Romanian is still checked in a real browser |

## Bugs caught before they shipped

| Found | What it would have done | Lesson |
| --- | --- | --- |
| Login and signup had no limit, 64 MiB per Argon2 hash (H1) | Exhaust the pod's memory | Expensive operations need a limit: rate limit in Nginx, bounded concurrent hashing |
| Any JWT secret was accepted, even the placeholder (H2) | Forgeable tokens | Refuse a bad configuration at startup |
| Ids above 2,147,483,647 returned 500 (M1) | A server error instead of 404 | Validate input against the database's limits |
| A `%` in the database password broke migrations (M2) | A failed deploy | Build the database URL from separate fields, never as text |
| `Number('')` is 0 | An empty weight became "bodyweight" | Empty is an error; 0 is written explicitly |
| `NaN` passes both `< 0` and `> 1000` | "abc" would have been valid | Check `Number.isFinite` first, then the range |
| `new Date('2026-11-02')` is read as UTC | The previous day shown west of Greenwich | Split the date into year, month and day |
| Commits landed on local `main` instead of the branch | Work on the wrong branch | Run `git branch --show-current` in the same command as the commit |
| Nginx crash-looped on a cold cluster start | Frontend down until the backend existed | Resolve the backend per request: `resolver` + a variable in `proxy_pass` |
| A forged X-Forwarded-For bypassed the rate limit | A fresh login budget per header value | Trust the header only from a known proxy (Envoy) |
| The editor did not validate the date range | A 422 from the API without saying which field | Mirror the backend's rules in the form, with the error next to the field |
| `pg_isready` on the socket passed on PostgreSQL's temporary init server (L18) | `migrate` and `backend` starting just before the database restarts | Check readiness the way clients connect: over TCP |
| A database outage gave 502 from Nginx in Kubernetes (L19) | Clients saw a broken gateway instead of "try again in 5 s" | When the proxy answers for the backend, answer what the backend would |
| My own review suggested PreSync for migrations | The migration would look for a ConfigMap that does not exist yet | Check the official documentation, even for what you wrote yourself |
| The S8 plan, read from v3.6-rc4's code, said self-heal never runs the migration | Wrong expectations about when Alembic runs | A test beats a code reading: on v3.5.7 a full sync runs it, a selective self-heal does not |
| In yq, `== "*"` matches anything, and `-N` merges files into one document | CI checks that always pass, or always fail | Test every new check against a broken copy before trusting it |
| `prod-guard` required the promotion's committer to be the bot; GitHub's API commits are committed by `web-flow` (#82) | The first real promotion would never have passed | Run the first real case before trusting synthetic tests; they only knew what I assumed |
| `check-promotion.sh` judged the revision (#75); prod runs the images written at it (#77) | A pin would have been judged on the wrong commits | Judge what runs, not what points to it |
| The `pull_request_target` event carried a stale `base.sha` when #82 was rewritten after #83 merged | `prod-guard` counted #83's commit as the promotion's second one | An event is a snapshot; read the live state when the rule depends on it |
| Romanian tab labels pushed the header past 390 px: the phone padding rule lost to a later `button.tab` rule of the same specificity | The page scrolled sideways on a phone | Measure the computed style in the browser before changing values again; an end-to-end test now checks that the tabs fit on one row |
| The S8 rollout observer started late and without its arguments (the wrapper dropped them) | The first timed change was measured only after the fact | Start the observer before the merge and check that its log fills before saying "merge" |
