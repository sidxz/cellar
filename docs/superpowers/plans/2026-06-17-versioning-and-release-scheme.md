# Versioning & Release Scheme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the frontend and backend an independent-per-component SemVer scheme with the git tag as single source of truth, surface the running version in the app (footer + About panel), and auto-produce per-component changelogs and GitHub Releases on tag.

**Architecture:** CI computes each component's version from its git tag (`backend-vX.Y.Z` / `frontend-vX.Y.Z`), injects it into the Docker image as build args baked to env vars, and the apps read those at runtime. The backend exposes build identity at an unauthenticated `GET /version`; the frontend bakes its own version and delivers it (plus the live API version) to a footer tag and an About dialog. A reworked `publish-images.yml` builds only the tagged component, tags its image with the clean semver, and publishes a git-cliff changelog as a GitHub Release.

**Tech Stack:** Python 3.13 / FastAPI / Pydantic v2 / uv · Next.js 16 / React 19 / TanStack Query / vitest / pnpm · GitHub Actions / docker-buildx / git-cliff / softprops/action-gh-release.

## Global Constraints

- **Scheme:** SemVer `MAJOR.MINOR.PATCH`. Bumps follow Conventional Commits: `fix:`→patch, `feat:`→minor, `feat!:`/`BREAKING CHANGE:`→major. Bump chosen by the human at tag time.
- **Independent per component.** Two git-tag namespaces: `backend-vX.Y.Z`, `frontend-vX.Y.Z`. Each is the single source of truth for its component's version.
- **Between-tag identity** is the `git describe` form, e.g. `1.4.0-128-g84e7848`.
- **`GET /version` is unauthenticated** — added to Sentinel `exclude_paths`. It carries no secrets.
- **Frontend version baking is image-specific, not environment-specific** — baking it is correct and does NOT use `NEXT_PUBLIC_*`. It is delivered through the existing `/api/config` runtime route. The `environment` field IS env-specific and comes from a runtime env var.
- **Honor the orval rule:** `/version` has a Pydantic `response_model` so its TS type is generated, not hand-rolled.
- **Commit with explicit pathspec** (`git commit -m ... -- <paths>`) — the working tree has an unrelated staged change (`frontend/src/features/screening-assay/components/run-dr-results.tsx`) that must never be swept into these commits.
- **`pyproject.toml` / `package.json` versions are non-authoritative dev fallbacks** — leave them as-is; do not treat them as the source of truth.

---

### Task 1: Backend build-info module

**Files:**
- Create: `backend/src/cellar/version.py`
- Test: `backend/tests/unit/test_version.py`

**Interfaces:**
- Produces: `build_info() -> BuildInfo`, where `BuildInfo` is a frozen dataclass with `version: str`, `git_sha: str`, `build_date: str`. Resolution priority for `version`: `CELLAR_VERSION` env → `importlib.metadata.version("cellar")` → `"0.0.0+dev"`. `git_sha`/`build_date` default to `"unknown"`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/test_version.py`:

```python
"""Unit tests for build identity resolution."""

from __future__ import annotations

import pytest

from cellar import version as version_mod
from cellar.version import build_info


def test_version_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELLAR_VERSION", "1.4.0")
    assert build_info().version == "1.4.0"


def test_version_falls_back_to_package_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELLAR_VERSION", raising=False)
    # `cellar` is installed in the test env, so metadata resolves a non-empty version.
    assert build_info().version


def test_version_dev_fallback_when_unpackaged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELLAR_VERSION", raising=False)

    def _raise(_name: str) -> str:
        raise version_mod.metadata.PackageNotFoundError(_name)

    monkeypatch.setattr(version_mod.metadata, "version", _raise)
    assert build_info().version == "0.0.0+dev"


def test_git_sha_and_build_date_default_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELLAR_GIT_SHA", raising=False)
    monkeypatch.delenv("CELLAR_BUILD_DATE", raising=False)
    info = build_info()
    assert info.git_sha == "unknown"
    assert info.build_date == "unknown"


def test_git_sha_and_build_date_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELLAR_GIT_SHA", "84e7848")
    monkeypatch.setenv("CELLAR_BUILD_DATE", "2026-06-17T12:00:00Z")
    info = build_info()
    assert info.git_sha == "84e7848"
    assert info.build_date == "2026-06-17T12:00:00Z"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/test_version.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cellar.version'`.

- [ ] **Step 3: Write the module**

Create `backend/src/cellar/version.py`:

```python
"""Build identity for the running backend image.

Resolves version, git SHA, and build date from environment variables baked
into the image at build time, with safe fallbacks for local/dev runs.

Pure: no settings dependency and no I/O beyond ``os.environ`` and
``importlib.metadata``. The runtime ``environment`` (dev/staging/prod) is a
settings concern and is intentionally NOT resolved here — the ``/version``
route composes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import metadata


@dataclass(frozen=True)
class BuildInfo:
    """Identity of the running build."""

    version: str
    git_sha: str
    build_date: str


def _resolve_version() -> str:
    env = os.environ.get("CELLAR_VERSION")
    if env:
        return env
    try:
        return metadata.version("cellar")
    except metadata.PackageNotFoundError:
        return "0.0.0+dev"


def build_info() -> BuildInfo:
    """Return the running build's identity."""
    return BuildInfo(
        version=_resolve_version(),
        git_sha=os.environ.get("CELLAR_GIT_SHA", "unknown"),
        build_date=os.environ.get("CELLAR_BUILD_DATE", "unknown"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/test_version.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(version): add backend build-info module

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- backend/src/cellar/version.py backend/tests/unit/test_version.py
```

---

### Task 2: Backend `/version` endpoint + FastAPI version wiring

**Files:**
- Create: `backend/src/cellar/interface/routes/version.py`
- Modify: `backend/src/cellar/interface/app.py` (import `build_info`; set `version=`; include router; add `/version` to `exclude_paths`)
- Test: `backend/tests/api/test_version.py`

**Interfaces:**
- Consumes: `build_info()` from Task 1.
- Produces: `GET /version` → `VersionResponse` Pydantic model with fields `name: str`, `version: str`, `git_sha: str`, `build_date: str`, `environment: str`. `name` is the constant `"cellar-backend"`; `environment` is `os.environ.get("ENVIRONMENT", "development")`. Route tagged `["meta"]`, unauthenticated.

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/api/test_version.py`:

```python
"""API tests for the build-identity endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_version_endpoint_returns_build_identity(client: AsyncClient) -> None:
    resp = await client.get("/version")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "cellar-backend"
    assert set(body) == {"name", "version", "git_sha", "build_date", "environment"}
    assert isinstance(body["version"], str) and body["version"]


@pytest.mark.asyncio
async def test_version_reports_injected_build_env(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CELLAR_VERSION", "1.4.0")
    monkeypatch.setenv("CELLAR_GIT_SHA", "84e7848")
    monkeypatch.setenv("ENVIRONMENT", "production")
    resp = await client.get("/version")
    body = resp.json()
    assert body["version"] == "1.4.0"
    assert body["git_sha"] == "84e7848"
    assert body["environment"] == "production"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/api/test_version.py -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Write the route module**

Create `backend/src/cellar/interface/routes/version.py`:

```python
"""Build-identity endpoint (`GET /version`) — unauthenticated, no DB.

Composes the pure ``build_info()`` with the runtime ``environment`` (a settings
concern) into the response.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.version import build_info

router = APIRouter()


class VersionResponse(BaseModel):
    """Identity of the running backend build."""

    name: str
    version: str
    git_sha: str
    build_date: str
    environment: str


@router.get("/version", response_model=VersionResponse, tags=["meta"])
async def get_version() -> VersionResponse:
    info = build_info()
    return VersionResponse(
        name="cellar-backend",
        version=info.version,
        git_sha=info.git_sha,
        build_date=info.build_date,
        environment=os.environ.get("ENVIRONMENT", "development"),
    )
```

- [ ] **Step 4: Wire the route + version + auth-exclude into `app.py`**

In `backend/src/cellar/interface/app.py`:

1. Add to the top-level imports:

```python
from cellar.version import build_info
```

2. Change the `FastAPI(...)` construction — replace `version="0.1.0",` with:

```python
        version=build_info().version,
```

3. Add `/version` to the Sentinel exclude list — change:

```python
        exclude_paths=["/health", "/docs", "/openapi.json"],
```
to:
```python
        exclude_paths=["/health", "/version", "/docs", "/openapi.json"],
```

4. Register the router — next to where the `/health` route is defined (just before `return app`), add:

```python
    from cellar.interface.routes.version import router as version_router

    app.include_router(version_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/api/test_version.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Verify nothing else broke + format/lint**

Run: `cd backend && uv run ruff format src/cellar/version.py src/cellar/interface/routes/version.py src/cellar/interface/app.py && uv run ruff check src/cellar/interface/routes/version.py src/cellar/interface/app.py && uv run pytest tests/api/test_version.py tests/unit/test_version.py -q`
Expected: format clean, lint clean, tests pass.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(version): expose GET /version build-identity endpoint

Unauthenticated; FastAPI app version now reads build_info() instead of a
hardcoded literal.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- backend/src/cellar/interface/routes/version.py backend/src/cellar/interface/app.py backend/tests/api/test_version.py
```

---

### Task 3: Backend Dockerfile build args

**Files:**
- Modify: `backend/Dockerfile`

**Interfaces:**
- Consumes: build args `APP_VERSION`, `GIT_SHA`, `BUILD_DATE` from CI (Task 7).
- Produces: image with `CELLAR_VERSION` / `CELLAR_GIT_SHA` / `CELLAR_BUILD_DATE` env vars baked in, which `build_info()` (Task 1) reads.

- [ ] **Step 1: Add ARG→ENV to the Dockerfile**

In `backend/Dockerfile`, insert immediately **before** the `EXPOSE 8000` line:

```dockerfile
# Build identity — injected by CI from the git tag (see publish-images.yml).
# Defaults keep local `docker build` runs honest about being unversioned.
ARG APP_VERSION=0.0.0+dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ENV CELLAR_VERSION=$APP_VERSION \
    CELLAR_GIT_SHA=$GIT_SHA \
    CELLAR_BUILD_DATE=$BUILD_DATE
```

- [ ] **Step 2: Verify the image builds and reports the injected version**

Run:
```bash
cd backend && docker build --build-arg APP_VERSION=9.9.9 --build-arg GIT_SHA=deadbee -t cellar-backend:verify . \
  && docker run --rm cellar-backend:verify .venv/bin/python -c "from cellar.version import build_info; print(build_info())"
```
Expected: prints `BuildInfo(version='9.9.9', git_sha='deadbee', build_date='unknown')`.

- [ ] **Step 3: Commit**

```bash
git commit -m "build(version): bake build identity into backend image

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- backend/Dockerfile
```

---

### Task 4: Frontend runtime config + AppConfig extension + Dockerfile

**Files:**
- Modify: `frontend/src/app/api/config/route.ts`
- Modify: `frontend/src/shared/lib/app-config.tsx`
- Modify: `frontend/Dockerfile`
- Test: `frontend/src/app/api/config/route.test.ts`

**Interfaces:**
- Produces: `/api/config` JSON gains `uiVersion`, `uiGitSha`, `uiBuildDate`, `environment` (all `string`). `AppConfig` interface gains the same four fields. Defaults: `uiVersion: "0.0.0+dev"`, `uiGitSha: "unknown"`, `uiBuildDate: "unknown"`, `environment: "development"`.

- [ ] **Step 1: Write the failing route test**

Create `frontend/src/app/api/config/route.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("/api/config", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns baked UI build info from env", async () => {
    vi.stubEnv("APP_VERSION", "2.1.0");
    vi.stubEnv("APP_GIT_SHA", "84e7848");
    vi.stubEnv("APP_BUILD_DATE", "2026-06-17T12:00:00Z");
    vi.stubEnv("APP_ENVIRONMENT", "production");

    const body = await GET().json();

    expect(body.uiVersion).toBe("2.1.0");
    expect(body.uiGitSha).toBe("84e7848");
    expect(body.uiBuildDate).toBe("2026-06-17T12:00:00Z");
    expect(body.environment).toBe("production");
  });

  it("falls back to dev placeholders when env is absent", async () => {
    vi.stubEnv("APP_VERSION", "");
    vi.stubEnv("APP_GIT_SHA", "");
    vi.stubEnv("APP_ENVIRONMENT", "");

    const body = await GET().json();

    expect(body.uiVersion).toBe("0.0.0+dev");
    expect(body.uiGitSha).toBe("unknown");
    expect(body.environment).toBe("development");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/app/api/config/route.test.ts`
Expected: FAIL — `uiVersion` is `undefined`.

- [ ] **Step 3: Extend the config route**

Replace the body of `frontend/src/app/api/config/route.ts`'s `GET` `Response.json({...})` to add the four fields (keep existing fields). The full file:

```ts
/**
 * Runtime configuration endpoint.
 *
 * Reads environment variables at request time (NOT build time) for
 * environment-specific values, enabling a single universal Docker image.
 *
 * The UI build identity (uiVersion/uiGitSha/uiBuildDate) is image-specific,
 * baked into the image at build time via APP_VERSION/APP_GIT_SHA/APP_BUILD_DATE
 * (see frontend/Dockerfile + publish-images.yml). It is delivered here so the
 * client has a single config-fetch mechanism.
 *
 * Variables use APP_ prefix (server-side only) instead of NEXT_PUBLIC_
 * (which gets baked into the JS bundle at build time).
 */
export function GET() {
  return Response.json({
    apiUrl: process.env.APP_API_URL ?? "http://localhost:8000",
    appUrl: process.env.APP_URL ?? "http://localhost:3000",
    sentinelUrl: process.env.APP_SENTINEL_URL ?? "http://localhost:9003",
    idpProvider: process.env.APP_IDP_PROVIDER ?? "google",
    googleClientId: process.env.APP_GOOGLE_CLIENT_ID ?? "",
    entraIdClientId: process.env.APP_ENTRA_ID_CLIENT_ID ?? "",
    entraIdTenantId: process.env.APP_ENTRA_ID_TENANT_ID ?? "",
    // Build identity (image-specific) + runtime environment (env-specific).
    uiVersion: process.env.APP_VERSION || "0.0.0+dev",
    uiGitSha: process.env.APP_GIT_SHA || "unknown",
    uiBuildDate: process.env.APP_BUILD_DATE || "unknown",
    environment: process.env.APP_ENVIRONMENT || "development",
  });
}
```

(Note: `||` not `??` so empty-string env from the test/deploy collapses to the fallback.)

- [ ] **Step 4: Run route test to verify it passes**

Run: `cd frontend && pnpm vitest run src/app/api/config/route.test.ts`
Expected: PASS.

- [ ] **Step 5: Extend the `AppConfig` interface + fallbacks**

In `frontend/src/shared/lib/app-config.tsx`:

1. Add to the `AppConfig` interface (after `entraIdTenantId: string;`):

```ts
  uiVersion: string;
  uiGitSha: string;
  uiBuildDate: string;
  environment: string;
```

2. Add to `defaultConfig` (after `entraIdTenantId: "",`):

```ts
  uiVersion: "0.0.0+dev",
  uiGitSha: "unknown",
  uiBuildDate: "unknown",
  environment: "development",
```

3. Add to the `fetchAppConfig` fallback return object (after the `entraIdTenantId:` line):

```ts
    uiVersion: process.env.NEXT_PUBLIC_UI_VERSION ?? defaultConfig.uiVersion,
    uiGitSha: process.env.NEXT_PUBLIC_UI_GIT_SHA ?? defaultConfig.uiGitSha,
    uiBuildDate: process.env.NEXT_PUBLIC_UI_BUILD_DATE ?? defaultConfig.uiBuildDate,
    environment: process.env.NEXT_PUBLIC_ENVIRONMENT ?? defaultConfig.environment,
```

(This branch only runs in SSR/test where `/api/config` is unreachable; the `NEXT_PUBLIC_*` reads here are a dev/test fallback, not image baking.)

- [ ] **Step 6: Add ARG→ENV to the frontend Dockerfile**

In `frontend/Dockerfile`, in the **`runner`** stage, insert immediately **after** `ENV NODE_ENV=production`:

```dockerfile

# Build identity — injected by CI from the git tag (see publish-images.yml).
# Image-specific (not environment-specific), so baking as ENV is correct; the
# Node server reads these at runtime and serves them from /api/config.
ARG APP_VERSION=0.0.0+dev
ARG APP_GIT_SHA=unknown
ARG APP_BUILD_DATE=unknown
ENV APP_VERSION=$APP_VERSION \
    APP_GIT_SHA=$APP_GIT_SHA \
    APP_BUILD_DATE=$APP_BUILD_DATE
```

- [ ] **Step 7: Lint + commit**

Run: `cd frontend && pnpm biome check --write src/app/api/config/route.ts src/app/api/config/route.test.ts src/shared/lib/app-config.tsx && pnpm lint`
Expected: exit code 0.

```bash
git commit -m "feat(version): deliver UI build identity via /api/config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- frontend/src/app/api/config/route.ts frontend/src/app/api/config/route.test.ts \
     frontend/src/shared/lib/app-config.tsx frontend/Dockerfile
```

---

### Task 5: Sidebar footer version tag

**Files:**
- Create: `frontend/src/shared/components/layout/app-version-tag.tsx`
- Modify: `frontend/src/shared/components/layout/app-sidebar.tsx`
- Test: `frontend/src/shared/components/layout/app-version-tag.test.tsx`

**Interfaces:**
- Consumes: `useAppConfig().uiVersion` (Task 4).
- Produces: `<AppVersionTag />` rendering `UI v{uiVersion}` (collapsed-sidebar-aware), reading config from context (no network).

- [ ] **Step 1: Write the failing component test**

Create `frontend/src/shared/components/layout/app-version-tag.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppConfigProvider } from "@/shared/lib/app-config";
import { AppVersionTag } from "./app-version-tag";

function renderWithConfig(uiVersion: string) {
  const config = {
    apiUrl: "",
    appUrl: "",
    sentinelUrl: "",
    idpProvider: "google",
    googleClientId: "",
    entraIdClientId: "",
    entraIdTenantId: "",
    uiVersion,
    uiGitSha: "unknown",
    uiBuildDate: "unknown",
    environment: "development",
  };
  return render(
    <AppConfigProvider config={config}>
      <AppVersionTag />
    </AppConfigProvider>,
  );
}

describe("AppVersionTag", () => {
  it("renders the UI version from config", () => {
    renderWithConfig("2.1.0");
    expect(screen.getByText("UI v2.1.0")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/shared/components/layout/app-version-tag.test.tsx`
Expected: FAIL — cannot resolve `./app-version-tag`.

- [ ] **Step 3: Write the component**

Create `frontend/src/shared/components/layout/app-version-tag.tsx`:

```tsx
"use client";

import { useAppConfig } from "@/shared/lib/app-config";

/**
 * Compact, always-visible UI version tag for the sidebar footer.
 * Reads the baked UI version from runtime config — no network call.
 */
export function AppVersionTag() {
  const { uiVersion } = useAppConfig();
  return (
    <span className="text-[11px] font-medium tracking-wide text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden">
      UI v{uiVersion}
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/shared/components/layout/app-version-tag.test.tsx`
Expected: PASS.

- [ ] **Step 5: Mount it in the sidebar footer**

In `frontend/src/shared/components/layout/app-sidebar.tsx`:

1. Add the import after the `UserMenu` import:

```tsx
import { AppVersionTag } from "./app-version-tag";
```

2. In the `SidebarFooter`, replace the `chemcellar.com` span with the version tag — change:

```tsx
          <span className="text-[11px] font-medium tracking-wide text-sidebar-foreground/40 group-data-[collapsible=icon]:hidden">
            chemcellar.com
          </span>
```
to:
```tsx
          <AppVersionTag />
```

- [ ] **Step 6: Lint + commit**

Run: `cd frontend && pnpm biome check --write src/shared/components/layout/app-version-tag.tsx src/shared/components/layout/app-version-tag.test.tsx src/shared/components/layout/app-sidebar.tsx && pnpm lint`
Expected: exit code 0.

```bash
git commit -m "feat(version): show UI version in sidebar footer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- frontend/src/shared/components/layout/app-version-tag.tsx \
     frontend/src/shared/components/layout/app-version-tag.test.tsx \
     frontend/src/shared/components/layout/app-sidebar.tsx
```

---

### Task 6: About dialog + live API version

**Files:**
- Create: `frontend/src/shared/hooks/use-api-version.ts`
- Create: `frontend/src/shared/components/layout/about-dialog.tsx`
- Modify: `frontend/src/shared/components/layout/user-menu.tsx`
- Test: `frontend/src/shared/components/layout/about-dialog.test.tsx`

**Interfaces:**
- Consumes: `useAppConfig()` (UI build info), `customInstance` (`{ url, method, signal }`) and `API`-root resolution from Task 4/existing lib.
- Produces:
  - `useApiVersion()` — TanStack Query hook returning `{ data?: ApiVersionResponse, isLoading, isError }`, querying `GET /version`. `ApiVersionResponse` = generated `VersionResponse` (preferred) or the local interface `{ name, version, git_sha, build_date, environment }`.
  - `<AboutDialog open onOpenChange />` — renders UI + API build info, with loading and "API version unavailable" states.

- [ ] **Step 1: Regenerate the API type (preferred path)**

With the backend running on `:8000` (so `/version`'s `VersionResponse` is in the live OpenAPI):

Run: `cd frontend && pnpm generate:api`
Expected: `frontend/src/shared/lib/api/model/versionResponse.ts` is created and barrel-exported in `model/index.ts`. Review the diff; it should be additive.

> If the backend cannot be brought up in this session, skip regen and use the local `ApiVersionResponse` interface defined in Step 2 instead (a build-info contract, not a domain DTO). Note the deviation in the commit body.

- [ ] **Step 2: Write the `use-api-version` hook**

Create `frontend/src/shared/hooks/use-api-version.ts`:

```ts
"use client";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { useQuery } from "@tanstack/react-query";

/**
 * Build identity reported by the backend `/version` endpoint.
 *
 * Prefer the orval-generated `VersionResponse` once `pnpm generate:api` has
 * run; this local shape is the same contract for environments where the type
 * has not yet been generated.
 */
export interface ApiVersionResponse {
  name: string;
  version: string;
  git_sha: string;
  build_date: string;
  environment: string;
}

/** Fetch the backend build identity. `/version` is a root path (not /api/v1). */
export function useApiVersion(enabled: boolean) {
  return useQuery({
    queryKey: ["api-version"],
    queryFn: ({ signal }) =>
      customInstance<ApiVersionResponse>({ url: "/version", method: "GET", signal }),
    enabled,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
}
```

- [ ] **Step 3: Write the failing About dialog test**

Create `frontend/src/shared/components/layout/about-dialog.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppConfigProvider } from "@/shared/lib/app-config";
import { AboutDialog } from "./about-dialog";

vi.mock("@/shared/hooks/use-api-version", () => ({
  useApiVersion: () => ({
    data: {
      name: "cellar-backend",
      version: "1.4.0",
      git_sha: "1a2b3c4",
      build_date: "2026-06-16",
      environment: "production",
    },
    isLoading: false,
    isError: false,
  }),
}));

function renderDialog() {
  const config = {
    apiUrl: "",
    appUrl: "",
    sentinelUrl: "",
    idpProvider: "google",
    googleClientId: "",
    entraIdClientId: "",
    entraIdTenantId: "",
    uiVersion: "2.1.0",
    uiGitSha: "84e7848",
    uiBuildDate: "2026-06-17",
    environment: "production",
  };
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AppConfigProvider config={config}>
        <AboutDialog open onOpenChange={vi.fn()} />
      </AppConfigProvider>
    </QueryClientProvider>,
  );
}

describe("AboutDialog", () => {
  it("shows UI and API versions", () => {
    renderDialog();
    expect(screen.getByText(/v2\.1\.0/)).toBeInTheDocument(); // UI
    expect(screen.getByText(/v1\.4\.0/)).toBeInTheDocument(); // API
    expect(screen.getByText(/84e7848/)).toBeInTheDocument(); // UI sha
    expect(screen.getByText(/1a2b3c4/)).toBeInTheDocument(); // API sha
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd frontend && pnpm vitest run src/shared/components/layout/about-dialog.test.tsx`
Expected: FAIL — cannot resolve `./about-dialog`.

- [ ] **Step 5: Write the About dialog**

Create `frontend/src/shared/components/layout/about-dialog.tsx`:

```tsx
"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useApiVersion } from "@/shared/hooks/use-api-version";
import { useAppConfig } from "@/shared/lib/app-config";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

export function AboutDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { uiVersion, uiGitSha, uiBuildDate, environment } = useAppConfig();
  const api = useApiVersion(open);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>About Cellar</DialogTitle>
          <DialogDescription>Running build identity.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              UI
            </h3>
            <Row label="Version" value={`v${uiVersion}`} />
            <Row label="Commit" value={uiGitSha} />
            <Row label="Built" value={uiBuildDate} />
          </section>

          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              API
            </h3>
            {api.isLoading ? (
              <p className="text-xs text-muted-foreground">Loading…</p>
            ) : api.isError || !api.data ? (
              <p className="text-xs text-muted-foreground">API version unavailable</p>
            ) : (
              <>
                <Row label="Version" value={`v${api.data.version}`} />
                <Row label="Commit" value={api.data.git_sha} />
                <Row label="Built" value={api.data.build_date} />
              </>
            )}
          </section>

          <Row label="Environment" value={environment} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && pnpm vitest run src/shared/components/layout/about-dialog.test.tsx`
Expected: PASS.

- [ ] **Step 7: Add an "About" entry to the user menu**

In `frontend/src/shared/components/layout/user-menu.tsx`:

1. Add React state + the dialog. Change the import of `lucide-react` icons to include `Info`:

```tsx
import { ChevronsUpDown, Info, LogOut, User } from "lucide-react";
```

2. Add at the top of the file (after the existing imports):

```tsx
import { useState } from "react";
import { AboutDialog } from "./about-dialog";
```

3. Inside `UserMenu`, add state after the existing hooks:

```tsx
  const [aboutOpen, setAboutOpen] = useState(false);
```

4. Add an About menu item — insert before the `<DropdownMenuItem onClick={logout}>` block (keep the surrounding `DropdownMenuSeparator`):

```tsx
            <DropdownMenuItem onClick={() => setAboutOpen(true)}>
              <Info className="mr-2 size-4" />
              About
            </DropdownMenuItem>
            <DropdownMenuSeparator />
```

5. Render the dialog — immediately after the closing `</DropdownMenu>` and before the closing `</SidebarMenuItem>`, add:

```tsx
        <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
```

- [ ] **Step 8: Lint + verify full frontend test run**

Run: `cd frontend && pnpm biome check --write src/shared/hooks/use-api-version.ts src/shared/components/layout/about-dialog.tsx src/shared/components/layout/about-dialog.test.tsx src/shared/components/layout/user-menu.tsx && pnpm lint && pnpm vitest run src/shared/components/layout src/app/api/config`
Expected: lint exit 0; tests pass.

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(version): add About dialog with UI + live API build info

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- frontend/src/shared/hooks/use-api-version.ts \
     frontend/src/shared/components/layout/about-dialog.tsx \
     frontend/src/shared/components/layout/about-dialog.test.tsx \
     frontend/src/shared/components/layout/user-menu.tsx \
     frontend/src/shared/lib/api/model
```

(If `pnpm generate:api` ran in Step 1, the regenerated `model/` files are included by the trailing pathspec; if it did not run, drop that last path.)

---

### Task 7: Rework `publish-images.yml` for per-component tags

**Files:**
- Modify: `.github/workflows/publish-images.yml`

**Interfaces:**
- Consumes: git tags `backend-vX.Y.Z` / `frontend-vX.Y.Z`; Dockerfile build args from Tasks 3 & 4.
- Produces: on a component tag, builds ONLY that component, tags its image `X.Y.Z` / `X.Y` / `X`, and passes `APP_VERSION`/`GIT_SHA`/`BUILD_DATE` build args. Main-branch behaviour (`latest` + `sha-`, path-filtered) is preserved.

- [ ] **Step 1: Update the triggers + `changes` decision**

In `.github/workflows/publish-images.yml`, replace the `on:` block:

```yaml
on:
  push:
    branches: [main]
    tags:
      - 'backend-v*.*.*'
      - 'frontend-v*.*.*'
```

And replace the `decide` step's `run:` script with namespace-aware logic:

```yaml
      - id: decide
        run: |
          if [ "${{ github.ref_type }}" = "tag" ]; then
            case "${{ github.ref_name }}" in
              backend-v*)  echo "backend=true"  >> "$GITHUB_OUTPUT"; echo "frontend=false" >> "$GITHUB_OUTPUT" ;;
              frontend-v*) echo "backend=false" >> "$GITHUB_OUTPUT"; echo "frontend=true"  >> "$GITHUB_OUTPUT" ;;
              *)           echo "backend=false" >> "$GITHUB_OUTPUT"; echo "frontend=false" >> "$GITHUB_OUTPUT" ;;
            esac
          else
            echo "backend=${{ steps.filter.outputs.backend }}" >> "$GITHUB_OUTPUT"
            echo "frontend=${{ steps.filter.outputs.frontend }}" >> "$GITHUB_OUTPUT"
          fi
```

- [ ] **Step 2: Rework the `backend` job — checkout tags, derive version, build args**

Replace the `backend` job's `steps:` with:

```yaml
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0   # full history + tags so `git describe` works on non-tag builds
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: ver
        run: |
          if [ "${{ github.ref_type }}" = "tag" ]; then
            VERSION="${GITHUB_REF_NAME#backend-v}"
          else
            VERSION="$(git describe --tags --match 'backend-v*' --always | sed 's/^backend-v//')"
          fi
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "git_sha=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
          echo "build_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_OUTPUT"
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/sidxz/cellar-backend
          flavor: latest=false
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,prefix=sha-
            type=match,pattern=\d+\.\d+\.\d+,group=0
            type=match,pattern=\d+\.\d+,group=0
            type=match,pattern=\d+,group=0
      - uses: docker/build-push-action@v6
        with:
          context: ./backend
          platforms: linux/amd64
          push: true
          build-args: |
            APP_VERSION=${{ steps.ver.outputs.version }}
            GIT_SHA=${{ steps.ver.outputs.git_sha }}
            BUILD_DATE=${{ steps.ver.outputs.build_date }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha,scope=backend
          cache-to: type=gha,mode=max,scope=backend
```

> Why `type=match,...,group=0`: `docker/metadata-action`'s `type=semver` does not understand the `backend-v` prefix. `type=match` extracts the semver substring from the ref name (`backend-v1.4.0` → `1.4.0`, `1.4`, `1`) and only activates on tag pushes, so main builds keep just `latest` + `sha-`.

- [ ] **Step 3: Rework the `frontend` job identically (with `frontend-v` prefix)**

Replace the `frontend` job's `steps:` with the same shape, swapping `backend`→`frontend` everywhere:

```yaml
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: ver
        run: |
          if [ "${{ github.ref_type }}" = "tag" ]; then
            VERSION="${GITHUB_REF_NAME#frontend-v}"
          else
            VERSION="$(git describe --tags --match 'frontend-v*' --always | sed 's/^frontend-v//')"
          fi
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "git_sha=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
          echo "build_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_OUTPUT"
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/sidxz/cellar-frontend
          flavor: latest=false
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,prefix=sha-
            type=match,pattern=\d+\.\d+\.\d+,group=0
            type=match,pattern=\d+\.\d+,group=0
            type=match,pattern=\d+,group=0
      - uses: docker/build-push-action@v6
        with:
          context: ./frontend
          platforms: linux/amd64
          push: true
          build-args: |
            APP_VERSION=${{ steps.ver.outputs.version }}
            GIT_SHA=${{ steps.ver.outputs.git_sha }}
            BUILD_DATE=${{ steps.ver.outputs.build_date }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha,scope=frontend
          cache-to: type=gha,mode=max,scope=frontend
```

- [ ] **Step 4: Validate the workflow YAML**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/publish-images.yml')); print('valid yaml')"`
Expected: `valid yaml`. (Optionally `actionlint .github/workflows/publish-images.yml` if installed.)

- [ ] **Step 5: Commit**

```bash
git commit -m "ci(version): per-component release tags drive image builds

backend-v* / frontend-v* tags build only their component, tag the image with
the clean semver, and inject build identity via build args.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- .github/workflows/publish-images.yml
```

---

### Task 8: Auto changelog + GitHub Release

**Files:**
- Create: `cliff.toml` (repo root)
- Modify: `.github/workflows/publish-images.yml` (add a `release` job)

**Interfaces:**
- Consumes: the pushed component tag; full git history (`fetch-depth: 0`).
- Produces: a GitHub Release named e.g. "Backend v1.4.0" whose body is the git-cliff changelog of Conventional Commits touching that component's path since the previous same-namespace tag.

- [ ] **Step 1: Add `cliff.toml`**

Create `cliff.toml` at the repo root:

```toml
# git-cliff configuration — Conventional Commits → grouped changelog.
[changelog]
header = ""
body = """
{% for group, commits in commits | group_by(attribute="group") %}
### {{ group | upper_first }}
{% for commit in commits %}
- {{ commit.message | upper_first }}{% if commit.scope %} ({{ commit.scope }}){% endif %}\
{% endfor %}
{% endfor %}
"""
trim = true

[git]
conventional_commits = true
filter_unconventional = true
commit_parsers = [
  { message = "^feat", group = "Features" },
  { message = "^fix", group = "Bug Fixes" },
  { message = "^perf", group = "Performance" },
  { message = "^refactor", group = "Refactor" },
  { message = "^docs", group = "Documentation" },
  { message = "^test", group = "Tests" },
  { message = "^ci|^build", group = "Build & CI" },
  { message = "^chore", skip = true },
  { message = "^style", skip = true },
]
filter_commits = false
tag_pattern = "(backend|frontend)-v[0-9]*"
```

- [ ] **Step 2: Add the `release` job to the workflow**

In `.github/workflows/publish-images.yml`, append a `release` job after the `frontend` job:

```yaml
  release:
    name: Publish GitHub Release
    needs: [backend, frontend]
    if: ${{ always() && github.ref_type == 'tag' && (needs.backend.result == 'success' || needs.frontend.result == 'success') }}
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0
      - id: range
        run: |
          NS="${GITHUB_REF_NAME%%-v*}"                       # backend | frontend
          PREV="$(git tag --list "${NS}-v*" --sort=-creatordate | sed -n '2p')"
          if [ -n "$PREV" ]; then
            echo "range=${PREV}..${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"
          else
            echo "range=${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"
          fi
          echo "path=${NS}/**" >> "$GITHUB_OUTPUT"
          # Title-case the namespace: "backend" -> "Backend".
          TITLE="$(printf '%s' "$NS" | sed 's/^./\U&/') ${GITHUB_REF_NAME#${NS}-}"
          echo "title=${TITLE}" >> "$GITHUB_OUTPUT"
      - uses: orhun/git-cliff-action@v4
        id: cliff
        with:
          config: cliff.toml
          args: --include-path "${{ steps.range.outputs.path }}" ${{ steps.range.outputs.range }}
        env:
          OUTPUT: CHANGES.md
      - uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          name: ${{ steps.range.outputs.title }}
          body_path: ${{ steps.cliff.outputs.changelog }}
```

> `--include-path "<component>/**"` scopes the changelog to commits that touched that component; the `PREV..CURRENT` range scopes to the new tag's commits since the previous same-namespace tag.

- [ ] **Step 3: Validate the workflow YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/publish-images.yml')); print('valid yaml')"`
Expected: `valid yaml`.

- [ ] **Step 4: Commit**

```bash
git commit -m "ci(version): generate changelog + GitHub Release on component tag

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- cliff.toml .github/workflows/publish-images.yml
```

---

### Task 9: `RELEASING.md` process doc

**Files:**
- Create: `RELEASING.md` (repo root — tracked; `docs/` is gitignored)

**Interfaces:** none (human-facing).

- [ ] **Step 1: Write `RELEASING.md`**

Create `RELEASING.md` at the repo root:

```markdown
# Releasing Cellar

The frontend and backend are versioned **independently** with **SemVer**, and
the **git tag is the single source of truth**. CI builds the image, injects the
version, and publishes a changelog + GitHub Release.

## Tag namespaces

| Component | Tag form          | Image                              |
|-----------|-------------------|------------------------------------|
| Backend   | `backend-vX.Y.Z`  | `ghcr.io/sidxz/cellar-backend:X.Y.Z` |
| Frontend  | `frontend-vX.Y.Z` | `ghcr.io/sidxz/cellar-frontend:X.Y.Z` |

Pushing a tag in one namespace builds, tags, and releases **only** that
component. Pushes to `main` still publish `:latest` and `:sha-<sha>` images for
whichever component changed.

## Choosing the bump (Conventional Commits)

Look at the commits since the component's previous tag:

| Commit type                         | Bump   |
|-------------------------------------|--------|
| `fix:`                              | patch  |
| `feat:`                             | minor  |
| `feat!:` / `BREAKING CHANGE:` footer | major  |

A backend **major** bump signals a breaking API change — the moment to check the
frontend is compatible.

## Cutting a release

1. Make sure `main` is green and pulled locally.
2. Pick the next version per the table above. Inspect what changed:
   ```bash
   # commits touching the backend since its last tag
   git log "$(git tag --list 'backend-v*' --sort=-creatordate | head -1)"..HEAD -- backend/
   ```
3. Tag and push:
   ```bash
   git tag backend-v1.4.0      # or frontend-v2.1.0
   git push origin backend-v1.4.0
   ```
4. CI (`.github/workflows/publish-images.yml`) then:
   - builds **only** that component and tags the image `1.4.0`, `1.4`, `1`;
   - injects `APP_VERSION` / `GIT_SHA` / `BUILD_DATE` into the image;
   - generates a `git-cliff` changelog scoped to that component since its
     previous tag and publishes a **GitHub Release** ("Backend v1.4.0").

## Where the version shows up

- **App footer:** `UI v<version>` (sidebar), from the baked image.
- **About dialog** (user menu → About): UI version + commit + build date, the
  live **API** version (fetched from `GET /version`), and the environment.
- **Backend `GET /version`:** unauthenticated JSON
  `{name, version, git_sha, build_date, environment}` — handy for `curl`/monitoring.

## Between releases

Builds between tags identify as the `git describe` form, e.g.
`1.4.0-128-g84e7848` — base tag, commits ahead, short sha. That is expected and
honest: it is not a clean release.

## Not the source of truth

`backend/pyproject.toml` and `frontend/package.json` carry a placeholder version
used only as a local-dev fallback. **Do not** treat them as authoritative — the
git tag is. There is nothing to bump in those files when releasing.
```

- [ ] **Step 2: Commit**

```bash
git commit -m "docs(version): add RELEASING.md describing the versioning scheme

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" \
  -- RELEASING.md
```

---

## Self-Review

**Spec coverage:**
- Independent per-component SemVer → Tasks 7, 9 (tag namespaces) ✅
- Single source of truth = git tag + build injection → Tasks 1, 3, 4, 7 ✅
- Backend `version.py` + `/version` (auth-excluded) → Tasks 1, 2 ✅
- FastAPI hardcoded `0.1.0` removed → Task 2 Step 4 ✅
- Frontend baking via `/api/config` (not NEXT_PUBLIC) → Task 4 ✅
- Footer tag → Task 5 ✅
- About dialog (UI + live API + env, failure state) → Task 6 ✅
- Per-component changelog + GitHub Release → Task 8 ✅
- `RELEASING.md` at root → Task 9 ✅
- Honor orval rule (`response_model` + regen) → Task 2 (model) + Task 6 Step 1 ✅
- Non-goals (no compat gate, no release-please, no CalVer) → not implemented ✅

**Type consistency:** `BuildInfo`/`build_info()` (Task 1) consumed in Tasks 2 & 3 unchanged; `VersionResponse` fields (Task 2) match `ApiVersionResponse` (Task 6) and the About test; `AppConfig` fields added in Task 4 are consumed by name in Tasks 5 & 6; `useApiVersion(enabled)` signature defined in Task 6 Step 2 matches its call in the dialog.

**Placeholder scan:** No TBD/TODO; every code step shows complete content.
