"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type {
  ColDef,
  ColGroupDef,
  ICellRendererParams,
  RowClickedEvent,
  GridReadyEvent,
  SelectionChangedEvent,
} from "ag-grid-community";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Badge } from "@/shared/components/ui/badge";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { chemVaultTheme } from "@/shared/components/data-grid/ag-grid-theme";
import type { Molecule } from "@/features/chemical-registration/types";
import type { Protocol } from "@/features/screening-assay/types";
import type { ActivityValue, ReportConfig } from "../../types";
import { DoseResponseCell } from "./dose-response-cell";

// ─── Types ──────────────────────────────────────────────────────────────────

type EnrichedMolecule = Molecule & { activity?: Record<string, ActivityValue> };

interface ResultsGridProps {
  results: EnrichedMolecule[];
  protocolColumns: string[];
  protocols: Protocol[];
  reportConfig: ReportConfig;
  loading: boolean;
  onRowClick: (molecule: EnrichedMolecule) => void;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
}

// ─── Row height by image size ───────────────────────────────────────────────

const ROW_HEIGHTS: Record<string, number> = {
  small: 80,
  medium: 150,
  large: 250,
};

// ─── Curve class badge colors ───────────────────────────────────────────────

function CurveClassBadge({ curveClass }: { curveClass: string | null }) {
  if (!curveClass) return null;
  const upper = curveClass.toUpperCase();
  let colorClass = "";
  if (upper === "F" || upper === "FULL")
    colorClass = "bg-emerald-500/12 text-emerald-400";
  else if (upper === "P" || upper === "PARTIAL")
    colorClass = "bg-yellow-500/12 text-yellow-400";
  else if (upper === "I" || upper === "INACTIVE")
    colorClass = "bg-red-500/12 text-red-400";

  return (
    <Badge
      className={`ml-1.5 text-[10px] px-1 py-0 border-0 ${colorClass}`}
    >
      {upper.charAt(0)}
    </Badge>
  );
}

// ─── Column builders ────────────────────────────────────────────────────────

function buildFixedColumns(
  imageSize: string,
): ColDef<EnrichedMolecule>[] {
  const thumbSize = imageSize === "large" ? 200 : imageSize === "medium" ? 120 : 56;

  return [
    {
      headerCheckboxSelection: true,
      checkboxSelection: true,
      width: 48,
      sortable: false,
      filter: false,
      pinned: "left",
      suppressMovable: true,
      headerName: "",
    },
    {
      headerName: "Molecule",
      width: imageSize === "large" ? 280 : imageSize === "medium" ? 220 : 180,
      pinned: "left",
      sortable: false,
      filter: false,
      cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
        const mol = params.data;
        if (!mol) return null;
        const smiles = mol.structure?.smiles;
        return (
          <div className="flex items-center gap-2 py-1">
            {smiles ? (
              <StructureThumbnail smiles={smiles} size={thumbSize} />
            ) : (
              <div
                className="shrink-0 rounded bg-muted"
                style={{ width: thumbSize, height: thumbSize }}
              />
            )}
            <div className="min-w-0">
              <p className="truncate font-mono text-xs text-muted-foreground">
                {mol.registration_number ?? "\u2014"}
              </p>
              <p className="truncate text-sm font-medium">
                {mol.name || "Unnamed"}
              </p>
            </div>
          </div>
        );
      },
    },
  ];
}

function buildPropertyColumns(
  visibleProperties: string[],
): ColDef<EnrichedMolecule>[] {
  const cols: ColDef<EnrichedMolecule>[] = [];

  if (visibleProperties.includes("molecular_weight")) {
    cols.push({
      headerName: "MW",
      width: 90,
      valueGetter: (p) => p.data?.descriptors?.molecular_weight ?? null,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(1) : "\u2014",
    });
  }

  if (visibleProperties.includes("logp")) {
    cols.push({
      headerName: "LogP",
      width: 80,
      valueGetter: (p) => p.data?.descriptors?.logp ?? null,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(2) : "\u2014",
    });
  }

  if (visibleProperties.includes("tpsa")) {
    cols.push({
      headerName: "TPSA",
      width: 80,
      valueGetter: (p) => p.data?.descriptors?.tpsa ?? null,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(1) : "\u2014",
    });
  }

  return cols;
}

function buildProtocolColumnGroups(
  protocolColumns: string[],
  protocols: Protocol[],
): ColGroupDef[] {
  // Group columns by protocol ID
  const grouped = new Map<string, string[]>();
  for (const colId of protocolColumns) {
    const parts = colId.split(":");
    if (parts[0] !== "drc" || !parts[1]) continue;
    const protoId = parts[1];
    if (!grouped.has(protoId)) grouped.set(protoId, []);
    grouped.get(protoId)!.push(colId);
  }

  const groups: ColGroupDef[] = [];
  for (const [protoId, colIds] of grouped) {
    const proto = protocols.find((p) => p.id === protoId);
    const headerName = proto?.name ?? "Protocol";

    const children: ColDef<EnrichedMolecule>[] = [];

    for (const colId of colIds) {
      const curveType = colId.split(":")[2]?.toUpperCase() ?? "";

      // Fitted value column
      children.push({
        headerName: curveType,
        width: 120,
        valueGetter: (p) => p.data?.activity?.[colId]?.value ?? null,
        cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
          const av = params.data?.activity?.[colId];
          if (!av?.value) {
            return <span className="text-muted-foreground">&mdash;</span>;
          }
          const q =
            av.qualifier && av.qualifier !== "=" ? `${av.qualifier} ` : "";
          return (
            <span className="inline-flex items-center font-mono text-xs">
              {q}
              {av.value.toPrecision(4)}
              {av.unit ? ` ${av.unit}` : ""}
              <CurveClassBadge
                curveClass={av.curve_params?.curve_class ?? null}
              />
            </span>
          );
        },
      });

      // Plot column
      children.push({
        headerName: `${curveType} Plot`,
        width: 240,
        sortable: false,
        filter: false,
        cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
          const av = params.data?.activity?.[colId];
          return <DoseResponseCell value={av} />;
        },
      });
    }

    groups.push({
      headerName,
      headerClass: "ag-protocol-group-header",
      children,
    });
  }

  return groups;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function ResultsGrid({
  results,
  protocolColumns,
  protocols,
  reportConfig,
  loading,
  onRowClick,
  selectedIds,
  onSelectionChange,
}: ResultsGridProps) {
  const gridRef = useRef<AgGridReact<EnrichedMolecule>>(null);

  const rowHeight = ROW_HEIGHTS[reportConfig.imageSize] ?? 150;

  const columnDefs = useMemo<(ColDef<EnrichedMolecule> | ColGroupDef)[]>(() => {
    const fixed = buildFixedColumns(reportConfig.imageSize);
    const props = buildPropertyColumns(
      reportConfig.visibleFields.properties,
    );
    const protoGroups = buildProtocolColumnGroups(protocolColumns, protocols);
    return [...fixed, ...props, ...protoGroups];
  }, [reportConfig.imageSize, reportConfig.visibleFields.properties, protocolColumns, protocols]);

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      resizable: true,
      filter: false,
      suppressMovable: true,
      minWidth: 60,
    }),
    [],
  );

  const handleRowClicked = useCallback(
    (event: RowClickedEvent<EnrichedMolecule>) => {
      if (!event.data) return;
      const target = event.event?.target as HTMLElement | null;
      if (target?.closest("button, a, [role='button'], input[type='checkbox']"))
        return;
      onRowClick(event.data);
    },
    [onRowClick],
  );

  const handleGridReady = useCallback((event: GridReadyEvent) => {
    event.api.sizeColumnsToFit();
  }, []);

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<EnrichedMolecule>) => {
      const rows = event.api.getSelectedRows();
      onSelectionChange(new Set(rows.map((r) => r.id)));
    },
    [onSelectionChange],
  );

  // Sync grid selection when parent clears selectedIds (e.g. after search reset)
  useEffect(() => {
    if (selectedIds.size === 0) {
      gridRef.current?.api?.deselectAll();
    }
  }, [selectedIds.size]);

  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        No results to display.
      </p>
    );
  }

  return (
    <div style={{ height: "100%", width: "100%" }}>
      <style>{`
        .ag-protocol-group-header .ag-header-group-cell-label {
          color: hsl(var(--primary)) !important;
          font-weight: 600;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }
      `}</style>
      <AgGridReact<EnrichedMolecule>
        ref={gridRef}
        theme={chemVaultTheme}
        rowData={results}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        rowHeight={rowHeight}
        headerHeight={36}
        groupHeaderHeight={32}
        onRowClicked={handleRowClicked}
        onGridReady={handleGridReady}
        onSelectionChanged={handleSelectionChanged}
        rowSelection="multiple"
        suppressCellFocus
        animateRows={false}
      />
    </div>
  );
}
