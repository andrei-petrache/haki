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
# The unprivileged variant already runs as user 101 (nginx) and listens on 8080
FROM nginxinc/nginx-unprivileged:1.30.6-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
# A directory of our own, so none of the image's sample pages are served
COPY --from=build /app/dist /usr/share/nginx/haki

EXPOSE 8080
