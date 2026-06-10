"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { ClusterMapView } from "@/features/sar-analysis/components/cluster-map-view";
import type { ProtocolOption } from "@/features/sar-analysis/components/color-mode-picker";
import { SarView } from "@/features/sar-analysis/components/sar-view";
import { ScaffoldTreeView } from "@/features/sar-analysis/components/scaffold-tree-view";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Button } from "@/shared/components/ui/button";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { ColDef } from "ag-grid-community";
import { ExternalLink } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ReactNode, useCallback, useMemo } from "react";
import { useCreateCollection } from "../../hooks/use-collections";
import type { ViewMode } from "../../lib/use-view-mode";
import type { MembershipResult } from "../../types";
import { CardGrid } from "./card-grid";
import { ViewModeToggle } from "./view-mode-toggle";

// Minimum molecule count for the cluster view to be enabled.
const MIN_MOLS_FOR_CLUSTER = 10;
// Minimum molecule count for the SAR view to be meaningful.
const MIN_MOLS_FOR_SAR = 3;

export interface ResultsSurfaceProps {
  molecules: Molecule[];
  mode: ViewMode;
  onModeChange: (mode: ViewMode) => void;
  selectedIds: Set<string>;
  onSelectChange: (moleculeId: string, selected: boolean) => void;
  onOpen: (moleculeId: string) => void;
  isLoading?: boolean;
  /** Optional toolbar content rendered to the left of the toggle. */
  toolbarLeft?: ReactNode;
  /** Optional toolbar content rendered to the right of the toggle. */
  toolbarRight?: ReactNode;
  /**
   * When false, the internal toolbar row (view-mode toggle + toolbarLeft/toolbarRight slots)
   * is not rendered. Use this when the parent page owns the toggle externally.
   * @default true
   */
  showToolbar?: boolean;
  /** Optional protocol test counts keyed by molecule ID. Rendered on card tiles. */
  testCounts?: Record<string, number>;
  /**
   * Activity data keyed by molecule ID → protocol ID → ActivityValue.
   * Required for the scaffold-tree view's color-by-protocol feature.
   * When absent, the tree renders without activity coloring.
   */
  activityData?: Record<string, Record<string, any>>;
  /**
   * Optional collection identifier. When set, the scaffold-tree view computes
   * against the full collection on the BE (bypassing the search-pagination
   * cap) instead of the visible page of `molecules`. The cards on the right
   * pane still render the paginated visible set.
   */
  collectionId?: string;

  // ── Cluster view props ────────────────────────────────────────────────────

  /**
   * Protocol list for the cluster-view color-by-activity picker.
   * When empty the picker defaults to "Cluster" coloring.
   */
  clusterProtocols?: ProtocolOption[];
  /** Default protocol to use for activity coloring in the cluster view. */
  clusterDefaultProtocolId?: string | null;
  /**
   * Projects list for the Save-as-collection dialog inside the cluster view.
   * When omitted the dialog still works but the project picker is empty.
   */
  clusterProjects?: { id: string; name: string }[];
  /** Project to pre-select in the Save-as-collection dialog. */
  clusterDefaultProjectId?: string | null;
  /**
   * Human-readable label for the current data source (collection name or
   * "Search results"). Used in the default name for saved selections.
   */
  clusterSourceLabel?: string;
}

interface TableRow {
  id: string;
  name: string | null;
  registration_number: string | null;
  smiles: string | null;
  selected: boolean;
}

export function ResultsSurface({
  molecules,
  mode,
  onModeChange,
  selectedIds,
  onSelectChange,
  onOpen,
  isLoading = false,
  toolbarLeft,
  toolbarRight,
  showToolbar = true,
  testCounts,
  activityData,
  collectionId,
  clusterProtocols = [],
  clusterDefaultProtocolId = null,
  clusterProjects = [],
  clusterDefaultProjectId = null,
  clusterSourceLabel = "Search results",
}: ResultsSurfaceProps) {
  const router = useRouter();
  const createCollection = useCreateCollection();

  const tableRows: TableRow[] = useMemo(
    () =>
      molecules.map((m) => ({
        id: m.id,
        name: m.name ?? null,
        registration_number: m.registration_number ?? null,
        smiles: m.structure?.smiles ?? null,
        selected: selectedIds.has(m.id),
      })),
    [molecules, selectedIds],
  );

  const columnDefs: ColDef<TableRow>[] = useMemo(
    () => [
      {
        headerName: "",
        width: 120,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data?: TableRow }) =>
          data?.smiles ? (
            <div className="flex items-center justify-center h-full">
              <StructureThumbnail smiles={data.smiles} size={56} />
            </div>
          ) : null,
      },
      {
        headerName: "ID",
        field: "registration_number",
        width: 140,
      },
      {
        headerName: "Name",
        field: "name",
        flex: 1,
        minWidth: 200,
      },
      {
        headerName: "",
        width: 80,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data?: TableRow }) =>
          data ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => onOpen(data.id)}
              aria-label={`open ${data.name ?? data.id}`}
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </Button>
          ) : null,
      },
    ],
    [onOpen],
  );

  // Disabled modes: cluster requires MIN_MOLS_FOR_CLUSTER molecules; SAR needs
  // at least MIN_MOLS_FOR_SAR to be worth analysing.
  const disabledModes = useMemo<Set<ViewMode>>(() => {
    const disabled = new Set<ViewMode>();
    if (molecules.length < MIN_MOLS_FOR_CLUSTER) disabled.add("clusters");
    if (molecules.length < MIN_MOLS_FOR_SAR) disabled.add("sar");
    return disabled;
  }, [molecules.length]);

  // Save-as-collection handler for the cluster view: creates a new collection,
  // bulk-adds the selected molecules, then navigates to it in cluster mode.
  const handleSaveClusterCollection = useCallback(
    async (args: { name: string; projectId: string | null; moleculeIds: string[] }) => {
      // Step 1: create the collection.
      const newCollection = await new Promise<{ id: string }>((resolve, reject) => {
        createCollection.mutate(
          { name: args.name, project_id: args.projectId },
          {
            onSuccess: (c) => resolve(c as { id: string }),
            onError: (err) => reject(err),
          },
        );
      });

      // Step 2: add the selected molecules to the new collection.
      if (args.moleculeIds.length > 0) {
        await customInstance<MembershipResult>({
          url: `${API_V1}/collections/${newCollection.id}/molecules`,
          method: "POST",
          data: {
            references: args.moleculeIds.map((id) => ({
              value: id,
              ref_type: "uuid",
            })),
          },
        });
      }

      // Step 3: navigate to the new collection in cluster view.
      router.push(`/collections/${newCollection.id}?view=clusters`);
    },
    [createCollection, router],
  );

  return (
    <div className="flex flex-col gap-3">
      {showToolbar && (
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">{toolbarLeft}</div>
          <div className="flex items-center gap-2">
            {toolbarRight}
            <ViewModeToggle mode={mode} onChange={onModeChange} disabledModes={disabledModes} />
          </div>
        </div>
      )}

      {mode === "scaffold-tree" ? (
        <ScaffoldTreeView
          molecules={molecules}
          activityData={activityData ?? {}}
          collectionId={collectionId}
          onOpen={onOpen}
        />
      ) : mode === "clusters" ? (
        <ClusterMapView
          molecules={molecules}
          collectionId={collectionId}
          protocols={clusterProtocols}
          defaultColorProtocolId={clusterDefaultProtocolId}
          onSaveCollection={handleSaveClusterCollection}
          projects={clusterProjects}
          defaultProjectId={clusterDefaultProjectId}
          sourceLabel={clusterSourceLabel}
        />
      ) : mode === "sar" ? (
        <SarView
          molecules={molecules}
          collectionId={collectionId}
          projects={clusterProjects ?? []}
          defaultProjectId={clusterDefaultProjectId ?? null}
          sourceLabel={clusterSourceLabel ?? "this set"}
        />
      ) : mode === "cards" ? (
        <div className="h-[calc(100vh-14rem)] min-h-[480px]">
          <CardGrid
            molecules={molecules}
            selectedIds={selectedIds}
            onSelectChange={onSelectChange}
            onOpen={onOpen}
            isLoading={isLoading}
            testCounts={testCounts}
          />
        </div>
      ) : (
        <DataGrid<TableRow>
          rowData={tableRows}
          columnDefs={columnDefs}
          loading={isLoading}
          height="70vh"
          rowHeight={72}
          suppressFilters
        />
      )}
    </div>
  );
}
