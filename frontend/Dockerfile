# syntax=docker/dockerfile:1.7
# ──────────────────────────────────────────────
# Stage 1: Node build
# ──────────────────────────────────────────────
FROM node:24-slim AS builder

WORKDIR /build

# Copy dependency manifests first for layer caching.
# .npmrc carries legacy-peer-deps=true (needed for the eslint 10 peer ranges),
# so it must be present before `npm ci`.
COPY package.json package-lock.json .npmrc ./

# Clean install — uses lock file exactly; fails on drift
RUN npm ci --ignore-scripts

# Copy source and build
COPY . .
RUN npm run build

# ──────────────────────────────────────────────
# Stage 2: nginx runtime
# ──────────────────────────────────────────────
FROM nginx:alpine AS runtime

# Remove the default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Install curl for healthcheck
RUN apk add --no-cache curl

# Copy SPA nginx config
COPY nginx.conf /etc/nginx/conf.d/finsight.conf

# Copy built assets from builder stage
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/index.html || exit 1

CMD ["nginx", "-g", "daemon off;"]
