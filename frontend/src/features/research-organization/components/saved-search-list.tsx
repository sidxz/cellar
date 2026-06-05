"use client";

import { AdminDeleteButton } from "@/shared/components/admin-delete-button";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { MemberName } from "@/shared/components/entity-name";
import { PageHeader } from "@/shared/components/page-header";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Label } from "@/shared/components/ui/label";
import { Switch } from "@/shared/components/ui/switch";
import { formatRelativeDate } from "@/shared/lib/format-date";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { MoreHorizontal, Pencil, Play, Plus, Search, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useProjects } from "../hooks/use-projects";
import { useDeleteSavedSearch, useSavedSearches } from "../hooks/use-saved-searches";
import type { SavedSearch, SearchVisibility } from "../types";
import { CreateSavedSearchDialog } from "./create-saved-search-dialog";
import { QuerySummary } from "./search/query-summary";

function visibilityBadgeVariant(visibility: SearchVisibility): "default" | "outline" {
  return visibility === "project" ? "default" : "outline";
}

// ─── Row Actions Cell ────────────────────────────────────────────────────────

interface RowActionsProps {
  search: SavedSearch;
  isAdmin: boolean;
  onRun: (search: SavedSearch) => void;
  onEdit: (search: SavedSearch) => void;
  onDelete: (search: SavedSearch) => void;
  onAdminDeleted: () => void;
}

function RowActions({ search, isAdmin, onRun, onEdit, onDelete, onAdminDeleted }: RowActionsProps) {
  return (
    <div className="flex items-center gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7">
            <MoreHorizontal className="h-4 w-4" />
            <span className="sr-only">Actions</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => onRun(search)}>
            <Play className="mr-2 h-4 w-4" />
            Run
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onEdit(search)}>
            <Pencil className="mr-2 h-4 w-4" />
            Edit
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => onDelete(search)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {isAdmin && (
        <AdminDeleteButton
          entityType="saved_search"
          entityId={search.id}
          entityLabel={search.name}
          onDeleted={onAdminDeleted}
        />
      )}
    </div>
  );
}

// ─── SavedSearchList ─────────────────────────────────────────────────────────

interface SavedSearchListProps {
  /** Filter saved searches to a specific project */
  projectId?: string;
}

export function SavedSearchList({ projectId }: SavedSearchListProps) {
  const router = useRouter();
  const isAdmin = useAuthzHasRole("admin");
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editSearch, setEditSearch] = useState<SavedSearch | undefined>();
  const [mine, setMine] = useState(false);

  const { data: savedSearches, isLoading, error } = useSavedSearches(projectId, mine);
  const { data: projects } = useProjects();
  const deleteMutation = useDeleteSavedSearch();

  const projectLookup = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of projects ?? []) map.set(p.id, p.name);
    return map;
  }, [projects]);

  const handleRun = (search: SavedSearch) => {
    router.push(`/search?saved=${search.id}`);
  };

  const handleEdit = (search: SavedSearch) => {
    setEditSearch(search);
    setCreateOpen(true);
  };

  const handleDelete = (search: SavedSearch) => {
    deleteMutation.mutate(search.id);
  };

  const columnDefs = useMemo<ColDef<SavedSearch>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 180 },
      {
        headerName: "Query",
        width: 250,
        cellRenderer: (params: ICellRendererParams<SavedSearch>) =>
          params.data ? <QuerySummary query={params.data.query} /> : null,
      },
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
        headerName: "Last Run",
        field: "last_run_at",
        width: 130,
        valueFormatter: (params) =>
          params.value ? formatRelativeDate(params.value as string) : "\u2014",
      },
      {
        headerName: "Results",
        field: "result_count",
        width: 90,
        valueFormatter: (params) => (params.value != null ? String(params.value) : "\u2014"),
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 160,
        cellRenderer: (params: ICellRendererParams<SavedSearch>) =>
          params.value ? <MemberName id={params.value} /> : "\u2014",
      },
      {
        headerName: "",
        width: isAdmin ? 120 : 56,
        sortable: false,
        resizable: false,
        suppressHeaderMenuButton: true,
        cellRenderer: (params: ICellRendererParams<SavedSearch>) =>
          params.data ? (
            <RowActions
              search={params.data}
              isAdmin={isAdmin}
              onRun={handleRun}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onAdminDeleted={() => qc.invalidateQueries({ queryKey: ["saved-searches"] })}
            />
          ) : null,
      },
    ],
    [projectLookup, isAdmin, qc],
  );

  if (error) {
    return (
      <div>
        <ErrorState
          message="Failed to load saved searches. Is the backend running?"
          details={error.message}
        />
      </div>
    );
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Switch id="my-searches" checked={mine} onCheckedChange={setMine} size="sm" />
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
        onRowClick={handleRun}
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
      <PageHeader
        title="Saved Searches"
        subtitle="Reusable searches across compounds, assays, and inventory."
      />
      <SavedSearchList />
    </div>
  );
}
