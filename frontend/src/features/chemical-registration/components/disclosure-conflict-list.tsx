"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { MoleculeName } from "@/shared/components/entity-name";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { formatDate } from "@/shared/lib/format-date";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AlertTriangle } from "lucide-react";
import { useMemo, useState } from "react";
import { useConflictDisclosures } from "../hooks/use-disclosures";
import type { DisclosureRequest } from "../types/disclosure";
import { ResolveConflictDialog } from "./resolve-conflict-dialog";

export function DisclosureConflictList() {
  const { data: conflicts, isLoading } = useConflictDisclosures();
  const [selected, setSelected] = useState<DisclosureRequest | null>(null);

  const columnDefs = useMemo<ColDef<DisclosureRequest>[]>(
    () => [
      {
        headerName: "Compound",
        field: "molecule_id",
        flex: 1,
        minWidth: 160,
        cellRenderer: (params: ICellRendererParams<DisclosureRequest>) =>
          params.value ? <MoleculeName id={params.value} /> : "\u2014",
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
        valueFormatter: (p) => (p.value ? formatDate(p.value) : ""),
      },
      {
        headerName: "Status",
        field: "status",
        width: 100,
        cellRenderer: () => <Badge variant="destructive">Conflict</Badge>,
      },
      {
        headerName: "",
        width: 100,
        sortable: false,
        filter: false,
        cellRenderer: (params: ICellRendererParams<DisclosureRequest>) => {
          const data = params.data;
          if (!data) return null;
          return (
            <Button variant="outline" size="sm" onClick={() => setSelected(data)}>
              Resolve
            </Button>
          );
        },
      },
    ],
    [],
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
          <EmptyState
            icon={AlertTriangle}
            title="No conflicts"
            description="All disclosure requests have been resolved."
          />
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
