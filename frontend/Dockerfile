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
# public/ is not in git (its only content, the RDKit wasm, is gitignored) and
# the postinstall hook that copies the wasm ran in the deps stage where
# public/ didn't exist. Materialize it here so the build is hermetic and the
# runner stage's COPY of /app/public always has something to copy — and fail
# loudly if the wasm ever moves inside the package.
RUN mkdir -p public && cp node_modules/@rdkit/rdkit/dist/RDKit_minimal.wasm public/RDKit_minimal.wasm
RUN pnpm build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

# Build identity — injected by CI from the git tag (see publish-images.yml).
# Image-specific (not environment-specific), so baking as ENV is correct; the
# Node server reads these at runtime and serves them from /api/config.
ARG APP_VERSION=0.0.0+dev
ARG APP_GIT_SHA=unknown
ARG APP_BUILD_DATE=unknown
ENV APP_VERSION=$APP_VERSION \
    APP_GIT_SHA=$APP_GIT_SHA \
    APP_BUILD_DATE=$APP_BUILD_DATE

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

RUN adduser -D -u 1001 cellar
USER cellar

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
