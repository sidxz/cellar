"use client";

import { useSdfExport } from "@/features/chemical-registration/hooks/use-sdf-export";
import { TagTable } from "@/features/tagging/components/tag-table";
import { AdminDeleteButton } from "@/shared/components/admin-delete-button";
import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { DetailShell } from "@/shared/components/detail-shell";
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
import { Button } from "@/shared/components/ui/button";
import { useAuthzHasRole } from "@sentinel-auth/nextjs";
import { Download, Pencil, Plus, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useRemoveMolecules } from "../hooks/use-collection-molecules";
import { useCollectionSearch } from "../hooks/use-collection-search";
import { useCollection, useDeleteCollection } from "../hooks/use-collections";
import { useProject, useProjects } from "../hooks/use-projects";
import { useProtocolTestCounts } from "../hooks/use-protocol-test-counts";
import { useViewMode } from "../lib/use-view-mode";
import type { ViewMode } from "../lib/use-view-mode";
import { AddMoleculesDialog } from "./add-molecules-dialog";
import { CollectionHeader } from "./collection/collection-header";
import { CreateCollectionDialog } from "./create-collection-dialog";
import { ResultsSurface } from "./results/results-surface";
import { ViewModeToggle } from "./results/view-mode-toggle";

const FROZEN_TOOLTIP = "Frozen collection — unfreeze to modify.";

interface CollectionDetailProps {
  collectionId: string;
}

export function CollectionDetail({ collectionId }: CollectionDetailProps) {
  const router = useRouter();
  const isAdmin = useAuthzHasRole("admin");
  const canEditTags = useAuthzHasRole("editor");
  const query = useCollection(collectionId);
  const { data: project } = useProject(query.data?.project_id ?? undefined);
  const { data: allProjects } = useProjects();

  const search = useCollectionSearch(collectionId);
  const deleteMutation = useDeleteCollection();
  const removeMutation = useRemoveMolecules(collectionId);
  const { mode, setMode } = useViewMode("cards");

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [addMolOpen, setAddMolOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const molecules = search.data?.items ?? [];

  // Molecule IDs memoized so the test-count query key is stable.
  const moleculeIds = useMemo(() => molecules.map((m) => m.id), [molecules]);
  const { data: testCounts } = useProtocolTestCounts(moleculeIds, query.data?.project_id ?? null);

  // Cluster view: disabled when molecule count is below the UMAP threshold.
  const clusterDisabledModes = useMemo<Set<ViewMode>>(() => {
    const s = new Set<ViewMode>();
    if (molecules.length < 10) s.add("clusters");
    return s;
  }, [molecules.length]);

  // Projects list shape for the cluster view's Save-as-collection dialog.
  const clusterProjects = useMemo(
    () => (allProjects ?? []).map((p) => ({ id: p.id, name: p.name })),
    [allProjects],
  );

  const onSelectChange = useCallback((id: string, selected: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (selected) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const onOpen = useCallback((id: string) => router.push(`/compounds/${id}`), [router]);

  const { exportSdf } = useSdfExport();
  const handleExportSdf = useCallback(() => {
    const ids = molecules.map((m) => m.id);
    if (!ids.length) return;
    exportSdf(ids, `${query.data?.name ?? "collection"}.sdf`);
  }, [molecules, query.data?.name, exportSdf]);

  const handleDelete = () => {
    if (query.data) {
      deleteMutation.mutate(query.data.id, {
        onSuccess: () => router.push("/collections"),
      });
    }
  };

  const handleRemoveSelected = async () => {
    await removeMutation.mutateAsync({ molecule_ids: Array.from(selectedIds) });
    setSelectedIds(new Set());
    setRemoveOpen(false);
  };

  const isFrozen = query.data?.is_frozen ?? false;

  const selectionToolbar = useMemo(() => {
    if (selectedIds.size === 0) return null;
    return (
      <>
        <span className="text-xs text-muted-foreground">{selectedIds.size} selected</span>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => setRemoveOpen(true)}
          disabled={isFrozen}
          title={isFrozen ? FROZEN_TOOLTIP : undefined}
        >
          Remove
        </Button>
      </>
    );
  }, [selectedIds.size, isFrozen]);

  return (
    <>
      <DetailShell
        query={query}
        title={(c) => c.name}
        notFoundMessage="Collection not found."
        actions={() => (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExportSdf}
              disabled={!molecules.length}
            >
              <Download className="mr-2 h-4 w-4" />
              Export SDF
            </Button>
            <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
              <Pencil className="mr-2 h-4 w-4" />
              Edit
            </Button>
            <Button variant="outline" size="sm" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
            <Button
              size="sm"
              onClick={() => setAddMolOpen(true)}
              disabled={isFrozen}
              title={isFrozen ? FROZEN_TOOLTIP : undefined}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add Molecules
            </Button>
            <Link href={`/collections/${collectionId}/import`}>
              <Button
                variant="outline"
                size="sm"
                disabled={isFrozen}
                title={isFrozen ? FROZEN_TOOLTIP : undefined}
              >
                <Upload className="mr-2 h-4 w-4" />
                Bulk import
              </Button>
            </Link>
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
          <div className="flex flex-col gap-4">
            <CollectionHeader
              collection={{
                id: collection.id,
                name: collection.name,
                description: collection.description,
                project_id: collection.project_id,
                owned_by_org_id: collection.owned_by_org_id,
                created_by: collection.created_by,
                visibility: collection.visibility,
                molecule_count: collection.molecule_count,
                is_frozen: collection.is_frozen ?? false,
                type: collection.type,
                derived_from_campaign_id: collection.derived_from_campaign_id,
              }}
              projectName={project?.name}
              rightSlot={
                <>
                  {selectionToolbar}
                  <ViewModeToggle
                    mode={mode}
                    onChange={setMode}
                    disabledModes={clusterDisabledModes}
                  />
                </>
              }
            />

            <div className="mt-0.5">
              <TagTable entity="collections" entityId={collection.id} canEdit={canEditTags} />
            </div>

            <ResultsSurface
              molecules={molecules}
              mode={mode}
              onModeChange={setMode}
              selectedIds={selectedIds}
              onSelectChange={onSelectChange}
              onOpen={onOpen}
              isLoading={search.isLoading}
              showToolbar={false}
              testCounts={testCounts}
              collectionId={collection.id}
              clusterProjects={clusterProjects}
              clusterDefaultProjectId={collection.project_id ?? null}
              clusterSourceLabel={collection.name}
            />
          </div>
        )}
      </DetailShell>

      <CreateCollectionDialog open={editOpen} onOpenChange={setEditOpen} collection={query.data} />

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete collection?"
        description={`This will permanently delete "${query.data?.name ?? ""}" and remove all molecule associations. The molecules themselves will not be deleted.`}
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
      />

      <AlertDialog open={removeOpen} onOpenChange={setRemoveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove molecules?</AlertDialogTitle>
            <AlertDialogDescription>
              Remove {selectedIds.size} molecule{selectedIds.size === 1 ? "" : "s"} from this
              collection? The molecules themselves will not be deleted.
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

      <AddMoleculesDialog
        collectionId={collectionId}
        open={addMolOpen}
        onOpenChange={setAddMolOpen}
      />
    </>
  );
}
