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
- Andrei may edit files between steps; re-read before editing and build on
  their version instead of overwriting it.

## Stack

- Backend (`backend/`): FastAPI, SQLAlchemy 2 (`Mapped`/`mapped_column`),
  Alembic, PostgreSQL 18 via `docker compose` (service `db`).
- Config: pydantic-settings reading `../.env` (`app/config.py`).
- Auth: Argon2 via pwdlib, JWT via pyjwt (`app/security.py`, `app/auth.py`).
- Frontend (`frontend/`): React + TypeScript (Vite), proxies `/api` to `:8000`.
- Dependencies are pinned in `backend/requirements.txt` and
  `requirements-dev.txt`; pin any new one there.

## Commands

The venv lives at the repo root (`.venv`), not in `backend/`.

```bash
cd backend
../.venv/bin/pytest -q                          # tests
../.venv/bin/alembic upgrade head               # apply migrations (needs db)
../.venv/bin/alembic revision --autogenerate -m "..."
../.venv/bin/uvicorn app.main:app --reload      # http://localhost:8000/docs
```

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
