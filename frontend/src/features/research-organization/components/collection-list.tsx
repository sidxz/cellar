"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderOpen, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useCollections } from "../hooks/use-collections";
import { useProjects } from "../hooks/use-projects";
import { CreateCollectionDialog } from "./create-collection-dialog";
import type { Collection } from "../types";

interface CollectionListProps {
  /** Filter collections to a specific project */
  projectId?: string;
}

export function CollectionList({ projectId }: CollectionListProps) {
  const router = useRouter();
  const { data: collections, isLoading, error } = useCollections(projectId);
  const { data: projects } = useProjects();
  const [createOpen, setCreateOpen] = useState(false);

  const projectLookup = useMemo(() => {
    const map = new Map<string, string>();
    projects?.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [projects]);

  const columnDefs = useMemo<ColDef<Collection>[]>(
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
        headerName: "Molecules",
        field: "molecule_count",
        width: 120,
        type: "rightAligned",
        cellRenderer: (params: ICellRendererParams<Collection>) => (
          <Badge variant="secondary">{params.value ?? 0}</Badge>
        ),
      },
      {
        headerName: "Project",
        width: 140,
        valueGetter: (params) => {
          const pid = params.data?.project_id;
          if (!pid) return "\u2014";
          return projectLookup.get(pid) ?? pid.slice(0, 8) + "...";
        },
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 140,
        valueFormatter: (p) =>
          p.value ? String(p.value).slice(0, 8) + "..." : "\u2014",
      },
    ],
    [projectLookup]
  );

  if (error) {
    return (
      <div>
        <div className="rounded-lg border border-dashed border-destructive/50 p-8 text-center">
          <p className="text-sm text-destructive">
            Failed to load collections. Is the backend running?
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-4 flex items-center justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Collection
        </Button>
      </div>

      <DataGrid<Collection>
        rowData={collections}
        columnDefs={columnDefs}
        loading={isLoading}
        height="400px"
        suppressFilters
        onRowClick={(collection) =>
          router.push(`/collections/${collection.id}`)
        }
        emptyState={
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
            <FolderOpen className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-semibold">No collections</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Create a collection to organize molecules.
            </p>
            <Button
              className="mt-4"
              size="sm"
              onClick={() => setCreateOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              New Collection
            </Button>
          </div>
        }
      />

      <CreateCollectionDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultProjectId={projectId}
      />
    </div>
  );
}

export function CollectionListPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Collections</h1>
        <p className="mt-1 text-muted-foreground">
          Curated sets of molecules for research and analysis.
        </p>
      </div>
      <CollectionList />
    </div>
  );
}
