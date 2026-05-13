"use client";

import { useMemo } from "react";
import {
  type ColDef,
  type ColGroupDef,
  type ICellRendererParams,
} from "ag-grid-community";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { groupBy } from "@/shared/lib/group-by";
import type { Molecule } from "@/features/chemical-registration/types";
import { READOUT_NORMALIZATION_LABELS, type Protocol } from "@/features/screening-assay/types";
import { CurveClassBadge } from "@/features/screening-assay/components/curve-class-badge";
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
  small: 120,
  medium: 220,
  large: 330,
};

// ─── Similarity column ─────────────────────────────────────────────────────

function similarityBarColor(score: number): string {
  // Anchored at the same thresholds the literature uses (and that the mode
  // defaults expose): >=0.85 near-analog, >=0.70 similar, >=0.40 loose.
  if (score >= 0.85) return "bg-success/70";
  if (score >= 0.7) return "bg-success/50";
  if (score >= 0.55) return "bg-yellow-500/60";
  if (score >= 0.4) return "bg-yellow-500/40";
  return "bg-muted-foreground/30";
}

function buildSimilarityColumn(): ColDef<EnrichedMolecule> {
  return {
    headerName: "Sim",
    width: 130,
    headerTooltip:
      "Similarity score for this row, computed by the cartridge against the search query. " +
      "Range 0–1 (1.0 = identical). Algorithm + metric depend on the active mode.",
    valueGetter: (p) => p.data?.similarity_score ?? null,
    valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(3) : "—"),
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
      const score = params.data?.similarity_score;
      if (score == null) {
        return <span className="text-muted-foreground">—</span>;
      }
      const pct = Math.max(0, Math.min(100, score * 100));
      const color = similarityBarColor(score);
      return (
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tabular-nums">
            {score.toFixed(3)}
          </span>
          <div className="h-1.5 w-12 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full ${color}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      );
    },
  };
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
        p.value != null ? Number(p.value).toFixed(1) : "—",
    });
  }

  if (visibleProperties.includes("logp")) {
    cols.push({
      headerName: "LogP",
      width: 80,
      valueGetter: (p) => p.data?.descriptors?.logp ?? null,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(2) : "—",
    });
  }

  if (visibleProperties.includes("hbd")) {
    cols.push({
      headerName: "HBD",
      width: 70,
      headerTooltip: "Hydrogen-bond donors (Lipinski Rule of Five)",
      valueGetter: (p) => p.data?.descriptors?.hbd ?? null,
      valueFormatter: (p) => (p.value != null ? String(p.value) : "—"),
    });
  }

  if (visibleProperties.includes("hba")) {
    cols.push({
      headerName: "HBA",
      width: 70,
      headerTooltip: "Hydrogen-bond acceptors (Lipinski Rule of Five)",
      valueGetter: (p) => p.data?.descriptors?.hba ?? null,
      valueFormatter: (p) => (p.value != null ? String(p.value) : "—"),
    });
  }

  if (visibleProperties.includes("tpsa")) {
    cols.push({
      headerName: "TPSA",
      width: 80,
      headerTooltip:
        "Topological polar surface area (Veber's rule — predicts permeability)",
      valueGetter: (p) => p.data?.descriptors?.tpsa ?? null,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(1) : "—",
    });
  }

  return cols;
}

function buildProtocolColumnGroups(
  protocolColumns: string[],
  protocols: Protocol[],
): ColGroupDef[] {
  // Group columns by protocol ID — supports both drc: and rd: prefixes
  const validColumns = protocolColumns.filter((colId) => {
    const [prefix, protoId] = colId.split(":");
    return (prefix === "drc" || prefix === "rd") && !!protoId;
  });
  const grouped = groupBy(validColumns, (colId) => colId.split(":")[1]);

  const groups: ColGroupDef[] = [];
  for (const [protoId, colIds] of grouped) {
    const proto = protocols.find((p) => p.id === protoId);
    const headerName = proto?.name ?? "Protocol";

    const children: ColDef<EnrichedMolecule>[] = [];

    for (const colId of colIds) {
      const parts = colId.split(":");
      const prefix = parts[0];

      if (prefix === "rd") {
        // Readout value column — resolve name from protocol's readout definitions.
        // 4-segment IDs (`rd:<p>:<id>:<norm>`) view a specific normalization
        // of the readout (e.g. percent_inhibition). The backend hands us the
        // formula-appropriate unit in `av.unit`, so the header decorates with
        // the formula label and the cell renderer trusts `av.unit`.
        const rdId = parts[2];
        const normalization = parts[3] ?? null;
        const rd = proto?.readout_definitions?.find((r) => r.id === rdId);
        const rdName = rd?.name ?? "Readout";
        const normLabel = normalization
          ? READOUT_NORMALIZATION_LABELS[normalization as keyof typeof READOUT_NORMALIZATION_LABELS] ??
            normalization
          : null;
        const headerSuffix = normLabel
          ? ` (${normLabel})`
          : rd?.unit
            ? ` (${rd.unit})`
            : "";

        children.push({
          headerName: `${rdName}${headerSuffix}`,
          width: 130,
          valueGetter: (p) => p.data?.activity?.[colId]?.value ?? null,
          cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
            const av = params.data?.activity?.[colId];
            if (av?.value == null) {
              return <span className="text-muted-foreground">&mdash;</span>;
            }
            const q = av.qualifier && av.qualifier !== "=" ? `${av.qualifier} ` : "";
            return (
              <span className="font-mono text-xs">
                {q}{av.value.toPrecision(4)}{av.unit ? ` ${av.unit}` : ""}
              </span>
            );
          },
        });
      } else {
        // Dose-response curve columns (drc:)
        const curveType = parts[2]?.toUpperCase() ?? "";

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
                  compact
                  renderNullAs="nothing"
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
    }

    groups.push({
      headerName,
      headerClass: "ag-protocol-group-header",
      children,
    });
  }

  return groups;
}

// Fixed molecule column (structure + identity stack) — no standalone checkbox
// column because DataGrid's suppressSelectColumn + enableMultiSelect lets each
// caller host the checkbox inside the Molecule cell via the grid's built-in
// headerCheckboxSelection. Here we use DataGrid's auto-prepended __select__
// column for simplicity (suppressSelectColumn=false, enableMultiSelect=true).
function buildMoleculeColumn(
  imageSize: string,
): ColDef<EnrichedMolecule> {
  const thumbSize = imageSize === "large" ? 260 : imageSize === "medium" ? 156 : 72;
  return {
    headerName: "Molecule",
    width: imageSize === "large" ? 290 : imageSize === "medium" ? 200 : 130,
    pinned: "left",
    sortable: false,
    filter: false,
    cellStyle: { display: "flex", justifyContent: "center" },
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
      const mol = params.data;
      if (!mol) return null;
      const smiles = mol.structure?.smiles;
      return (
        <div className="flex h-full flex-col items-center justify-center py-2">
          {smiles ? (
            <StructureThumbnail smiles={smiles} size={thumbSize} />
          ) : (
            <div
              className="shrink-0 rounded bg-muted"
              style={{ width: thumbSize, height: thumbSize }}
            />
          )}
          <div className="mt-1 text-center min-w-0 w-full">
            <p className="truncate font-mono text-xs text-muted-foreground">
              {mol.registration_number ?? "—"}
            </p>
            <p className="truncate text-sm">
              {mol.name || "Unnamed"}
            </p>
          </div>
        </div>
      );
    },
  };
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
  const rowHeight = ROW_HEIGHTS[reportConfig.imageSize] ?? 150;

  // Show the similarity column only when at least one row actually carries
  // a score (i.e. the active search was a similarity search). Substructure /
  // exact / property-only searches return null scores and we hide the column.
  const hasSimilarityScores = useMemo(
    () => results.some((r) => r.similarity_score != null),
    [results],
  );

  const columnDefs = useMemo<(ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>)[]>(() => {
    const molecule = buildMoleculeColumn(reportConfig.imageSize);
    const sim = hasSimilarityScores ? [buildSimilarityColumn()] : [];
    const props = buildPropertyColumns(reportConfig.visibleFields.properties);
    const protoGroups = buildProtocolColumnGroups(protocolColumns, protocols);
    return [molecule, ...sim, ...props, ...protoGroups];
  }, [
    reportConfig.imageSize,
    reportConfig.visibleFields.properties,
    protocolColumns,
    protocols,
    hasSimilarityScores,
  ]);

  // When the parent resets selection (selectedIds.size → 0), DataGrid's
  // clearSelectionToken mechanism detects the falsy value and calls deselectAll.
  const clearSelectionToken = selectedIds.size;

  return (
    <>
      <style>{`
        .ag-protocol-group-header .ag-header-group-cell-label {
          color: hsl(var(--primary)) !important;
          font-weight: 600;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }
      `}</style>
      <DataGrid<EnrichedMolecule>
        rowData={results}
        columnDefs={columnDefs}
        loading={loading}
        emptyState={
          <p className="py-12 text-center text-sm text-muted-foreground">
            No results to display.
          </p>
        }
        height="calc(100vh - 80px)"
        rowHeight={rowHeight}
        headerHeight={36}
        groupHeaderHeight={32}
        enableMultiSelect
        suppressSelectColumn
        searchPlaceholder={false}
        onRowClick={onRowClick}
        onSelectionChanged={(event) => {
          const rows = event.api.getSelectedRows();
          onSelectionChange(new Set(rows.map((r) => r.id)));
        }}
        clearSelectionToken={clearSelectionToken}
        suppressCellFocus
        animateRows={false}
      />
    </>
  );
}
