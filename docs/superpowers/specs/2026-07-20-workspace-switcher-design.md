# Workspace Switcher & Login Continuity — Design

**Date:** 2026-07-20
**Status:** Implemented (2026-07-20, chrome-harmonization branch)
**Scope:** Frontend only. No backend changes, no new dependencies.

## Problem

Cellar has no way to switch workspaces. The previous sidebar switcher was removed on
`chrome-harmonization` (commit `1b7eddb5`) because it was dead on arrival: it read the
IdP token from localStorage, but the Sentinel authz-mode SDK keeps that token
memory-only, so the switcher could never list workspaces nor re-mint a token.
Separately, multi-workspace users see the workspace picker on every interactive login,
even when they always work in the same workspace.

daikon-gen3 solves both on the same Sentinel SDK (`@duar-auth/*` 0.15.0, dual-token
authz mode). We adopt its pattern unchanged.

## What we adopt — and what we deliberately don't

Adopted (daikon parity):

1. **Last-workspace memory** — an app-owned localStorage key that survives logout and
   auto-skips the login picker while it points at a workspace the user can still access.
2. **"Switch workspace" affordance** — a user-menu item that clears that memory and logs
   out; the next login shows the picker again.

**Out of scope: an in-place switcher** (re-mint without logout). It is technically
possible via SDK `resolve()` / `selectWorkspace()`, but the IdP token required to list
workspaces is short-lived and memory-only (the switcher would routinely hit a dead token
and need a reauth dance), and a mid-session re-mint swaps the authz token in
localStorage under other open tabs, which would then silently query the new workspace
while rendering the old one's UI. Daikon chose the logout round-trip for these reasons;
so do we. Recorded here so nobody re-attempts the dead switcher's approach.

**Refresh continuity needs no work.** The SDK persists the workspace-scoped authz token
(`sentinel_authz_token`, claims `wid`/`wslug`) plus `sentinel_workspace_id`; on refresh,
silent reauth re-mints into the same workspace. This already works in Cellar today.

## Design

### 1. Workspace memory helper (new file)

`frontend/src/shared/lib/auth/workspace-memory.ts` (~15 lines):

- Key: `cellar.lastWorkspaceId`
- `rememberedWorkspace(): string | null`, `rememberWorkspace(id: string)`,
  `forgetWorkspace()` — each with try/catch around localStorage access.
- Why not reuse the SDK's `sentinel_workspace_id`: `logout()` wipes it, so it cannot
  carry continuity across login cycles. Surviving logout is the entire feature, and
  "Switch workspace" deletes the key deliberately.
- The memory is per-browser, not per-user: on a shared machine, the next person to sign
  in auto-enters the previous user's remembered workspace if they are also a member of
  it (the mint always runs against the signer-in's own membership, so this is authorized
  by design). Accepted — daikon parity.

### 2. Callback picker guard

`frontend/src/app/auth/callback/page.tsx`: extract the inline `workspaceSelector`
render prop into a `WorkspaceSelector` component in the same file.

- On mount (`useEffect`, fires once): if `rememberedWorkspace()` is in the returned
  workspace list → auto-`onSelect(remembered)` and render a brief
  "Entering *{workspace name}*…" state instead of the button list. Otherwise → render
  the picker exactly as today.
- Manual pick: `rememberWorkspace(id)` then `onSelect(id)`.
- If the auto-selected mint fails, the existing `AuthzCallback` `onError` path
  (redirect to `/login?error=…`) applies unchanged.

### 3. Header user menu

`frontend/src/shared/components/layout/header.tsx`: the avatar + name/email cluster
becomes the trigger of a shadcn `DropdownMenu` (component already in repo), with a
chevron affordance:

- Menu label: user name + email
- Separator
- **Switch workspace** → `forgetWorkspace(); logout();`
- **Sign out** → `logout()`
- The standalone sign-out icon button is removed (absorbed into the menu).

## Flows

- **Refresh:** unchanged — SDK-persisted authz token; silent reauth re-mints the same
  workspace.
- **Login:** Google → `/auth/callback` → SDK resolves workspace list → remembered
  workspace still valid? auto-enter it : show picker → pick (remembered) → mint → app.
- **Switch:** menu item → forget memory + SDK logout (clears `sentinel_*` keys;
  BroadcastChannel logs out other tabs, so no stale-tab data mixing) → `/login` →
  Google (instant if IdP session live) → picker (memory gone) → pick → remember +
  mint → app.

## Testing

- Vitest component test for the `WorkspaceSelector` guard: auto-select fires when the
  remembered workspace is in the list; picker renders when it is stale/absent; a manual
  pick calls `rememberWorkspace`. (jsdom localStorage polyfill already exists in
  `vitest.setup.ts`.)
- Runtime verification via the repo `verify` skill (mock-auth E2E recipe): login lands
  in the remembered workspace; "Switch workspace" produces the picker.

## Files touched

- **New:** `frontend/src/shared/lib/auth/workspace-memory.ts`
- **New:** `frontend/src/app/auth/callback/workspace-selector.tsx` (guard extracted to its
  own file — not inline in `page.tsx` as originally written — so the component test can
  import it without pulling the whole page)
- **New:** `frontend/src/app/auth/callback/workspace-selector.test.tsx`
- `frontend/src/app/auth/callback/page.tsx`
- `frontend/src/shared/components/layout/header.tsx`
- `frontend/src/shared/components/layout/header.test.tsx` (updated to the menu structure)
