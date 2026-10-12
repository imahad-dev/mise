# syntax=docker/dockerfile:1
FROM node:22-alpine AS builder
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app

# Manifests only, so the install layer is cached
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc* ./
COPY apps/guest-web/package.json apps/guest-web/package.json
COPY apps/owner-web/package.json apps/owner-web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN pnpm install --frozen-lockfile

# Fail early, with a clear message, if next did not get linked
RUN test -f apps/guest-web/node_modules/next/package.json \
    || (echo "NEXT NOT INSTALLED for guest-web"; ls -la apps/guest-web/node_modules | head -20; exit 1)

# Source (host node_modules excluded by .dockerignore)
COPY . .
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
RUN pnpm --filter guest-web build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
COPY --from=builder /app/apps/guest-web/.next/standalone ./
COPY --from=builder /app/apps/guest-web/.next/static ./apps/guest-web/.next/static
COPY --from=builder /app/apps/guest-web/public ./apps/guest-web/public
CMD ["node", "apps/guest-web/server.js"]