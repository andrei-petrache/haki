# Haki frontend image: build the React app with Node, serve it with Nginx.
# Build from the frontend/ directory:
#   docker build -t haki-frontend:dev .
# Nginx proxies /api/ to $BACKEND_URL (default http://backend:8000), chosen
# when the container starts and resolved per request through DNS.

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

# The backend's address is set when the container starts, not baked in:
# e.g. docker run -e BACKEND_URL=http://haki-backend:8000. The image's
# entrypoint renders templates/*.template into conf.d with envsubst; the
# filter limits it to our variables, so nginx's own $host, $uri, ... stay
# as-is. NGINX_ENTRYPOINT_LOCAL_RESOLVERS makes the entrypoint set
# NGINX_LOCAL_RESOLVERS to the DNS servers in /etc/resolv.conf.
# REAL_IP_FROM: the address or CIDR of the proxy in front whose
# X-Forwarded-For is trusted (e.g. the pod CIDR in Kubernetes); the default
# "unix:" trusts nobody.
ENV BACKEND_URL=http://backend:8000 \
    REAL_IP_FROM=unix: \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    NGINX_ENVSUBST_FILTER=^(BACKEND_URL|REAL_IP_FROM|NGINX_LOCAL_RESOLVERS)$
COPY nginx.conf /etc/nginx/nginx.conf
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# A directory of our own, so none of the image's sample pages are served
COPY --from=build /app/dist /usr/share/nginx/haki

EXPOSE 8080
