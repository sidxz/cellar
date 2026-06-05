"use client";

import { ExportToolbar as SharedExportToolbar } from "@/shared/components/export/export-toolbar";
import type { ExportFormat, ExportRequest } from "@/shared/components/export/types";
import type { ColDef, ColGroupDef, ICellRendererParams } from "ag-grid-community";
import { useMemo } from "react";

import type { Molecule } from "@/features/chemical-registration/types";
import { CurveClassBadge } from "@/features/screening-assay/components/curve-class-badge";
import {
  findInterceptValue,
  formatInterceptDisplay,
  interceptLabel,
  maxDoseFromRawData,
} from "@/features/screening-assay/lib/intercept-label";
import {
  type InterceptSpec,
  type Protocol,
  READOUT_NORMALIZATION_LABELS,
} from "@/features/screening-assay/types";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Badge } from "@/shared/components/ui/badge";
import { groupBy } from "@/shared/lib/group-by";
import {
  type ResolvedColumn,
  drcColId,
  resolveColumns as resolveColumnsShared,
} from "../../lib/protocol-column-id";
import { type AggregationMode, useAggregationMode } from "../../lib/use-aggregation-mode";
import type { ActivityValue, ReportConfig } from "../../types";
import { DoseResponseCell } from "./dose-response-cell";
import { InterceptCell } from "./intercept-cell";

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
  /** When provided, renders the shared ExportToolbar in the grid toolbar
   *  alongside the other action buttons. The closure captures the current
   *  query / columns / aggregation so exports always reflect what is on
   *  screen. */
  buildExportRequest?: (format: ExportFormat) => ExportRequest | null;
  /** Content for the LEFT side of the grid's toolbar row — e.g. result
   *  count + select-all/none on /search. Shares the row with the export
   *  dropdown so the toolbar collapses to one line instead of two. */
  toolbarLeft?: React.ReactNode;
  /** Action buttons rendered between `toolbarLeft` and the Export dropdown
   *  on the toolbar row. */
  toolbarActions?: React.ReactNode;
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

function formatSimilarityPercent(score: number): string {
  // Match the structure filter's "≥ NN %" UI — integer percent. 1 decimal
  // place would carry more info but creates a unit mismatch with the
  // threshold the chemist just typed.
  return `${Math.round(score * 100)}%`;
}

function buildSimilarityColumn(): ColDef<EnrichedMolecule> {
  return {
    headerName: "Sim",
    width: 130,
    headerTooltip:
      "Similarity score for this row, computed by the cartridge against the search query. " +
      "Expressed as percent (100% = identical) to match the search threshold input. " +
      "Algorithm + metric depend on the active mode.",
    valueGetter: (p) => p.data?.similarity_score ?? null,
    valueFormatter: (p) => (p.value != null ? formatSimilarityPercent(Number(p.value)) : "—"),
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
      const score = params.data?.similarity_score;
      if (score == null) {
        return <span className="text-muted-foreground">—</span>;
      }
      const pct = Math.max(0, Math.min(100, score * 100));
      const color = similarityBarColor(score);
      return (
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tabular-nums">{formatSimilarityPercent(score)}</span>
          <div className="h-1.5 w-12 rounded-full bg-muted overflow-hidden">
            <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
          </div>
        </div>
      );
    },
  };
}

function buildPropertyColumns(visibleProperties: string[]): ColDef<EnrichedMolecule>[] {
  const cols: ColDef<EnrichedMolecule>[] = [];

  if (visibleProperties.includes("molecular_weight")) {
    cols.push({
      headerName: "MW",
      width: 90,
      valueGetter: (p) => p.data?.descriptors?.molecular_weight ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "—"),
    });
  }

  if (visibleProperties.includes("logp")) {
    cols.push({
      headerName: "LogP",
      width: 80,
      valueGetter: (p) => p.data?.descriptors?.logp ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(2) : "—"),
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
      headerTooltip: "Topological polar surface area (Veber's rule — predicts permeability)",
      valueGetter: (p) => p.data?.descriptors?.tpsa ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "—"),
    });
  }

  return cols;
}

// Re-export the shared resolver so existing imports from this module
// (and the colocated test file) keep working. The implementation lives
// in `../../lib/protocol-column-id.ts` so the search-page can use the
// same logic to derive `visibleProtocolIds` without a feature-cross
// import into the grid component.
export type { ResolvedColumn };
export const resolveColumns = resolveColumnsShared;

function renderInterceptCell(
  av: ActivityValue | undefined,
  spec: InterceptSpec,
  isPrimary: boolean,
): React.ReactNode {
  if (!av) return <span className="text-muted-foreground">&mdash;</span>;
  const iv = findInterceptValue(av.intercept_values, spec);
  const value = iv?.value ?? (isPrimary ? av.value : null);
  const display = formatInterceptDisplay({
    value,
    at_bound: iv?.at_bound,
    curve_class: av.curve_params?.curve_class,
    max_dose: maxDoseFromRawData(av.raw_data),
  });
  // ActivityValue can carry a wire-level qualifier (">", "<") from upstream
  // — only prepend it when we're actually rendering a numeric scalar; ND /
  // qualifier / missing cells already self-describe.
  const q =
    av.qualifier && av.qualifier !== "=" && display.kind === "scalar" ? `${av.qualifier} ` : "";
  const showUnit = display.kind === "scalar" || display.kind === "qualifier";
  const unitSuffix = showUnit && av.unit ? ` ${av.unit}` : "";
  if (display.warning) {
    return (
      <Badge
        variant="outline"
        className="text-xs border-amber-500 text-amber-700"
        title={display.tooltip}
      >
        <span className="font-mono">
          {q}
          {display.text}
          {unitSuffix}
        </span>
      </Badge>
    );
  }
  const isScalar = display.kind === "scalar";
  return (
    <span
      className={`inline-flex items-center font-mono text-xs${isScalar ? "" : " text-muted-foreground"}`}
      title={display.tooltip || undefined}
    >
      {q}
      {display.text}
      {unitSuffix}
      {isPrimary && isScalar ? (
        <CurveClassBadge
          curveClass={av.curve_params?.curve_class ?? null}
          compact
          renderNullAs="nothing"
        />
      ) : null}
    </span>
  );
}

function buildReadoutColumn(
  colId: string,
  proto: Protocol | undefined,
  readoutDefId: string,
  normalization: string | null,
): ColDef<EnrichedMolecule> {
  // Header resolves from the protocol's readout definitions. 4-segment IDs
  // (`rd:<p>:<id>:<norm>`) view a specific normalization (e.g.
  // percent_inhibition). The backend hands us the formula-appropriate unit
  // in `av.unit`, so the header decorates with the formula label and the
  // cell renderer trusts `av.unit`.
  const rd = proto?.readout_definitions?.find((r) => r.id === readoutDefId);
  const rdName = rd?.name ?? "Readout";
  const normLabel = normalization
    ? (READOUT_NORMALIZATION_LABELS[normalization as keyof typeof READOUT_NORMALIZATION_LABELS] ??
      normalization)
    : null;
  const headerSuffix = normLabel ? ` (${normLabel})` : rd?.unit ? ` (${rd.unit})` : "";

  return {
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
          {q}
          {av.value.toPrecision(4)}
          {av.unit ? ` ${av.unit}` : ""}
        </span>
      );
    },
  };
}

/** Build one dynamic intercept column per `dose_response_config.intercepts`
 *  entry on the readout-def. Primary intercept reads `av.value` as a
 *  fallback for legacy curves; secondaries fall back to "—" with a
 *  Recompute hint. Plot column sits at the end of the readout-def's
 *  child set.
 *
 *  ``visibleIntercepts`` narrows the rendered set to a chemist-picked
 *  subset (matched by ``(kind, level)``). Omitted / null = render every
 *  intercept the protocol declares (today's default). Empty array =
 *  render none (caller should suppress the whole group instead — empty
 *  is treated as "render all" here as a defensive fallback).
 */
export function buildDrcColumns(
  colId: string,
  proto: Protocol | undefined,
  readoutDefId: string,
  visibleIntercepts?: ReadonlyArray<{ kind: string; level: number }> | null,
  aggregationMode: AggregationMode = "latest",
): ColDef<EnrichedMolecule>[] {
  const rd = proto?.readout_definitions?.find((r) => r.id === readoutDefId);
  const allIntercepts = rd?.dose_response_config?.intercepts ?? [];
  const intercepts =
    visibleIntercepts && visibleIntercepts.length > 0
      ? allIntercepts.filter((spec) =>
          visibleIntercepts.some((ik) => ik.kind === spec.kind && ik.level === spec.level),
        )
      : allIntercepts;

  const cols: ColDef<EnrichedMolecule>[] = [];

  if (intercepts.length === 0) {
    // Defensive fallback: protocol's DR readout declared no intercepts
    // (e.g. server default never explicitly populated `intercepts`). Emit
    // a single anonymous value column so the grid still surfaces the
    // headline fitted_value.
    cols.push({
      headerName: rd?.name ?? "Curve",
      colId: `${colId}:value`,
      width: 130,
      valueGetter: (p) => {
        const av = p.data?.activity?.[colId];
        if (!av) return null;
        return formatInterceptDisplay({
          value: av.value ?? null,
          at_bound: undefined,
          curve_class: av.curve_params?.curve_class,
          max_dose: maxDoseFromRawData(av.raw_data),
        }).sortValue;
      },
      cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
        const av = params.data?.activity?.[colId];
        if (!av) {
          return <span className="text-muted-foreground">&mdash;</span>;
        }
        // No protocol-declared intercept list → no per-spec at_bound to read,
        // so the helper only acts on curve_class / null value. Inactive
        // curves still route to "ND" instead of a misleading scalar.
        const display = formatInterceptDisplay({
          value: av.value ?? null,
          at_bound: undefined,
          curve_class: av.curve_params?.curve_class,
          max_dose: maxDoseFromRawData(av.raw_data),
        });
        const isScalar = display.kind === "scalar";
        return (
          <span
            className={`inline-flex items-center font-mono text-xs${isScalar ? "" : " text-muted-foreground"}`}
            title={display.tooltip || undefined}
          >
            {display.text}
            {isScalar && av.unit ? ` ${av.unit}` : ""}
            {isScalar ? (
              <CurveClassBadge
                curveClass={av.curve_params?.curve_class ?? null}
                compact
                renderNullAs="nothing"
              />
            ) : null}
          </span>
        );
      },
    });
  } else {
    intercepts.forEach((spec, idx) => {
      const isPrimary = idx === 0;
      cols.push({
        headerName: interceptLabel(spec),
        colId: `${colId}:${spec.kind}:${spec.level}`,
        width: 130,
        valueGetter: (p) => {
          const av = p.data?.activity?.[colId];
          if (!av) return null;
          const iv = findInterceptValue(av.intercept_values, spec);
          const value = iv?.value ?? (isPrimary ? (av.value ?? null) : null);
          return formatInterceptDisplay({
            value,
            at_bound: iv?.at_bound,
            curve_class: av.curve_params?.curve_class,
            max_dose: maxDoseFromRawData(av.raw_data),
          }).sortValue;
        },
        cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => (
          <InterceptCell
            av={params.data?.activity?.[colId]}
            spec={spec}
            isPrimary={isPrimary}
            mode={aggregationMode}
          />
        ),
      });
    });
  }

  // Single Plot column per DR readout — one curve serves every intercept.
  cols.push({
    headerName: "Plot",
    colId: `${colId}:plot`,
    width: 240,
    sortable: false,
    filter: false,
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
      const av = params.data?.activity?.[colId];
      return <DoseResponseCell value={av} />;
    },
  });

  return cols;
}

function buildProtocolColumnGroups(
  protocolColumns: string[],
  protocols: Protocol[],
  aggregationMode: AggregationMode = "latest",
): ColGroupDef[] {
  const resolved = resolveColumns(protocolColumns, protocols);
  const grouped = groupBy(resolved, (r) => r.protocolId);

  const groups: ColGroupDef[] = [];
  for (const [protoId, entries] of grouped) {
    const proto = protocols.find((p) => p.id === protoId);
    const headerName = proto?.name ?? "Protocol";

    const children: ColDef<EnrichedMolecule>[] = [];
    // DR tokens for the same readout-def may arrive as either a parent
    // `drc:<rd_id>` (= render all intercepts) or as one or more narrowed
    // `drc:<rd_id>:<kind>:<level>` (= render only this intercept). Collapse
    // per rd-id so we emit ONE column block per readout-def with the
    // combined intercept-visibility set.
    const drcByRdId = new Map<
      string,
      { parentColId: string; visible: Array<{ kind: string; level: number }> | null }
    >();

    for (const entry of entries) {
      if (entry.prefix === "rd") {
        const parts = entry.colId.split(":");
        const normalization = parts.length >= 4 ? parts[3] || null : null;
        children.push(
          buildReadoutColumn(entry.colId, proto, entry.readoutDefId ?? "", normalization),
        );
      } else {
        const rdId = entry.readoutDefId ?? "";
        const parentColId = drcColId(rdId);
        const existing = drcByRdId.get(rdId);
        if (entry.interceptKey === null) {
          // Parent token short-circuits to "render all" — clear any
          // previously-accumulated narrowing.
          drcByRdId.set(rdId, { parentColId, visible: null });
        } else if (!existing) {
          drcByRdId.set(rdId, { parentColId, visible: [entry.interceptKey] });
        } else if (existing.visible !== null) {
          existing.visible.push(entry.interceptKey);
        }
      }
    }

    for (const { parentColId, visible } of drcByRdId.values()) {
      const rdId = parentColId.split(":")[1];
      const proto2 = protocols.find((p) => p.id === protoId);
      children.push(...buildDrcColumns(parentColId, proto2, rdId, visible, aggregationMode));
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
function buildMoleculeColumn(imageSize: string): ColDef<EnrichedMolecule> {
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
            <p className="truncate text-sm">{mol.name || "Unnamed"}</p>
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
  buildExportRequest,
  toolbarLeft,
  toolbarActions,
}: ResultsGridProps) {
  const rowHeight = ROW_HEIGHTS[reportConfig.imageSize] ?? 150;

  // Show the similarity column only when at least one row actually carries
  // a score (i.e. the active search was a similarity search). Substructure /
  // exact / property-only searches return null scores and we hide the column.
  const hasSimilarityScores = useMemo(
    () => results.some((r) => r.similarity_score != null),
    [results],
  );

  // Aggregation mode picked from `?agg=` is read here so DR intercept cells
  // know whether to render the fold-range chip (gmean/mean only) — the value
  // is closed over by the cellRenderer factories and `aggregationMode` is
  // listed as a memo dep so the column block rebuilds when the toolbar
  // flips modes.
  const { mode: aggregationMode } = useAggregationMode();

  const columnDefs = useMemo<(ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>)[]>(() => {
    const molecule = buildMoleculeColumn(reportConfig.imageSize);
    const sim = hasSimilarityScores ? [buildSimilarityColumn()] : [];
    const props = buildPropertyColumns(reportConfig.visibleFields.properties);
    const protoGroups = buildProtocolColumnGroups(protocolColumns, protocols, aggregationMode);
    return [molecule, ...sim, ...props, ...protoGroups];
  }, [
    reportConfig.imageSize,
    reportConfig.visibleFields.properties,
    protocolColumns,
    protocols,
    hasSimilarityScores,
    aggregationMode,
  ]);

  // When the parent resets selection (selectedIds.size → 0), DataGrid's
  // clearSelectionToken mechanism detects the falsy value and calls deselectAll.
  const clearSelectionToken = selectedIds.size;

  // Compose the shared ExportToolbar alongside the caller-supplied action
  // buttons. Rendered as a single React node so the grid's toolbar row
  // stays a single flex row. T20 will clean up the old export props on
  // <DataGrid> once no callers use them.
  const toolbarActionsWithExport = (
    <>
      {toolbarActions}
      {buildExportRequest ? <SharedExportToolbar buildRequest={buildExportRequest} /> : null}
    </>
  );

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
          <p className="py-12 text-center text-sm text-muted-foreground">No results to display.</p>
        }
        height="calc(100vh - 80px)"
        rowHeight={rowHeight}
        headerHeight={36}
        groupHeaderHeight={32}
        enableMultiSelect
        suppressSelectColumn
        searchPlaceholder={false}
        toolbarLeft={toolbarLeft}
        toolbarActions={toolbarActionsWithExport}
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
