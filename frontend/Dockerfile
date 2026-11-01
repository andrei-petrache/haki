# Haki frontend image: build the React app with Node, serve it with Nginx.
# Build from the frontend/ directory:
#   docker build -t haki-frontend:dev .
# Nginx proxies /api/ to http://backend:8000, so a "backend" host must be
# resolvable on the container's network when Nginx starts.

# ---- Build: compile the app into static files in dist/ ----
FROM node:22.23.3-trixie-slim AS build

WORKDIR /app

# Lockfile before code: dependencies are reinstalled only when they change
COPY package.json package-lock.json ./
RUN npm ci

COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY public ./public
COPY src ./src
RUN npm run build

# ---- Runtime: Nginx serving only the built files ----
# The unprivileged variant runs as user 101 (nginx) and listens on 8080.
# 1.30 is the current stable branch (even minor).
FROM nginxinc/nginx-unprivileged:1.30.6-alpine AS runtime

# Alpine security fixes released after this image was built. A trade-off:
# two builds on different days may get different patch levels, which is
# better than shipping known, already-fixed vulnerabilities until a new
# image appears. Root only for this step, then back to the nginx user.
# CI rebuilds this stage without cache, so the upgrade runs on every build.
USER root
RUN apk upgrade --no-cache
USER 101

COPY nginx.conf /etc/nginx/conf.d/default.conf
# A directory of our own, so none of the image's sample pages are served
COPY --from=build /app/dist /usr/share/nginx/haki

EXPOSE 8080
