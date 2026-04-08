"use client";

import { useMemo, useState } from "react";
import { Search, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { MemberName } from "@/shared/components/entity-name";
import { useSavedSearches } from "../hooks/use-saved-searches";
import { useProjects } from "../hooks/use-projects";
import { CreateSavedSearchDialog } from "./create-saved-search-dialog";
import type { SavedSearch, SearchVisibility } from "../types";

function visibilityBadgeVariant(
  visibility: SearchVisibility
): "default" | "outline" {
  return visibility === "project" ? "default" : "outline";
}

interface SavedSearchListProps {
  /** Filter saved searches to a specific project */
  projectId?: string;
}

export function SavedSearchList({ projectId }: SavedSearchListProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [editSearch, setEditSearch] = useState<SavedSearch | undefined>();
  const [mine, setMine] = useState(false);

  const { data: savedSearches, isLoading, error } = useSavedSearches(projectId, mine);
  const { data: projects } = useProjects();

  const projectLookup = useMemo(() => {
    const map = new Map<string, string>();
    projects?.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [projects]);

  const columnDefs = useMemo<ColDef<SavedSearch>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 180 },
      {
        headerName: "Visibility",
        field: "visibility",
        width: 100,
        cellRenderer: (params: ICellRendererParams<SavedSearch>) => (
          <Badge variant={visibilityBadgeVariant(params.value as SearchVisibility)}>
            {params.value}
          </Badge>
        ),
      },
      {
        headerName: "Project",
        width: 140,
        valueGetter: (params) => {
          const pid = params.data?.project_id;
          if (!pid) return "\u2014";
          return projectLookup.get(pid) ?? "\u2014";
        },
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 160,
        cellRenderer: (params: ICellRendererParams<SavedSearch>) =>
          params.value ? <MemberName id={params.value} /> : "\u2014",
      },
    ],
    [projectLookup]
  );

  if (error) {
    return (
      <div>
        <ErrorState message="Failed to load saved searches. Is the backend running?" details={error.message} />
      </div>
    );
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Switch
            id="my-searches"
            checked={mine}
            onCheckedChange={setMine}
            size="sm"
          />
          <Label htmlFor="my-searches" className="text-sm text-muted-foreground">
            My Searches
          </Label>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Saved Search
        </Button>
      </div>

      <DataGrid<SavedSearch>
        rowData={savedSearches}
        columnDefs={columnDefs}
        loading={isLoading}
        height="400px"
        suppressFilters
        onRowClick={(search) => {
          setEditSearch(search);
          setCreateOpen(true);
        }}
        emptyState={
          <EmptyState
            icon={Search}
            title="No saved searches"
            description="Save a search to quickly re-run it later."
            action={{ label: "New Saved Search", onClick: () => setCreateOpen(true), icon: Plus }}
          />
        }
      />

      <CreateSavedSearchDialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) setEditSearch(undefined);
        }}
        savedSearch={editSearch}
        defaultProjectId={projectId}
      />
    </div>
  );
}

export function SavedSearchListPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Saved Searches</h1>
        <p className="mt-1 text-muted-foreground">
          Reusable searches across compounds, assays, and inventory.
        </p>
      </div>
      <SavedSearchList />
    </div>
  );
}
