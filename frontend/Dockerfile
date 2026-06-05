FROM node:22-alpine AS base
# pnpm version is pinned via the packageManager field in package.json;
# corepack resolves it per-project so Docker/CI/local all use the same version.
RUN corepack enable

FROM base AS deps
WORKDIR /app
# pnpm-workspace.yaml carries the allowBuilds approvals — without it pnpm
# refuses to run dependency build scripts and install fails (ERR_PNPM_IGNORED_BUILDS).
COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

RUN adduser -D -u 1001 cellar
USER cellar

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
