"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import type { ExcelEnhancer } from "@/shared/components/data-grid/export-toolbar";
import { EmptyState } from "@/shared/components/empty-state";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { renderCurveToBase64 } from "@/shared/lib/export/curve-image";
import { fetchStructureImages } from "@/shared/lib/export/structure-image";
import type { SelectionChangedEvent } from "ag-grid-community";
import { Eye, Filter, FlaskConical, Settings2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useProtocol } from "../hooks/use-protocols";
import { worstZPrime } from "../lib/qc-metrics";
import type { DoseResponseCurve, HitCriterion, Run } from "../types";
import { ComparisonTable } from "./comparison-table";
import { CurveNavigator } from "./curve-navigator";
import { DoseResponseChart } from "./dose-response-chart";
import { HitCriteriaDialog } from "./hit-criteria-dialog";
import { COLUMN_DEFS } from "./run-dr-results-columns";
import { applyHitFilter, buildCompoundRows } from "./run-dr-results-transforms";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

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

export function RunDoseResponseResults({ run, curves, isLoading }: RunDoseResponseResultsProps) {
  const { data: protocol } = useProtocol(run.protocol_id);

  // Hit criteria state
  const savedCriteria: HitCriterion[] = protocol?.recommended_hit_criteria ?? [];
  const [activeCriteria, setActiveCriteria] = useState<HitCriterion[]>(savedCriteria);
  const isModified = JSON.stringify(activeCriteria) !== JSON.stringify(savedCriteria);

  const [criteriaDialogOpen, setCriteriaDialogOpen] = useState(false);

  // Selection state (checkbox-driven, for multi-compound comparison)
  const [selectedRows, setSelectedRows] = useState<CompoundCurveRow[]>([]);

  const handleSelectionChanged = useCallback((event: SelectionChangedEvent<CompoundCurveRow>) => {
    setSelectedRows(event.api.getSelectedRows());
  }, []);

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
    [allRows, activeCriteria],
  );

  // Curve navigation (prev/next of the currently viewed compound)
  const viewing = useMemo(
    () => filteredRows.find((r) => r.molecule_id === viewingId) ?? null,
    [filteredRows, viewingId],
  );
  const selectedIndex = viewing
    ? filteredRows.findIndex((r) => r.molecule_id === viewing.molecule_id)
    : -1;

  const navigateTo = useCallback(
    (index: number) => {
      const target = filteredRows[index];
      if (target) setViewingId(target.molecule_id);
    },
    [filteredRows],
  );

  const handlePrev = useCallback(() => {
    const newIdx = selectedIndex <= 0 ? filteredRows.length - 1 : selectedIndex - 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredRows.length, navigateTo]);

  const handleNext = useCallback(() => {
    const newIdx = selectedIndex >= filteredRows.length - 1 ? 0 : selectedIndex + 1;
    navigateTo(newIdx);
  }, [selectedIndex, filteredRows.length, navigateTo]);

  const columnDefs = COLUMN_DEFS;

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
      const allSmiles = rows.map((r) => r.smiles).filter((s): s is string => !!s);
      const structImages = await fetchStructureImages(allSmiles, 150, 100);

      // Fill existing "Structure" column with images
      const structColIdx = findCol("Structure");
      if (structColIdx >= 0) {
        worksheet.getColumn(structColIdx + 1).width = 22;
        for (let r = 0; r < rows.length; r++) {
          const smiles = rows[r].smiles;
          if (smiles && structImages[smiles]) {
            const imgId = workbook.addImage({
              base64: structImages[smiles],
              extension: "png",
            });
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
            {
              hill_slope: row.hill_slope,
              top: row.top,
              bottom: row.bottom,
              fitted_value: row.fitted_value,
            },
            row.data_points,
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
        worksheet.getRow(r + 2).getCell(synonymsCol).value = row.synonyms.join("; ");
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
            rawSheet.addRow([row.registration_number, row.smiles ?? "", pt.x, pt.y]);
          }
        }
      }
      rawSheet.getColumn(1).width = 20;
      rawSheet.getColumn(2).width = 40;
      rawSheet.getColumn(3).width = 15;
      rawSheet.getColumn(4).width = 15;
    },
    [],
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
          const cls =
            zp >= 0.5
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
                const op =
                  { gt: ">", lt: "<", gte: ">=", lte: "<=", in: "in" }[rule.operator] ??
                  rule.operator;
                const val = Array.isArray(rule.value) ? rule.value.join(", ") : rule.value;
                return (
                  // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
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
              <Badge variant="outline" className="border-yellow-500/40 text-yellow-400">
                Modified
              </Badge>
            )}
            <div className="ml-auto flex items-center gap-2">
              {activeCriteria.length > 0 ? (
                <Button variant="ghost" size="sm" onClick={() => setActiveCriteria([])}>
                  <Eye className="mr-1 h-3.5 w-3.5" />
                  Show All
                </Button>
              ) : (
                <Button variant="ghost" size="sm" onClick={() => setActiveCriteria(savedCriteria)}>
                  <Filter className="mr-1 h-3.5 w-3.5" />
                  Apply Filter
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => setCriteriaDialogOpen(true)}>
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
        onOpenChange={(open) => {
          if (!open) setViewingId(null);
        }}
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
                {viewingCurves &&
                  (() => {
                    const drDef = protocol?.readout_definitions.find(
                      (rd) => rd.dose_response_config != null,
                    );
                    const yName = drDef?.dose_response_config?.y_readout_name;
                    const yDef = yName
                      ? protocol?.readout_definitions.find((r) => r.name === yName)
                      : undefined;
                    return (
                      <DoseResponseChart
                        curves={viewingCurves}
                        isInteractive={!run.is_locked}
                        protocolConfig={drDef?.dose_response_config ?? null}
                        yReadoutNormalization={
                          drDef?.dose_response_config?.y_normalization ??
                          yDef?.normalizations?.find((n) => n !== "none") ??
                          null
                        }
                      />
                    );
                  })()}
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
