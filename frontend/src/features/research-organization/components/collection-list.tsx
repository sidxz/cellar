"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderOpen, GitMerge, Plus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { MemberName } from "@/shared/components/entity-name";
import { useCollections } from "../hooks/use-collections";
import { useProjects } from "../hooks/use-projects";
import { BooleanCollectionsDialog } from "./boolean-collections-dialog";
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
  const [booleanOpsOpen, setBooleanOpsOpen] = useState(false);

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
          return projectLookup.get(pid) ?? "\u2014";
        },
      },
      {
        headerName: "Visibility",
        field: "visibility",
        width: 110,
        cellRenderer: (params: { value: string }) => {
          return params.value === "shared" ? "Shared" : "Private";
        },
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 160,
        cellRenderer: (params: ICellRendererParams<Collection>) =>
          params.value ? <MemberName id={params.value} /> : "\u2014",
      },
    ],
    [projectLookup]
  );

  if (error) {
    return (
      <div>
        <ErrorState message="Failed to load collections. Is the backend running?" details={error.message} />
      </div>
    );
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-4 flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => setBooleanOpsOpen(true)}>
          <GitMerge className="mr-2 h-4 w-4" />
          Boolean Ops
        </Button>
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
          <EmptyState
            icon={FolderOpen}
            title="No collections"
            description="Create a collection to organize molecules."
            action={{ label: "New Collection", onClick: () => setCreateOpen(true), icon: Plus }}
          />
        }
      />

      <CreateCollectionDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultProjectId={projectId}
      />

      <BooleanCollectionsDialog
        open={booleanOpsOpen}
        onOpenChange={setBooleanOpsOpen}
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
