"use client";

import { useMemo, useState, useCallback } from "react";
import { Eye, Filter, FlaskConical, Settings2, RotateCcw } from "lucide-react";
import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { groupBy } from "@/shared/lib/group-by";
import type {
  ColDef,
  ICellRendererParams,
  SelectionChangedEvent,
} from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { EmptyState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import type { ExcelEnhancer } from "@/shared/components/data-grid/export-toolbar";
import { renderCurveToBase64 } from "@/shared/lib/export/curve-image";
import { fetchStructureImages } from "@/shared/lib/export/structure-image";
import { DoseResponseSparkline } from "./dose-response-sparkline";
import { CurveNavigator } from "./curve-navigator";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { DoseResponseChart } from "./dose-response-chart";
import { worstZPrime } from "../lib/qc-metrics";
import { HitCriteriaDialog } from "./hit-criteria-dialog";
import { ComparisonTable } from "./comparison-table";
import { useProtocol } from "../hooks/use-protocols";
import {
  CURVE_CLASS_LABELS,
  CURVE_TYPE_LABELS,
  type CurveClass,
  type CurveType,
  type DoseResponseCurve,
  type HitCriterion,
  type Run,
} from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** One row in the grid = one compound (best curve per molecule) */
interface CompoundCurveRow {
  molecule_id: string;
  molecule_name: string;
  registration_number: string;
  synonyms: string[];
  smiles: string | null;
  batch_number: string | null;
  curve_type: string;
  fitted_value: number;
  fitted_unit: string;
  hill_slope: number;
  top: number;
  bottom: number;
  r_squared: number;
  num_points: number;
  curve_class: CurveClass | null;
  data_points: Array<{ x: number; y: number }> | null;
  /** All curves for this molecule in this run (for detail panel) */
  all_curves: DoseResponseCurve[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function curveClassBadge(cc: CurveClass | null) {
  if (cc == null) {
    return (
      <Badge variant="outline" className="text-muted-foreground">
        --
      </Badge>
    );
  }
  // All classes use the same `border-x/40 bg-x/10 text-x` pattern so the
  // visual weight stays consistent. variant="outline" clears the default
  // primary fill — without it, "inactive" rendered as solid blue (no bg
  // class to override the default) with hard-to-read text.
  const styles: Record<CurveClass, string> = {
    full: "border-success/40 bg-success/10 text-success",
    partial: "border-yellow-500/40 bg-yellow-500/10 text-yellow-400",
    bell_shaped: "border-primary/40 bg-primary/10 text-primary",
    inactive:
      "border-muted-foreground/30 bg-muted/50 text-muted-foreground",
  };
  return (
    <Badge variant="outline" className={styles[cc]}>
      {CURVE_CLASS_LABELS[cc]}
    </Badge>
  );
}

/** Group curves by molecule, pick best (lowest fitted_value for IC50-type).
 *
 * The enrichment reader pre-populates `registration_number`, `synonyms`,
 * and `smiles` on each curve, so this no longer depends on a separate
 * paginated `useMolecules()` lookup (which hid structure for any compound
 * past the first page).
 */
function buildCompoundRows(curves: DoseResponseCurve[]): CompoundCurveRow[] {
  const byMolecule = groupBy(curves, (c) => c.molecule_id);

  const rows: CompoundCurveRow[] = [];
  for (const [, molCurves] of byMolecule) {
    // Best curve = lowest fitted_value (most potent), excluding inactive
    const active = molCurves.filter((c) => c.curve_class !== "inactive");
    const sorted = (active.length > 0 ? active : molCurves).sort(
      (a, b) => a.fitted_value - b.fitted_value
    );
    const best = sorted[0];

    // Condense raw_data to [{x, y}]
    let dataPoints: Array<{ x: number; y: number }> | null = null;
    if (best.raw_data && Array.isArray(best.raw_data)) {
      dataPoints = [];
      for (const pt of best.raw_data) {
        const x = (pt as Record<string, unknown>).concentration ?? (pt as Record<string, unknown>).x;
        const y = (pt as Record<string, unknown>).response ?? (pt as Record<string, unknown>).y;
        if (typeof x === "number" && typeof y === "number") {
          dataPoints.push({ x, y });
        }
      }
    }

    rows.push({
      molecule_id: best.molecule_id,
      molecule_name: best.molecule_name ?? "",
      registration_number:
        best.registration_number ?? best.molecule_id.slice(0, 8),
      synonyms: best.synonyms ?? [],
      smiles: best.smiles,
      batch_number: best.batch_number,
      curve_type: best.curve_type,
      fitted_value: best.fitted_value,
      fitted_unit: best.fitted_unit,
      hill_slope: best.hill_slope,
      top: best.top,
      bottom: best.bottom,
      r_squared: best.r_squared,
      num_points: best.num_points,
      curve_class: best.curve_class as CurveClass | null,
      data_points: dataPoints,
      all_curves: molCurves,
    });
  }
  return rows;
}

/** Apply hit criteria filter to compound rows */
function applyHitFilter(
  rows: CompoundCurveRow[],
  criteria: HitCriterion[]
): CompoundCurveRow[] {
  if (criteria.length === 0) return rows;
  return rows.filter((row) =>
    criteria.every((rule) => {
      if (rule.readout_name === "Curve Class") {
        if (rule.operator === "in" && Array.isArray(rule.value)) {
          return (
            row.curve_class != null &&
            (rule.value as string[]).includes(row.curve_class)
          );
        }
        return true;
      }
      // For IC50/EC50 rules — match against fitted_value
      const threshold = typeof rule.value === "number" ? rule.value : 0;
      switch (rule.operator) {
        case "gt":
          return row.fitted_value > threshold;
        case "lt":
          return row.fitted_value < threshold;
        case "gte":
          return row.fitted_value >= threshold;
        case "lte":
          return row.fitted_value <= threshold;
        default:
          return true;
      }
    })
  );
}

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

function buildColumnDefs(): ColDef<CompoundCurveRow>[] {
  return [
    {
      headerName: "Compound",
      field: "registration_number",
      pinned: "left",
      flex: 1,
      minWidth: 160,
      autoHeight: true,
      wrapText: true,
      cellStyle: { lineHeight: "1.3", paddingTop: 6, paddingBottom: 6 },
      // Quick-filter input spans every identifier surfaced in the cell —
      // reg id, internal name, vendor synonyms, batch number — so a search
      // for "Compound-3" or a partial vendor alias matches the row.
      getQuickFilterText: (params) => {
        if (!params.data) return "";
        const { registration_number, molecule_name, synonyms, batch_number } =
          params.data;
        return [registration_number, molecule_name, batch_number, ...(synonyms ?? [])]
          .filter((s): s is string => !!s)
          .join(" ");
      },
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        const { registration_number, molecule_name, synonyms, batch_number } =
          params.data;
        const aliases: string[] = [];
        if (molecule_name && molecule_name !== registration_number) {
          aliases.push(molecule_name);
        }
        for (const s of synonyms) {
          if (s && s !== registration_number && !aliases.includes(s)) {
            aliases.push(s);
          }
        }
        return (
          <div className="leading-tight">
            <div className="font-mono font-medium">{registration_number}</div>
            {aliases.length > 0 && (
              <div
                className="text-xs text-muted-foreground break-words whitespace-normal"
                title={aliases.join(", ")}
              >
                {aliases.join(" · ")}
              </div>
            )}
            {batch_number && (
              <div className="text-[10px] text-muted-foreground">
                Batch: {batch_number}
              </div>
            )}
          </div>
        );
      },
    },
    {
      headerName: "Structure",
      colId: "structure",
      width: 130,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data?.smiles) return <span className="text-muted-foreground">--</span>;
        return (
          <div className="flex h-full items-center justify-center py-1">
            <StructureThumbnail smiles={params.data.smiles} size={104} />
          </div>
        );
      },
    },
    {
      headerName: "Type",
      field: "curve_type",
      width: 70,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.value) return null;
        return (
          <Badge variant="outline" className="text-xs">
            {CURVE_TYPE_LABELS[params.value as CurveType] ?? params.value}
          </Badge>
        );
      },
    },
    {
      headerName: "Fitted Value",
      field: "fitted_value",
      width: 120,
      sort: "desc",
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        return (
          <span className="font-mono">
            {params.data.fitted_value.toPrecision(4)} {params.data.fitted_unit}
          </span>
        );
      },
    },
    {
      headerName: "R\u00B2",
      field: "r_squared",
      width: 80,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(3) : "--",
      cellClass: "font-mono",
    },
    {
      headerName: "Class",
      field: "curve_class",
      width: 90,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) =>
        curveClassBadge(params.value ?? null),
    },
    {
      headerName: "Hill Slope",
      field: "hill_slope",
      width: 90,
      valueFormatter: (p) =>
        p.value != null ? Number(p.value).toFixed(2) : "--",
      cellClass: "font-mono",
    },
    {
      headerName: "Curve",
      colId: "sparkline",
      width: 150,
      cellRenderer: (params: ICellRendererParams<CompoundCurveRow>) => {
        if (!params.data) return null;
        return (
          <DoseResponseSparkline
            params={{
              hill_slope: params.data.hill_slope,
              top: params.data.top,
              bottom: params.data.bottom,
              fitted_value: params.data.fitted_value,
              r_squared: params.data.r_squared,
            }}
            dataPoints={params.data.data_points}
            curveClass={params.data.curve_class}
          />
        );
      },
    },
    {
      headerName: "Points",
      field: "num_points",
      width: 70,
    },
  ];
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RunDoseResponseResultsProps {
  run: Run;
  curves: DoseResponseCurve[];
  isLoading?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function RunDoseResponseResults({
  run,
  curves,
  isLoading,
}: RunDoseResponseResultsProps) {
  const { data: protocol } = useProtocol(run.protocol_id);

  // Hit criteria state
  const savedCriteria: HitCriterion[] =
    protocol?.recommended_hit_criteria ?? [];
  const [activeCriteria, setActiveCriteria] =
    useState<HitCriterion[]>(savedCriteria);
  const isModified =
    JSON.stringify(activeCriteria) !== JSON.stringify(savedCriteria);

  const [criteriaDialogOpen, setCriteriaDialogOpen] = useState(false);

  // Selection state (checkbox-driven, for multi-compound comparison)
  const [selectedRows, setSelectedRows] = useState<CompoundCurveRow[]>([]);

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<CompoundCurveRow>) => {
      setSelectedRows(event.api.getSelectedRows());
    },
    []
  );

  // Viewing state (row-click-driven, for single-compound detail sheet)
  const [viewingId, setViewingId] = useState<string | null>(null);

  // Sync savedCriteria when protocol updates
  const prevSavedRef = JSON.stringify(protocol?.recommended_hit_criteria ?? []);
  const [lastSynced, setLastSynced] = useState(prevSavedRef);
  if (prevSavedRef !== lastSynced) {
    setActiveCriteria(protocol?.recommended_hit_criteria ?? []);
    setLastSynced(prevSavedRef);
  }

  // Build rows from curves (already enriched with reg#, smiles, synonyms)
  const allRows = useMemo(() => buildCompoundRows(curves), [curves]);
  const filteredRows = useMemo(
    () => applyHitFilter(allRows, activeCriteria),
    [allRows, activeCriteria]
  );

  // Curve navigation (prev/next of the currently viewed compound)
  const viewing = useMemo(
    () => filteredRows.find((r) => r.molecule_id === viewingId) ?? null,
    [filteredRows, viewingId]
  );
  const selectedIndex = viewing
    ? filteredRows.findIndex((r) => r.molecule_id === viewing.molecule_id)
    : -1;

  const navigateTo = useCallback((index: number) => {
    const target = filteredRows[index];
    if (target) setViewingId(target.molecule_id);
  }, [filteredRows]);

  const handlePrev = useCallback(() => {
    const newIdx = selectedIndex <= 0 ? filteredRows.length - 1 : selectedIndex - 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredRows.length, navigateTo]);

  const handleNext = useCallback(() => {
    const newIdx = selectedIndex >= filteredRows.length - 1 ? 0 : selectedIndex + 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredRows.length, navigateTo]);

  const columnDefs = useMemo(() => buildColumnDefs(), []);

  // Excel enhancer — fill image columns + add SMILES/Synonyms + raw data sheet
  const excelEnhancer: ExcelEnhancer = useCallback(
    async (workbook, worksheet, rows: CompoundCurveRow[]) => {
      // Helper: find column index (0-based) by header text
      const findCol = (name: string) => {
        const row1 = worksheet.getRow(1);
        for (let c = 1; c <= worksheet.columnCount; c++) {
          if (row1.getCell(c).value === name) return c - 1;
        }
        return -1;
      };

      // Batch-fetch structure images from backend
      const allSmiles = rows
        .map((r) => r.smiles)
        .filter((s): s is string => !!s);
      const structImages = await fetchStructureImages(allSmiles, 150, 100);

      // Fill existing "Structure" column with images
      const structColIdx = findCol("Structure");
      if (structColIdx >= 0) {
        worksheet.getColumn(structColIdx + 1).width = 22;
        for (let r = 0; r < rows.length; r++) {
          const smiles = rows[r].smiles;
          if (smiles && structImages[smiles]) {
            const imgId = workbook.addImage({ base64: structImages[smiles], extension: "png" });
            worksheet.addImage(imgId, {
              tl: { col: structColIdx, row: r + 1 },
              ext: { width: 150, height: 80 },
            });
          }
        }
      }

      // Fill existing "Curve" column with sparkline images
      const curveColIdx = findCol("Curve");
      if (curveColIdx >= 0) {
        worksheet.getColumn(curveColIdx + 1).width = 30;
        for (let r = 0; r < rows.length; r++) {
          const row = rows[r];
          const base64 = renderCurveToBase64(
            { hill_slope: row.hill_slope, top: row.top, bottom: row.bottom, fitted_value: row.fitted_value },
            row.data_points
          );
          if (!base64) continue;
          const imageId = workbook.addImage({ base64, extension: "png" });
          worksheet.addImage(imageId, {
            tl: { col: curveColIdx, row: r + 1 },
            ext: { width: 200, height: 60 },
          });
        }
      }

      // Consistent row heights
      for (let r = 2; r <= rows.length + 1; r++) {
        worksheet.getRow(r).height = 65;
      }

      // Append SMILES and Synonyms as new text columns
      const lastCol = worksheet.columnCount;
      const smilesCol = lastCol + 1;
      const synonymsCol = lastCol + 2;
      worksheet.getRow(1).getCell(smilesCol).value = "SMILES";
      worksheet.getRow(1).getCell(synonymsCol).value = "Synonyms";
      for (let r = 0; r < rows.length; r++) {
        const row = rows[r];
        worksheet.getRow(r + 2).getCell(smilesCol).value = row.smiles ?? "";
        worksheet.getRow(r + 2).getCell(synonymsCol).value =
          row.synonyms.join("; ");
      }
      worksheet.getColumn(smilesCol).width = 40;
      worksheet.getColumn(synonymsCol).width = 30;

      // Raw data points sheet — exports use the canonical reg id as the
      // compound label for analyst consistency.
      const rawSheet = workbook.addWorksheet("Raw Data Points");
      rawSheet.addRow(["Compound", "SMILES", "Concentration", "Response"]);
      for (const row of rows) {
        if (row.data_points) {
          for (const pt of row.data_points) {
            rawSheet.addRow([
              row.registration_number,
              row.smiles ?? "",
              pt.x,
              pt.y,
            ]);
          }
        }
      }
      rawSheet.getColumn(1).width = 20;
      rawSheet.getColumn(2).width = 40;
      rawSheet.getColumn(3).width = 15;
      rawSheet.getColumn(4).width = 15;
    },
    []
  );

  // Detail panel: curves for the viewed compound
  const viewingCurves = viewing?.all_curves ?? null;

  // Loading
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (curves.length === 0) {
    return (
      <EmptyState
        icon={FlaskConical}
        title="No dose-response curves"
        description="Fit curves from readout data or add curves manually to see results here."
      />
    );
  }

  const hasCriteria = savedCriteria.length > 0 || activeCriteria.length > 0;

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center gap-4 text-sm">
        <Badge variant="secondary">
          {allRows.length} compound{allRows.length !== 1 ? "s" : ""}
        </Badge>
        {hasCriteria && (
          <Badge variant="outline" className="border-success/40 text-success">
            {filteredRows.length} hit{filteredRows.length !== 1 ? "s" : ""}
          </Badge>
        )}
        {(() => {
          const zp = worstZPrime(run.qc_metrics);
          if (zp === null) return null;
          const label = zp >= 0.5 ? "Excellent" : zp >= 0 ? "Marginal" : "Poor";
          const cls = zp >= 0.5
            ? "border-success/40 text-success"
            : zp >= 0
            ? "border-yellow-500/40 text-yellow-400"
            : "border-destructive/40 text-destructive";
          return (
            <Badge variant="outline" className={cls}>
              Worst Z&prime; = {zp.toFixed(2)} &mdash; {label}
            </Badge>
          );
        })()}
      </div>

      {/* Hit Criteria Filter Bar */}
      {!hasCriteria ? (
        <Card className="border-2 border-dashed">
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="font-medium">No hit criteria defined</p>
              <p className="text-sm text-muted-foreground">
                Define criteria on the protocol to filter hits in this run.
              </p>
            </div>
            <Button onClick={() => setCriteriaDialogOpen(true)}>
              <Settings2 className="mr-2 h-4 w-4" /> Set Hit Criteria
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2 p-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Hit Criteria Filter</span>
            <span className="text-muted-foreground">|</span>

            {activeCriteria.length > 0 ? (
              activeCriteria.map((rule, i) => {
                const op = { gt: ">", lt: "<", gte: ">=", lte: "<=", in: "in" }[
                  rule.operator
                ] ?? rule.operator;
                const val = Array.isArray(rule.value)
                  ? rule.value.join(", ")
                  : rule.value;
                return (
                  <Badge key={i} variant="secondary">
                    {rule.readout_name} {op} {val}
                  </Badge>
                );
              })
            ) : (
              <span className="text-sm text-muted-foreground italic">
                Disabled — showing all compounds
              </span>
            )}

            {isModified && activeCriteria.length > 0 && (
              <Badge
                variant="outline"
                className="border-yellow-500/40 text-yellow-400"
              >
                Modified
              </Badge>
            )}
            <div className="ml-auto flex items-center gap-2">
              {activeCriteria.length > 0 ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveCriteria([])}
                >
                  <Eye className="mr-1 h-3.5 w-3.5" />
                  Show All
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveCriteria(savedCriteria)}
                >
                  <Filter className="mr-1 h-3.5 w-3.5" />
                  Apply Filter
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCriteriaDialogOpen(true)}
              >
                <Settings2 className="mr-1 h-3.5 w-3.5" /> Edit Criteria
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AG Grid */}
      <DataGrid<CompoundCurveRow>
        rowData={filteredRows}
        columnDefs={columnDefs}
        height="auto"
        domLayout="autoHeight"
        rowHeight={115}
        onRowClick={(row) => setViewingId(row.molecule_id)}
        enableMultiSelect
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.molecule_id}
        exportFilename={`run-${run.id.slice(0, 8)}-dose-response`}
        excelEnhancer={excelEnhancer}
        emptyState={
          <EmptyState
            icon={Filter}
            title="No compounds match criteria"
            description="Adjust or remove hit criteria to see more compounds."
          />
        }
      />

      {/* Detail sheet — driven by row click, independent from selection */}
      <Sheet
        open={!!viewing}
        onOpenChange={(open) => { if (!open) setViewingId(null); }}
      >
        <SheetContent side="right" className="w-[55vw] sm:max-w-[55vw] p-0 flex flex-col">
          {viewing && (
            <>
              <SheetHeader className="px-4 pt-4 pb-2 pr-12 shrink-0 flex flex-row items-center justify-between">
                <div>
                  <SheetTitle>{viewing.registration_number}</SheetTitle>
                  {viewing.molecule_name && (
                    <p className="text-sm text-muted-foreground">{viewing.molecule_name}</p>
                  )}
                  {viewing.batch_number && (
                    <p className="text-xs text-muted-foreground">Batch: {viewing.batch_number}</p>
                  )}
                </div>
                <CurveNavigator
                  currentIndex={selectedIndex}
                  total={filteredRows.length}
                  onPrev={handlePrev}
                  onNext={handleNext}
                />
              </SheetHeader>
              <ScrollArea className="flex-1 min-h-0 px-4 pb-6">
                {viewingCurves && (
                  <DoseResponseChart
                    curves={viewingCurves}
                    isInteractive={!run.is_locked}
                  />
                )}
              </ScrollArea>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Multi-select comparison — 2-5 compounds */}
      {selectedRows.length >= 2 && selectedRows.length <= 5 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Comparison ({selectedRows.length} compounds)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ComparisonTable
              rows={selectedRows.map((row, i) => ({
                label: row.registration_number,
                batch: row.batch_number,
                color: GROUP_PALETTE[i % GROUP_PALETTE.length],
                curve_type: row.curve_type,
                fitted_value: row.fitted_value,
                fitted_unit: row.fitted_unit,
                hill_slope: row.hill_slope,
                r_squared: row.r_squared,
                curve_class: row.curve_class,
                top: row.top,
                bottom: row.bottom,
              }))}
            />
          </CardContent>
        </Card>
      )}

      {/* Hit criteria dialog */}
      {protocol && (
        <HitCriteriaDialog
          protocolId={protocol.id}
          readoutDefinitions={protocol.readout_definitions}
          currentCriteria={protocol.recommended_hit_criteria}
          open={criteriaDialogOpen}
          onOpenChange={setCriteriaDialogOpen}
        />
      )}
    </div>
  );
}
