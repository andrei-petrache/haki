# Plan

Each sprint teaches one DevOps area; new app features are the vehicles that
carry it, and everything that can run locally for free comes before AWS.
Sprint numbers are those of the original plan, with the shifts noted below.

| Sprint | Phase | What it covers | Status |
| --- | --- | --- | --- |
| S0-S2 | 1. App + Docker | API, database, frontend, accounts, foods and meals | Done |
| S3 | 1. App + Docker | Images for backend and frontend, full stack in Compose | Done |
| S4 | 2. CI | Lint, tests, build on every PR, protected `main`, Dependabot, PostgreSQL integration tests | Done |
| S5 | 2. CI | Images published to GHCR by commit SHA, Trivy scan, releases from tags | Done |
| S6-S7 | 3. Kubernetes (local) | kind, manifests, StatefulSet, probes, self-healing, resource limits, Kustomize for staging and prod, Gateway | Done |
| - | Feature | **Workouts**, planned with S5, shipped after S7 as the first release through Kustomize, Gateway and probes | Done |
| S8 | 4. GitOps | ArgoCD: the cluster's state lives in Git; staging updates itself on merge | In progress |
| S9 | 4. GitOps | Prod updated only with approval: promotion between environments behind a gate. Feature **Programs** (weekly plans, e.g. Push/Pull/Legs), shipped staging first, then prod | Next |
| S9-S10 | 6. Hardening (local) | Prometheus and Grafana with alerts; Argo Rollouts (blue-green, automatic rollback); scheduled database backups and a restore drill | Next |
| S11 | 6. Hardening (local) | Feature **Dashboard** (weekly calories and training volume), shipped blue-green; a broken release rolls back on its own | Next |
| S11-S13 | 5. AWS with Terraform | VPC, EKS and IAM as code; everything that works locally moves to the cloud; secrets in AWS Secrets Manager synced into the cluster | Next |
| S14 | Final | A last pass over everything; portfolio documentation: README, architecture diagram, decisions | Next |

## Rules for AWS

- Infrastructure is created at the start of a session and destroyed at the
  end (`terraform destroy`), with a budget alert.
- Estimated total: 20-40 USD with that discipline. Every step that costs money
  is announced before it runs.

## Changes to the plan

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
slow there. A realistic finish: March-April 2027.
