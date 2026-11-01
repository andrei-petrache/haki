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

To check the Nginx config and the login/signup rate limit of a built image:

```bash
docker build -t haki-frontend:dev .
scripts/check-rate-limit.sh haki-frontend:dev
```
