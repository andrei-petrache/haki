# Next promotion: readiness

Read-only report, 11 November 2026, about 20:10 UTC, updated on
12 November 2026, about 13:30 UTC (next section). Nothing was promoted;
the promotion needs Andrei's approval in the Environment `prod`.

## Update, 12 November 2026

The sections after this one are the report of 11 November; where they
differ, this section holds.

### Where prod and main are now

| | Revision | Images (backend, frontend, migrate) |
| --- | --- | --- |
| Prod now | `2817619` | `4957cfc` |
| `main` now | `369f672` | `bc51045` |

- `haki-prod`: Synced, Healthy on `2817619`, last sync still 11 November,
  16:05:00 UTC. Every prod and staging pod shows one restart, all at
  13:08:22 UTC on 12 November: the kind node itself restarted at 13:08:20
  (the machine started), not a crash.
- `scripts/check-promotion.sh 2817619 369f672 main` passes (exit 0): forward,
  both images published, the migration image moves `4957cfc` -> `bc51045`,
  one new migration so far (`f187f906dc7d`). 64 commits.
- Merged since `7ff7e82`: #138, #139, #146 (journal), #140 (catalog client
  and Credits), #149 (staging bump to `bc51045`), #142 (foods up to
  950 kcal per 100 g, 13:17 UTC), #144 (catalog plan, docs).

### A second migration: #147, `foods.favourited_at`

#147 ("Let users mark their own foods as favourites", merged on
12 November as `3de39ad`) adds
`backend/migrations/versions/ef6cd72f7e99_add_favourited_at_to_foods.py`:

- Revision `ef6cd72f7e99`, revises `f187f906dc7d`. Prod's chain becomes
  `3bf97e2ee106` (prod now) -> `f187f906dc7d` (catalog) -> `ef6cd72f7e99`.
  One `alembic upgrade head` in the migration hook applies both, in order.
  The backend session confirmed the id will not change on rebase.
- `ALTER TABLE foods ADD COLUMN favourited_at timestamptz`: nullable, no
  default, no backfill, no index. Expand-only. In PostgreSQL a nullable
  column without a default is a catalog change only: no table rewrite.
- The previous image neither reads nor writes the column, so it keeps
  working on the new schema; a favourite set after the promotion simply
  stays in the column during a rollback pin.
- On staging it ran on 12 November at about 13:45 UTC (images `3de39ad`):
  `Running upgrade f187f906dc7d -> ef6cd72f7e99`, no error; the column is
  `timestamp with time zone`, nullable, no default. The catalog import
  after it inserted one food (lard, from #142) and left the rest unchanged.
- A promotion from a SHA at or after `3de39ad` carries it. Run
  `check-promotion.sh` again on the SHA staging runs: it must list both
  `f187f906dc7d` and `ef6cd72f7e99`.
- The dump step still applies, now for two migrations: dump prod right
  before the merge of the promotion.

### Rollback risk from #142: foods above 900 kcal

#142 has no migration (the database checks only `>= 0`), but it moves a
bound that the old code also applies to its responses: `FoodResponse`
inherits `FoodIn`'s `le=900`. Checked on the published images:
`FoodResponse` of `4957cfc` (prod now) refuses 902 and 950 ("Input should
be less than or equal to 900"); `558d731` accepts both.

After the promotion a user can save a food between 900 and 950 kcal, or
copy one from the catalog once the import runs on prod (lard is 902). If
prod were then rolled back to
`4957cfc`, `GET /foods`, `POST /foods` and `PUT /foods/{id}` would answer
500 for that food's owner (response validation), and the Foods screen
would not load for them. Meal entries and other users are not affected.

Before any rollback pin to `4957cfc`, read (read only):

```sql
SELECT count(*) FROM foods WHERE calories_per_100g > 900;
```

0 means the rollback is safe on this point (on staging, `catalog_foods`
already holds one such food, lard, so a copy of it is one tap away).
Anything else is a decision
for Andrei (changing users' data is his gate). The lasting fix belongs to
the backend: response models without input bounds, so a later change of
a limit stays rollback-safe; the backend session has been told.

### Rollback pin after this promotion

Unchanged in shape: backend and frontend back on `4957cfc`, the migration
image kept on the promoted tag, because the older `alembic upgrade head`
knows neither `f187f906dc7d` nor `ef6cd72f7e99`. Plus the check above.

### Still open before the promotion

- #141 (the catalog import on prod) stays a draft until the promotion; it
  must be in `main` before the promote-prod run, with a fresh dump and
  Andrei's OK.
- Announced by the backend session, no migration: #145 (recent foods),
  #148 (copy a meal) and a pull request that streams the catalog import
  in batches of 1,000 (same command and exit codes).

## Where prod and main are

| | Revision | Images (backend, frontend, migrate) |
| --- | --- | --- |
| Prod now | `2817619` | `4957cfc` |
| `main` now | `7ff7e82` | `dbc06bb` |

- `haki-prod`: Synced, Healthy, last sync 16:05:00 UTC (promotion #96).
  Two backend pods and one frontend pod on `4957cfc`, 0 restarts.
- 57 commits between the two revisions, from 42 pull requests: the 41 below
  and #96, the previous promotion itself.
- `scripts/check-promotion.sh 2817619 7ff7e82 main` passes (exit 0): a
  forward promotion, both images published on GHCR, the migration image
  moves forward `4957cfc` -> `dbc06bb`.
- `main` keeps moving: the promotion takes the SHA that staging ran, Synced
  and Healthy, at the time it is dispatched. Run `check-promotion.sh` again
  on that SHA.

## Migrations

One new migration between the two migration images:

- `f187f906dc7d` (`backend/migrations/versions/f187f906dc7d_add_the_catalog_sources_foods_exercises_.py`):
  `CREATE EXTENSION pg_trgm`, the tables `catalog_sources`, `catalog_foods`
  and `catalog_exercises` with GIN indexes, and one nullable column with a
  foreign key on `foods` and on `exercises`. Expand-only: nothing renamed,
  dropped or made NOT NULL. The previous image keeps working on the new
  schema.
- Prod's `alembic_version` is `3bf97e2ee106`, the head `f187f906dc7d`
  follows from.
- On staging it ran on 11 November at 19:23 UTC (images `02b0780`): no error,
  `pg_trgm` created, pods 0 restarts.

## Can prod's migration user create `pg_trgm`?

Yes. Checked read-only (`begin read only` ... `rollback`) in prod's database:

- The only login role is `haki`: superuser, owner of the database `haki`,
  with the CREATE right on it.
- The migration Job's `DB_USER` and the database container's
  `POSTGRES_USER` come from the same key, `haki-secrets/DB_USER`, so the
  migration connects as `haki`.
- `pg_trgm` is available (1.3 to 1.6) and trusted; it is not installed yet.
  Being trusted, it would not even need a superuser, only the CREATE right.

## Rollback pin

None active: `k8s/components/images/` holds only `kustomization.yaml`, and
all three prod images at `main` are one tag, `dbc06bb`.

The way back after this promotion is the rollback pin (`k8s/README.md`): the
backend and frontend on `4957cfc`, the migration image kept on `dbc06bb`
(the older `alembic upgrade head` does not know `f187f906dc7d`). The old
code never reads the new tables or columns, so it runs on the new schema.

## The dump

The dump step applies. `check-promotion.sh` prints "**New migrations**
(dump prod before merging the promotion)" with `f187f906dc7d`, and the
promote-prod summary shows the same list. Step 4 of "Promote to prod" in
`k8s/README.md` says: if the summary lists new migrations, dump prod right
before the merge ("Back up before a migration").

Row counts in prod now, for the comparison after: `users` 9, `foods` 8,
`exercises` 5, `meal_entries` 0, `workouts` 5, `programs` 0. Take the full
counts again with the dump.

## The catalog import on prod

The import Job runs on staging only. A separate pull request moves it into
the prod overlay. It is not to be merged before the promotion, and is
merged only at promotion time, with a fresh dump and Andrei's OK. Prod
renders `k8s/overlays/prod` at the promoted SHA, so that pull request must
be in `main` before the promote-prod run for prod to get the Job. Without
it, prod gets the empty catalog tables and the catalog endpoints return
empty lists.

## Pull requests between `2817619` and `7ff7e82`

| PR | Title | Branch | Merged (UTC) |
| --- | --- | --- | --- |
| #93 | Weights in kg or lb, chosen in Profile | `feat/weight-units` | 16:23 |
| #97 | Record the standing orders for Claude Code sessions in CLAUDE.md | `docs/claude-standing-orders` | 16:18 |
| #98 | Journal: the second promotion and the proof of github.sha | `docs/second-promotion` | 16:13 |
| #99 | Move staging to a0cf08a | `bot/bump-staging` | 16:28 |
| #100 | Translations, part 1: typed dictionaries, the app frame and Profile in English and Romanian | `feat/i18n-core` | 16:32 |
| #101 | Auto-merge for Dependabot minor/patch and docs-only pull requests, in dry run | `ci/automerge` | 16:49 |
| #102 | Journal: the decisions of 11 November, settings included | `docs/decisions-11-november` | 16:53 |
| #103 | Translations, part 2: Foods and Today | `feat/i18n-foods-today` | 16:35 |
| #104 | Move staging to c0726f9 | `bot/bump-staging` | 16:38 |
| #105 | Translations, part 3: Workouts | `feat/i18n-workouts` | 16:58 |
| #106 | Move staging to c357598 | `bot/bump-staging` | 16:41 |
| #107 | Move staging to 1fe6096 | `bot/bump-staging` | 17:04 |
| #108 | Give the weight field room on a phone | `fix/ro-weight-row` | 17:44 |
| #109 | Move staging to dd3244c | `bot/bump-staging` | 17:49 |
| #110 | Add Prometheus and kube-state-metrics for staging, through ArgoCD | `ci/monitoring` | 17:53 |
| #111 | Translations, part 4: Programs | `feat/i18n-programs` | 18:02 |
| #112 | Give /api its own route rule on staging, for Envoy's metrics | `ci/staging-api-rule` | 17:58 |
| #113 | Add Grafana and the staging dashboards, as files in Git | `ci/monitoring-grafana` | 18:25 |
| #114 | Alert on sustained 5xx and on restart loops in staging | `ci/monitoring-alerts` | 18:46 |
| #115 | Move staging to 0cd98af | `bot/bump-staging` | 18:07 |
| #116 | Translations, part 5: validation, formats and the API client | `feat/i18n-forms-format` | 18:10 |
| #117 | Journal: the monitoring decisions and where they stand | `docs/monitoring-notes` | 18:57 |
| #118 | Add the catalog schema: sources, foods, exercises and links | `feat/catalog-design` | 19:12 |
| #119 | Move staging to 72f95c8 | `bot/bump-staging` | 18:15 |
| #120 | Record the active-language and phone-layout decisions | `docs/decisions-i18n-layout` | 18:22 |
| #122 | Phase 2, part 1: a rest timer between sets | `feat/rest-timer` | 18:49 |
| #123 | Serve request metrics for Prometheus on a port of their own | `feat/backend-metrics` | 18:42 |
| #124 | Stop Grafana's plugin downloads and give it the memory it uses | `ci/grafana-no-preinstall` | 18:39 |
| #125 | Move staging to 188ed49 | `bot/bump-staging` | 18:54 |
| #126 | Phase 2, part 2: last time for each exercise | `feat/last-time` | 19:00 |
| #127 | Scrape the staging backend's own metrics on port 9000 | `ci/scrape-backend-metrics` | 19:02 |
| #128 | Move staging to 2a44a16 | `bot/bump-staging` | 19:05 |
| #129 | Phase 2, part 3: mark personal records | `feat/records` | 19:08 |
| #130 | Move staging to 02b0780 | `bot/bump-staging` | 19:21 |
| #131 | Import the catalog from data files shipped in the image | `feat/catalog-import` | 19:16 |
| #132 | Search the catalog and copy items into the user's own lists | `feat/catalog-api` | 19:34 |
| #133 | Import the catalog on staging after every sync, as a PostSync hook | `ci/catalog-import-job` | 19:26 |
| #134 | Move staging to dbc06bb | `bot/bump-staging` | 19:39 |
| #135 | Show the backend's own metrics per route on the staging dashboard | `ci/dashboards-backend-metrics` | 19:47 |
| #136 | Note that a change to a hook alone starts no ArgoCD sync | `ci/readme-hook-sync` | 19:51 |
| #137 | Journal: the catalog import hook, the backend scrape, and a hook lesson | `docs/catalog-import-notes` | 19:57 |

#96 itself, the previous promotion, merged at 16:00 UTC; its commit `093a0af` is the first one after `2817619`.
