"use client";

import { useMemo, type ReactNode } from "react";
import type { ColDef } from "ag-grid-community";
import { ExternalLink } from "lucide-react";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import type { Molecule } from "@/features/chemical-registration/types";
import type { ActivityValue } from "../../types";
import type { ViewMode } from "../../lib/use-view-mode";
import { ViewModeToggle } from "./view-mode-toggle";
import { CardGrid } from "./card-grid";

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
  /**
   * Optional activity data to pass to card-view tiles for sparkline rendering.
   * Keyed by molecule ID → column ID → ActivityValue.
   * Ignored in table mode (V1.5: table-view activity columns are a V2 follow-up).
   */
  activityData?: Record<string, Record<string, ActivityValue>>;
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
  activityData,
}: ResultsSurfaceProps) {
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

  return (
    <div className="flex flex-col gap-3">
      {showToolbar && (
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">{toolbarLeft}</div>
          <div className="flex items-center gap-2">
            {toolbarRight}
            <ViewModeToggle mode={mode} onChange={onModeChange} />
          </div>
        </div>
      )}

      {mode === "cards" ? (
        <CardGrid
          molecules={molecules}
          selectedIds={selectedIds}
          onSelectChange={onSelectChange}
          onOpen={onOpen}
          isLoading={isLoading}
          activityData={activityData}
        />
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
