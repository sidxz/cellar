"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  FolderOpen,
  Pencil,
  Plus,
  Trash2,
  ExternalLink,
} from "lucide-react";
import type { ColDef, GridApi } from "ag-grid-community";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { MoleculeName, OrgName } from "@/shared/components/entity-name";
import {
  useCollection,
  useDeleteCollection,
} from "../hooks/use-collections";
import { useCollectionMolecules, useRemoveMolecules } from "../hooks/use-collection-molecules";
import { useProject } from "../hooks/use-projects";
import { CreateCollectionDialog } from "./create-collection-dialog";
import { AddMoleculesDialog } from "./add-molecules-dialog";

interface CollectionDetailProps {
  collectionId: string;
}

interface MoleculeRow {
  id: string;
}

export function CollectionDetail({ collectionId }: CollectionDetailProps) {
  const router = useRouter();
  const { data: collection, isLoading } = useCollection(collectionId);
  const { data: moleculeIds, isLoading: moleculesLoading } =
    useCollectionMolecules(collectionId);
  const { data: project } = useProject(collection?.project_id ?? undefined);
  const deleteMutation = useDeleteCollection();
  const removeMutation = useRemoveMolecules(collectionId);

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [addMolOpen, setAddMolOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [removeOpen, setRemoveOpen] = useState(false);
  const gridApiRef = useRef<GridApi<MoleculeRow> | null>(null);

  const moleculeRows: MoleculeRow[] = useMemo(
    () => (moleculeIds ?? []).map((id) => ({ id })),
    [moleculeIds]
  );

  const columnDefs = useMemo<ColDef<MoleculeRow>[]>(
    () => [
      {
        headerName: "Molecule",
        field: "id",
        flex: 1,
        minWidth: 200,
        cellRenderer: ({ data }: { data: MoleculeRow | undefined }) =>
          data ? <MoleculeName id={data.id} /> : null,
      },
      {
        headerName: "ID",
        field: "id",
        width: 280,
        cellClass: "font-mono text-xs",
        valueFormatter: (p) =>
          p.value ? String(p.value).slice(0, 12) + "..." : "",
      },
      {
        headerName: "",
        width: 80,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data: MoleculeRow | undefined }) =>
          data ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => router.push(`/compounds/${data.id}`)}
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
          ) : null,
      },
    ],
    [router]
  );

  // --- Loading ---
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // --- Not found ---
  if (!collection) {
    return (
      <div className="text-center text-muted-foreground py-12">
        <FolderOpen className="mx-auto h-12 w-12 text-muted-foreground/40" />
        <p className="mt-4">Collection not found.</p>
        <Button
          variant="ghost"
          size="sm"
          className="mt-4"
          onClick={() => router.push("/collections")}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Collections
        </Button>
      </div>
    );
  }

  const handleDelete = () => {
    deleteMutation.mutate(collection.id, {
      onSuccess: () => router.push("/collections"),
    });
  };

  const handleRemoveSelected = () => {
    removeMutation.mutate(
      { molecule_ids: selectedIds },
      {
        onSuccess: () => {
          setSelectedIds([]);
          setRemoveOpen(false);
          gridApiRef.current?.deselectAll();
        },
      }
    );
  };

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push("/collections")}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Collections
      </Button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold tracking-tight">
            {collection.name}
          </h1>
          <Badge variant="secondary">
            {collection.molecule_count} molecule
            {collection.molecule_count !== 1 ? "s" : ""}
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditOpen(true)}
          >
            <Pencil className="mr-2 h-4 w-4" />
            Edit
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDeleteOpen(true)}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
          <Button size="sm" onClick={() => setAddMolOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add Molecules
          </Button>
        </div>
      </div>

      {/* Metadata Card */}
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
            <div>
              <p className="text-sm text-muted-foreground">Description</p>
              <p className="font-medium">
                {collection.description || "\u2014"}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Project</p>
              <p className="font-medium">
                {project ? (
                  <Button
                    variant="link"
                    className="h-auto p-0 text-base font-medium"
                    onClick={() => router.push(`/projects/${project.id}`)}
                  >
                    {project.name}
                  </Button>
                ) : (
                  "\u2014"
                )}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Organization</p>
              <p className="font-medium">
                {collection.owned_by_org_id ? (
                  <OrgName id={collection.owned_by_org_id} />
                ) : (
                  "\u2014"
                )}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Created By</p>
              <p className="font-mono text-sm">
                {collection.created_by.slice(0, 8)}...
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Molecules Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Molecules</CardTitle>
            {selectedIds.length > 0 && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setRemoveOpen(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Remove Selected ({selectedIds.length})
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <DataGrid<MoleculeRow>
            rowData={moleculeRows}
            columnDefs={columnDefs}
            loading={moleculesLoading}
            height="400px"
            suppressFilters
            rowSelection="multiple"
            onSelectionChanged={(e) => {
              const rows = e.api.getSelectedRows();
              setSelectedIds(rows.map((r) => r.id));
              gridApiRef.current = e.api;
            }}
            emptyState={
              <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
                <FolderOpen className="h-10 w-10 text-muted-foreground/40" />
                <p className="mt-3 text-sm text-muted-foreground">
                  No molecules in this collection yet.
                </p>
                <Button
                  className="mt-3"
                  size="sm"
                  onClick={() => setAddMolOpen(true)}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Add Molecules
                </Button>
              </div>
            }
          />
        </CardContent>
      </Card>

      {/* Edit dialog */}
      <CreateCollectionDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        collection={collection}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete collection?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete &ldquo;{collection.name}&rdquo; and
              remove all molecule associations. The molecules themselves will not
              be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Remove molecules confirmation */}
      <AlertDialog open={removeOpen} onOpenChange={setRemoveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove molecules?</AlertDialogTitle>
            <AlertDialogDescription>
              Remove {selectedIds.length} molecule
              {selectedIds.length !== 1 ? "s" : ""} from this collection? The
              molecules themselves will not be deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRemoveSelected}
              disabled={removeMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {removeMutation.isPending ? "Removing..." : "Remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Add Molecules dialog */}
      <AddMoleculesDialog
        collectionId={collectionId}
        open={addMolOpen}
        onOpenChange={setAddMolOpen}
      />
    </div>
  );
}
