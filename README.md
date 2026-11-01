# Haki

[![CI](https://github.com/andrei-petrache/haki/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/andrei-petrache/haki/actions/workflows/ci.yml)

A fitness and nutrition tracker, built as an end-to-end DevOps learning project:
from local development to a production-grade deployment on AWS.

## Stack

- **Backend:** FastAPI (Python), SQLAlchemy, Alembic, PostgreSQL
- **Frontend:** React + TypeScript (Vite)
- **Auth:** Argon2 password hashing, JWT access tokens
- **Containers:** Docker images for backend and frontend (Nginx), Docker Compose
- **CI:** GitHub Actions (lint, tests, build, Docker images) on every pull request
- **Coming next:** Kubernetes, ArgoCD, Terraform on AWS

## Configuration

```bash
cp .env.example .env              # then set real values
```

Both modes below read `.env`. Compose refuses to start if `POSTGRES_*` or
`JWT_SECRET_KEY` is missing, and the backend refuses a `JWT_SECRET_KEY` shorter
than 32 bytes or still set to the `.env.example` placeholder. Generate one with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`. Its containers build their own `DATABASE_URL`
with host `db`; the `DATABASE_URL` in `.env` (host `localhost`) is only for
the backend running on your machine.

## Run the full stack in containers

Requirements: Docker.

```bash
docker compose up -d --build      # http://127.0.0.1:8080
docker compose ps                 # all services healthy, migrate "Exited (0)"
docker compose logs -f backend    # follow the backend logs
docker compose down               # stop; data stays in the db-data volume
```

Services start in order: `db` (healthy) → `migrate` (runs `alembic upgrade
head`, then exits) → `backend` (healthy) → `frontend`. Only the frontend is
published; Nginx serves the app and proxies `/api/` to the backend.

Never run `docker compose down -v` unless you mean to delete the database:
`-v` removes the `db-data` volume.

CI starts this same stack with throwaway credentials on every pull request
and runs `scripts/smoke-test.sh` against it (page, health, readiness, signup,
login, authenticated calls). Locally, it creates a test user in your
database: `scripts/smoke-test.sh [base URL]`.

CI also scans both images with Trivy. Every finding goes to the repository's
Security tab (from `main`); the job fails only on CRITICAL or HIGH
vulnerabilities that already have a fix. Accepted exceptions live in
`.trivyignore`, each with a reason and an expiry date. To scan locally:

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD:/repo:ro" \
  aquasec/trivy:0.76.0 image --scanners vuln --severity CRITICAL,HIGH \
  --ignore-unfixed --ignorefile /repo/.trivyignore haki-frontend:dev
```

## Published images

Each image is built once per commit in CI; that same image is scanned,
smoke-tested and, for commits on `main` whose checks all pass, published to
GitHub Container Registry:

- `ghcr.io/andrei-petrache/haki-backend`
- `ghcr.io/andrei-petrache/haki-frontend`

Both packages are public (they inherit this public repository's visibility)
and linked to it, so anyone can pull them without logging in, and Kubernetes
needs no `imagePullSecret`. They contain no secrets: configuration comes only
from environment variables at runtime.

Tags: the full commit SHA (never changes; deploy this, or better, its digest)
and `main` (moves to the newest commit on `main`). There is no `latest`. The
`publish` job's summary lists each image's digest.

```bash
docker pull ghcr.io/andrei-petrache/haki-backend:<commit-sha>
```

## Develop locally

Requirements: Docker, Python 3.14, Node.js 22+.

```bash
docker compose up -d db           # PostgreSQL only

cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload     # http://localhost:8000/docs

cd ../frontend
npm install
npm run dev                       # http://localhost:5173
```

### Python dependencies

`backend/requirements.in` lists the direct runtime dependencies and
`requirements-dev.in` the dev tools; both are edited by hand. The `.txt`
files are generated locks: every package, including transitive ones, pinned
with its hashes, so `pip install` refuses anything else. To add, remove or
upgrade a dependency, edit the `.in` file and regenerate the locks (needs
Docker; runs pip-compile in the backend's Python image):

```bash
backend/scripts/compile-requirements.sh                          # after editing a .in
backend/scripts/compile-requirements.sh --upgrade-package fastapi  # bump one package
```

Dependabot edits the `.in` files and regenerates the locks itself.

## Tests

```bash
cd backend && pytest -v           # in-memory SQLite, no setup needed
```

### Integration tests (real PostgreSQL)

Tests marked `integration` check the migrations and the database constraints
against PostgreSQL. They are skipped unless `TEST_DATABASE_URL` is set, and
refuse to run unless its database name ends in `_test`, so they can never
touch the development database `haki`. CI runs them on every pull request.

One-time setup: a separate `haki_test` database inside the compose `db`.

```bash
docker compose up -d db
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" haki_test'
```

Run them from `backend/` with the venv active. Use the `POSTGRES_USER` and
`POSTGRES_PASSWORD` values from `.env`:

```bash
export TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/haki_test
DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head   # migrates haki_test, not haki
pytest -m integration -v
```

Alembic reads `DATABASE_URL`; the prefix on that one command points it at
`haki_test`. To start over: `docker compose exec db sh -c 'dropdb -U "$POSTGRES_USER" haki_test'`.
