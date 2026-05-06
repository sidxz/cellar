"use client";

import { useMemo } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import { cn } from "@/shared/lib/utils";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";
import {
  READOUT_NORMALIZATION_LABELS,
  type DoseResponseCurve,
  type ReadoutData,
  type ReadoutDefinition,
} from "../types";

interface ReadoutDataTableProps {
  runId: string;
  protocolId: string;
  className?: string;
}

interface PivotRow {
  key: string;
  label: string;
  registrationNumber: string;
  moleculeName: string;
  /** molecule.name + custom synonyms, deduped against the registration number. */
  aliases: string[];
  batchNumber: string;
  moleculeId: string;
  batchId: string;
  wellId: string | null;
  /** Keyed by `${readout_def_id}::${"raw"|"computed"}` so the raw and
   * post-normalization layers stay separate (they share readout_def_id).
   * Per-molecule calculated readouts are merged into every well row of the
   * same (molecule, batch) group. */
  values: Map<string, ReadoutData>;
  /** dose_response readout def id -> curve. Same value for every row in the
   * (molecule, batch) group — DR is not per-well. */
  curves: Map<string, DoseResponseCurve>;
}

const valueKey = (defId: string, isComputed: boolean) =>
  `${defId}::${isComputed ? "c" : "r"}`;

/** Display label for the post-normalization layer of a readout def.
 * E.g. "raw AU" + PERCENT_INHIBITION → "raw AU — % Inhibition". */
function computedLayerHeader(rd: ReadoutDefinition): string {
  if (rd.is_calculated) return rd.unit ? `${rd.name} (${rd.unit})` : rd.name;
  if (rd.normalization && rd.normalization !== "none") {
    const label = READOUT_NORMALIZATION_LABELS[rd.normalization] ?? rd.normalization;
    return `${rd.name} — ${label}`;
  }
  return rd.name;
}

function hasComputedLayer(rd: ReadoutDefinition): boolean {
  return rd.is_calculated || (rd.normalization && rd.normalization !== "none");
}

/** Format a value with qualifier prefix: "85.2", "<12.7", ">1000" */
function formatValue(row: ReadoutData): string {
  if (row.value_numeric === null || row.value_numeric === undefined) {
    return row.value_text ?? "\u2014";
  }
  const prefix =
    row.value_qualifier && row.value_qualifier !== "=" ? row.value_qualifier : "";
  return `${prefix}${row.value_numeric.toFixed(3)}`;
}

export function ReadoutDataTable({
  runId,
  protocolId,
  className,
}: ReadoutDataTableProps) {
  const { data, isLoading } = useReadoutDataByRun(runId);
  const { data: curves } = useDoseResponseByRun(runId);
  const { data: protocol } = useProtocol(protocolId);

  const readoutDefs = protocol?.readout_definitions ?? [];

  // Map dose-response readout def id -> {(molecule_id::batch_id) -> curve}.
  // The IC50 column on the readout-data table reads the per-(mol,batch)
  // fitted_value here so every row of a compound shows that compound's curve
  // value (curves don't exist per-well; this is the natural way to surface
  // DR results alongside per-well readouts).
  const curveLookup = useMemo(() => {
    const map = new Map<string, Map<string, DoseResponseCurve>>();
    for (const rd of readoutDefs) {
      if (rd.data_type !== "dose_response") continue;
      map.set(rd.id, new Map());
    }
    for (const c of curves ?? []) {
      // Pick the curve matching the protocol's dose-response def by curve_type
      const def = readoutDefs.find(
        (rd) =>
          rd.data_type === "dose_response" &&
          rd.dose_response_config?.curve_type === c.curve_type,
      );
      if (!def) continue;
      const inner = map.get(def.id);
      if (!inner) continue;
      const key = `${c.molecule_id}::${c.batch_id}`;
      // If multiple curves exist for the same (mol, batch) (e.g. refits),
      // prefer the one with the higher r_squared.
      const existing = inner.get(key);
      if (!existing || c.r_squared > existing.r_squared) {
        inner.set(key, c);
      }
    }
    return map;
  }, [curves, readoutDefs]);

  /** Build aliases for a row from its (already enriched) name + synonyms,
   * deduped against the registration number so the Compound column doesn't
   * echo the same value as Aliases. */
  const buildAliases = (row: ReadoutData): string[] => {
    const aliases: string[] = [];
    if (
      row.molecule_name &&
      row.molecule_name !== row.registration_number &&
      !aliases.includes(row.molecule_name)
    ) {
      aliases.push(row.molecule_name);
    }
    for (const s of row.synonyms ?? []) {
      if (s && s !== row.registration_number && !aliases.includes(s)) {
        aliases.push(s);
      }
    }
    return aliases;
  };

  // Pivot readout data into rows
  const pivotRows = useMemo<PivotRow[]>(() => {
    if (!data) return [];

    // 1. Bucket per-molecule rows (no well_id) — these are calculated
    // readouts that the engine produced once per (mol, batch). They get
    // merged into every well row of the same group below.
    const perMol = new Map<string, ReadoutData[]>();
    for (const row of data) {
      if (!row.molecule_id || row.well_id) continue;
      const k = `${row.molecule_id}::${row.batch_id ?? ""}`;
      if (!perMol.has(k)) perMol.set(k, []);
      perMol.get(k)!.push(row);
    }

    // 2. Group per-well rows by (molecule, batch, well).
    const groups = new Map<string, PivotRow>();
    for (const row of data) {
      if (!row.molecule_id) continue;
      if (!row.well_id) continue; // per-mol rows handled in step 3
      const key = `${row.molecule_id}::${row.batch_id}::${row.well_id}`;
      let group = groups.get(key);
      if (!group) {
        const curveKey = `${row.molecule_id}::${row.batch_id ?? ""}`;
        const rowCurves = new Map<string, DoseResponseCurve>();
        for (const [defId, byKey] of curveLookup) {
          const c = byKey.get(curveKey);
          if (c) rowCurves.set(defId, c);
        }
        group = {
          key,
          label: row.registration_number ?? "Unknown",
          registrationNumber: row.registration_number ?? "",
          moleculeName: row.molecule_name ?? "",
          aliases: buildAliases(row),
          batchNumber: row.batch_number ?? "",
          moleculeId: row.molecule_id,
          batchId: row.batch_id ?? "",
          wellId: row.well_id,
          values: new Map(),
          curves: rowCurves,
        };
        groups.set(key, group);
      }
      // Raw and computed layers share readout_definition_id but differ on
      // is_computed — key them separately so neither overwrites the other.
      group.values.set(valueKey(row.readout_definition_id, row.is_computed), row);
    }

    // 3. Merge per-(mol, batch) calculated readouts into every well of
    // that group so they show on every row that compound appears on.
    for (const group of groups.values()) {
      const molRows = perMol.get(`${group.moleculeId}::${group.batchId}`);
      if (!molRows) continue;
      for (const row of molRows) {
        group.values.set(valueKey(row.readout_definition_id, row.is_computed), row);
      }
    }

    return Array.from(groups.values());
  }, [data, curveLookup]);

  // Dynamic columns: Compound + one per readout definition
  const columnDefs = useMemo<ColDef<PivotRow>[]>(() => {
    const cols: ColDef<PivotRow>[] = [
      {
        headerName: "Compound",
        field: "registrationNumber",
        pinned: "left",
        width: 120,
        cellRenderer: (params: ICellRendererParams<PivotRow>) => {
          const row = params.data;
          if (!row) return null;
          return (
            <EntityLink
              type="compound"
              id={row.moleculeId}
              label={row.registrationNumber}
              className="text-xs"
            />
          );
        },
      },
      {
        headerName: "Aliases",
        colId: "aliases",
        width: 180,
        sortable: false,
        valueGetter: (p) => p.data?.aliases.join(", ") ?? "",
        cellRenderer: (params: ICellRendererParams<PivotRow>) => {
          const aliases = params.data?.aliases ?? [];
          if (aliases.length === 0) {
            return <span className="text-muted-foreground">{"\u2014"}</span>;
          }
          // Show up to 2 inline; rest available via tooltip.
          const visible = aliases.slice(0, 2);
          const overflow = aliases.length - visible.length;
          return (
            <span
              className="text-xs text-muted-foreground"
              title={aliases.join(", ")}
            >
              {visible.join(" · ")}
              {overflow > 0 && ` +${overflow}`}
            </span>
          );
        },
      },
      {
        headerName: "Batch",
        field: "batchNumber",
        width: 100,
      },
    ];

    for (const rd of readoutDefs) {
      // Dose-response readouts: single column from the curves table.
      if (rd.data_type === "dose_response") {
        const drHeader = rd.unit ? `${rd.name} (${rd.unit})` : rd.name;
        cols.push({
          headerName: drHeader,
          headerTooltip:
            "Dose-response fit value — same for every well of a compound",
          colId: rd.id,
          width: 130,
          cellClass: "text-right tabular-nums",
          headerClass: "ag-right-aligned-header italic",
          valueGetter: (p) => p.data?.curves.get(rd.id)?.fitted_value ?? null,
          cellRenderer: (params: { data: PivotRow | undefined }) => {
            const curve = params.data?.curves.get(rd.id);
            if (!curve) {
              return <span className="text-muted-foreground">{"\u2014"}</span>;
            }
            return (
              <span
                className={cn(
                  curve.curve_class === "inactive" && "text-muted-foreground",
                )}
                title={
                  curve.curve_class
                    ? `${curve.curve_class} · R² = ${curve.r_squared.toFixed(3)}`
                    : undefined
                }
              >
                {curve.fitted_value.toPrecision(4)} {curve.fitted_unit}
              </span>
            );
          },
        });
        continue;
      }

      // Raw column — present unless the readout is purely calculated (in
      // which case there is no raw layer; only the formula output).
      if (!rd.is_calculated) {
        const rawHeader = rd.unit ? `${rd.name} (${rd.unit})` : rd.name;
        cols.push({
          headerName: rawHeader,
          colId: `${rd.id}::raw`,
          width: 130,
          cellClass: "text-right tabular-nums",
          headerClass: "ag-right-aligned-header",
          valueGetter: (p) => {
            const row = p.data?.values.get(valueKey(rd.id, false));
            if (!row) return null;
            return row.value_numeric ?? row.value_text ?? null;
          },
          cellRenderer: (params: { data: PivotRow | undefined }) => {
            const row = params.data?.values.get(valueKey(rd.id, false));
            if (!row)
              return <span className="text-muted-foreground">{"\u2014"}</span>;
            return (
              <span
                className={cn(
                  row.is_outlier &&
                    "text-destructive line-through decoration-destructive/50",
                )}
                title={row.is_outlier ? "Flagged as outlier" : undefined}
              >
                {formatValue(row)}
              </span>
            );
          },
        });
      }

      // Computed column — emitted whenever the def is normalized or the
      // engine evaluates a formula for it. Italic header + italic muted
      // cells signal "this value is derived, not directly imported"; the
      // tooltip explains the derivation.
      if (hasComputedLayer(rd)) {
        cols.push({
          headerName: computedLayerHeader(rd),
          headerTooltip: rd.is_calculated && rd.calculation_formula
            ? `Calculated: ${rd.calculation_formula}`
            : rd.normalization && rd.normalization !== "none"
            ? `Per-plate normalization (${
                READOUT_NORMALIZATION_LABELS[rd.normalization] ?? rd.normalization
              }) of ${rd.name}`
            : undefined,
          colId: `${rd.id}::computed`,
          width: 140,
          cellClass: "text-right tabular-nums italic",
          headerClass: "ag-right-aligned-header italic",
          valueGetter: (p) => {
            const row = p.data?.values.get(valueKey(rd.id, true));
            if (!row) return null;
            return row.value_numeric ?? row.value_text ?? null;
          },
          cellRenderer: (params: { data: PivotRow | undefined }) => {
            const row = params.data?.values.get(valueKey(rd.id, true));
            if (!row)
              return <span className="text-muted-foreground">{"\u2014"}</span>;
            return (
              <span
                className={cn(
                  "text-muted-foreground",
                  row.is_outlier &&
                    "text-destructive line-through decoration-destructive/50",
                )}
                title={
                  row.is_outlier ? "Flagged as outlier" : "Calculated value"
                }
              >
                {formatValue(row)}
              </span>
            );
          },
        });
      }
    }
    return cols;
  }, [readoutDefs]);

  return (
    <div className={className}>
      <DataGrid<PivotRow>
        rowData={pivotRows}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        suppressFilters
        exportFilename={`readout-data-${runId}`}
        getRowId={(params) => params.data.key}
        emptyState={
          <p className="py-8 text-center text-sm text-muted-foreground">
            No readout data recorded for this run.
          </p>
        }
      />
    </div>
  );
}
