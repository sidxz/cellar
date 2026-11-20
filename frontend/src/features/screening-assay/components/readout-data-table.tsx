"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Input } from "@/shared/components/ui/input";
import { resolveCategoryColor } from "@/shared/lib/category-colors";
import { cn } from "@/shared/lib/utils";
import type { ColDef, ColGroupDef, ICellRendererParams } from "ag-grid-community";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { useDoseResponseByRun } from "../hooks/use-dose-response";
import { usePlateMap } from "../hooks/use-plate-setup";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";
import {
  doseRange,
  findInterceptValue,
  formatInterceptDisplay,
  interceptLabel,
} from "../lib/intercept-label";
import {
  type PivotRow,
  hasComputedLayer,
  hasRawLayer,
  pivotReadoutData,
  valueKey,
} from "../lib/readout-data-pivot";
import {
  type DoseResponseCurve,
  type InterceptSpec,
  READOUT_NORMALIZATION_LABELS,
  type ReadoutData,
  type ReadoutDefinition,
  type ReadoutNormalization,
  narrowInterceptValues,
} from "../types";
import { ReadoutCompoundCell, ReadoutPositionCell } from "./readout-data-table-cells";
import { type ReadoutTableRow, readoutTableRows } from "./readout-data-table-view";
import { RunResultsMaximizeHeader, RunStructureCell } from "./run-dr-results-cells";
import { normalizeDoseUnit } from "./run-dr-results-view";
import { useRunResultsFocus } from "./use-run-results-focus";
import "./readout-data-table.css";

interface ReadoutDataTableProps {
  runId: string;
  protocolId: string;
  className?: string;
  /** Extra controls rendered in the table toolbar (e.g. Import Run File). */
  toolbarActions?: ReactNode;
}

/** First non-NONE normalization on a readout def, or null. When a def emits
 * multiple formulas (e.g. raw + %inh + z-score) we surface the first as the
 * primary label; other layers can be added later if needed. */
function primaryNormalization(rd: ReadoutDefinition): ReadoutNormalization | null {
  return rd.normalizations?.find((n) => n !== "none") ?? null;
}

/** The readout name is in the group header; each child names its own layer. */
function computedLayerHeader(rd: ReadoutDefinition): string {
  if (!hasRawLayer(rd)) return rd.unit ? `Calculated (${rd.unit})` : "Calculated";
  const norm = primaryNormalization(rd);
  if (norm) {
    const label = READOUT_NORMALIZATION_LABELS[norm] ?? norm;
    return label;
  }
  return "Calculated";
}

/** Format a value with qualifier prefix: "85.2", "<12.7", ">1000" */
function formatValue(row: ReadoutData): string {
  if (row.value_numeric === null || row.value_numeric === undefined) {
    return row.value_text ?? "\u2014";
  }
  const prefix = row.value_qualifier && row.value_qualifier !== "=" ? row.value_qualifier : "";
  return `${prefix}${row.value_numeric.toFixed(3)}`;
}

/** "n=3" after a summary value; a quiet "n —" when the count wasn't recorded. */
function ReplicateCount({ n }: { n: number | null }) {
  return (
    <span
      className="ml-1.5 text-[11px] text-muted-foreground"
      title={n == null ? "Replicates not recorded" : `Mean of ${n} replicates`}
    >
      {n == null ? "n —" : `n=${n}`}
    </span>
  );
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
  const { data: plateMap } = usePlateMap(runId);

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

  const pivotRows = useMemo(() => pivotReadoutData(data, curveLookup), [data, curveLookup]);
  const tableRows = useMemo(() => readoutTableRows(pivotRows, plateMap), [pivotRows, plateMap]);
  const [quickFilter, setQuickFilter] = useState("");
  const [visibleCount, setVisibleCount] = useState<number | null>(null);
  const [hiddenReadouts, setHiddenReadouts] = useState<string[]>([]);
  const [outliersOnly, setOutliersOnly] = useState(false);
  const { expanded, setExpanded, resultsRef, buttonRef } = useRunResultsFocus();
  const outlierRows = useMemo(
    () => tableRows.filter((row) => [...row.values.values()].some((value) => value.is_outlier)),
    [tableRows],
  );
  // A refetch can clear the last outlier and hide the toggle; never leave its filter on unseen.
  const showOutliersOnly = outliersOnly && outlierRows.length > 0;
  const rowData = showOutliersOnly ? outlierRows : tableRows;
  const compoundCount = new Set(tableRows.map((row) => row.moleculeId)).size;

  // Off by default; showing structures gives each row a larger drawing canvas.
  const [showStructures, setShowStructures] = useState(false);

  // Keep identifiers pinned; group each readout's raw, normalized or fitted layers.
  const columnDefs = useMemo<(ColDef<ReadoutTableRow> | ColGroupDef<ReadoutTableRow>)[]>(() => {
    const cols: (ColDef<ReadoutTableRow> | ColGroupDef<ReadoutTableRow>)[] = [
      {
        headerName: "Compound & aliases",
        field: "registrationNumber",
        pinned: "left",
        lockPinned: true,
        initialWidth: 260,
        minWidth: 220,
        maxWidth: 340,
        initialSort: "asc",
        initialSortIndex: 0,
        getQuickFilterText: ({ data: row }) =>
          row ? [row.registrationNumber, ...row.aliases, row.batchNumber].join(" ") : "",
        cellRenderer: ({ data: row }: ICellRendererParams<ReadoutTableRow>) =>
          row ? <ReadoutCompoundCell data={row} query={quickFilter} /> : null,
      },
      {
        headerName: "Plate / well",
        colId: "position",
        initialWidth: 130,
        minWidth: 110,
        maxWidth: 180,
        wrapHeaderText: true,
        autoHeaderHeight: true,
        valueGetter: ({ data: row }) => row?.positionOrder ?? null,
        getQuickFilterText: ({ data: row }) =>
          row ? `${row.plateLabel ?? ""} ${row.position ?? (row.wellId ? "" : "Summary")}` : "",
        cellRenderer: ({ data: row }: ICellRendererParams<ReadoutTableRow>) =>
          row ? <ReadoutPositionCell data={row} /> : null,
      },
      {
        headerName: plateMap?.dose_unit
          ? `Concentration (${plateMap.dose_unit.replace(/uM/g, "µM")})`
          : "Concentration",
        headerTooltip: "Tested concentration for this well",
        field: "dose",
        initialWidth: 165,
        minWidth: 130,
        cellClass: "text-right tabular-nums",
        headerClass: "ag-right-aligned-header",
        wrapHeaderText: true,
        autoHeaderHeight: true,
        valueFormatter: ({ value }) => (value == null ? "—" : String(Number(value.toPrecision(5)))),
      },
    ];

    // Optional structure column (toggled): right after Compound so the
    // thumbnail sits next to its identifier, mirroring the DR table.
    if (showStructures) {
      cols.splice(1, 0, {
        headerName: "Structure",
        colId: "structure",
        initialWidth: 200,
        minWidth: 180,
        sortable: false,
        cellRenderer: (params: ICellRendererParams<ReadoutTableRow>) => {
          const smiles = params.data?.smiles;
          if (!smiles) return <span className="text-muted-foreground">{"—"}</span>;
          return (
            <div className="h-full w-full">
              <RunStructureCell
                data={{ smiles, registration_number: params.data?.registrationNumber ?? "" }}
              />
            </div>
          );
        },
      });
    }

    for (const rd of readoutDefs) {
      if (hiddenReadouts.includes(rd.id)) continue;
      const children: ColDef<ReadoutTableRow>[] = [];
      const addGroup = () => {
        cols.push({ headerName: rd.name, groupId: rd.id, marryChildren: true, children });
      };
      // Dose-response readouts: one denormalized column per protocol
      // intercept (EC50, EC90, ...). Header via `interceptLabel(spec)`,
      // cell value via `findInterceptValue` (matched by (kind, level) so
      // per-protocol label drift doesn't break the lookup). Primary
      // intercept falls back to `curve.fitted_value` for legacy curves
      // fit before `intercept_values` were persisted (spec §6).
      if (rd.data_type === "dose_response") {
        const intercepts: InterceptSpec[] = rd.dose_response_config?.intercepts ?? [];
        if (intercepts.length > 0) {
          intercepts.forEach((spec, idx) => {
            const isPrimary = idx === 0;
            // The readout group names the assay; its children name each intercept.
            const baseLabel = interceptLabel(spec);
            const header = rd.unit ? `${baseLabel} (${rd.unit})` : baseLabel;
            children.push({
              headerName: header,
              headerTooltip:
                rd.description ||
                "Dose-response intercept (derived) — same for every well of a compound",
              colId: `${rd.id}::${spec.kind}::${spec.level}`,
              initialWidth: 160,
              minWidth: 140,
              wrapHeaderText: true,
              autoHeaderHeight: true,
              cellClass: "text-right tabular-nums",
              headerClass: "ag-right-aligned-header",
              valueGetter: (p) => {
                const curve = p.data?.curves.get(rd.id);
                if (!curve) return null;
                const iv = findInterceptValue(narrowInterceptValues(curve.intercept_values), spec);
                const value = iv?.value ?? (isPrimary ? curve.fitted_value : null);
                return formatInterceptDisplay({
                  value,
                  at_bound: iv?.at_bound,
                  qualifier: iv?.qualifier,
                  primary: isPrimary,
                  curve_class: curve.curve_class,
                  ...doseRange(curve.raw_data),
                }).sortValue;
              },
              cellRenderer: (params: { data: PivotRow | undefined }) => {
                const curve = params.data?.curves.get(rd.id);
                if (!curve) {
                  return <span className="text-muted-foreground">{"—"}</span>;
                }
                const iv = findInterceptValue(narrowInterceptValues(curve.intercept_values), spec);
                const value = iv?.value ?? (isPrimary ? curve.fitted_value : null);
                const display = formatInterceptDisplay({
                  value,
                  at_bound: iv?.at_bound,
                  qualifier: iv?.qualifier,
                  primary: isPrimary,
                  curve_class: curve.curve_class,
                  ...doseRange(curve.raw_data),
                });
                const showUnit = display.kind === "scalar" || display.kind === "qualifier";
                const unitSuffix =
                  showUnit &&
                  curve.fitted_unit &&
                  normalizeDoseUnit(curve.fitted_unit) !== normalizeDoseUnit(rd.unit ?? "")
                    ? ` ${curve.fitted_unit}`
                    : "";
                if (display.warning) {
                  return (
                    <Badge
                      variant="outline"
                      className="text-xs border-amber-500 text-amber-700"
                      title={display.tooltip}
                    >
                      <span className="tabular-nums">
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
                      "tabular-nums",
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
          addGroup();
          continue;
        }
        children.push({
          headerName: rd.unit ? `Fitted (${rd.unit})` : "Fitted",
          headerTooltip:
            rd.description || "Dose-response fit value — same for every well of a compound",
          colId: rd.id,
          initialWidth: 160,
          minWidth: 140,
          cellClass: "text-right tabular-nums",
          headerClass: "ag-right-aligned-header",
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
                {curve.fitted_value.toPrecision(4)}
                {normalizeDoseUnit(curve.fitted_unit) !== normalizeDoseUnit(rd.unit ?? "")
                  ? ` ${curve.fitted_unit}`
                  : ""}
              </span>
            );
          },
        });
        addGroup();
        continue;
      }

      // Raw column — absent for calculated and temperature-window readouts,
      // whose only layer is the computed one.
      if (hasRawLayer(rd)) {
        const rawHeader = hasComputedLayer(rd)
          ? rd.unit
            ? `Raw (${rd.unit})`
            : "Raw"
          : rd.unit
            ? `${rd.name} (${rd.unit})`
            : rd.name;
        const isPickList = rd.data_type === "pick_list";
        children.push({
          headerName: rawHeader,
          headerTooltip: rd.description ?? undefined,
          colId: `${rd.id}::raw`,
          initialWidth: rd.data_type === "numeric" ? 160 : 180,
          minWidth: 130,
          wrapHeaderText: true,
          autoHeaderHeight: true,
          cellClass: rd.data_type === "numeric" ? "text-right tabular-nums" : undefined,
          headerClass: rd.data_type === "numeric" ? "ag-right-aligned-header" : undefined,
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
              const color = resolveCategoryColor(row.value_text, declared?.color);
              return (
                <Badge variant="outline" className={cn("text-xs", color.bg, color.text)}>
                  {row.value_text}
                </Badge>
              );
            }
            return (
              <>
                <span
                  className={cn(
                    row.is_outlier && "text-destructive line-through decoration-destructive/50",
                  )}
                  title={row.is_outlier ? "Flagged as outlier" : undefined}
                >
                  {formatValue(row)}
                </span>
                {/* A summary (well-less) value is a reported mean: say of how many. */}
                {params.data?.wellId === null && <ReplicateCount n={row.replicate_count ?? null} />}
              </>
            );
          },
        });
      }

      // Normalized values stay as legible as raw measurements; the group,
      // layer label and tooltip identify their derivation.
      if (hasComputedLayer(rd)) {
        children.push({
          headerName: computedLayerHeader(rd),
          headerTooltip: (() => {
            if (rd.is_calculated && rd.calculation_formula) {
              return `Calculated: ${rd.calculation_formula}`;
            }
            if (rd.melt_config) {
              const { window, low, high } = rd.melt_config;
              return `From the peak named ${window} on each position (by temperature range ${low}–${high} °C, or chosen by hand). See the Traces tab.`;
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
          initialWidth: 170,
          minWidth: 140,
          wrapHeaderText: true,
          autoHeaderHeight: true,
          cellClass: "text-right tabular-nums font-medium",
          headerClass: "ag-right-aligned-header",
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
      if (hasComputedLayer(rd)) addGroup();
      else cols.push(...children);
    }
    cols.push({
      colId: "__table_controls__",
      headerName: "",
      pinned: "right",
      lockPinned: true,
      lockPosition: "right",
      lockVisible: true,
      initialWidth: 44,
      minWidth: 44,
      maxWidth: 44,
      resizable: false,
      sortable: false,
      suppressSizeToFit: true,
      headerComponent: RunResultsMaximizeHeader,
      headerComponentParams: {
        expanded,
        onToggle: () => setExpanded((value) => !value),
        buttonRef,
      },
      cellRenderer: () => null,
    });
    return cols;
  }, [
    readoutDefs,
    showStructures,
    quickFilter,
    hiddenReadouts,
    expanded,
    setExpanded,
    buttonRef,
    plateMap?.dose_unit,
  ]);

  return (
    <section
      ref={resultsRef}
      aria-label="Run readouts"
      tabIndex={-1}
      className={cn(
        "min-w-0 space-y-2 outline-none",
        className,
        expanded &&
          "fixed inset-0 z-40 flex flex-col gap-3 space-y-0 overflow-y-auto bg-background p-4 sm:p-6",
      )}
    >
      {expanded && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-lg font-semibold">Readouts</h2>
          <span className="text-sm text-muted-foreground">{protocol?.name}</span>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2" aria-label="Readout table toolbar">
        <p className="mr-auto text-sm tabular-nums" aria-live="polite">
          <span className="font-medium">
            {quickFilter || showOutliersOnly ? `${visibleCount ?? rowData.length} of ` : ""}
            {tableRows.length} rows
          </span>
          <span className="ml-2 text-muted-foreground">· {compoundCount} compounds</span>
        </p>
        {outlierRows.length > 0 && (
          <Button
            size="sm"
            variant={outliersOnly ? "secondary" : "outline"}
            aria-pressed={outliersOnly}
            onClick={() => setOutliersOnly((value) => !value)}
          >
            Outliers ({outlierRows.length})
          </Button>
        )}
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            className="h-9 pl-8 pr-8"
            placeholder="Compound, alias, batch or well…"
            aria-label="Search readouts"
            value={quickFilter}
            onChange={(event) => setQuickFilter(event.target.value)}
          />
          {quickFilter && (
            <Button
              size="icon"
              variant="ghost"
              className="absolute right-0.5 top-0.5 size-8"
              aria-label="Clear readout search"
              onClick={() => setQuickFilter("")}
            >
              <X className="size-3.5" />
            </Button>
          )}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm">
              <SlidersHorizontal className="size-4" />
              View
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-72">
            <DropdownMenuLabel>Display</DropdownMenuLabel>
            <DropdownMenuCheckboxItem
              checked={showStructures}
              onCheckedChange={setShowStructures}
              onSelect={(event) => event.preventDefault()}
            >
              Chemical structures
            </DropdownMenuCheckboxItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Readout columns</DropdownMenuLabel>
            {readoutDefs.map((readout) => (
              <DropdownMenuCheckboxItem
                key={readout.id}
                checked={!hiddenReadouts.includes(readout.id)}
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={(checked) =>
                  setHiddenReadouts((hidden) =>
                    checked ? hidden.filter((id) => id !== readout.id) : [...hidden, readout.id],
                  )
                }
                className="items-start whitespace-normal"
              >
                <span>
                  {readout.name}
                  {readout.data_type === "dose_response" && (
                    <span className="block text-xs text-muted-foreground">
                      Fitted · repeated for each well
                    </span>
                  )}
                </span>
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        {toolbarActions}
      </div>
      <div className="run-readout-table" data-maximized={expanded}>
        <DataGrid<ReadoutTableRow>
          rowData={rowData}
          columnDefs={columnDefs}
          loading={isLoading}
          height="auto"
          domLayout="autoHeight"
          rowHeight={showStructures ? 136 : 76}
          headerHeight={44}
          groupHeaderHeight={32}
          searchPlaceholder={false}
          quickFilterText={quickFilter}
          onModelUpdated={(event) => setVisibleCount(event.api.getDisplayedRowCount())}
          suppressFilters
          getRowId={(params) => params.data.key}
          noRowsOverlayComponent={() => (
            <p className="p-6 text-sm text-muted-foreground">
              No readouts match. Try another search or clear the outlier filter.
            </p>
          )}
          emptyState={
            <p className="py-8 text-center text-sm text-muted-foreground">
              No readout data recorded for this run.
            </p>
          }
        />
      </div>
    </section>
  );
}
