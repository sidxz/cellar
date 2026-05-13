"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Download,
  FolderOpen,
  Pencil,
  Plus,
  Trash2,
  ExternalLink,
} from "lucide-react";
import type { ColDef } from "ag-grid-community";
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
import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { DetailShell } from "@/shared/components/detail-shell";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { MemberName, MoleculeName, OrgName } from "@/shared/components/entity-name";
import {
  useCollection,
  useDeleteCollection,
} from "../hooks/use-collections";
import { useCollectionMolecules, useRemoveMolecules } from "../hooks/use-collection-molecules";
import { useProject } from "../hooks/use-projects";
import { useSdfExport } from "@/features/chemical-registration/hooks/use-sdf-export";
import { CreateCollectionDialog } from "./create-collection-dialog";
import { AddMoleculesDialog } from "./add-molecules-dialog";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { AdminDeleteButton } from "@/shared/components/admin-delete-button";

interface CollectionDetailProps {
  collectionId: string;
}

interface MoleculeRow {
  id: string;
}

export function CollectionDetail({ collectionId }: CollectionDetailProps) {
  const router = useRouter();
  const isAdmin = useAuthzHasRole("admin");
  const query = useCollection(collectionId);
  const { data: moleculeIds, isLoading: moleculesLoading } =
    useCollectionMolecules(collectionId);
  const { data: project } = useProject(query.data?.project_id ?? undefined);
  const deleteMutation = useDeleteCollection();
  const removeMutation = useRemoveMolecules(collectionId);

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [addMolOpen, setAddMolOpen] = useState(false);
  const [removeIds, setRemoveIds] = useState<string[]>([]);
  const [removeOpen, setRemoveOpen] = useState(false);

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

  const { exportSdf } = useSdfExport();
  const handleExportSdf = useCallback(() => {
    if (!moleculeIds?.length) return;
    exportSdf(moleculeIds, `${query.data?.name ?? "collection"}.sdf`);
  }, [moleculeIds, query.data?.name, exportSdf]);

  const handleDelete = () => {
    if (query.data) {
      deleteMutation.mutate(query.data.id, {
        onSuccess: () => router.push("/collections"),
      });
    }
  };

  const handleRemoveSelected = async () => {
    await removeMutation.mutateAsync({ molecule_ids: removeIds });
    setRemoveIds([]);
    setRemoveOpen(false);
  };

  return (
    <>
      <DetailShell
        query={query}
        backHref="/collections"
        backLabel="Back to Collections"
        title={(c) => c.name}
        notFoundMessage="Collection not found."
        actions={() => (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportSdf}
              disabled={!moleculeIds?.length}
            >
              <Download className="mr-2 h-4 w-4" />
              Export SDF
            </Button>
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
            {isAdmin && (
              <AdminDeleteButton
                entityType="collection"
                entityId={collectionId}
                entityLabel={query.data?.name ?? collectionId}
                onDeleted={() => router.push("/collections")}
              />
            )}
          </>
        )}
      >
        {(collection) => (
          <>
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
                    <p className="text-sm font-medium">
                      <MemberName id={collection.created_by} />
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Molecules Section */}
            <Card>
              <CardHeader>
                <CardTitle>
                  Molecules
                  <Badge variant="secondary" className="ml-2">
                    {collection.molecule_count} molecule
                    {collection.molecule_count !== 1 ? "s" : ""}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <DataGrid<MoleculeRow>
                  rowData={moleculeRows}
                  columnDefs={columnDefs}
                  loading={moleculesLoading}
                  height="400px"
                  suppressFilters
                  selectionToolbar={(selected) => (
                    <>
                      <span className="text-sm text-muted-foreground">
                        {selected.length} selected
                      </span>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => {
                          setRemoveIds(selected.map((r) => r.id));
                          setRemoveOpen(true);
                        }}
                      >
                        Remove Selected
                      </Button>
                    </>
                  )}
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
          </>
        )}
      </DetailShell>

      {/* Edit dialog */}
      <CreateCollectionDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        collection={query.data}
      />

      {/* Delete confirmation */}
      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete collection?"
        description={`This will permanently delete "${query.data?.name ?? ""}" and remove all molecule associations. The molecules themselves will not be deleted.`}
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
      />

      {/* Remove molecules confirmation */}
      <AlertDialog open={removeOpen} onOpenChange={setRemoveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove molecules?</AlertDialogTitle>
            <AlertDialogDescription>
              Remove {removeIds.length} molecule
              {removeIds.length !== 1 ? "s" : ""} from this collection? The
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
    </>
  );
}
