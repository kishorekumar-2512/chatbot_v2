# web/Dockerfile
# Multi-stage build: compile the React SPA, then serve the static output
# with nginx. Build from the web/ directory:
#   docker build -t chatbot-web ./web
#
# For production you may prefer S3 + CloudFront instead of running this as
# its own container (cheaper, no server to patch) — this image exists for
# ECS/Fargate deployment or local docker-compose parity, whichever you pick.

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
# Left unset here on purpose — the app's default (VITE_API_URL unset ->
# falls back to relative "/api") is what lets nginx below reverse-proxy to
# the backend at CONTAINER START time via BACKEND_UPSTREAM, not build time.
# This means you don't need to rebuild this image just because the backend's
# internal URL changed between environments/deploys.
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx:alpine auto-runs envsubst on any *.template file in this directory
# at container startup, substituting $BACKEND_UPSTREAM below.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV BACKEND_UPSTREAM=http://backend:8000
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
