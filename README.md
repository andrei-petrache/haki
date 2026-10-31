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
`JWT_SECRET_KEY` is missing. Its containers build their own `DATABASE_URL`
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

## Tests

```bash
cd backend && pytest -v
```
