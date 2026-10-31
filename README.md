# Haki

A fitness and nutrition tracker, built as an end-to-end DevOps learning project:
from local development to a production-grade deployment on AWS.

## Stack

- **Backend:** FastAPI (Python), SQLAlchemy, Alembic, PostgreSQL
- **Frontend:** React + TypeScript (Vite)
- **Auth:** Argon2 password hashing, JWT access tokens
- **Coming next:** Docker images, GitHub Actions CI, Kubernetes, ArgoCD, Terraform on AWS

## Run locally

Requirements: Docker, Python 3.14, Node.js 22+.

```bash
cp .env.example .env              # then set real values
docker compose up -d              # PostgreSQL

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
