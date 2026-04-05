"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderKanban, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useProjects } from "../hooks/use-projects";
import { CreateProjectDialog } from "./create-project-dialog";
import type { Project, ProjectStatus } from "../types";

function statusBadgeVariant(
  status: ProjectStatus
): "default" | "destructive" {
  return status === "active" ? "default" : "destructive";
}

export function ProjectListPage() {
  const router = useRouter();
  const { data: projects, isLoading, error } = useProjects();
  const [createOpen, setCreateOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  const filteredProjects = useMemo(() => {
    if (!projects) return undefined;
    if (showArchived) return projects;
    return projects.filter((p) => p.status === "active");
  }, [projects, showArchived]);

  const columnDefs = useMemo<ColDef<Project>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 180 },
      {
        headerName: "Description",
        field: "description",
        flex: 1,
        minWidth: 180,
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Status",
        field: "status",
        width: 100,
        cellRenderer: (params: ICellRendererParams<Project>) => (
          <Badge variant={statusBadgeVariant(params.value as ProjectStatus)}>
            {params.value}
          </Badge>
        ),
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 140,
        valueFormatter: (p) =>
          p.value ? String(p.value).slice(0, 8) + "..." : "\u2014",
      },
    ],
    []
  );

  if (error) {
    return (
      <div>
        <PageHeader onNew={() => setCreateOpen(true)} />
        <div className="rounded-lg border border-dashed border-destructive/50 p-8 text-center">
          <p className="text-sm text-destructive">
            Failed to load projects. Is the backend running?
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader onNew={() => setCreateOpen(true)} />

      {/* Toolbar */}
      <div className="mb-4 flex items-center gap-3">
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
      </div>

      <DataGrid<Project>
        rowData={filteredProjects}
        columnDefs={columnDefs}
        loading={isLoading}
        height="400px"
        suppressFilters
        onRowClick={(project) => router.push(`/projects/${project.id}`)}
        emptyState={
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
            <FolderKanban className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-semibold">No projects</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Create your first research project to get started.
            </p>
            <Button
              className="mt-4"
              size="sm"
              onClick={() => setCreateOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              New Project
            </Button>
          </div>
        }
      />

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

function PageHeader({ onNew }: { onNew: () => void }) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
        <p className="mt-1 text-muted-foreground">
          Organize research projects and collections.
        </p>
      </div>
      <Button onClick={onNew}>
        <Plus className="mr-2 h-4 w-4" />
        New Project
      </Button>
    </div>
  );
}
