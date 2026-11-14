"use client";

import { ExportToolbar as SharedExportToolbar } from "@/shared/components/export/export-toolbar";
import type { ExportFormat, ExportRequest } from "@/shared/components/export/types";
import { MAX_OVERLAY_CURVES, overlayColor } from "@structflo/components/dose-response";
import type {
  ColDef,
  ColGroupDef,
  ICellRendererParams,
  IHeaderGroupParams,
} from "ag-grid-community";
import { Maximize2, Minimize2 } from "lucide-react";
import { type ReactNode, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { Molecule } from "@/features/chemical-registration/types";
import { activityCatalog } from "@/features/screening-assay/lib/activity-columns";
import { interceptLabel } from "@/features/screening-assay/lib/intercept-label";
import { type Protocol, READOUT_NORMALIZATION_LABELS } from "@/features/screening-assay/types";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import { Button } from "@/shared/components/ui/button";
import { groupBy } from "@/shared/lib/group-by";
import { detectQueryKind } from "@/shared/lib/rdkit/detect-query-kind";
import { cn } from "@/shared/lib/utils";
import { shownPlotLayout } from "../../hooks/use-report-config";
import { activityEndpoint, sameUnit } from "../../lib/assay-evidence";
import { compoundRef, curvesTarget } from "../../lib/curves-target";
import {
  ANY_COLUMN_ID,
  type ResolvedColumn,
  canOverlaySplit,
  drcColId,
  resolveColumns as resolveColumnsShared,
} from "../../lib/protocol-column-id";
import { serverSortToken } from "../../lib/search-sort";
import type { AggregationMode } from "../../lib/use-aggregation-mode";
import {
  type ActivityValue,
  type ColumnGroup,
  type PlotLayout,
  type ProtocolColumnGroups,
  type ReportConfig,
  type SortDir,
  type StructureCriterion,
  anyProtocolActivity,
} from "../../types";
import { ActiveInCell } from "./active-in-cell";
import { AssayEvidence } from "./assay-evidence";
import { DoseResponseCell, DoseResponseOverlay } from "./dose-response-cell";
import { InterceptCell } from "./intercept-cell";

// ─── Types ──────────────────────────────────────────────────────────────────

type EnrichedMolecule = Molecule & { activity?: Record<string, ActivityValue> };

interface ResultsGridProps {
  results: EnrichedMolecule[];
  structureCriterion?: StructureCriterion;
  aggregationMode?: AggregationMode;
  protocolColumns: string[];
  /** Split protocols' column groups from the search response. */
  columnGroups?: Record<string, ProtocolColumnGroups> | null;
  /** A header click asks the server to rank the whole result set by that
   *  column (undefined = back to the default order). The grid never
   *  re-sorts the loaded rows itself. */
  onSortChange?: (sortBy: string | undefined, sortDir: SortDir) => void;
  protocols: Protocol[];
  reportConfig: ReportConfig;
  loading: boolean;
  /** `colId`: the clicked column, so the drawer can open on its split group. */
  onRowClick: (molecule: EnrichedMolecule, colId?: string) => void;
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
  footer?: React.ReactNode;
  summary?: React.ReactNode;
  viewControls?: React.ReactNode;
  selectionActions?: React.ReactNode;
}

// ─── Row height by image size ───────────────────────────────────────────────

const ROW_HEIGHTS: Record<string, number> = {
  small: 104,
  medium: 220,
  large: 330,
};

// ─── Similarity column ─────────────────────────────────────────────────────

function formatSimilarityPercent(score: number): string {
  // Match the structure filter's "≥ NN %" UI — integer percent. 1 decimal
  // place would carry more info but creates a unit mismatch with the
  // threshold the chemist just typed.
  return `${Math.round(score * 100)}%`;
}

function buildSimilarityColumn(criterion?: StructureCriterion): ColDef<EnrichedMolecule> {
  return {
    headerName: "Similarity",
    colId: "similarity",
    width: 130,
    headerTooltip: `${criterion?.mode === "scaffold_hop" ? "Tanimoto similarity over feature-class (FCFP4) fingerprints" : criterion?.mode === "fragment_in_target" ? "Asymmetric Tversky similarity (α=1, β=0) over query features" : "Tanimoto similarity over Morgan/ECFP4 fingerprints"}. A 100% score does not establish chemical identity.`,
    valueGetter: (p) => p.data?.similarity_score ?? null,
    valueFormatter: (p) => (p.value != null ? formatSimilarityPercent(Number(p.value)) : "—"),
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
      const score = params.data?.similarity_score;
      if (score == null) {
        return <span className="text-muted-foreground">—</span>;
      }
      const pct = Math.max(0, Math.min(100, score * 100));
      return (
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs tabular-nums">{formatSimilarityPercent(score)}</span>
          <div className="h-1.5 w-12 rounded-full bg-muted overflow-hidden">
            <div className="h-full bg-primary/60" style={{ width: `${pct}%` }} />
          </div>
        </div>
      );
    },
  };
}

// Every property the customizer offers (keys = `MoleculeDescriptors` fields,
// shared with the export column builder). Listed in display order.
const PROPERTY_COLUMNS: Record<
  string,
  { header: string; width: number; digits?: number; tooltip?: string }
> = {
  molecular_weight: { header: "MW", width: 90, digits: 1 },
  logp: { header: "LogP", width: 80, digits: 2 },
  tpsa: {
    header: "TPSA",
    width: 80,
    digits: 1,
    tooltip: "Topological polar surface area (Veber's rule — predicts permeability)",
  },
  hbd: { header: "HBD", width: 70, tooltip: "Hydrogen-bond donors (Lipinski Rule of Five)" },
  hba: { header: "HBA", width: 70, tooltip: "Hydrogen-bond acceptors (Lipinski Rule of Five)" },
  rotatable_bonds: { header: "RotB", width: 70, tooltip: "Rotatable bonds" },
  heavy_atom_count: { header: "HAC", width: 70, tooltip: "Heavy atom count" },
  aromatic_rings: { header: "ArRings", width: 80, tooltip: "Aromatic rings" },
  ring_count: { header: "Rings", width: 70, tooltip: "Ring count" },
  ro5_violations: { header: "Ro5", width: 70, tooltip: "Lipinski Rule-of-Five violations" },
  molecular_formula: { header: "Formula", width: 140 },
};

function buildPropertyColumns(visibleProperties: string[]): ColDef<EnrichedMolecule>[] {
  return Object.entries(PROPERTY_COLUMNS)
    .filter(([key]) => visibleProperties.includes(key))
    .map(([key, spec]) => ({
      headerName: spec.header,
      colId: `prop:${key}`,
      width: spec.width,
      ...(spec.tooltip ? { headerTooltip: spec.tooltip } : {}),
      valueGetter: (p) =>
        (p.data?.descriptors as Record<string, number | string | null> | null)?.[key] ?? null,
      valueFormatter: (p) =>
        p.value == null
          ? "—"
          : spec.digits != null
            ? Number(p.value).toFixed(spec.digits)
            : String(p.value),
    }));
}

/** SMILES / InChIKey / lifecycle columns the customizer can switch on. */
function buildIdentityColumns(
  structureFields: string[],
  moleculeFields: string[],
): ColDef<EnrichedMolecule>[] {
  const cols: ColDef<EnrichedMolecule>[] = [];
  const mono = (value: string | null | undefined) =>
    value ? (
      <span className="block truncate font-mono text-xs" title={value}>
        {value}
      </span>
    ) : (
      <span className="text-muted-foreground">—</span>
    );
  if (structureFields.includes("smiles")) {
    cols.push({
      headerName: "SMILES",
      colId: "smiles",
      width: 220,
      valueGetter: (p) => p.data?.structure?.smiles ?? null,
      cellRenderer: (p: ICellRendererParams<EnrichedMolecule>) => mono(p.data?.structure?.smiles),
    });
  }
  if (structureFields.includes("inchi_key")) {
    cols.push({
      headerName: "InChIKey",
      colId: "inchi_key",
      width: 220,
      valueGetter: (p) => p.data?.structure?.inchi_key ?? null,
      cellRenderer: (p: ICellRendererParams<EnrichedMolecule>) =>
        mono(p.data?.structure?.inchi_key),
    });
  }
  if (moleculeFields.includes("lifecycle_stage")) {
    cols.push({
      headerName: "Stage",
      colId: "lifecycle_stage",
      width: 110,
      valueGetter: (p) => p.data?.lifecycle_stage ?? null,
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

/** The row compound's curves in the column's protocol, from the protocol's
 *  flag only: nothing is fetched per cell. */
function rowCurves(proto: Protocol | undefined, row: EnrichedMolecule | undefined) {
  return row ? curvesTarget(proto, [compoundRef(row)]) : null;
}

/** Sorting is the server's: a column with a sort token keeps the rows in the
 *  order they arrived (the comparator never reorders), any other column is
 *  not sortable. */
function serverSorted(
  column: ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>,
): ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule> {
  if ("children" in column) return { ...column, children: column.children.map(serverSorted) };
  return serverSortToken(column.colId)
    ? { ...column, sortable: true, comparator: () => 0 }
    : { ...column, sortable: false };
}

/** Never squeezed below its own width (the grid's fit-to-width would shrink
 *  a wide table's columns to the 80px floor and cut every header); a long
 *  header wraps to a second line; a nested header still gets its tooltip. */
function readable(column: ColDef<EnrichedMolecule>): ColDef<EnrichedMolecule> {
  return {
    ...column,
    minWidth: column.width,
    wrapHeaderText: true,
    autoHeaderHeight: true,
    headerTooltip: column.headerTooltip ?? column.headerName,
  };
}

/** A Plot column, split or not (``drc:<rd>:plot`` / ``drc:<rd>:plot@<group>``). */
function isPlotColumn(colId: string | undefined): boolean {
  return !!colId && colId.split("@")[0].endsWith(":plot");
}

/** ``<column>@<group>`` — a split group's activity key and grid column id. */
function withGroup(id: string, groupKey: string): string {
  return groupKey ? `${id}@${groupKey}` : id;
}

function buildReadoutColumn(
  token: string,
  proto: Protocol | undefined,
  readoutDefId: string,
  normalization: string | null,
  mode: AggregationMode,
  groupKey = "",
  /** Short header from the protocol's activity catalog (unit included). */
  catalogLabel?: string,
): ColDef<EnrichedMolecule> {
  const colId = withGroup(token, groupKey);
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
  // The header states the unit, so a value in it leaves it out of the cell.
  const headerUnit = normLabel ? null : (rd?.unit ?? null);

  return {
    headerName: normLabel
      ? `${rdName}${headerSuffix}`
      : (catalogLabel ?? `${rdName}${headerSuffix}`),
    headerTooltip: `${rdName}${headerSuffix} · ${proto?.name ?? "Assay"}`,
    colId,
    width: 112,
    valueGetter: (p) => p.data?.activity?.[colId]?.value ?? null,
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
      const av = params.data?.activity?.[colId];
      if (av?.qualifier === "nd") {
        // Runs exist but none gave a reportable value — not "no data".
        return <span className="font-mono text-xs text-muted-foreground">ND</span>;
      }
      if (av?.value == null) {
        return <span className="text-muted-foreground">&mdash;</span>;
      }
      const q = av.qualifier && av.qualifier !== "=" ? `${av.qualifier} ` : "";
      return (
        <AssayEvidence av={av} mode={mode} curves={rowCurves(proto, params.data)}>
          <span className="font-mono text-xs">
            {q}
            {av.value.toPrecision(4)}
            {av.unit && !sameUnit(av.unit, headerUnit) ? ` ${av.unit}` : ""}
          </span>
        </AssayEvidence>
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
  token: string,
  proto: Protocol | undefined,
  readoutDefId: string,
  visibleIntercepts?: ReadonlyArray<{ kind: string; level: number }> | null,
  aggregationMode: AggregationMode = "latest",
  groupKey = "",
): ColDef<EnrichedMolecule>[] {
  // Cells read the group's activity key; grid column ids carry the group last.
  const colId = withGroup(token, groupKey);
  const columnId = (suffix: string) => withGroup(`${token}:${suffix}`, groupKey);
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
      headerName: `${rd?.name ?? "Curve"}${proto?.dose_unit ? ` (${proto.dose_unit})` : ""}`,
      colId: columnId("value"),
      width: 130,
      valueGetter: (p) => {
        const av = p.data?.activity?.[colId];
        if (!av) return null;
        return activityEndpoint(av, null, true, aggregationMode).display.sortValue;
      },
      cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => (
        <InterceptCell
          av={params.data?.activity?.[colId]}
          spec={null}
          isPrimary
          mode={aggregationMode}
          curves={rowCurves(proto, params.data)}
          headerUnit={proto?.dose_unit}
        />
      ),
    });
  } else {
    intercepts.forEach((spec, idx) => {
      const isPrimary = idx === 0;
      cols.push({
        headerName: `${interceptLabel(spec)}${proto?.dose_unit ? ` (${proto.dose_unit})` : ""}`,
        headerTooltip: `${rd?.name ?? "Endpoint"} · ${proto?.name ?? "Assay"}`,
        colId: columnId(`${spec.kind}:${spec.level}`),
        width: 150,
        valueGetter: (p) => {
          const av = p.data?.activity?.[colId];
          if (!av) return null;
          return activityEndpoint(av, spec, isPrimary, aggregationMode).display.sortValue;
        },
        cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => (
          <InterceptCell
            av={params.data?.activity?.[colId]}
            spec={spec}
            isPrimary={isPrimary}
            mode={aggregationMode}
            curves={rowCurves(proto, params.data)}
            headerUnit={proto?.dose_unit}
          />
        ),
      });
    });
  }

  // Single Plot column per DR readout — one curve serves every intercept.
  cols.push({
    headerName: "Plot",
    colId: columnId("plot"),
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

/** A group folds to its headline: its first `keep` columns (and any plot)
 *  stay, the rest show only while the group is open. Every group starts
 *  open — folding is the chemist's choice, never the default. */
function foldable<T extends ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>>(
  children: T[],
  keep = 1,
): T[] {
  let kept = 0;
  return children.map((c) =>
    "children" in c || isPlotColumn(c.colId) || kept++ < keep
      ? c
      : { ...c, columnGroupShow: "open" },
  );
}

/** Not measured in this assay (within the search's run filter): one muted
 *  note in the assay's first column instead of a dash in every column. */
function NoResult() {
  return (
    <span
      className="text-xs italic text-muted-foreground/70"
      title="No result for this compound in this assay within the search's run filter."
    >
      no result
    </span>
  );
}

function quietWhenUntested(
  leaves: ColDef<EnrichedMolecule>[],
  activityKeys: string[],
): ColDef<EnrichedMolecule>[] {
  const tested = (row: EnrichedMolecule | undefined) =>
    activityKeys.some((k) => row?.activity?.[k] != null);
  return leaves.map((col, i) => {
    const render = col.cellRenderer as (p: ICellRendererParams<EnrichedMolecule>) => ReactNode;
    return {
      ...col,
      cellRenderer: (p: ICellRendererParams<EnrichedMolecule>) =>
        tested(p.data) ? render(p) : i === 0 ? <NoResult /> : null,
    };
  });
}

/** One protocol's columns for one split group (or the unsplit columns).
 *  Plain readouts take the protocol Activity tab's short labels, order and
 *  groups (a thermal-shift window per group), so a protocol reads the same
 *  on both pages; every readout still shows. */
function buildProtocolChildren(
  entries: ResolvedColumn[],
  proto: Protocol | undefined,
  aggregationMode: AggregationMode,
  groupKey: string,
  groupId: string,
): (ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>)[] {
  const catalog = new Map(
    activityCatalog(
      (proto?.readout_definitions ?? []).map((rd) => ({
        name: rd.name,
        data_type: rd.data_type,
        unit: rd.unit ?? null,
        melt_config: rd.melt_config,
      })),
      [],
      [],
    )
      .filter((c) => c.kind === "value")
      .map((c, order) => [c.readout, { label: c.label, group: c.group, order }]),
  );
  const readouts: { col: ColDef<EnrichedMolecule>; name: string }[] = [];
  const activityKeys: string[] = [];
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
      const name = proto?.readout_definitions?.find((r) => r.id === entry.readoutDefId)?.name ?? "";
      activityKeys.push(withGroup(entry.colId, groupKey));
      readouts.push({
        name,
        col: buildReadoutColumn(
          entry.colId,
          proto,
          entry.readoutDefId ?? "",
          normalization,
          aggregationMode,
          groupKey,
          catalog.get(name)?.label,
        ),
      });
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

  const order = (name: string) => catalog.get(name)?.order ?? Number.MAX_SAFE_INTEGER;
  readouts.sort((a, b) => order(a.name) - order(b.name));
  const curves: ColDef<EnrichedMolecule>[] = [];
  for (const { parentColId, visible } of drcByRdId.values()) {
    const rdId = parentColId.split(":")[1];
    activityKeys.push(withGroup(parentColId, groupKey));
    curves.push(...buildDrcColumns(parentColId, proto, rdId, visible, aggregationMode, groupKey));
  }

  const leaves = quietWhenUntested([...readouts.map((r) => r.col), ...curves], activityKeys);
  // Consecutive readouts sharing a catalog group (a thermal window, "Other
  // readouts") sit under that group's header.
  const children: (ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>)[] = [];
  readouts.forEach(({ name }, i) => {
    const header = catalog.get(name)?.group;
    const last = children.at(-1);
    if (!header) children.push(leaves[i]);
    else if (last && "children" in last && last.headerName === header)
      last.children.push(leaves[i]);
    else
      children.push({
        headerName: header,
        headerTooltip: header,
        groupId: `${groupId}:${header}`,
        openByDefault: true,
        headerClass: "ag-protocol-split-header",
        children: [leaves[i]],
      });
  });
  return foldable([
    ...children.map((c) => ("children" in c ? { ...c, children: foldable(c.children) } : c)),
    ...leaves.slice(readouts.length),
  ]);
}

function groupHeader(group: ColumnGroup, split: ProtocolColumnGroups["split"]): string {
  if (group.flags?.includes("rejected")) return `${group.label} (rejected)`;
  if (group.flags?.includes("deleted")) return group.label;
  if (split.by === "run") return group.label;
  return `${group.label} · ${group.run_count} run${group.run_count === 1 ? "" : "s"}`;
}

function groupTooltip(group: ColumnGroup, split: ProtocolColumnGroups["split"]): string {
  if (group.flags?.includes("deleted")) return "This run is no longer available.";
  if (group.flags?.includes("rejected"))
    return `Run ${group.label} was rejected; it contributes no values.`;
  if (split.by === "run") return `Run ${group.label}`;
  return `${split.condition} = ${group.label} · ${group.run_count} run${group.run_count === 1 ? "" : "s"}`;
}

/** A split group's header with the colour its curve takes in an overlay. */
function OverlayGroupHeader({ displayName, color }: IHeaderGroupParams & { color: string }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <span
        aria-hidden
        className="size-2.5 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span className="truncate">{displayName}</span>
    </span>
  );
}

/** One plot per dose-response readout holding every group's curve, each in
 *  the colour of its group's header. */
function buildOverlayPlotColumns(
  entries: ResolvedColumn[],
  proto: Protocol | undefined,
  split: ProtocolColumnGroups,
): ColDef<EnrichedMolecule>[] {
  const rdIds = [
    ...new Set(entries.filter((e) => e.prefix === "drc").map((e) => e.readoutDefId ?? "")),
  ];
  return rdIds.map((rdId) => {
    const name = proto?.readout_definitions?.find((r) => r.id === rdId)?.name;
    return {
      headerName: rdIds.length > 1 && name ? `Plot · ${name}` : "Plot",
      headerTooltip: "Every group's curve on one axis, coloured like its group's header",
      colId: `${drcColId(rdId)}:plot@overlay`,
      width: 240,
      sortable: false,
      filter: false,
      cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => (
        <DoseResponseOverlay
          entries={split.groups.map((group) => ({
            value: params.data?.activity?.[withGroup(drcColId(rdId), group.key)],
            label: group.label,
          }))}
        />
      ),
    };
  });
}

export function buildProtocolColumnGroups(
  protocolColumns: string[],
  protocols: Protocol[],
  aggregationMode: AggregationMode = "latest",
  columnGroups?: Record<string, ProtocolColumnGroups> | null,
  plotLayout: PlotLayout = "side_by_side",
): ColGroupDef[] {
  const resolved = resolveColumns(protocolColumns, protocols);
  const grouped = groupBy(resolved, (r) => r.protocolId);

  const groups: ColGroupDef[] = [];
  for (const [protoId, entries] of grouped) {
    const proto = protocols.find((p) => p.id === protoId);
    const name = proto?.name ?? "Protocol";
    const split = columnGroups?.[protoId];
    if (!split) {
      groups.push({
        headerName: name,
        headerTooltip: name,
        groupId: `p:${protoId}`,
        openByDefault: true,
        headerClass: "ag-protocol-group-header",
        children: buildProtocolChildren(entries, proto, aggregationMode, "", `p:${protoId}`),
      });
      continue;
    }
    const headerName = `${name} · by ${split.split.by === "run" ? "run" : split.split.condition}`;
    const wantsOverlay = plotLayout === "overlay" && entries.some((e) => e.prefix === "drc");
    const overlay = wantsOverlay && canOverlaySplit(split);
    const children: (ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>)[] =
      split.groups.length === 0
        ? [
            {
              headerName: "No runs match",
              headerTooltip: "No run in this search's run filter measured these compounds.",
              colId: `${protoId}:no-runs`,
              width: 140,
              sortable: false,
              valueGetter: () => null,
              cellRenderer: () => <span className="text-muted-foreground">&mdash;</span>,
            },
          ]
        : split.groups.map((group, i) => ({
            headerName: groupHeader(group, split.split),
            headerTooltip: groupTooltip(group, split.split),
            groupId: `p:${protoId}@${group.key}`,
            openByDefault: true,
            headerClass: "ag-protocol-split-header",
            ...(overlay
              ? {
                  headerGroupComponent: OverlayGroupHeader,
                  headerGroupComponentParams: { color: overlayColor(i) },
                }
              : {}),
            children: buildProtocolChildren(
              entries,
              proto,
              aggregationMode,
              group.key,
              `p:${protoId}@${group.key}`,
            ).filter((c) => !overlay || "children" in c || !isPlotColumn(c.colId)),
          }));
    if (overlay) children.push(...buildOverlayPlotColumns(entries, proto, split));
    groups.push({
      headerName,
      groupId: `p:${protoId}`,
      openByDefault: true,
      headerTooltip:
        wantsOverlay && !overlay && split.groups.length > 0
          ? `${headerName} — more than ${MAX_OVERLAY_CURVES} groups, so their plots stay side by side`
          : headerName,
      headerClass: "ag-protocol-group-header",
      children,
    });
  }

  return groups;
}

// Fixed molecule column (structure + identity stack). Row selection uses
// DataGrid's auto-prepended __select__ checkbox column (enableMultiSelect).
function buildMoleculeColumn(
  imageSize: string,
  structureFields: string[],
  moleculeFields: string[],
  criterion?: StructureCriterion,
  pinIdentity = true,
): ColDef<EnrichedMolecule> {
  const showImage = structureFields.includes("structure");
  const showReg = structureFields.includes("registration_number");
  const showName = moleculeFields.includes("name");
  const thumbSize = imageSize === "large" ? 260 : imageSize === "medium" ? 156 : 80;
  const imageWidth = imageSize === "large" ? 290 : imageSize === "medium" ? 200 : 240;
  return {
    headerName: "Molecule",
    colId: "molecule",
    width: showImage ? imageWidth : 150,
    suppressSizeToFit: true,
    pinned: pinIdentity ? "left" : null,
    filter: false,
    cellStyle: { display: "flex", justifyContent: "center" },
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
      const mol = params.data;
      if (!mol) return null;
      const smiles = mol.structure?.smiles;
      return (
        <div
          className={cn(
            "flex h-full w-full items-center justify-center py-2",
            imageSize === "small" ? "flex-row gap-3" : "flex-col",
          )}
        >
          {showImage &&
            (smiles ? (
              <StructureThumbnail
                smiles={smiles}
                size={thumbSize}
                highlightQuery={
                  criterion?.search_type === "substructure"
                    ? (criterion.smiles_or_smarts ?? criterion.smarts)
                    : undefined
                }
                queryKind={
                  criterion?.query_kind ??
                  detectQueryKind(criterion?.smiles_or_smarts ?? criterion?.smarts ?? "")
                }
              />
            ) : (
              <div
                className="shrink-0 rounded bg-muted"
                style={{ width: thumbSize, height: thumbSize }}
              />
            ))}
          <div
            className={cn(
              "min-w-0",
              imageSize === "small" ? "flex-1 text-left" : "w-full text-center",
              showImage && imageSize !== "small" && "mt-1",
            )}
          >
            {showReg &&
              (mol.registration_number ? (
                <EntityLink
                  type="compound"
                  id={mol.id}
                  label={mol.registration_number}
                  className="block truncate text-xs"
                />
              ) : (
                <p className="truncate font-mono text-xs text-muted-foreground">—</p>
              ))}
            {showName && <p className="truncate text-sm">{mol.name || "Unnamed"}</p>}
          </div>
        </div>
      );
    },
  };
}

/** The cross-protocol "Active in" column. Sorts client-side by the best
 *  µM-normalized entry (nulls last), like the other activity columns. */
export function buildActiveInColumn(): ColDef<EnrichedMolecule> {
  return {
    headerName: "Active in",
    colId: ANY_COLUMN_ID,
    width: 320,
    filter: false,
    valueGetter: (p) => {
      const first = p.data ? anyProtocolActivity(p.data)?.entries[0] : undefined;
      return first?.value_um ?? null;
    },
    // AG Grid negates the whole comparator for desc sort, so a plain
    // "nulls last" return would flip to "nulls first" on desc — direction
    // must be baked in explicitly to keep nulls last both ways.
    comparator: (a: number | null, b: number | null, _nA, _nB, isDescending) => {
      if (a == null && b == null) return 0;
      if (a == null) return isDescending ? -1 : 1;
      if (b == null) return isDescending ? 1 : -1;
      return a - b;
    },
    cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => (
      <ActiveInCell value={params.data ? anyProtocolActivity(params.data) : undefined} />
    ),
  };
}

// ─── Component ──────────────────────────────────────────────────────────────

export function ResultsGrid({
  results,
  protocolColumns,
  columnGroups = null,
  onSortChange,
  protocols,
  reportConfig,
  structureCriterion,
  aggregationMode = "latest",
  loading,
  onRowClick,
  selectedIds,
  onSelectionChange,
  buildExportRequest,
  toolbarLeft,
  toolbarActions,
  footer,
  summary,
  viewControls,
  selectionActions,
}: ResultsGridProps) {
  const resultsHost = useRef<HTMLDivElement>(null);
  const maximizeButton = useRef<HTMLButtonElement>(null);
  const gridHost = useRef<HTMLDivElement>(null);
  const [maximized, setMaximized] = useState(false);
  const [gridHeight, setGridHeight] = useState(480);
  const [pinIdentity, setPinIdentity] = useState(true);
  useLayoutEffect(() => {
    const host = gridHost.current;
    if (!host) return;
    const measure = () => {
      setGridHeight(
        maximized
          ? host.clientHeight
          : Math.max(360, window.innerHeight - Math.max(96, host.getBoundingClientRect().top) - 24),
      );
      setPinIdentity(window.innerWidth >= 640);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(host);
    observer.observe(host.parentElement?.parentElement ?? host);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [maximized]);

  useLayoutEffect(() => {
    if (!maximized) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Keep the existing grid mounted, and keep hidden page controls out of
    // keyboard navigation. New portaled menus and dialogs remain interactive.
    const siblings: { element: HTMLElement; inert: boolean }[] = [];
    let ancestor: HTMLElement | null = resultsHost.current;
    while (ancestor && ancestor !== document.body) {
      for (const sibling of ancestor.parentElement?.children ?? []) {
        if (sibling !== ancestor && sibling instanceof HTMLElement) {
          siblings.push({ element: sibling, inert: sibling.inert });
          sibling.inert = true;
        }
      }
      ancestor = ancestor.parentElement;
    }
    const onEscape = (event: KeyboardEvent) => {
      if (
        event.key !== "Escape" ||
        event.defaultPrevented ||
        document.querySelector(
          '[role="dialog"][data-state="open"], [data-radix-popper-content-wrapper]',
        )
      )
        return;
      setMaximized(false);
      maximizeButton.current?.focus();
    };
    window.addEventListener("keydown", onEscape);
    return () => {
      document.body.style.overflow = overflow;
      for (const { element, inert } of siblings) element.inert = inert;
      window.removeEventListener("keydown", onEscape);
    };
  }, [maximized]);
  const { structure: structureFields, molecule: moleculeFields } = reportConfig.visibleFields;
  // Without the structure image a row only holds text — don't keep the
  // image-sized height (a plot cell still needs ~90px).
  const rowHeight = structureFields.includes("structure")
    ? (ROW_HEIGHTS[reportConfig.imageSize] ?? 150)
    : 96;

  // Show the similarity column only when at least one row actually carries
  // a score (i.e. the active search was a similarity search). Substructure /
  // exact / property-only searches return null scores and we hide the column.
  const hasSimilarityScores = useMemo(
    () => results.some((r) => r.similarity_score != null),
    [results],
  );

  // Use the aggregation committed with these rows, including while a new
  // mode is loading or after a failed request.
  const columnDefs = useMemo<(ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>)[]>(() => {
    const molecule = buildMoleculeColumn(
      reportConfig.imageSize,
      structureFields,
      moleculeFields,
      structureCriterion,
      pinIdentity,
    );
    const identity = buildIdentityColumns(structureFields, moleculeFields);
    const sim = hasSimilarityScores ? [buildSimilarityColumn(structureCriterion)] : [];
    const props = buildPropertyColumns(reportConfig.visibleFields.properties);
    const activeIn = protocolColumns.includes(ANY_COLUMN_ID) ? [buildActiveInColumn()] : [];
    const showPlots = (reportConfig.displayPreset ?? "detailed") === "detailed";
    const styleLeaves = (
      column: ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule>,
    ): ColDef<EnrichedMolecule> | ColGroupDef<EnrichedMolecule> =>
      "children" in column
        ? { ...column, children: column.children.map(styleLeaves) }
        : {
            ...readable(column),
            headerClass: "search-assay-header",
            ...(isPlotColumn(column.colId) ? { hide: !showPlots } : {}),
          };
    const protoGroups = buildProtocolColumnGroups(
      protocolColumns,
      protocols,
      aggregationMode,
      columnGroups,
      shownPlotLayout(reportConfig),
    ).map((group) => styleLeaves(group) as ColGroupDef<EnrichedMolecule>);
    const properties: ColGroupDef<EnrichedMolecule>[] =
      props.length > 0
        ? [
            {
              headerName: "Properties",
              groupId: "properties",
              openByDefault: true,
              headerClass: "search-properties-group-header",
              // Folded, MW and LogP stay: what potency is weighed against.
              children: foldable(props.map(readable), 2),
            },
          ]
        : [];
    return [molecule, ...identity, ...sim, ...activeIn, ...protoGroups, ...properties].map(
      serverSorted,
    );
  }, [
    reportConfig.imageSize,
    reportConfig.displayPreset,
    reportConfig.plotLayout,
    structureCriterion,
    pinIdentity,
    structureFields,
    moleculeFields,
    reportConfig.visibleFields.properties,
    protocolColumns,
    columnGroups,
    protocols,
    hasSimilarityScores,
    aggregationMode,
  ]);

  // DataGrid clears on a falsy token; a nonempty selection must keep it true.
  const clearSelectionToken = selectedIds.size > 0;

  // Keep actions together while allowing the toolbar to wrap on narrower screens.
  const toolbarActionsWithExport = (
    <>
      {toolbarActions}
      {buildExportRequest ? <SharedExportToolbar buildRequest={buildExportRequest} /> : null}
    </>
  );

  return (
    <div
      ref={resultsHost}
      className={cn(
        "search-results-grid min-w-0 rounded-xl border border-border/80 bg-card shadow-sm",
        maximized &&
          "fixed inset-0 z-40 flex flex-col overflow-auto rounded-none border-0 bg-background",
      )}
    >
      <style>{`
        .search-results-grid .ag-root-wrapper { border: 0; border-radius: 0 0 12px 12px; }
        .search-results-grid .ag-cell { display: flex; align-items: center; }
        .search-results-grid .ag-header {
          background: color-mix(in srgb, var(--muted) 65%, var(--background));
          border-top: 1px solid var(--border);
          border-bottom: 1px solid color-mix(in srgb, var(--primary) 20%, var(--border));
        }
        .search-results-grid .ag-header-cell { font-size: 12px; font-weight: 600; }
        .search-results-grid .ag-header-cell::after,
        .search-results-grid .ag-header-group-cell::after { display: none; }
        .search-results-grid .ag-header-cell-resize::after { opacity: 0; width: 1px; }
        .search-results-grid .ag-header-cell:hover .ag-header-cell-resize::after,
        .search-results-grid .ag-header-cell:focus-within .ag-header-cell-resize::after,
        .search-results-grid .ag-header-group-cell:hover .ag-header-cell-resize::after { opacity: 1; }
        .search-results-grid .ag-header-cell-filter-button { opacity: 0.45; }
        .search-results-grid .ag-header-cell:hover .ag-header-cell-filter-button,
        .search-results-grid .ag-header-cell:focus-within .ag-header-cell-filter-button,
        .search-results-grid .ag-header-cell-filtered .ag-header-cell-filter-button { opacity: 1; }
        .search-results-grid .ag-protocol-group-header {
          background: color-mix(in srgb, var(--primary) 12%, var(--background));
          border-bottom: 1px solid color-mix(in srgb, var(--primary) 18%, transparent);
        }
        .search-results-grid .ag-protocol-group-header .ag-header-group-cell-label {
          color: var(--primary);
          font-weight: 650;
          font-size: 11px;
          letter-spacing: 0.01em;
        }
        .search-results-grid .ag-protocol-group-header .ag-header-group-cell-label::before {
          content: ""; width: 6px; height: 6px; flex-shrink: 0;
          border-radius: 50%; background: var(--primary); margin-right: 7px;
        }
        .search-results-grid .search-assay-header {
          background: color-mix(in srgb, var(--primary) 5%, var(--background));
        }
        .search-results-grid .search-properties-group-header {
          color: color-mix(in srgb, var(--foreground) 70%, var(--background)); font-size: 11px; font-weight: 600;
          letter-spacing: 0.02em;
        }
        .search-results-grid .ag-row-odd:not(.ag-row-selected) {
          background: color-mix(in srgb, var(--muted) 16%, var(--background));
        }
        .search-results-grid .ag-row-selected {
          background: var(--background);
        }
        .search-results-grid .ag-row-selected::before {
          background: color-mix(in srgb, var(--primary) 10%, transparent);
        }
      `}</style>
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 py-3">
        <div className="min-w-0 flex-1 basis-64 space-y-1">
          <div className="flex flex-wrap items-center gap-2">{toolbarLeft}</div>
          {summary}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {toolbarActionsWithExport}
          <Button
            ref={maximizeButton}
            variant="ghost"
            size="icon-sm"
            aria-label={maximized ? "Restore search results" : "Maximize search results"}
            aria-pressed={maximized}
            title={maximized ? "Restore search results (Esc)" : "Maximize search results"}
            onClick={() => setMaximized((value) => !value)}
          >
            {maximized ? <Minimize2 /> : <Maximize2 />}
          </Button>
        </div>
      </div>
      {(viewControls || selectionActions) && (
        <div className="shrink-0 space-y-2 border-t border-border/60 px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">{viewControls}</div>
            {selectedIds.size === 0 && selectionActions}
          </div>
          {selectedIds.size > 0 && selectionActions}
        </div>
      )}
      <div ref={gridHost} className={maximized ? "min-h-40 flex-1" : undefined}>
        <DataGrid<EnrichedMolecule>
          rowData={results}
          // Stable ids keep ticked rows ticked when Load More appends a page
          // (without them AG Grid treats every row as new and drops selection).
          getRowId={(p) => p.data.id}
          columnDefs={columnDefs}
          onSortChanged={(event) => {
            const sorted = event.api.getColumnState().find((c) => c.sort);
            onSortChange?.(
              serverSortToken(sorted?.colId) ?? undefined,
              sorted?.sort === "desc" ? "desc" : "asc",
            );
          }}
          loading={loading}
          emptyState={
            <p className="py-12 text-center text-sm text-muted-foreground">
              No results to display.
            </p>
          }
          height={gridHeight}
          rowHeight={rowHeight}
          headerHeight={36}
          groupHeaderHeight={32}
          enableMultiSelect
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
      </div>
      {footer && <div className="shrink-0">{footer}</div>}
    </div>
  );
}
