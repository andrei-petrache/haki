# Plan

Decided on 11 November 2026: Haki is meant to become a live app that can
compete on the market, not only a DevOps learning project. The market is
international, English first, with Romanian foods and values done especially
well. Features are chosen by their value to users, and each one carries the
next DevOps topic, not the other way around. Everything that can run locally
for free still comes before AWS.

The positioning: nutrition and training in one fast app for people who lift,
no ads, with regional foods done right.

## Done: S0-S9

Until S9 each sprint taught one DevOps area, and app features were the
vehicles that carried it. Sprint numbers are those of the original plan,
with the shifts noted below.

| Sprint | Phase | What it covers | Status |
| --- | --- | --- | --- |
| S0-S2 | 1. App + Docker | API, database, frontend, accounts, foods and meals | Done |
| S3 | 1. App + Docker | Images for backend and frontend, full stack in Compose | Done |
| S4 | 2. CI | Lint, tests, build on every PR, protected `main`, Dependabot, PostgreSQL integration tests | Done |
| S5 | 2. CI | Images published to GHCR by commit SHA, Trivy scan, releases from tags | Done |
| S6-S7 | 3. Kubernetes (local) | kind, manifests, StatefulSet, probes, self-healing, resource limits, Kustomize for staging and prod, Gateway | Done |
| - | Feature | **Workouts**, planned with S5, shipped after S7 as the first release through Kustomize, Gateway and probes | Done |
| S8 | 4. GitOps | ArgoCD: the cluster's state lives in Git; staging updates itself on merge; a rollback is a `git revert` | Done |
| S9 | 4. GitOps | Prod updated only with approval: promotion between environments behind a gate. CI updates the image tag in Git (until then, a code change reaches staging through a separate pull request that changes the tag). Choose and test the explicit exception that lets an older image pass the migration hook for a rollback. Feature **Programs** (weekly plans, e.g. Push/Pull/Legs), shipped staging first, then prod, with a revert drill of its migration on staging | Done |

## Next: the feature chooses the sprint

In this order:

| # | Product phase | The DevOps topic it carries | Status |
| --- | --- | --- | --- |
| 1 | **Catalog**: exercises from free-exercise-db, generic foods from USDA, curated Romanian basics | Data migrations as opposed to schema migrations, an import Job, static assets | Next |
| 2 | **Fast logging**: recents, favourites, copy a meal, quick add; in the gym: last time's numbers, a rest timer, personal records, kg/lb | Prometheus and Grafana, alerts (failed publishes included) | Next |
| 3 | **Body weight** and an adaptive calorie target, linked to training volume | Argo Rollouts: blue-green with automatic rollback | Next |
| 4 | **Trust**: GDPR account deletion, data export and consent; password reset; e-mail verification | Scheduled backups and a restore drill, secrets handling | Next |
| 5 | **Mobile**: a PWA with offline logging; barcode scanning through Open Food Facts, cached and attributed | Caching, an external service | Next |
| 6 | **Dashboard**: weekly calories and training volume | A blue-green release | Next |
| 7 | **Go-live**: AWS with Terraform, a domain, TLS, e-mail, monitoring, a private beta; a last pass and the portfolio documentation (the old S14) | Terraform, costs; the hosting choice (EKS or something cheaper) | Next |

## Why: the market (research, November 2026)

- The market is split between calorie apps (MyFitnessPal, Cronometer,
  MacroFactor, Lose It!, Yazio) and gym loggers (Hevy, Strong, Fitbod,
  JEFIT). Even MacroFactor ships nutrition and workouts as two separate apps,
  with no shared coaching at launch. Haki already has both in one app.
- People quit because logging is tedious, not for lack of features: in one
  MyFitnessPal study, consistent logging fell from 68% in week 1 to 21% by
  week 12. Logging speed comes first.
- Common complaints: wrong user-submitted values, missing regional foods
  (Romanian users say so explicitly), ads and aggressive upselling. A
  Romanian competitor exists: Eat & Track, with 50k+ Romanian store foods.
- The leaders' edges: MacroFactor, an adaptive calorie target from the
  weight trend; Cronometer, data accuracy; Hevy, a generous free tier and a
  cheap lifetime licence.

## Data sources

| Source | Content | Licence and conditions |
| --- | --- | --- |
| USDA FoodData Central | Generic foods, nutrients | Public domain (CC0); a citation is requested |
| Open Food Facts | Barcoded products, strong in Europe | ODbL: attribution on screens, and share-alike for a derived database; kept separate from our own data |
| free-exercise-db | 800+ exercises with images | Unlicense (a public-domain dedication); credited anyway |
| wger | Exercises | CC-BY-SA (attribution and share-alike); not mixed in unless needed |

## Before real users

- GDPR: calorie intake against a weight goal is health data (Article 9), so
  explicit consent, a privacy policy, data export, account deletion (there
  is no endpoint for it yet) and hosting in the EU.
- Password reset and e-mail verification.
- Mobile use in the gym: a PWA first (installable, works offline), native
  later if needed.
- International basics: kg/lb, dates and numbers in the user's locale,
  translations (Romanian first).

## S9 progress

- [x] CI updates the image tag in Git: the `bump-staging` job opens the tag
  pull request (#52); first real bump through #55 (3 November)
- [x] The explicit rollback exception, chosen and built: the migration image
  pinned separately, `rollback-pin.yaml` (#56)
- [x] Auto-merge of the tag pull request, behind `tag-pr-scope` and
  `TAG_BOT_AUTO_MERGE` (#57); first real run with #60 (4 November)
- [x] Feature **Programs** on staging (#59, then #60; 4 November)
- [x] Revert drill of the Programs migration on staging, with the rollback
  pin (#61) and its lift (#62; 4 November)
- [x] Prod under ArgoCD, pinned to one commit SHA and guarded by
  `prod-guard` (#68, #69, #70; 9 November); promotion through the
  `promote-prod` workflow with approval (#75, #77; 10 November)
- [x] Programs on prod through the first promotion (#82), then automated
  sync for prod without prune (#83, #84; 11 November). S9 done

## Rules for AWS

- Infrastructure is created at the start of a session and destroyed at the
  end (`terraform destroy`), with a budget alert.
- Estimated total: 20-40 USD with that discipline. Every step that costs money
  is announced before it runs.
- These rules hold until go-live (phase 7). A live app runs 24/7, so
  "destroy every evening" no longer fits prod; the hosting (EKS or something
  cheaper) and its budget are decided then.

## Changes to the plan

- **The feature chooses the sprint** (decided on 11 November 2026): Haki is
  meant to become a live app, and the work after S9 follows the seven
  product phases above instead of the DevOps areas. The DevOps of the old
  S9-S10 to S13 moves with them: Prometheus, Grafana and alerts to phase 2,
  Argo Rollouts to 3, scheduled backups and the restore drill to 4, the
  Dashboard and its blue-green release to 6, AWS with Terraform to 7. The
  old S14, a last pass over everything and the portfolio documentation, is
  absorbed into phase 7.
- **Workouts moved** from S5 to after S7, so the first visible feature went
  through the whole new chain (Kustomize, Gateway, probes).
- **Approval for prod moved** from S8 to S9: S8 automates staging only, prod
  keeps the manual phases from `k8s/README.md` until then.
- **S8 starts with ArgoCD v3.5.7, not v3.6.0** (decided on 2 November 2026).
  v3.5 is tested on Kubernetes 1.33-1.36, not on the cluster's 1.37; v3.6.0,
  the first tested on 1.37, was not out yet, and the 7-day cooldown from
  `.github/dependabot.yml` would have meant waiting until about 10 November.
  The cluster is local, holds no real data and everything in it can be
  rebuilt, so waiting bought little. Upgrade to v3.6.x once it is out.

## Pace

The original plan aimed at May 2027 at 8-10 hours a week. The first sprints
went much faster; Kubernetes and AWS are harder conceptually, so the pace will
slow there. A realistic finish: March-April 2027. That estimate was made for
the old plan; the seven phases are more work, and it is redone once the
first of them is planned.
