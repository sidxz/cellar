# App Chrome Harmonization (docustore parity) — Design

**Date:** 2026-07-16
**Status:** Approved (user, this session)
**Scope:** frontend only — no backend changes.

## Goal

Harmonize Cellar's app chrome (user identity, logout, settings, appearance
preferences, brand mark) with docu-store's layout. This is the chrome pattern
all our apps will adopt. Reference implementation:
`~/workspace/docu-store/web/apps/portal` (`Topbar.tsx`, `Sidebar.tsx`,
`settings/general/page.tsx`, `FontSizeControl.tsx`, `font-scale-store.ts`).

## Decisions (user-confirmed)

1. **Exact docustore user chrome** — static avatar + name/email in the topbar
   right with a standalone logout icon button. No user dropdown anywhere.
2. **New `/settings` page** reached by a gear item at the sidebar bottom.
   Existing `/admin/*` pages stay untouched (no migration, no tab shell yet).
3. **Full topbar parity** — port docustore's font-size slider (A—●—A).
4. **New hex-lens logo** (`docs/branding/hex-lens-logo.svg`) replaces
   `FlaskConical` as the brand mark (sidebar tile, login page, favicon).
   Gradient stays DocuStore-spectrum until a chem-vault identity exists
   (per the note embedded in the SVG).

## Design

### 1. Topbar — `src/shared/components/layout/header.tsx`

Right cluster, in docustore order:

```
[breadcrumbs] ....... [Search ⌘K] [A—●—A] [☀/☾] │ (SR) Name          [⇥]
                                                       email
```

- Remove `<FontToggle />` (family choice moves to `/settings`).
- Remove the inert Bell button (no handler, no feature behind it).
- Wire the Search button to open the existing global ⌘K command palette
  (currently decorative). Mechanism decided in the plan after reading
  `command-palette.tsx` — either an exported open-state store or dispatching
  the palette's existing toggle.
- Add `FontSizeControl` (ported, see §4) left of the theme toggle.
- Add a vertical `Separator`, then the user block: shadcn `Avatar` with
  initials (same `getInitials` logic as today's user-menu), name + email
  stacked beside it (`hidden sm:flex`), purely informational — not a button.
- Add a standalone logout ghost icon button (`LogOut` icon, tooltip
  "Sign out") calling `useAuthz().logout` — identical behavior to today's
  "Sign out" menu item (no manual redirect; the SDK handles it as today).
- Keep Cellar's dense `h-10` header — we match docustore's *placement*, not
  its 56 px height.

### 2. Sidebar — `src/shared/components/layout/app-sidebar.tsx`

- `SidebarFooter`: remove `<UserMenu />`.
- Add a **⚙ Settings** item above the version row, linking to `/settings`
  (docustore's gear-at-bottom pattern). Must behave correctly when the
  sidebar is icon-collapsed (icon-only, tooltip), like `NavMain` items.
- Version + collapse-trigger row unchanged.
- **Delete** `user-menu.tsx`.

### 3. Settings page — `src/app/(dashboard)/settings/page.tsx` (new)

Single page, two cards (no tab shell — add tabs when a second section
exists):

- **Appearance card**
  - *Theme*: Light/Dark toggle group, same next-themes + preferences-store
    mirroring logic as `theme-toggle.tsx` (which stays in the topbar; the two
    controls share state via next-themes).
  - *Font family*: IBM Plex / Inter toggle group backed by the existing
    `font-family-store` (`ds-font` key). **Delete** `font-toggle.tsx`; its
    logic moves here.
- **About card** — inline the current About dialog's content: UI
  version/commit/built from `useAppConfig()`, API version/commit/built from
  `useApiVersion()` (fetch on mount now that there's no dialog-open gate),
  environment row. Shows the hex-lens logo next to the "About Cellar"
  heading. **Delete** `about-dialog.tsx`.
- Breadcrumb/nav: `/settings` gets a proper label in whatever drives
  `Breadcrumbs` (checked in plan — `src/shared/lib/navigation.ts`).

### 4. Font-size slider (ported from docustore)

- `src/shared/lib/stores/font-scale-store.ts` — port of docustore's store:
  zustand + persist, key `ds-font-scale`, range 80–120 step 5, default 100,
  clamped setter, `reset()`. Drop the `trackEvent` analytics call (Cellar has
  no analytics layer).
- `src/shared/components/layout/font-size-control.tsx` — port of
  `FontSizeControl.tsx`, re-tokened to Cellar's Tailwind vocabulary
  (`text-muted-foreground` etc.). shadcn `Slider`/`Tooltip` already exist.
- **Applying the scale:** extend `src/shared/providers/font-family-provider.tsx`
  to also subscribe to the scale store and set
  `document.documentElement.style.fontSize = scale === 100 ? "" : scale + "%"`.
  Everything is rem-based, so the whole UI scales.
- **Anti-flash:** extend the existing inline script in `src/app/layout.tsx`
  (currently reads `ds-font`) to also read `ds-font-scale` and set the root
  font-size before paint.

### 5. Hex-lens logo

Source: `docs/branding/hex-lens-logo.svg` (32-grid, strokes 2.4/3.2, crisp
at 16/26/48/128 px).

- `src/shared/components/hex-lens-logo.tsx` (new) — the SVG as a React
  component. Gradient lens as delivered; the handle's hardcoded `#0b0b0d`
  becomes `stroke="currentColor"` so it adapts to theme. Size via
  `className` (defaults sensible for the tile). The `<linearGradient>` id
  must be collision-safe if the mark renders more than once per page (use
  `useId`).
- **Workspace-switcher tile** (`workspace-switcher.tsx`): logo replaces
  `FlaskConical` in the brand tile. Per-workspace dropdown items keep
  `FlaskConical` (they denote workspaces, not the brand).
- **Login page** (`src/app/login/page.tsx`): logo added to the top-right
  branding block beside the "Cellar" heading.
- **Favicon**: new `src/app/icon.svg` (Next.js file-convention favicon —
  none exists today). Same art plus a small `prefers-color-scheme` style so
  the handle is visible on dark browser tabs.

## Files

| Action | Path |
|---|---|
| modify | `src/shared/components/layout/header.tsx` |
| modify | `src/shared/components/layout/app-sidebar.tsx` |
| modify | `src/shared/components/layout/workspace-switcher.tsx` |
| modify | `src/shared/providers/font-family-provider.tsx` |
| modify | `src/app/layout.tsx` (anti-flash script) |
| modify | `src/app/login/page.tsx` |
| modify | `src/shared/lib/navigation.ts` (breadcrumb label for /settings, if needed) |
| new | `src/app/(dashboard)/settings/page.tsx` |
| new | `src/shared/lib/stores/font-scale-store.ts` |
| new | `src/shared/components/layout/font-size-control.tsx` |
| new | `src/shared/components/hex-lens-logo.tsx` |
| new | `src/app/icon.svg` |
| delete | `src/shared/components/layout/user-menu.tsx` |
| delete | `src/shared/components/layout/about-dialog.tsx` |
| delete | `src/shared/components/font-toggle.tsx` |

## Error handling / edge cases

- No user loaded (auth race): avatar falls back to "?" initials, name falls
  back to "User" — same as today's user-menu.
- API version fetch fails on settings page: "API version unavailable" row,
  as the dialog does today.
- Icon-collapsed sidebar: Settings gear shows icon + tooltip; version tag
  already hides itself.
- Font scale localStorage corrupt: anti-flash script try/catches to default,
  store's persist merge handles the rest (same pattern as `ds-font`).

## Testing

- Update/replace any unit tests referencing `user-menu`, `font-toggle`,
  `about-dialog` (inventory taken during planning).
- New minimal tests: font-scale store clamping; settings page renders both
  cards; header renders logout + user identity.
- Manual verify (run app): topbar layout light+dark, slider scales UI and
  persists across reload without flash, settings page controls work, logout
  works, favicon renders, login page brand block.

## Out of scope

- Recoloring the logo gradient (waits for chem-vault brand identity).
- Settings tab shell / migrating `/admin/*` pages.
- Notifications (Bell removed, feature never existed).
- docu-store repo changes (it's the reference, not a target).
