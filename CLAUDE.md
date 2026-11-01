# Haki

Fitness and nutrition tracker, built by Andrei as an end-to-end DevOps learning
project (local dev → Docker → CI → Kubernetes/ArgoCD → Terraform on AWS).
See README.md for setup.

## How to work with Andrei

- Andrei is learning. Write the code, but explain every change and every new
  term **in Romanian**. Code, comments, commit messages and docs stay in English.
- Work in small steps and run the tests after each step.
- **Never print, read out or commit `.env`.** Use `.env.example` for shape.
- **Show the diff and wait for an explicit OK before any `git commit`.** New
  files don't appear in `git diff`; show them too
  (e.g. `git add -N <path> && git diff`).
- **Never `git push`.** Andrei does all pushing; an OK for a commit covers
  only the commit.
- **Never commit on `main`.** It is protected: changes land only through pull
  requests with all 6 required CI checks green (`backend`, `frontend`,
  `docker (backend)`, `docker (frontend)`, `postgres-image`, `integration`);
  no direct or force pushes. When a change adds or renames a CI job, tell
  Andrei to update the ruleset's required checks.
- Start every change on a new branch from an up-to-date `main`, named after
  the change with a type prefix: `feat/...`, `fix/...`, `ci/...`, `docs/...`,
  `refactor/...`, `chore/...` (e.g. `feat/weekly-summary`). Andrei pushes the
  branch and opens the PR. Claude's shell has no SSH agent, so `git fetch` and
  `git pull` fail there: ask Andrei to pull `main` first.
- Every commit must pass the CI steps on its own (ruff check, ruff format
  --check, pytest, npm run lint, npm test, npm run build). When models or
  migrations change, also run the integration steps (see Tests); when
  `frontend/nginx.conf` changes, run `frontend/scripts/check-rate-limit.sh`.
- Andrei may edit files between steps; re-read before editing and build on
  their version instead of overwriting it.

## Stack

- Backend (`backend/`): FastAPI, SQLAlchemy 2 (`Mapped`/`mapped_column`),
  Alembic, PostgreSQL 18 via `docker compose` (service `db`).
- Config: pydantic-settings reading `../.env` (`app/config.py`).
- Auth: Argon2 via pwdlib, JWT via pyjwt (`app/security.py`, `app/auth.py`).
- Frontend (`frontend/`): React + TypeScript (Vite), proxies `/api` to `:8000`.
- Python dependencies: add or change direct ones only in `backend/requirements.in`
  (runtime) or `requirements-dev.in` (tools), then run
  `backend/scripts/compile-requirements.sh` to regenerate the hashed locks
  `requirements.txt` / `requirements-dev.txt`. Never edit the `.txt` locks by
  hand; CI fails if they don't match the `.in` files.

## Commands

The venv lives at the repo root (`.venv`), not in `backend/`.

```bash
cd backend
../.venv/bin/pytest -q                          # tests
../.venv/bin/alembic upgrade head               # apply migrations (needs db)
../.venv/bin/alembic revision --autogenerate -m "..."
../.venv/bin/uvicorn app.main:app --reload      # http://localhost:8000/docs
```

Docker Compose: `docker compose up -d db` for local development (database
only), `docker compose up -d --build` for the full stack on
http://127.0.0.1:8080. **Never run `docker compose down -v`**: it deletes the
`db-data` volume with Andrei's data.

## Backend conventions

- One router module per resource (`app/auth.py`, `app/foods.py`), registered in
  `app/main.py`. Reuse `SessionDep` and `CurrentUser` from `app/auth.py`.
- Schemas live in `app/schemas.py`: `XIn` for request bodies, `XResponse`
  (with `from_attributes=True`) for responses. Never expose `password_hash`.
- Let database constraints be the source of truth for uniqueness and
  foreign keys: catch `IntegrityError`, roll back, return 409.
- **IDOR protection:** every single-resource access goes through one helper
  (e.g. `get_own_food`) that returns 404, not 403, when the row belongs to
  another user.
- Style: Black-like formatting, lines ≤ 88 chars, type hints everywhere,
  short docstrings on public functions. No linter is configured yet.

## Tests

- pytest with an in-memory SQLite per test (`backend/tests/conftest.py`), with
  foreign keys enabled via `PRAGMA foreign_keys=ON` to match PostgreSQL.
  Tests need neither `.env` nor a running database.
- Fixtures: `client`, `auth_headers`, `other_auth_headers`; helper
  `register_and_login(client, email)`.
- Structure tests as arrange / act / assert separated by blank lines. Cover
  happy paths, validation (422), conflicts (409), auth required (401), and
  IDOR (another user gets 404 and the data stays unchanged).
- Integration tests (`backend/tests/integration/`, marker `integration`) run
  against a migrated PostgreSQL in `TEST_DATABASE_URL`, each test inside a
  rolled-back transaction (fixture `db`). The guard in `database.py` refuses
  any database whose name does not end in `_test`. **Never point
  `TEST_DATABASE_URL` or a migration/downgrade at the dev database `haki`**;
  for local checks prefer a throwaway container of the image in `compose.yaml`.
- The PostgreSQL image is pinned only in `compose.yaml` (`services.db.image`);
  the CI job `postgres-image` reads it from there for the `integration` job.
- Frontend: Vitest (`npm test`), test files next to the code (`*.test.ts`).
  `frontend/scripts/check-rate-limit.sh <image>` runs `nginx -t` and checks
  the login/signup rate limit on a built image (CI runs it in
  `docker (frontend)`).
