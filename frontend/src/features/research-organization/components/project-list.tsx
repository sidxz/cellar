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

  const projectIds = useMemo(() => (filteredProjects ?? []).map((p) => p.id), [filteredProjects]);
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
            onToggleFavorite={(p, favorited) => toggleFavorite.mutate({ entityId: p.id, favorited })}
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
