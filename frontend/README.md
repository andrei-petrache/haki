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
