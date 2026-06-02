"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderKanban, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { MemberName } from "@/shared/components/entity-name";
import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { useProjects } from "../hooks/use-projects";
import { CreateProjectDialog } from "./create-project-dialog";
import type { Project } from "../types";

export function ProjectListPage() {
  const router = useRouter();
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const { data: projects, isLoading, error } = useProjects({
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
  });
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
          <StatusBadge status={params.value} />
        ),
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 160,
        cellRenderer: (params: ICellRendererParams<Project>) =>
          params.value ? <MemberName id={params.value} /> : "\u2014",
      },
    ],
    []
  );

  if (error) {
    return (
      <div>
        <PageHeader title="Projects" subtitle="Organize research projects and collections.">
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Project
          </Button>
        </PageHeader>
        <ErrorState message="Failed to load projects. Is the backend running?" details={error.message} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Projects" subtitle="Organize research projects and collections.">
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Project
        </Button>
      </PageHeader>

      {/* Toolbar */}
      <div className="mb-4 flex items-center gap-3">
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
      </div>

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

      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
