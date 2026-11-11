# Haki — frontend

React + TypeScript single-page app, built with Vite.

## Run locally

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to the backend on :8000
npm run lint     # ESLint
npm test         # Vitest
npm run build    # type-check + production build into dist/
```

## Image

Nginx serves the built app and proxies `/api/` to the backend. Its config is
`nginx.conf.template`, rendered when the container starts: set `BACKEND_URL`
to where the backend is reachable (default `http://backend:8000`, the compose
service), e.g. in Kubernetes:

```bash
docker run -e BACKEND_URL=http://haki-backend:8000 -p 8080:8080 haki-frontend:dev
```

To check the Nginx config and the login/signup rate limit of a built image:

```bash
docker build -t haki-frontend:dev .
scripts/check-rate-limit.sh haki-frontend:dev
```

## End-to-end tests

Playwright drives a real browser through the app on a throwaway stack:

```bash
npm ci                    # once: the test runner comes from node_modules
scripts/e2e.sh [out-dir]  # from frontend/ or anywhere in the repository
```

The script builds this checkout's images as `haki-*:e2e` and runs them as the
Compose project `haki-e2e`, with the override `e2e/compose.e2e.yaml`: the
database lives in memory, nothing is published on the host and no container
has a fixed name, so the dev stack (`haki-db`, port 8080) is never touched.
The tests run in the Playwright image pinned in that override, which must stay
on the same version as `@playwright/test` in `package.json`. Each run signs up
one fresh account and deletes everything it created at the end; the stack, its
images and the temporary env file are removed whatever the outcome.
Screenshots and failure traces go to `out-dir` (default: a new directory under
`/tmp`). Test files are named `*.e2e.ts`, so Vitest does not pick them up.
Each file signs up its own account (`e2e/helpers.ts`); `weight-units.e2e.ts`
checks through the API that weights shown and typed in pounds are stored in
kilograms and never change by themselves.
