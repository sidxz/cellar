---
name: verify
description: Runtime verification recipe for Cellar — launch backend+frontend, drive the UI headlessly past Sentinel auth with mocked IdP endpoints
---

# Verifying Cellar frontend changes end-to-end

## Launch

Infra (postgres/valkey/temporal/infisical) usually already up (`docker ps | grep chem-vault2`); else `make up` from repo root.

- Backend: `make dev-be` → :8000 (logs: `.logs/backend.log`). MUST go through make so root `.env` exports `SENTINEL_SERVICE_KEY`.
- Frontend: `make dev-fe` → :3000 (Next dev, hot-reloads the working tree — no restart needed after edits).
- Check first: `curl -s localhost:8000/version` and `curl -s -o /dev/null -w '%{http_code}' localhost:3000` — servers are often already running; don't restart the user's servers.

## Driving the authed UI headlessly (no real Google login needed)

Auth is client-side (Sentinel AuthZ, tokens in localStorage; middleware.ts does NOT gate). `authState === "authenticated"` needs an unexpired `sentinel_authz_token` in localStorage AND a memory-only IdP token — so you cannot fake it by localStorage injection alone. Instead intercept the three auth hops in Playwright and let the real login flow run:

1. `**accounts.google.com/o/oauth2/**` → 302 to `<redirect_uri>#id_token=<crafted JWT>`. The JWT payload MUST echo the `nonce` query param; include `email`, `name`, `exp`.
2. `**/authz/resolve` (remote Sentinel) → `{ workspaces: [{ id, name, slug, role }] }`. Exactly one workspace ⇒ SDK auto-selects (no picker).
3. `**/api/auth/mint` (same-origin Next route) → `{ authz_token: <crafted JWT with sub, wid, wslug, wrole, exp>, user: { email, name } }`.

Crafted JWT = base64url(header).base64url(claims).base64url(anything) — client only decodes payload + checks `exp`. Then goto `/login`, click "Continue with Google", waitForURL `/`. Backend API calls will 401 with crafted tokens, but `/version` and `/api/config` are public (About card + app config work).

Working harness from 2026-07-16 (adapt selectors): `verify-chrome.mjs` in that session's scratchpad; key selectors below.

## Playwright setup

No playwright in the repo (frontend/tests/e2e is all .TODO stubs). Use `npm i playwright-core` in scratchpad + cached browser:
`executablePath: ~/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`

## Gotchas that cost time

- Theme: next-themes is `attribute="data-theme"` (NOT class). Assert `documentElement.getAttribute("data-theme")`, and waitForFunction — the attribute applies async after click. Default theme is **dark**.
- Radix Slider: keyboard events go to the thumb `[role="slider"]`, not the root that carries `aria-label`.
- shadcn Avatar: wrapper + fallback are both `<span>`s with the same text — text locators count 2, use `>= 1`.
- Font family: asserts via `documentElement.getAttribute("data-font")` (`plex`/`inter`, persisted in `ds-font`).
- Font scale: root inline `style.fontSize` (`""` at 100%), persisted in `ds-font-scale`.
- Shell is fish: `echo ===` breaks; use `echo ---`.
