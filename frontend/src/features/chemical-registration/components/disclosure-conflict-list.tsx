"use client";

import { useState, useMemo } from "react";
import { AlertTriangle } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { useConflictDisclosures } from "../hooks/use-disclosures";
import type { DisclosureRequest } from "../types/disclosure";
import { ResolveConflictDialog } from "./resolve-conflict-dialog";

export function DisclosureConflictList() {
  const { data: conflicts, isLoading } = useConflictDisclosures();
  const [selected, setSelected] = useState<DisclosureRequest | null>(null);

  const columnDefs = useMemo<ColDef<DisclosureRequest>[]>(
    () => [
      {
        headerName: "Molecule ID",
        field: "molecule_id",
        flex: 1,
        minWidth: 120,
        cellClass: "font-mono text-xs",
        valueFormatter: (p) => p.value?.slice(0, 8) ?? "",
      },
      {
        headerName: "Disclosed SMILES",
        field: "disclosed_smiles",
        flex: 2,
        minWidth: 200,
        cellClass: "font-mono text-xs",
      },
      {
        headerName: "Conflict Reason",
        field: "conflict_reason",
        flex: 1,
        minWidth: 150,
        cellClass: "text-sm",
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Requested",
        field: "requested_at",
        width: 120,
        valueFormatter: (p) =>
          p.value ? new Date(p.value).toLocaleDateString() : "",
      },
      {
        headerName: "Status",
        field: "status",
        width: 100,
        cellRenderer: () => (
          <Badge variant="destructive">Conflict</Badge>
        ),
      },
      {
        headerName: "",
        width: 100,
        sortable: false,
        filter: false,
        cellRenderer: (params: ICellRendererParams<DisclosureRequest>) => {
          if (!params.data) return null;
          return (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelected(params.data!)}
            >
              Resolve
            </Button>
          );
        },
      },
    ],
    []
  );

  return (
    <>
      <DataGrid<DisclosureRequest>
        rowData={conflicts}
        columnDefs={columnDefs}
        loading={isLoading}
        height="400px"
        suppressFilters
        emptyState={
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
            <AlertTriangle className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-semibold">No conflicts</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              All disclosure requests have been resolved.
            </p>
          </div>
        }
      />

      {selected && (
        <ResolveConflictDialog
          disclosure={selected}
          open={!!selected}
          onOpenChange={(open) => !open && setSelected(null)}
        />
      )}
    </>
  );
}
