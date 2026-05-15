"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import { Badge } from "@/shared/components/ui/badge";
import { groupBy } from "@/shared/lib/group-by";
import { cn } from "@/shared/lib/utils";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { type ReactNode, useMemo } from "react";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";
import {
  findInterceptValue,
  formatInterceptDisplay,
  interceptLabel,
  maxDoseFromRawData,
} from "../lib/intercept-label";
import { resolvePickListColor } from "../lib/pick-list-colors";
import {
  type DoseResponseCurve,
  type InterceptSpec,
  READOUT_NORMALIZATION_LABELS,
  type ReadoutData,
  type ReadoutDefinition,
  type ReadoutNormalization,
} from "../types";

interface ReadoutDataTableProps {
  runId: string;
  protocolId: string;
  className?: string;
  /** Extra controls rendered in the table toolbar (e.g. Import Run File). */
  toolbarActions?: ReactNode;
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

const valueKey = (defId: string, isComputed: boolean) => `${defId}::${isComputed ? "c" : "r"}`;

/** First non-NONE normalization on a readout def, or null. When a def emits
 * multiple formulas (e.g. raw + %inh + z-score) we surface the first as the
 * primary label; other layers can be added later if needed. */
function primaryNormalization(rd: ReadoutDefinition): ReadoutNormalization | null {
  return rd.normalizations?.find((n) => n !== "none") ?? null;
}

/** Display label for the post-normalization layer of a readout def.
 * E.g. "raw AU" + PERCENT_INHIBITION → "raw AU — % Inhibition". */
function computedLayerHeader(rd: ReadoutDefinition): string {
  if (rd.is_calculated) return rd.unit ? `${rd.name} (${rd.unit})` : rd.name;
  const norm = primaryNormalization(rd);
  if (norm) {
    const label = READOUT_NORMALIZATION_LABELS[norm] ?? norm;
    return `${rd.name} — ${label}`;
  }
  return rd.name;
}

function hasComputedLayer(rd: ReadoutDefinition): boolean {
  return rd.is_calculated || primaryNormalization(rd) !== null;
}

/** Format a value with qualifier prefix: "85.2", "<12.7", ">1000" */
function formatValue(row: ReadoutData): string {
  if (row.value_numeric === null || row.value_numeric === undefined) {
    return row.value_text ?? "\u2014";
  }
  const prefix = row.value_qualifier && row.value_qualifier !== "=" ? row.value_qualifier : "";
  return `${prefix}${row.value_numeric.toFixed(3)}`;
}

/** Aliases for a row from its enriched name + synonyms, deduped against the
 * registration number so the Compound column doesn't echo Aliases. */
function buildAliases(row: ReadoutData): string[] {
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
}

export function ReadoutDataTable({
  runId,
  protocolId,
  className,
  toolbarActions,
}: ReadoutDataTableProps) {
  const { data, isLoading } = useReadoutDataByRun(runId);
  const { data: curves } = useDoseResponseByRun(runId);
  const { data: protocol } = useProtocol(protocolId);

  const readoutDefs = useMemo(() => protocol?.readout_definitions ?? [], [protocol]);

  // Map dose-response readout def id -> {(molecule_id::batch_id) -> curve}.
  // The IC50 column on the readout-data table reads the per-(mol,batch)
  // fitted_value here so every row of a compound shows that compound's curve
  // value (curves don't exist per-well; this is the natural way to surface
  // DR results alongside per-well readouts).
  //
  // Curves are matched by ``readout_definition_id`` — a protocol can have
  // multiple DR readouts sharing one curve_type (target IC50 + counter-
  // screen IC50), so matching by curve_type would mix them together.
  const curveLookup = useMemo(() => {
    const map = new Map<string, Map<string, DoseResponseCurve>>();
    for (const rd of readoutDefs) {
      if (rd.data_type !== "dose_response") continue;
      map.set(rd.id, new Map());
    }
    for (const c of curves ?? []) {
      const inner = map.get(c.readout_definition_id);
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

  // Pivot readout data into rows
  const pivotRows = useMemo<PivotRow[]>(() => {
    if (!data) return [];

    // 1. Bucket per-molecule rows (no well_id) — these are calculated
    // readouts that the engine produced once per (mol, batch). They get
    // merged into every well row of the same group below.
    const perMolRows = data.filter((row) => row.molecule_id && !row.well_id);
    const perMol = groupBy(perMolRows, (row) => `${row.molecule_id}::${row.batch_id ?? ""}`);

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
            <span className="text-xs text-muted-foreground" title={aliases.join(", ")}>
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
      // Dose-response readouts: one denormalized column per protocol
      // intercept (EC50, EC90, ...). Header via `interceptLabel(spec)`,
      // cell value via `findInterceptValue` (matched by (kind, level) so
      // per-protocol label drift doesn't break the lookup). Primary
      // intercept falls back to `curve.fitted_value` for legacy curves
      // fit before `intercept_values` were persisted (spec §6).
      if (rd.data_type === "dose_response") {
        const intercepts: InterceptSpec[] = rd.dose_response_config?.intercepts ?? [];
        const drHeader = rd.unit ? `${rd.name} (${rd.unit})` : rd.name;
        if (intercepts.length > 0) {
          intercepts.forEach((spec, idx) => {
            const isPrimary = idx === 0;
            const header = `${rd.name} ${interceptLabel(spec)}${rd.unit ? ` (${rd.unit})` : ""}`;
            cols.push({
              headerName: header,
              headerTooltip:
                rd.description ||
                "Dose-response intercept (derived) — same for every well of a compound",
              colId: `${rd.id}::${spec.kind}::${spec.level}`,
              width: 140,
              cellClass: "text-right tabular-nums",
              headerClass: "ag-right-aligned-header italic",
              valueGetter: (p) => {
                const curve = p.data?.curves.get(rd.id);
                if (!curve) return null;
                const iv = findInterceptValue(curve.intercept_values, spec);
                const value = iv?.value ?? (isPrimary ? curve.fitted_value : null);
                return formatInterceptDisplay({
                  value,
                  at_bound: iv?.at_bound,
                  curve_class: curve.curve_class,
                  max_dose: maxDoseFromRawData(
                    curve.raw_data as Array<{ x?: number; concentration?: number }> | null,
                  ),
                }).sortValue;
              },
              cellRenderer: (params: { data: PivotRow | undefined }) => {
                const curve = params.data?.curves.get(rd.id);
                if (!curve) {
                  return <span className="text-muted-foreground">{"—"}</span>;
                }
                const iv = findInterceptValue(curve.intercept_values, spec);
                const value = iv?.value ?? (isPrimary ? curve.fitted_value : null);
                const display = formatInterceptDisplay({
                  value,
                  at_bound: iv?.at_bound,
                  curve_class: curve.curve_class,
                  max_dose: maxDoseFromRawData(
                    curve.raw_data as Array<{ x?: number; concentration?: number }> | null,
                  ),
                });
                const showUnit = display.kind === "scalar" || display.kind === "qualifier";
                const unitSuffix =
                  showUnit && curve.fitted_unit ? ` ${curve.fitted_unit}` : "";
                if (display.warning) {
                  return (
                    <Badge
                      variant="outline"
                      className="text-xs border-amber-500 text-amber-700"
                      title={display.tooltip}
                    >
                      <span className="font-mono">
                        {display.text}
                        {unitSuffix}
                      </span>
                    </Badge>
                  );
                }
                const baseTooltip =
                  display.tooltip ||
                  (curve.curve_class
                    ? `${curve.curve_class} · R² = ${curve.r_squared.toFixed(3)}`
                    : undefined);
                return (
                  <span
                    className={cn(
                      "font-mono",
                      display.kind !== "scalar" && "text-muted-foreground",
                    )}
                    title={baseTooltip}
                  >
                    {display.text}
                    {unitSuffix}
                  </span>
                );
              },
            });
          });
          continue;
        }
        cols.push({
          headerName: drHeader,
          headerTooltip:
            rd.description || "Dose-response fit value — same for every well of a compound",
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
                className={cn(curve.curve_class === "inactive" && "text-muted-foreground")}
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
        const isPickList = rd.data_type === "pick_list";
        cols.push({
          headerName: rawHeader,
          headerTooltip: rd.description ?? undefined,
          colId: `${rd.id}::raw`,
          width: 130,
          cellClass: isPickList ? undefined : "text-right tabular-nums",
          headerClass: isPickList ? undefined : "ag-right-aligned-header",
          valueGetter: (p) => {
            const row = p.data?.values.get(valueKey(rd.id, false));
            if (!row) return null;
            return row.value_numeric ?? row.value_text ?? null;
          },
          cellRenderer: (params: { data: PivotRow | undefined }) => {
            const row = params.data?.values.get(valueKey(rd.id, false));
            if (!row) return <span className="text-muted-foreground">{"\u2014"}</span>;
            // Pick-list cells render as a colored Badge using the
            // declared color (or hash-derived fallback when null).
            if (isPickList && row.value_text) {
              const declared = rd.pick_list_values?.find((v) => v.label === row.value_text);
              const color = resolvePickListColor(row.value_text, declared?.color);
              return (
                <Badge variant="outline" className={cn("text-xs", color.bg, color.text)}>
                  {row.value_text}
                </Badge>
              );
            }
            return (
              <span
                className={cn(
                  row.is_outlier && "text-destructive line-through decoration-destructive/50",
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
          headerTooltip: (() => {
            if (rd.is_calculated && rd.calculation_formula) {
              return `Calculated: ${rd.calculation_formula}`;
            }
            const norm = primaryNormalization(rd);
            if (norm) {
              return `Per-plate normalization (${
                READOUT_NORMALIZATION_LABELS[norm] ?? norm
              }) of ${rd.name}`;
            }
            return undefined;
          })(),
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
            if (!row) return <span className="text-muted-foreground">{"\u2014"}</span>;
            return (
              <span
                className={cn(
                  "text-muted-foreground",
                  row.is_outlier && "text-destructive line-through decoration-destructive/50",
                )}
                title={row.is_outlier ? "Flagged as outlier" : "Calculated value"}
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
        toolbarActions={toolbarActions}
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
