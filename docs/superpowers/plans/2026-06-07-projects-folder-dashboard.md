# Projects Folder Dashboard (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Projects table with a folder-style **card grid** optimized for fast navigation — identity-colored cards (compounds · campaigns count strip, member stack, recency), a ★ Pinned section, sort + cards⇄table toolbar — while preserving the existing ag-grid table as "table" mode.

**Architecture:** New presentational components under `features/research-organization/components/` (`ProjectCard`, `ProjectCardGrid`) plus two small helpers (`timeAgo`, `projectIdentityColor`). `ProjectListPage` becomes the host: it fetches projects (`useProjects`), batch stats (`useProjectScopeStats`, Phase 2), and favorites (`useFavorites('project')`, Phase 1), and toggles between the card grid and the existing `DataGrid`. View + sort persist in `localStorage`; favorites are server-side (Phase 1).

**Tech Stack:** Next.js / React 19 / TypeScript / Tailwind v4 / shadcn ui / TanStack Query v5 / lucide-react / vitest.

**Spec:** `docs/superpowers/specs/2026-06-07-projects-folder-dashboard-design.md` (Phase 3). **Depends on Phase 1 (favorites hook) and Phase 2 (extended stats) being merged.**

**Verified facts:** `resolveCategoryColor(label, color?)` in `shared/lib/category-colors.ts` returns `{hex,name,bg,text,dot}` (hash fallback on unknown color). `useWorkspaceMembers()` returns `WorkspaceMember[]` = `{user_id,email,name,avatar_url}` from one cached query (no N+1). Avatar primitives `Avatar`(size `sm`)/`AvatarFallback`/`AvatarGroup`/`AvatarGroupCount` exist. Current `project-list.tsx` uses `DataGrid` + `TagFilter` + `Switch` "Show archived" + `CreateProjectDialog`. `useProjectScopeStats(ids)` returns `Record<string, ProjectScopeStats>`.

---

## Task 1: `timeAgo` relative-time helper

**Files:**
- Create: `frontend/src/shared/lib/time-ago.ts`
- Test: `frontend/src/shared/lib/time-ago.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/shared/lib/time-ago.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { timeAgo } from "./time-ago";

describe("timeAgo", () => {
  const now = new Date("2026-06-07T12:00:00Z").getTime();
  it("returns em dash for null/undefined", () => {
    expect(timeAgo(null, now)).toBe("—");
    expect(timeAgo(undefined, now)).toBe("—");
  });
  it("formats minutes", () => expect(timeAgo("2026-06-07T11:30:00Z", now)).toBe("30m ago"));
  it("formats hours", () => expect(timeAgo("2026-06-07T09:00:00Z", now)).toBe("3h ago"));
  it("formats days", () => expect(timeAgo("2026-06-04T12:00:00Z", now)).toBe("3d ago"));
  it("formats weeks", () => expect(timeAgo("2026-05-24T12:00:00Z", now)).toBe("2w ago"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- time-ago`
Expected: FAIL — cannot find module `./time-ago`.

- [ ] **Step 3: Create the helper**

Create `frontend/src/shared/lib/time-ago.ts`:

```ts
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** Compact relative time: "just now", "5m ago", "3h ago", "2d ago", "4w ago", else a date. */
export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = now - then;
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}d ago`;
  if (diff < 28 * DAY) return `${Math.floor(diff / (7 * DAY))}w ago`;
  return new Date(iso).toLocaleDateString();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- time-ago`
Expected: PASS (5 assertions)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/lib/time-ago.ts frontend/src/shared/lib/time-ago.test.ts
git commit -m "feat(ui): add timeAgo relative-time helper"
```

---

## Task 2: `projectIdentityColor` helper

**Files:**
- Create: `frontend/src/features/research-organization/lib/project-identity.ts`

- [ ] **Step 1: Create the helper** (pure pass-through over `resolveCategoryColor`; no separate test — covered via ProjectCard test)

Create `frontend/src/features/research-organization/lib/project-identity.ts`:

```ts
import { type CategoryColor, resolveCategoryColor } from "@/shared/lib/category-colors";
import type { Project } from "../types";

/**
 * Stable visual identity color for a project folder card.
 *
 * v1: a stable hash of the project name (same color every visit). Tag-based
 * override slots in here once project tags ship in the projects list payload —
 * pass the tag's hex as the second arg to resolveCategoryColor.
 */
export function projectIdentityColor(project: Project): CategoryColor {
  return resolveCategoryColor(project.name);
}
```

- [ ] **Step 2: Lint + commit**

Run: `cd frontend && pnpm lint`
Expected: exit 0.

```bash
git add frontend/src/features/research-organization/lib/project-identity.ts
git commit -m "feat(projects): stable identity color per project card"
```

---

## Task 3: `ProjectCard` component

**Files:**
- Create: `frontend/src/features/research-organization/components/project-card.tsx`
- Test: `frontend/src/features/research-organization/components/project-card.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/research-organization/components/project-card.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Project } from "../types";
import { ProjectCard } from "./project-card";

vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [] }),
}));

const project: Project = {
  id: "p1",
  workspace_id: "w1",
  name: "Intramacrophage",
  description: null,
  status: "active",
  created_by: "u1",
  version: 1,
};

const stats = {
  molecule_count: 142,
  protocol_count: 3,
  run_count: 48,
  campaign_count: 3,
  last_activity_at: null,
  member_count: 0,
  member_ids: [],
};

describe("ProjectCard", () => {
  it("renders name, compounds and campaigns counts and a description fallback", () => {
    render(
      <ProjectCard
        project={project}
        stats={stats}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("Intramacrophage")).toBeInTheDocument();
    expect(screen.getByText("142")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("No description")).toBeInTheDocument();
  });

  it("toggles favorite without opening the project", () => {
    const onToggle = vi.fn();
    const onOpen = vi.fn();
    render(
      <ProjectCard
        project={project}
        stats={stats}
        favorited={false}
        onToggleFavorite={onToggle}
        onOpen={onOpen}
      />,
    );
    fireEvent.click(screen.getByLabelText("Pin project"));
    expect(onToggle).toHaveBeenCalledWith(project, false);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("opens the project when the body is clicked", () => {
    const onOpen = vi.fn();
    render(
      <ProjectCard
        project={project}
        stats={stats}
        favorited={false}
        onToggleFavorite={vi.fn()}
        onOpen={onOpen}
      />,
    );
    fireEvent.click(screen.getByText("Intramacrophage"));
    expect(onOpen).toHaveBeenCalledWith(project);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- project-card`
Expected: FAIL — cannot find module `./project-card`.

- [ ] **Step 3: Create the component**

Create `frontend/src/features/research-organization/components/project-card.tsx`:

```tsx
"use client";

import {
  Avatar,
  AvatarFallback,
  AvatarGroup,
  AvatarGroupCount,
} from "@/shared/components/ui/avatar";
import { Badge } from "@/shared/components/ui/badge";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { cn } from "@/shared/lib/utils";
import { timeAgo } from "@/shared/lib/time-ago";
import { FolderKanban, Star } from "lucide-react";
import type { ProjectScopeStats } from "../hooks/use-project-scope-stats";
import { projectIdentityColor } from "../lib/project-identity";
import type { Project } from "../types";

function initials(nameOrEmail: string): string {
  const base = nameOrEmail.trim();
  const parts = base.split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

interface ProjectCardProps {
  project: Project;
  stats?: ProjectScopeStats;
  favorited: boolean;
  onToggleFavorite: (project: Project, favorited: boolean) => void;
  onOpen: (project: Project) => void;
}

export function ProjectCard({
  project,
  stats,
  favorited,
  onToggleFavorite,
  onOpen,
}: ProjectCardProps) {
  const color = projectIdentityColor(project);
  const { data: members } = useWorkspaceMembers();
  const archived = project.status === "archived";

  const memberIds = stats?.member_ids ?? [];
  const resolved = memberIds
    .map((id) => members?.find((m) => m.user_id === id))
    .filter((m): m is NonNullable<typeof m> => Boolean(m));
  const overflow = (stats?.member_count ?? memberIds.length) - Math.min(resolved.length, 3);

  return (
    <div
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-shadow hover:shadow-md",
        archived && "opacity-60",
      )}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", color.dot)} />

      {!archived && (
        <button
          type="button"
          aria-label={favorited ? "Unpin project" : "Pin project"}
          aria-pressed={favorited}
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite(project, favorited);
          }}
          className={cn(
            "absolute right-2 top-2 z-10 rounded p-1 transition-opacity hover:text-foreground",
            favorited
              ? "text-amber-500 opacity-100"
              : "text-muted-foreground opacity-0 group-hover:opacity-100",
          )}
        >
          <Star className={cn("h-4 w-4", favorited && "fill-current")} />
        </button>
      )}

      <button
        type="button"
        onClick={() => onOpen(project)}
        className="flex flex-1 flex-col gap-3 p-4 pl-5 text-left"
      >
        <div className="flex items-start gap-2">
          <span
            className={cn(
              "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded",
              color.bg,
            )}
          >
            <FolderKanban className={cn("h-4 w-4", color.text)} />
          </span>
          <div className="min-w-0 pr-6">
            <div className="truncate font-semibold leading-tight">{project.name}</div>
            <div className="truncate text-xs text-muted-foreground">
              {project.description?.trim() || "No description"}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x rounded-md border bg-muted/30 text-center">
          <div className="px-2 py-2">
            <div className="font-semibold tabular-nums">{stats ? stats.molecule_count : "—"}</div>
            <div className="text-[11px] text-muted-foreground">compounds</div>
          </div>
          <div className="px-2 py-2">
            <div className="font-semibold tabular-nums">{stats ? stats.campaign_count : "—"}</div>
            <div className="text-[11px] text-muted-foreground">
              {stats && stats.campaign_count === 0 ? "no campaigns" : "campaigns"}
            </div>
          </div>
        </div>

        <div className="mt-auto flex items-center justify-between">
          {resolved.length > 0 ? (
            <AvatarGroup>
              {resolved.slice(0, 3).map((m) => (
                <Avatar key={m.user_id} size="sm">
                  <AvatarFallback>{initials(m.name || m.email)}</AvatarFallback>
                </Avatar>
              ))}
              {overflow > 0 && <AvatarGroupCount>+{overflow}</AvatarGroupCount>}
            </AvatarGroup>
          ) : (
            <span />
          )}
          {archived ? (
            <Badge variant="outline">Archived</Badge>
          ) : (
            <span className="text-xs text-muted-foreground">{timeAgo(stats?.last_activity_at)}</span>
          )}
        </div>
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- project-card`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/components/project-card.tsx \
        frontend/src/features/research-organization/components/project-card.test.tsx
git commit -m "feat(projects): ProjectCard folder card"
```

---

## Task 4: `ProjectCardGrid` (sections + sorting)

**Files:**
- Create: `frontend/src/features/research-organization/components/project-card-grid.tsx`
- Test: `frontend/src/features/research-organization/components/project-card-grid.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/features/research-organization/components/project-card-grid.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Project } from "../types";
import { ProjectCardGrid } from "./project-card-grid";

vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [] }),
}));

const mk = (id: string, name: string): Project => ({
  id,
  workspace_id: "w",
  name,
  description: null,
  status: "active",
  created_by: "u",
  version: 1,
});

describe("ProjectCardGrid", () => {
  it("splits favorited projects into a Pinned section", () => {
    render(
      <ProjectCardGrid
        projects={[mk("a", "Alpha"), mk("b", "Beta")]}
        statsById={{}}
        favorites={new Set(["b"])}
        sort="name"
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByText("Pinned")).toBeInTheDocument();
    expect(screen.getByText("All projects")).toBeInTheDocument();
  });

  it("shows the empty state when there are no projects", () => {
    render(
      <ProjectCardGrid
        projects={[]}
        statsById={{}}
        favorites={new Set()}
        sort="name"
        onToggleFavorite={vi.fn()}
        onOpen={vi.fn()}
        onCreate={vi.fn()}
      />,
    );
    expect(screen.getByText("No projects")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && pnpm test -- project-card-grid`
Expected: FAIL — cannot find module `./project-card-grid`.

- [ ] **Step 3: Create the component**

Create `frontend/src/features/research-organization/components/project-card-grid.tsx`:

```tsx
"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { FolderKanban, Plus, Star } from "lucide-react";
import type { ProjectScopeStats } from "../hooks/use-project-scope-stats";
import type { Project } from "../types";
import { ProjectCard } from "./project-card";

export type ProjectSort = "recent" | "name" | "size";

interface ProjectCardGridProps {
  projects: Project[];
  statsById: Record<string, ProjectScopeStats>;
  favorites: Set<string>;
  sort: ProjectSort;
  onToggleFavorite: (project: Project, favorited: boolean) => void;
  onOpen: (project: Project) => void;
  onCreate: () => void;
}

function sortProjects(
  projects: Project[],
  statsById: Record<string, ProjectScopeStats>,
  sort: ProjectSort,
): Project[] {
  const copy = [...projects];
  if (sort === "name") {
    copy.sort((a, b) => a.name.localeCompare(b.name));
  } else if (sort === "size") {
    copy.sort(
      (a, b) => (statsById[b.id]?.molecule_count ?? 0) - (statsById[a.id]?.molecule_count ?? 0),
    );
  } else {
    copy.sort((a, b) => {
      const ta = statsById[a.id]?.last_activity_at;
      const tb = statsById[b.id]?.last_activity_at;
      return (tb ? new Date(tb).getTime() : 0) - (ta ? new Date(ta).getTime() : 0);
    });
  }
  return copy;
}

export function ProjectCardGrid({
  projects,
  statsById,
  favorites,
  sort,
  onToggleFavorite,
  onOpen,
  onCreate,
}: ProjectCardGridProps) {
  if (projects.length === 0) {
    return (
      <EmptyState
        icon={FolderKanban}
        title="No projects"
        description="Create your first research project to get started."
        action={{ label: "New Project", onClick: onCreate, icon: Plus }}
      />
    );
  }

  const pinned = sortProjects(
    projects.filter((p) => favorites.has(p.id)),
    statsById,
    sort,
  );
  const rest = sortProjects(
    projects.filter((p) => !favorites.has(p.id)),
    statsById,
    sort,
  );

  const grid = (list: Project[]) => (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {list.map((p) => (
        <ProjectCard
          key={p.id}
          project={p}
          stats={statsById[p.id]}
          favorited={favorites.has(p.id)}
          onToggleFavorite={onToggleFavorite}
          onOpen={onOpen}
        />
      ))}
    </div>
  );

  return (
    <div className="flex flex-col gap-6">
      {pinned.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Star className="h-3.5 w-3.5 fill-current text-amber-500" /> Pinned
          </h2>
          {grid(pinned)}
        </section>
      )}
      <section className="flex flex-col gap-2">
        {pinned.length > 0 && (
          <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            All projects
          </h2>
        )}
        {grid(rest)}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && pnpm test -- project-card-grid`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/research-organization/components/project-card-grid.tsx \
        frontend/src/features/research-organization/components/project-card-grid.test.tsx
git commit -m "feat(projects): ProjectCardGrid with Pinned section + sorting"
```

---

## Task 5: Wire the grid + toolbar into `ProjectListPage`

**Files:**
- Modify: `frontend/src/features/research-organization/components/project-list.tsx`

- [ ] **Step 1: Replace the component**

Replace the entire contents of `frontend/src/features/research-organization/components/project-list.tsx` with:

```tsx
"use client";

import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { MemberName } from "@/shared/components/entity-name";
import { PageHeader } from "@/shared/components/page-header";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Switch } from "@/shared/components/ui/switch";
import { useFavorites, useToggleFavorite } from "@/shared/hooks/use-favorites";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { FolderKanban, LayoutGrid, Plus, Table as TableIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useProjectScopeStats } from "../hooks/use-project-scope-stats";
import { useProjects } from "../hooks/use-projects";
import type { Project } from "../types";
import { CreateProjectDialog } from "./create-project-dialog";
import { ProjectCardGrid, type ProjectSort } from "./project-card-grid";

function readPref<T extends string>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  return (window.localStorage.getItem(key) as T | null) ?? fallback;
}
function writePref(key: string, value: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(key, value);
}

export function ProjectListPage() {
  const router = useRouter();
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const {
    data: projects,
    isLoading,
    error,
  } = useProjects({ tags: tagFilter.tagIds, tagLogic: tagFilter.tagLogic });
  const [createOpen, setCreateOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [view, setView] = useState<"cards" | "table">(() =>
    readPref<"cards" | "table">("projects:view", "cards"),
  );
  const [sort, setSort] = useState<ProjectSort>(() =>
    readPref<ProjectSort>("projects:sort", "recent"),
  );
  useEffect(() => writePref("projects:view", view), [view]);
  useEffect(() => writePref("projects:sort", sort), [sort]);

  const favoritesQuery = useFavorites("project");
  const favorites = favoritesQuery.data ?? new Set<string>();
  const toggleFavorite = useToggleFavorite("project");

  const filteredProjects = useMemo(() => {
    if (!projects) return undefined;
    if (showArchived) return projects;
    return projects.filter((p) => p.status === "active");
  }, [projects, showArchived]);

  const projectIds = useMemo(
    () => (filteredProjects ?? []).map((p) => p.id),
    [filteredProjects],
  );
  const statsQuery = useProjectScopeStats(projectIds);
  const statsById = statsQuery.data ?? {};

  const columnDefs = useMemo<ColDef<Project>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 180 },
      {
        headerName: "Description",
        field: "description",
        flex: 1,
        minWidth: 180,
        valueFormatter: (p) => p.value ?? "—",
      },
      {
        headerName: "Status",
        field: "status",
        width: 100,
        cellRenderer: (params: ICellRendererParams<Project>) => (
          <StatusBadge status={params.value} />
        ),
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 160,
        cellRenderer: (params: ICellRendererParams<Project>) =>
          params.value ? <MemberName id={params.value} /> : "—",
      },
    ],
    [],
  );

  const header = (
    <PageHeader title="Projects" subtitle="Organize research projects and collections.">
      <Button onClick={() => setCreateOpen(true)}>
        <Plus className="mr-2 h-4 w-4" />
        New Project
      </Button>
    </PageHeader>
  );

  if (error) {
    return (
      <div>
        {header}
        <ErrorState
          message="Failed to load projects. Is the backend running?"
          details={error.message}
        />
      </div>
    );
  }

  return (
    <div>
      {header}

      {/* Toolbar */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <TagFilter value={tagFilter} onChange={setTagFilter} />
        <div className="flex items-center gap-2">
          <Switch
            id="show-archived"
            checked={showArchived}
            onCheckedChange={setShowArchived}
            size="sm"
          />
          <Label htmlFor="show-archived" className="text-sm text-muted-foreground">
            Show archived
          </Label>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {view === "cards" && (
            <Select value={sort} onValueChange={(v) => setSort(v as ProjectSort)}>
              <SelectTrigger className="h-8 w-[170px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="recent">Recently active</SelectItem>
                <SelectItem value="name">Name (A–Z)</SelectItem>
                <SelectItem value="size">Most compounds</SelectItem>
              </SelectContent>
            </Select>
          )}
          <div className="flex items-center rounded-md border p-0.5">
            <Button
              variant={view === "cards" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 px-2"
              onClick={() => setView("cards")}
              aria-label="Card view"
              aria-pressed={view === "cards"}
            >
              <LayoutGrid className="h-4 w-4" />
            </Button>
            <Button
              variant={view === "table" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 px-2"
              onClick={() => setView("table")}
              aria-label="Table view"
              aria-pressed={view === "table"}
            >
              <TableIcon className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {view === "cards" ? (
        isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={`skeleton-${i}`}
                className="h-40 animate-pulse rounded-lg border bg-muted/30"
              />
            ))}
          </div>
        ) : (
          <ProjectCardGrid
            projects={filteredProjects ?? []}
            statsById={statsById}
            favorites={favorites}
            sort={sort}
            onToggleFavorite={(p, favorited) =>
              toggleFavorite.mutate({ entityId: p.id, favorited })
            }
            onOpen={(p) => router.push(`/projects/${p.id}`)}
            onCreate={() => setCreateOpen(true)}
          />
        )
      ) : (
        <DataGrid<Project>
          rowData={filteredProjects}
          columnDefs={columnDefs}
          loading={isLoading}
          height="400px"
          suppressFilters
          onRowClick={(project) => router.push(`/projects/${project.id}`)}
          emptyState={
            <EmptyState
              icon={FolderKanban}
              title="No projects"
              description="Create your first research project to get started."
              action={{ label: "New Project", onClick: () => setCreateOpen(true), icon: Plus }}
            />
          }
        />
      )}

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
```

- [ ] **Step 2: Run the existing component tests + lint**

Run: `cd frontend && pnpm test -- project-card project-card-grid time-ago use-favorites`
Expected: all PASS.

Run: `cd frontend && pnpm lint`
Expected: exit 0. (If `SelectTrigger`/`Switch`/`Button` reject a prop, adjust to the actual component API — e.g. drop `size="sm"` on Switch if unsupported — these are the only likely deltas.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/research-organization/components/project-list.tsx
git commit -m "feat(projects): folder card grid + sort + cards/table toggle"
```

---

## Task 6: Manual verification (running app)

> Card-grid behavior that spans the live backend + persistence is verified by hand (or via the `verify`/`run` skills). No Playwright harness is fabricated here.

- [ ] **Step 1: Start the stack** — bring up the dev backend (`:8000`) and frontend, signed into a workspace that has projects (the TB cascade dataset).

- [ ] **Step 2: Folder grid renders** — `/projects` shows identity-colored folder cards in a responsive grid; each card shows name, description (or "No description"), a compounds · campaigns strip, member avatars, and a recency stamp.

- [ ] **Step 3: Pinning persists server-side** — click a card's star → it jumps to the **★ Pinned** section. Reload the page → it's still pinned. Open a different browser/profile for the same user → still pinned (confirms server-side, not localStorage).

- [ ] **Step 4: Sort works** — switch Sort between Recently active / Name (A–Z) / Most compounds and confirm card order changes accordingly.

- [ ] **Step 5: Cards⇄table toggle persists** — switch to Table → the original ag-grid table renders; reload → it reopens in Table (localStorage). Switch back to Cards.

- [ ] **Step 6: Archived** — toggle "Show archived" → archived projects appear dimmed with an `Archived` chip and no pin control.

- [ ] **Step 7: Quiet/empty projects** — a project with 0 campaigns shows "no campaigns" gracefully; a project with no members shows no avatar stack and the layout still looks right.

- [ ] **Step 8: Update the GitHub project board** — mark the Projects folder dashboard (Phase 3) done; link the three plan files.

---

## Phase 3 Done — verification

- [ ] `cd frontend && pnpm test -- time-ago project-card project-card-grid use-favorites` — green
- [ ] `cd frontend && pnpm lint` — exit 0
- [ ] Manual checklist (Task 6) walked end-to-end
- [ ] Screenshots captured for the PR (cards view, pinned section, table toggle)
