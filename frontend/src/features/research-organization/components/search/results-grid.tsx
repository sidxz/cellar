"use client";

import { useMemo } from "react";
import {
  type ColDef,
  type ColGroupDef,
  type ICellRendererParams,
} from "ag-grid-community";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Badge } from "@/shared/components/ui/badge";
import { groupBy } from "@/shared/lib/group-by";
import type { Molecule } from "@/features/chemical-registration/types";
import {
  READOUT_NORMALIZATION_LABELS,
  type InterceptSpec,
  type Protocol,
} from "@/features/screening-assay/types";
import { CurveClassBadge } from "@/features/screening-assay/components/curve-class-badge";
import {
  findInterceptValue,
  interceptLabel,
} from "@/features/screening-assay/lib/intercept-label";
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

/** colId shapes that resolve to a protocol column:
 *    rd:<protoId>:<rdId>[:<norm>]   — aggregated readout (scoped)
 *    rd:<rdId>                      — aggregated readout (unscoped/legacy)
 *    drc:<rdId>                     — best dose-response curve for that DR
 *                                     readout-def (curve identity is by
 *                                     readout-def, not curve_type, per 033). */
export interface ResolvedColumn {
  colId: string;
  prefix: "rd" | "drc";
  protocolId: string;
  readoutDefId: string | null;
}

export function resolveColumns(
  protocolColumns: string[],
  protocols: Protocol[],
): ResolvedColumn[] {
  // Build a reverse index so 2-segment colIds (drc:<rd_id> or legacy
  // rd:<rd_id>) can find their owning protocol.
  const protoByRdId = new Map<string, Protocol>();
  for (const p of protocols) {
    for (const rd of p.readout_definitions ?? []) {
      protoByRdId.set(rd.id, p);
    }
  }

  const resolved: ResolvedColumn[] = [];
  for (const colId of protocolColumns) {
    const parts = colId.split(":");
    const prefix = parts[0];
    if (prefix !== "rd" && prefix !== "drc") continue;

    if (prefix === "drc") {
      const rdId = parts[1];
      if (!rdId) continue;
      const proto = protoByRdId.get(rdId);
      if (!proto) continue;
      resolved.push({ colId, prefix, protocolId: proto.id, readoutDefId: rdId });
    } else if (parts.length >= 3) {
      // rd:<proto>:<rd>[:<norm>]
      const protoId = parts[1];
      const rdId = parts[2];
      if (!protoId || !rdId) continue;
      resolved.push({ colId, prefix, protocolId: protoId, readoutDefId: rdId });
    } else {
      // rd:<rd_id> legacy fallback
      const rdId = parts[1];
      if (!rdId) continue;
      const proto = protoByRdId.get(rdId);
      if (!proto) continue;
      resolved.push({ colId, prefix, protocolId: proto.id, readoutDefId: rdId });
    }
  }

  return resolved;
}

function renderInterceptCell(
  av: ActivityValue | undefined,
  spec: InterceptSpec,
  isPrimary: boolean,
): React.ReactNode {
  if (!av) return <span className="text-muted-foreground">&mdash;</span>;
  const iv = findInterceptValue(av.intercept_values, spec);
  // Primary intercept falls back to `value` (== fitted_value) so legacy
  // curves fit before intercept_values were persisted still render in the
  // primary column.
  const value = iv?.value ?? (isPrimary ? av.value : null);
  if (value == null) {
    return (
      <span
        className="text-muted-foreground"
        title="No value for this intercept. Recompute the curve to refresh."
      >
        &mdash;
      </span>
    );
  }
  const q = av.qualifier && av.qualifier !== "=" ? `${av.qualifier} ` : "";
  if (iv?.at_bound) {
    return (
      <Badge variant="outline" className="text-xs border-amber-500 text-amber-700">
        <span className="font-mono">
          {q}
          {value.toPrecision(4)}
        </span>
        <span className="ml-1">⚠︎ at bound</span>
      </Badge>
    );
  }
  return (
    <span className="inline-flex items-center font-mono text-xs">
      {q}
      {value.toPrecision(4)}
      {av.unit ? ` ${av.unit}` : ""}
      {isPrimary ? (
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
    ? READOUT_NORMALIZATION_LABELS[normalization as keyof typeof READOUT_NORMALIZATION_LABELS] ??
      normalization
    : null;
  const headerSuffix = normLabel
    ? ` (${normLabel})`
    : rd?.unit
      ? ` (${rd.unit})`
      : "";

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
 *  child set. */
export function buildDrcColumns(
  colId: string,
  proto: Protocol | undefined,
  readoutDefId: string,
): ColDef<EnrichedMolecule>[] {
  const rd = proto?.readout_definitions?.find((r) => r.id === readoutDefId);
  const intercepts = rd?.dose_response_config?.intercepts ?? [];

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
      valueGetter: (p) => p.data?.activity?.[colId]?.value ?? null,
      cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
        const av = params.data?.activity?.[colId];
        if (av?.value == null) {
          return <span className="text-muted-foreground">&mdash;</span>;
        }
        return (
          <span className="inline-flex items-center font-mono text-xs">
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
          if (iv) return iv.value;
          return isPrimary ? (av.value ?? null) : null;
        },
        cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) =>
          renderInterceptCell(params.data?.activity?.[colId], spec, isPrimary),
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
): ColGroupDef[] {
  const resolved = resolveColumns(protocolColumns, protocols);
  const grouped = groupBy(resolved, (r) => r.protocolId);

  const groups: ColGroupDef[] = [];
  for (const [protoId, entries] of grouped) {
    const proto = protocols.find((p) => p.id === protoId);
    const headerName = proto?.name ?? "Protocol";

    const children: ColDef<EnrichedMolecule>[] = [];
    for (const entry of entries) {
      if (entry.prefix === "rd") {
        const parts = entry.colId.split(":");
        const normalization = parts.length >= 4 ? parts[3] || null : null;
        children.push(
          buildReadoutColumn(
            entry.colId,
            proto,
            entry.readoutDefId ?? "",
            normalization,
          ),
        );
      } else {
        children.push(
          ...buildDrcColumns(entry.colId, proto, entry.readoutDefId ?? ""),
        );
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
