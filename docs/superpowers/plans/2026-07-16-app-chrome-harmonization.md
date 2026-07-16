# App Chrome Harmonization (docustore parity + hex-lens logo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Match Cellar's app chrome to docu-store: static avatar + standalone logout in the topbar, gear-to-`/settings` in the sidebar, font family moved off the topbar into Settings, ported font-size slider, hex-lens logo everywhere the brand shows.

**Architecture:** Frontend-only. Chrome components live in `src/shared/components/layout/`; per-user preferences are zustand persist stores (`ds-*` localStorage keys) applied by `FontFamilyProvider` plus an anti-flash inline script in the root layout. Spec: `docs/superpowers/specs/2026-07-16-app-chrome-harmonization-design.md`.

**Tech Stack:** Next.js 16 App Router, React 19, shadcn/ui (Avatar, Button, Card, Separator, Slider, Tooltip, Sidebar), zustand + persist, next-themes, `@sentinel-auth/nextjs`, vitest + testing-library, biome.

## Global Constraints

- All commands run from `frontend/`; package manager is `pnpm`.
- Verify `pnpm lint` (biome) by **exit code**, never by piped output (format errors gate at error severity while lint rules warn).
- Commit with explicit pathspecs (`git commit -m "..." -- <paths>`) — the working tree may hold unrelated user work. Never `git add -A` / `git add .`.
- Test files are colocated next to their source (see `about-dialog.test.tsx` precedent).
- localStorage keys: font family `ds-font` (exists), font scale `ds-font-scale` (new) — anti-flash script and stores must agree.
- Do NOT bump `package.json` version (releases come from git tags).
- No new dependencies.

---

### Task 1: Hex-lens logo component, brand adoption, favicon

**Files:**
- Create: `src/shared/components/hex-lens-logo.tsx`
- Create: `src/shared/components/hex-lens-logo.test.tsx`
- Create: `src/app/icon.svg`
- Modify: `src/shared/components/layout/workspace-switcher.tsx` (brand tile, ~line 92-94)
- Modify: `src/app/login/page.tsx` (branding block, ~line 66)

**Interfaces:**
- Produces: `HexLensLogo({ className }: { className?: string })` — exported from `@/shared/components/hex-lens-logo`. Task 3 renders it on the settings page.

- [ ] **Step 1: Write the failing test**

`src/shared/components/hex-lens-logo.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HexLensLogo } from "./hex-lens-logo";

describe("HexLensLogo", () => {
  it("renders the handle with currentColor so it adapts to theme", () => {
    const { container } = render(<HexLensLogo />);
    expect(container.querySelector("line")?.getAttribute("stroke")).toBe("currentColor");
  });

  it("gives each instance a unique gradient id (no collisions when rendered twice)", () => {
    const { container } = render(
      <>
        <HexLensLogo />
        <HexLensLogo />
      </>,
    );
    const ids = Array.from(container.querySelectorAll("linearGradient")).map((g) => g.id);
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/shared/components/hex-lens-logo.test.tsx`
Expected: FAIL — cannot resolve `./hex-lens-logo`.

- [ ] **Step 3: Implement the component**

`src/shared/components/hex-lens-logo.tsx` — art from `docs/branding/hex-lens-logo.svg` (repo root). Per the note embedded in that SVG, the gradient stays DocuStore-spectrum until a chem-vault identity exists; the handle's hardcoded `#0b0b0d` becomes `currentColor` (it would vanish on dark backgrounds):

```tsx
import { useId } from "react";

/** Brand mark — magnifier whose lens is a benzene ring: chemical search.
 *  Source art: docs/branding/hex-lens-logo.svg (32 grid, crisp at 16-128px).
 *  Handle uses currentColor to adapt to theme; gradient is still DocuStore's
 *  spectrum palette — re-color when a chem-vault identity exists. */
export function HexLensLogo({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <linearGradient
          id={id}
          gradientUnits="userSpaceOnUse"
          x1="7.5"
          y1="21.5"
          x2="20.5"
          y2="6.5"
        >
          <stop offset="0" stopColor="#37d7fa" />
          <stop offset="0.4" stopColor="#4b72fe" />
          <stop offset="0.68" stopColor="#ff8df2" />
          <stop offset="1" stopColor="#ff8705" />
        </linearGradient>
      </defs>
      <polygon
        points="14,6.5 20.5,10.25 20.5,17.75 14,21.5 7.5,17.75 7.5,10.25"
        fill="none"
        stroke={`url(#${id})`}
        strokeWidth="2.4"
      />
      <line x1="20.3" y1="17.55" x2="26.1" y2="23.35" stroke="currentColor" strokeWidth="3.2" />
    </svg>
  );
}
```

(No `"use client"` — `useId` is RSC-safe; consumers are client components anyway.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/shared/components/hex-lens-logo.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Favicon**

Create `src/app/icon.svg` (Next.js file-convention favicon — none exists today). Same art with a `prefers-color-scheme` guard for the handle:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <style>
    .handle { stroke: #0b0b0d; }
    @media (prefers-color-scheme: dark) { .handle { stroke: #e7e7ea; } }
  </style>
  <defs>
    <linearGradient id="lens" gradientUnits="userSpaceOnUse" x1="7.5" y1="21.5" x2="20.5" y2="6.5">
      <stop offset="0" stop-color="#37d7fa"/>
      <stop offset="0.4" stop-color="#4b72fe"/>
      <stop offset="0.68" stop-color="#ff8df2"/>
      <stop offset="1" stop-color="#ff8705"/>
    </linearGradient>
  </defs>
  <polygon points="14,6.5 20.5,10.25 20.5,17.75 14,21.5 7.5,17.75 7.5,10.25" fill="none" stroke="url(#lens)" stroke-width="2.4"/>
  <line class="handle" x1="20.3" y1="17.55" x2="26.1" y2="23.35" stroke-width="3.2"/>
</svg>
```

- [ ] **Step 6: Brand tile in workspace switcher**

In `src/shared/components/layout/workspace-switcher.tsx`:
- Add import: `import { HexLensLogo } from "@/shared/components/hex-lens-logo";`
- In the trigger tile (~line 92), replace `<FlaskConical className="size-4" />` with `<HexLensLogo className="size-5" />`. The tile keeps `bg-sidebar-primary text-sidebar-primary-foreground` — `currentColor` gives the handle the foreground color.
- Leave the per-workspace `FlaskConical` items in the dropdown untouched (they denote workspaces, not the brand). `FlaskConical` stays imported.

- [ ] **Step 7: Login page branding**

In `src/app/login/page.tsx`, inside the top-right branding `<div>` (~line 62-75), wrap the `<h1>` with the logo:

```tsx
<div className="flex items-center gap-2">
  <HexLensLogo className="size-6" />
  <h1 className="text-lg font-semibold tracking-tight">Cellar</h1>
</div>
```

(The parent column is `items-end`, so the chemcellar.com link stays right-aligned beneath.)
Add the import: `import { HexLensLogo } from "@/shared/components/hex-lens-logo";`

- [ ] **Step 8: Lint + full test sweep**

Run: `pnpm lint && pnpm test` — both must exit 0.

- [ ] **Step 9: Commit**

```bash
git add src/shared/components/hex-lens-logo.tsx src/shared/components/hex-lens-logo.test.tsx src/app/icon.svg
git commit -m "feat(frontend): adopt hex-lens logo (brand tile, login, favicon)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- src/shared/components/hex-lens-logo.tsx src/shared/components/hex-lens-logo.test.tsx src/app/icon.svg src/shared/components/layout/workspace-switcher.tsx src/app/login/page.tsx
```

---

### Task 2: Font-scale store, slider control, apply + anti-flash

**Files:**
- Create: `src/shared/lib/stores/font-scale-store.ts`
- Create: `src/shared/lib/stores/font-scale-store.test.ts`
- Create: `src/shared/components/layout/font-size-control.tsx`
- Modify: `src/shared/providers/font-family-provider.tsx`
- Modify: `src/app/layout.tsx` (anti-flash script, line 45)

**Interfaces:**
- Produces: `useFontScaleStore` (state `{ scale: number; setScale(n): void; reset(): void }`) and constants `FONT_SCALE_MIN/MAX/STEP/DEFAULT` from `@/shared/lib/stores/font-scale-store`; `FontSizeControl()` component from `@/shared/components/layout/font-size-control` (Task 4 puts it in the header).

- [ ] **Step 1: Write the failing store test**

`src/shared/lib/stores/font-scale-store.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";

import { FONT_SCALE_DEFAULT, useFontScaleStore } from "./font-scale-store";

describe("font-scale-store", () => {
  beforeEach(() => {
    useFontScaleStore.getState().reset();
  });

  it("clamps setScale to the 80-120 range", () => {
    useFontScaleStore.getState().setScale(300);
    expect(useFontScaleStore.getState().scale).toBe(120);
    useFontScaleStore.getState().setScale(10);
    expect(useFontScaleStore.getState().scale).toBe(80);
  });

  it("accepts in-range values and resets to default", () => {
    useFontScaleStore.getState().setScale(110);
    expect(useFontScaleStore.getState().scale).toBe(110);
    useFontScaleStore.getState().reset();
    expect(useFontScaleStore.getState().scale).toBe(FONT_SCALE_DEFAULT);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/shared/lib/stores/font-scale-store.test.ts`
Expected: FAIL — cannot resolve `./font-scale-store`.

- [ ] **Step 3: Implement the store**

`src/shared/lib/stores/font-scale-store.ts` (port of docustore's `font-scale-store.ts` minus its analytics call):

```ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

// localStorage key — must match the key read by the inline anti-flash script
// in app/layout.tsx, which runs before React hydrates.
const STORAGE_KEY = "ds-font-scale";

// Percent of the browser's default font-size (100 = browser default). Relative
// (not absolute px) so a user who raised their browser font-size for
// accessibility keeps that baseline; this scales on top of it.
export const FONT_SCALE_MIN = 80;
export const FONT_SCALE_MAX = 120;
export const FONT_SCALE_STEP = 5;
export const FONT_SCALE_DEFAULT = 100;

interface FontScaleState {
  scale: number;
  setScale: (scale: number) => void;
  reset: () => void;
}

export const useFontScaleStore = create<FontScaleState>()(
  persist(
    (set) => ({
      scale: FONT_SCALE_DEFAULT,
      setScale: (scale) =>
        set({ scale: Math.min(FONT_SCALE_MAX, Math.max(FONT_SCALE_MIN, scale)) }),
      reset: () => set({ scale: FONT_SCALE_DEFAULT }),
    }),
    { name: STORAGE_KEY },
  ),
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/shared/lib/stores/font-scale-store.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Slider control**

`src/shared/components/layout/font-size-control.tsx` (port of docustore's `FontSizeControl.tsx`, re-tokened to Cellar's Tailwind vocabulary; Cellar's `Tooltip` wrapper does NOT embed a provider, so wrap one here):

```tsx
"use client";

import { RotateCcw } from "lucide-react";

import { Slider } from "@/shared/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/shared/components/ui/tooltip";
import {
  FONT_SCALE_DEFAULT,
  FONT_SCALE_MAX,
  FONT_SCALE_MIN,
  FONT_SCALE_STEP,
  useFontScaleStore,
} from "@/shared/lib/stores/font-scale-store";

/** Global text-size slider — sets the root font-size (percent of browser
 *  default); every rem-based utility scales off it. Sits next to the theme
 *  toggle in the top bar. */
export function FontSizeControl() {
  const scale = useFontScaleStore((s) => s.scale);
  const setScale = useFontScaleStore((s) => s.setScale);
  const reset = useFontScaleStore((s) => s.reset);
  const isDefault = scale === FONT_SCALE_DEFAULT;

  return (
    <TooltipProvider delayDuration={300}>
      <div className="hidden items-center gap-1.5 px-1 lg:flex">
        <span aria-hidden className="text-xs font-semibold text-muted-foreground">
          A
        </span>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center">
              <Slider
                value={[scale]}
                min={FONT_SCALE_MIN}
                max={FONT_SCALE_MAX}
                step={FONT_SCALE_STEP}
                onValueChange={([v]) => setScale(v)}
                onDoubleClick={reset}
                aria-label="Text size"
                className="w-16"
              />
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom">
            Text size {scale}%{isDefault ? "" : " · double-click to reset"}
          </TooltipContent>
        </Tooltip>
        <span aria-hidden className="text-base font-semibold text-muted-foreground">
          A
        </span>
        {!isDefault && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={reset}
                aria-label="Reset text size to 100%"
                className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
              >
                <RotateCcw className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Reset to 100%</TooltipContent>
          </Tooltip>
        )}
      </div>
    </TooltipProvider>
  );
}
```

- [ ] **Step 6: Apply the scale (provider)**

`src/shared/providers/font-family-provider.tsx` — add a second effect (full file after change):

```tsx
"use client";
import { useFontFamilyStore } from "@/shared/lib/stores/font-family-store";
import { FONT_SCALE_DEFAULT, useFontScaleStore } from "@/shared/lib/stores/font-scale-store";
import { type ReactNode, useEffect } from "react";

export function FontFamilyProvider({ children }: { children: ReactNode }) {
  const font = useFontFamilyStore((s) => s.font);
  const scale = useFontScaleStore((s) => s.scale);
  useEffect(() => {
    document.documentElement.setAttribute("data-font", font);
  }, [font]);
  useEffect(() => {
    // Empty string removes the inline style at the 100% default so the
    // browser/user-agent baseline stays in charge.
    document.documentElement.style.fontSize = scale === FONT_SCALE_DEFAULT ? "" : `${scale}%`;
  }, [scale]);
  return <>{children}</>;
}
```

- [ ] **Step 7: Anti-flash script**

In `src/app/layout.tsx` line 45, replace the `__html` string with (one string, `ds-font` part unchanged, `ds-font-scale` read appended):

```js
(function(){try{var g=JSON.parse(localStorage.getItem('ds-font')||'{}');document.documentElement.setAttribute('data-font',(g.state&&g.state.font)||'plex')}catch(e){document.documentElement.setAttribute('data-font','plex')}try{var s=JSON.parse(localStorage.getItem('ds-font-scale')||'{}');var sc=s.state&&s.state.scale;if(sc&&sc!==100){document.documentElement.style.fontSize=sc+'%'}}catch(e){}})()
```

- [ ] **Step 8: Lint + full test sweep**

Run: `pnpm lint && pnpm test` — both must exit 0.

- [ ] **Step 9: Commit**

```bash
git add src/shared/lib/stores/font-scale-store.ts src/shared/lib/stores/font-scale-store.test.ts src/shared/components/layout/font-size-control.tsx
git commit -m "feat(frontend): global font-size scale (store, slider, anti-flash)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- src/shared/lib/stores/font-scale-store.ts src/shared/lib/stores/font-scale-store.test.ts src/shared/components/layout/font-size-control.tsx src/shared/providers/font-family-provider.tsx src/app/layout.tsx
```

---

### Task 3: Settings page + sidebar gear

**Files:**
- Create: `src/app/(dashboard)/settings/page.tsx`
- Create: `src/app/(dashboard)/settings/page.test.tsx`
- Modify: `src/shared/components/layout/app-sidebar.tsx`

**Interfaces:**
- Consumes: `HexLensLogo` (Task 1); existing `useFontFamilyStore`/`FontFamily` (`@/shared/lib/stores/font-family-store`), `usePreferencesStore` (`@/shared/lib/stores/preferences-store`), `useApiVersion(enabled: boolean)` (`@/shared/hooks/use-api-version`), `useAppConfig()` (`@/shared/lib/app-config`).
- Produces: route `/settings`. (Breadcrumbs need no config change — the URL fallback capitalizes the segment to "Settings".)

- [ ] **Step 1: Write the failing page test**

`src/app/(dashboard)/settings/page.test.tsx` (mocks follow the `about-dialog.test.tsx` precedent, which Task 5 deletes):

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppConfigProvider } from "@/shared/lib/app-config";
import { useFontFamilyStore } from "@/shared/lib/stores/font-family-store";
import SettingsPage from "./page";

vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "light", setTheme: vi.fn() }),
}));

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

function renderPage() {
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
        <SettingsPage />
      </AppConfigProvider>
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    useFontFamilyStore.setState({ font: "plex" });
  });

  it("shows appearance controls and build identity", () => {
    renderPage();
    expect(screen.getByText("Appearance")).toBeInTheDocument();
    expect(screen.getByText(/v2\.1\.0/)).toBeInTheDocument(); // UI version
    expect(screen.getByText(/v1\.4\.0/)).toBeInTheDocument(); // API version
    expect(screen.getByText(/84e7848/)).toBeInTheDocument(); // UI sha
  });

  it("switches the font family store", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Inter" }));
    expect(useFontFamilyStore.getState().font).toBe("inter");
    expect(screen.getByRole("button", { name: "Inter" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run "src/app/(dashboard)/settings/page.test.tsx"`
Expected: FAIL — cannot resolve `./page`.

- [ ] **Step 3: Implement the page**

`src/app/(dashboard)/settings/page.tsx`:

```tsx
"use client";

import { useTheme } from "next-themes";

import { HexLensLogo } from "@/shared/components/hex-lens-logo";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { useApiVersion } from "@/shared/hooks/use-api-version";
import { useAppConfig } from "@/shared/lib/app-config";
import { type FontFamily, useFontFamilyStore } from "@/shared/lib/stores/font-family-store";
import { usePreferencesStore } from "@/shared/lib/stores/preferences-store";

const FONTS: { value: FontFamily; label: string }[] = [
  { value: "plex", label: "IBM Plex" },
  { value: "inter", label: "Inter" },
];

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

function VersionRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

export default function SettingsPage() {
  const { resolvedTheme, setTheme: setNextTheme } = useTheme();
  const setStoreTheme = usePreferencesStore((s) => s.setTheme);
  const font = useFontFamilyStore((s) => s.font);
  const setFont = useFontFamilyStore((s) => s.setFont);
  const { uiVersion, uiGitSha, uiBuildDate, environment } = useAppConfig();
  const api = useApiVersion(true);

  // Same dual-write as ThemeToggle: next-themes drives the DOM, the
  // preferences store keeps its mirror.
  const setTheme = (theme: "light" | "dark") => {
    setNextTheme(theme);
    setStoreTheme(theme);
  };

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 p-6">
      <h1 className="text-lg font-semibold">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Per-user preferences, stored in this browser.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm">Theme</span>
            <div className="flex gap-1">
              {THEMES.map((t) => (
                <Button
                  key={t.value}
                  variant={resolvedTheme === t.value ? "secondary" : "ghost"}
                  size="sm"
                  aria-pressed={resolvedTheme === t.value}
                  onClick={() => setTheme(t.value)}
                >
                  {t.label}
                </Button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm">Font</span>
            <div className="flex gap-1">
              {FONTS.map((f) => (
                <Button
                  key={f.value}
                  variant={font === f.value ? "secondary" : "ghost"}
                  size="sm"
                  aria-pressed={font === f.value}
                  onClick={() => setFont(f.value)}
                >
                  {f.label}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <HexLensLogo className="size-5" />
            <CardTitle>About Cellar</CardTitle>
          </div>
          <CardDescription>Running build identity.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              UI
            </h3>
            <VersionRow label="Version" value={`v${uiVersion}`} />
            <VersionRow label="Commit" value={uiGitSha} />
            <VersionRow label="Built" value={uiBuildDate} />
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
                <VersionRow label="Version" value={`v${api.data.version}`} />
                <VersionRow label="Commit" value={api.data.git_sha} />
                <VersionRow label="Built" value={api.data.build_date} />
              </>
            )}
          </section>
          <VersionRow label="Environment" value={environment} />
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm vitest run "src/app/(dashboard)/settings/page.test.tsx"`
Expected: PASS (2 tests).

- [ ] **Step 5: Sidebar gear**

`src/shared/components/layout/app-sidebar.tsx` — full file after change (adds the gear between `UserMenu` and the version row; `UserMenu` itself is removed in Task 5):

```tsx
"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
} from "@/shared/components/ui/sidebar";
import { AppVersionTag } from "./app-version-tag";
import { NavMain } from "./nav-main";
import { UserMenu } from "./user-menu";
import { WorkspaceSwitcher } from "./workspace-switcher";

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <WorkspaceSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <NavMain />
      </SidebarContent>
      <SidebarFooter>
        <UserMenu />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild isActive={pathname === "/settings"} tooltip="Settings">
              <Link href="/settings">
                <Settings />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <div className="flex items-center justify-between border-t border-sidebar-border px-3 py-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0">
          <AppVersionTag />
          <SidebarTrigger className="size-7 text-sidebar-foreground/40 hover:text-sidebar-foreground" />
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
```

- [ ] **Step 6: Lint + full test sweep**

Run: `pnpm lint && pnpm test` — both must exit 0.

- [ ] **Step 7: Commit**

```bash
git add "src/app/(dashboard)/settings/page.tsx" "src/app/(dashboard)/settings/page.test.tsx"
git commit -m "feat(frontend): /settings page (appearance + about) with sidebar gear

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- "src/app/(dashboard)/settings/page.tsx" "src/app/(dashboard)/settings/page.test.tsx" src/shared/components/layout/app-sidebar.tsx
```

---

### Task 4: Header rework (user block, logout, slider; drop FontToggle + Bell; wire ⌘K)

**Files:**
- Create: `src/shared/lib/stores/command-palette-store.ts`
- Create: `src/shared/components/layout/header.test.tsx`
- Modify: `src/shared/components/layout/header.tsx`
- Modify: `src/shared/components/layout/command-palette.tsx`
- Delete: `src/shared/components/font-toggle.tsx`

**Interfaces:**
- Consumes: `FontSizeControl` (Task 2); `useAuthz()` from `@sentinel-auth/nextjs` (`{ user: { name?, email? }, logout }` — same usage as today's `user-menu.tsx`).
- Produces: `useCommandPaletteStore` (state `{ open: boolean; setOpen(open: boolean): void; toggle(): void }`) from `@/shared/lib/stores/command-palette-store`.

- [ ] **Step 1: Write the failing header test**

`src/shared/components/layout/header.test.tsx` (mock the two chrome children with their own providers — `next-themes`, radix slider — the test targets the header's own behavior):

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Header } from "./header";

const logoutMock = vi.fn();

vi.mock("@sentinel-auth/nextjs", () => ({
  useAuthz: () => ({
    user: { name: "Ada Lovelace", email: "ada@example.com" },
    logout: logoutMock,
  }),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("./theme-toggle", () => ({ ThemeToggle: () => null }));
vi.mock("./font-size-control", () => ({ FontSizeControl: () => null }));

describe("Header", () => {
  it("shows the signed-in user's identity", () => {
    render(<Header />);
    expect(screen.getByText("AL")).toBeInTheDocument(); // initials
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });

  it("signs out via the standalone logout button", () => {
    render(<Header />);
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logoutMock).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/shared/components/layout/header.test.tsx`
Expected: FAIL — no "Sign out" button / no user identity in current header.

- [ ] **Step 3: Command palette store + wiring**

`src/shared/lib/stores/command-palette-store.ts`:

```ts
import { create } from "zustand";

// Shared open-state so the header's Search button and the global ⌘K listener
// drive the same dialog.
interface CommandPaletteState {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}

export const useCommandPaletteStore = create<CommandPaletteState>()((set, get) => ({
  open: false,
  setOpen: (open) => set({ open }),
  toggle: () => set({ open: !get().open }),
}));
```

In `src/shared/components/layout/command-palette.tsx`, replace the local state with the store:
- Remove `useState` import usage: `const [open, setOpen] = useState(false);` →
  ```ts
  const open = useCommandPaletteStore((s) => s.open);
  const setOpen = useCommandPaletteStore((s) => s.setOpen);
  const toggle = useCommandPaletteStore((s) => s.toggle);
  ```
- In `handleKeyDown`, replace `setOpen((prev) => !prev)` with `toggle()` and add `toggle` to the `useCallback` deps array.
- Add import: `import { useCommandPaletteStore } from "@/shared/lib/stores/command-palette-store";` and drop `useState` from the react import.

- [ ] **Step 4: Rework the header**

`src/shared/components/layout/header.tsx` — full file after change:

```tsx
"use client";

import { useAuthz } from "@sentinel-auth/nextjs";
import { LogOut, Search } from "lucide-react";

import { Avatar, AvatarFallback } from "@/shared/components/ui/avatar";
import { Button } from "@/shared/components/ui/button";
import { Separator } from "@/shared/components/ui/separator";
import { useCommandPaletteStore } from "@/shared/lib/stores/command-palette-store";
import { Breadcrumbs } from "./breadcrumbs";
import { FontSizeControl } from "./font-size-control";
import { ThemeToggle } from "./theme-toggle";

export function Header() {
  const { user, logout } = useAuthz();
  const openPalette = useCommandPaletteStore((s) => s.setOpen);

  const initials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "?";

  return (
    <header className="flex h-10 shrink-0 items-center gap-2 border-b border-border/60 px-4">
      <Breadcrumbs />
      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => openPalette(true)}
          className="hidden gap-2 text-muted-foreground md:flex"
        >
          <Search className="size-4" />
          <span className="text-xs">Search</span>
          <kbd className="pointer-events-none ml-1 inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground">
            <span className="text-xs">&#8984;</span>K
          </kbd>
        </Button>
        <FontSizeControl />
        <ThemeToggle />
        <Separator orientation="vertical" className="mx-1.5 data-[orientation=vertical]:h-5" />
        <div className="flex items-center gap-2">
          <Avatar className="size-7 rounded-lg">
            <AvatarFallback className="rounded-lg text-xs">{initials}</AvatarFallback>
          </Avatar>
          <div className="hidden flex-col text-left leading-tight sm:flex">
            <span className="text-xs font-medium">{user?.name ?? "User"}</span>
            <span className="text-[10px] text-muted-foreground">{user?.email ?? ""}</span>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={logout}
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </Button>
        </div>
      </div>
    </header>
  );
}
```

(FontToggle and the inert Bell are gone; logout behavior is identical to the old "Sign out" menu item — the SDK handles redirect.)

- [ ] **Step 5: Delete the font toggle**

```bash
git rm src/shared/components/font-toggle.tsx
```

(Its only consumer was the old header; the settings page owns font choice now.)

- [ ] **Step 6: Run test to verify it passes**

Run: `pnpm vitest run src/shared/components/layout/header.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 7: Lint + full test sweep**

Run: `pnpm lint && pnpm test` — both must exit 0.

- [ ] **Step 8: Commit**

```bash
git add src/shared/lib/stores/command-palette-store.ts src/shared/components/layout/header.test.tsx
git commit -m "feat(frontend): docustore-style topbar (user identity, logout, font-size slider)

Font family choice moved to /settings; inert Bell removed; Search button
now opens the command palette.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- src/shared/lib/stores/command-palette-store.ts src/shared/components/layout/header.test.tsx src/shared/components/layout/header.tsx src/shared/components/layout/command-palette.tsx src/shared/components/font-toggle.tsx
```

---

### Task 5: Remove the sidebar user menu + About dialog

**Files:**
- Modify: `src/shared/components/layout/app-sidebar.tsx`
- Delete: `src/shared/components/layout/user-menu.tsx`
- Delete: `src/shared/components/layout/about-dialog.tsx`
- Delete: `src/shared/components/layout/about-dialog.test.tsx`

**Interfaces:**
- Consumes: header user block (Task 4) and settings About card (Task 3) — the replacements must already be merged; this task only deletes.

- [ ] **Step 1: Drop UserMenu from the sidebar**

In `src/shared/components/layout/app-sidebar.tsx`:
- Remove `import { UserMenu } from "./user-menu";`
- Remove the `<UserMenu />` line from `SidebarFooter` (the gear menu from Task 3 becomes the footer's first child).

- [ ] **Step 2: Delete the dead components**

```bash
git rm src/shared/components/layout/user-menu.tsx src/shared/components/layout/about-dialog.tsx src/shared/components/layout/about-dialog.test.tsx
```

- [ ] **Step 3: Verify nothing still references them**

Run: `grep -rn -E "user-menu|about-dialog|UserMenu|AboutDialog" src/`
Expected: no matches.

- [ ] **Step 4: Lint + full test sweep**

Run: `pnpm lint && pnpm test` — both must exit 0 (the about-dialog test is gone; settings page test covers the same assertions).

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(frontend): remove sidebar user menu + About dialog

User identity/logout live in the topbar; About content lives on /settings.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" -- src/shared/components/layout/app-sidebar.tsx src/shared/components/layout/user-menu.tsx src/shared/components/layout/about-dialog.tsx src/shared/components/layout/about-dialog.test.tsx
```

---

### Task 6: End-to-end verification (manual, dev server)

**Files:** none (verification only).

- [ ] **Step 1: Run the app**

Start backend + frontend per repo convention (`make` targets from repo root; backend on :8000 so `/api/config` and `/version` resolve). Then verify in the browser, light AND dark theme:

1. Topbar right cluster order: Search ⌘K → A—●—A slider → theme toggle → separator → avatar/name/email → logout button.
2. Search button opens the ⌘K palette; ⌘K still works.
3. Slider scales the whole UI; reload → no flash, scale persists; double-click resets.
4. Sidebar footer: ⚙ Settings (icon+tooltip when collapsed) → `/settings`; version row intact; no user menu.
5. `/settings`: theme buttons switch theme (topbar toggle stays in sync); font buttons switch family instantly; About card shows UI + API versions; breadcrumb reads "Settings".
6. Logout button signs out (Sentinel redirect to /login).
7. Hex-lens logo: sidebar brand tile, login page, favicon in the browser tab (handle visible in dark tab theme).

- [ ] **Step 2: Record outcome**

If any check fails, fix within the owning task's files and amend that task's commit message convention (`fix(frontend): ...`). Push only when the user says to.
