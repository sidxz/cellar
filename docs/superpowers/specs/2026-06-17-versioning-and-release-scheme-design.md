# Versioning & Release Scheme — Design

**Date:** 2026-06-17
**Status:** Approved (design); pending implementation plan
**Branch:** design-7

## Problem

The frontend and backend have no real versioning scheme. The version `0.1.0` is
hardcoded in three places that silently drift:

- `backend/pyproject.toml` → `0.1.0`
- `backend/src/cellar/interface/app.py` → `version="0.1.0"` (a second hardcoding)
- `frontend/package.json` → `0.1.0`

There is a single git tag `v0.1.0` (2026-06-15); `HEAD` is `v0.1.0-128-g84e7848`
— 128 commits past it, so virtually every running build is *between* releases.
No version is shown anywhere in the app. The backend exposes only its hardcoded
version at `/openapi.json`. No GitHub Releases are produced — `publish-images.yml`
only tags images. Conventional Commits are already in use across the history.

## Goals

1. A standard, explicit versioning scheme for FE and BE.
2. A single source of truth per component (no drift across files).
3. Show the running version in the app (footer + detailed About panel).
4. Produce GitHub Releases with changelogs on release.

## Decisions

| Decision | Choice |
|---|---|
| Version unit | **Independent per component** — `backend-vX.Y.Z`, `frontend-vX.Y.Z` |
| Scheme | **SemVer**, bumps follow Conventional Commits (`fix`→patch, `feat`→minor, `feat!`/`BREAKING CHANGE`→major). Bump chosen by the human at tag time. |
| Between-tag identity | `git describe` form per component, e.g. `1.4.0-128-g84e7848` |
| Source of truth | The **git tag**. `pyproject.toml`/`package.json` become coarse dev fallbacks only. |
| In-app display | Subtle footer tag + detailed About dialog |
| Release flow | Manual tag → CI auto-generates changelog, GitHub Release, and image |
| `/version` endpoint | **Auth-excluded** (carries no secrets; ops/monitoring can curl it) |
| Process doc | `RELEASING.md` at repo root (tracked; `docs/` is gitignored) |

## Architecture

### Source of truth & build-time injection

CI computes each component's version from its git tag and injects build identity
into the image as build args, baked to env vars. Git is **not** available inside
the Docker build context (`context: ./backend` excludes the repo-root `.git`), so
the version/sha/date are computed in a CI **step** and passed as `--build-arg`.

```
CI step computes:  APP_VERSION (from tag, prefix stripped), GIT_SHA, BUILD_DATE
  ↓ docker build --build-arg ...
  backend image  → ENV CELLAR_VERSION / CELLAR_GIT_SHA / CELLAR_BUILD_DATE
  frontend image → ENV APP_VERSION   / APP_GIT_SHA     / APP_BUILD_DATE
```

For non-tag (main / local) builds, `APP_VERSION` is the `git describe` form, or a
`0.0.0+dev` fallback when git/env is absent. Nothing crashes when build env is
missing.

### Backend

- **`backend/src/cellar/version.py`** (new) — a small, **pure** module (package
  root, no settings dependency) that resolves build identity:
  - `version`: `os.environ["CELLAR_VERSION"]` → `importlib.metadata.version("cellar")` → `"0.0.0+dev"`
  - `git_sha`: `os.environ.get("CELLAR_GIT_SHA")` → `"unknown"`
  - `build_date`: `os.environ.get("CELLAR_BUILD_DATE")` → `"unknown"`
  - Exposes a single `build_info()` returning a typed object of those three.
  - One purpose: provide build identity. No I/O beyond env + metadata. The
    runtime `environment` is intentionally **not** here — it is a settings
    concern, composed in the route below (keeps this module layer-pure).
- **`app.py`** — replace the hardcoded `version="0.1.0"` with `build_info().version`.
- **`GET /version`** (new route in `interface`) — thin endpoint returning
  `{name, version, git_sha, build_date, environment}`. It composes `build_info()`
  with `environment` read from settings (where settings are available via DI).
  Added to the auth `exclude_paths` list alongside `/health`, `/docs`,
  `/openapi.json`.
- **`backend/Dockerfile`** — `ARG APP_VERSION/GIT_SHA/BUILD_DATE` → `ENV CELLAR_*`.

### Frontend

The frontend's own version is **image-specific, not environment-specific**, so
baking it at build time is correct and does **not** violate the runtime-config
rule (which bans baking env-specific values like API URLs into the image). It is
delivered to the client through the **existing `/api/config` route** so there is
one config-delivery mechanism.

- **`frontend/Dockerfile`** — `ARG APP_VERSION/GIT_SHA/BUILD_DATE` → `ENV APP_*`.
- **`frontend/src/app/api/config/route.ts`** — extend the payload with
  `uiVersion`, `uiGitSha`, `uiBuildDate` (build-time, baked into the image), and
  `environment` (runtime / env-specific, like the other config values here), all
  read from `process.env.*` server-side with dev fallbacks.
- **`frontend/src/shared/lib/app-config.tsx`** — extend the `AppConfig` interface
  and `defaultConfig`/`fetchAppConfig` fallbacks with the new fields.
- **Footer** — render a compact `Cellar · UI vX.Y.Z` in the existing
  `SidebarFooter` (`shared/components/layout/app-sidebar.tsx`). Reads
  `AppConfig.uiVersion`; no network call.
- **About dialog** — opened from `shared/components/layout/user-menu.tsx`. Shows:
  - **UI**: version + sha + build date (from `AppConfig`)
  - **API**: version + sha + build date + environment (fetched live)
  - Graceful "API version unavailable" when the fetch fails.
- **`use-api-version` hook** — TanStack Query hook calling `GET /version` via
  `customInstance` (per the hand-written-hooks convention).

### Release pipeline

Rework `.github/workflows/publish-images.yml`:

- **Triggers:** `push` to `main` (unchanged behaviour: `latest` + `sha-` tags via
  path-filter), **plus** tags `backend-v*.*.*` and `frontend-v*.*.*`.
- A `backend-v1.4.0` tag builds **only** the backend. A shell step strips the
  `backend-` prefix to a clean semver (the single computed value), feeding both:
  - image tags `1.4.0`, `1.4`, `1` via `docker/metadata-action` `type=raw`
    (reusing the computed value rather than re-parsing the prefixed ref), and
  - the `APP_VERSION`/`GIT_SHA`/`BUILD_DATE` build args.
  The `frontend-v*` tag does the same, frontend-only.
- **Changelog:** `git-cliff` with `--include-path 'backend/**'` (resp.
  `frontend/**`), over commits since the previous **same-namespace** tag →
  component-scoped notes. A repo-root **`cliff.toml`** configures
  conventional-commit grouping.
- **GitHub Release:** published via `softprops/action-gh-release` (title e.g.
  "Backend v1.4.0", body = generated changelog).

### Process doc

**`RELEASING.md`** at repo root (tracked — `docs/` is gitignored in this repo):
the scheme, tag conventions, Conventional-Commit→bump mapping, and the
step-by-step "how to cut a backend/frontend release".

## Components (isolated units)

| Unit | What it does | Depends on |
|---|---|---|
| `version.py` | Resolve build identity from env, dev fallback | env, importlib.metadata, settings |
| `GET /version` route | Expose build identity (auth-excluded) | `version.py` |
| `backend/Dockerfile` ARG→ENV | Bake version/sha/date | CI build args |
| `frontend/Dockerfile` ARG→ENV | Bake version/sha/date | CI build args |
| `/api/config` + `AppConfig` ext | Deliver UI build info to client | `process.env.APP_*` |
| `SidebarFooter` tag | Always-visible UI version | `AppConfig` |
| About dialog + `use-api-version` | Detailed UI+API panel | `AppConfig`, `GET /version` |
| `publish-images.yml` + `cliff.toml` | Per-component tag→image+release | git tags |
| `RELEASING.md` | Human process doc | — |

## Error handling

- Missing build env → dev placeholders (`0.0.0+dev`, `unknown`); never crash.
- About panel `/version` fetch failure → "API version unavailable" state.
- A push of both a `backend-v*` and `frontend-v*` tag is independent; each job is
  gated on its own tag namespace.

## Testing

- **Backend unit:** `version.py` fallback priority (env > metadata > dev).
- **Backend api:** `/version` returns the expected shape and is reachable without
  auth (in `exclude_paths`).
- **Frontend:** footer renders the version; About dialog renders UI info +
  mocked `/version`, including the failure state.
- **CI:** small shell test for the prefix-strip/version-derive logic; the
  pipeline itself verified by review and a real tag push.

## Non-goals (YAGNI)

- **No automated UI↔API compatibility gate** (UI refusing to run against an
  out-of-range API). The About panel surfaces both versions for humans; an
  enforced minimum-API check is a separate, larger feature.
- **No release-please / semantic-release bot** — manual-tag control was chosen.
- **No CalVer** — SemVer only (date may appear in release notes incidentally).
