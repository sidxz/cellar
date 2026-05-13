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
import { CHART_AXIS, CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { renderCurveToBase64 } from "@/shared/lib/export/curve-image";
import { fetchStructureImages } from "@/shared/lib/export/structure-image";
import { groupBy } from "@/shared/lib/group-by";
import { Plot } from "@/shared/lib/plotly";
import type { ColDef } from "ag-grid-community";
import { Eye, Filter, FlaskConical, FolderPlus, Settings2, Star } from "lucide-react";
import { useCallback, useMemo } from "react";
import { COMPACT_DR_CHART } from "../../lib/dose-response-display";
import type { CompoundActivity, CurveClass, Protocol } from "../../types";
import { CollectionPickerDialog } from "@/shared/components/collection-picker-dialog";
import { ComparisonTable, buildComparisonRows } from "../comparison-table";
import { CurveClassBadge } from "../curve-class-badge";
import { CurveNavigator } from "../curve-navigator";
import { DoseResponseChart } from "../dose-response-chart";
import { HitCriteriaDialog } from "../hit-criteria-dialog";
import { buildColumnDefs } from "./activity-tab-columns";
import { criterionLabel, useActivityTab } from "./use-activity-tab";

// ---------------------------------------------------------------------------
// Curve class badge
// ---------------------------------------------------------------------------

function curveClassBadge(cc: CurveClass | null) {
  return <CurveClassBadge curveClass={cc} />;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ActivityTabProps {
  protocol: Protocol;
  protocolId: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ActivityTab({ protocol, protocolId }: ActivityTabProps) {
  const {
    activity,
    isLoading,
    readoutDefs,
    filteredItems,
    flagsByMolecule,
    showFlaggedOnly,
    setShowFlaggedOnly,
    handleToggleFlag,
    savedCriteria,
    activeCriteria,
    setActiveCriteria,
    isModified,
    criteriaDialogOpen,
    setCriteriaDialogOpen,
    collectionDialogOpen,
    setCollectionDialogOpen,
    selectedRows,
    handleSelectionChanged,
    setViewingId,
    viewing,
    selectedIndex,
    handlePrev,
    handleNext,
    compoundCurves,
    curvesLoading,
    multiCurves,
    multiCurvesLoading,
    hasDRCurves,
  } = useActivityTab(protocol, protocolId);

  // AG Grid columns (dynamic from readout definitions).
  const columnDefs = useMemo<ColDef<CompoundActivity>[]>(
    () => buildColumnDefs(readoutDefs, flagsByMolecule, handleToggleFlag),
    [readoutDefs, flagsByMolecule, handleToggleFlag],
  );

  // ---------------------------------------------------------------------------
  // Build Plotly curve overlay traces
  // ---------------------------------------------------------------------------
  const overlayTraces = useMemo(() => {
    if (!multiCurves || multiCurves.length === 0) return null;
    const TRACE_COLORS = GROUP_PALETTE.slice(0, 5);
    // biome-ignore lint/suspicious/noExplicitAny: Plotly trace objects are dynamically constructed
    const traces: any[] = [];

    const byMolecule = groupBy(multiCurves, (curve) => curve.molecule_id);

    let colorIdx = 0;
    for (const [molId, curves] of byMolecule) {
      const color = TRACE_COLORS[colorIdx % TRACE_COLORS.length];
      const row = selectedRows.find((r) => r.molecule_id === molId);
      const label = row?.registration_number ?? molId.slice(0, 8);
      const bestCurve = curves[0];

      const allX = curves.flatMap((c) =>
        (c.raw_data ?? [])
          .map((pt: Record<string, unknown>) => (pt.concentration ?? pt.x) as number)
          .filter((v): v is number => typeof v === "number"),
      );
      const xMin = Math.max(Math.min(...allX, bestCurve.fitted_value) * 0.1, 1e-12);
      const xMax = Math.max(...allX, bestCurve.fitted_value) * 10;

      // Data points scatter
      const rawPts = bestCurve.raw_data ?? [];
      const ptX = rawPts
        .map((p: Record<string, unknown>) => (p.concentration ?? p.x) as number)
        .filter((v): v is number => typeof v === "number");
      const ptY = rawPts
        .map((p: Record<string, unknown>) => (p.response ?? p.y) as number)
        .filter((v): v is number => typeof v === "number");

      if (ptX.length > 0) {
        traces.push({
          type: "scatter",
          mode: "markers",
          name: label,
          legendgroup: label,
          x: ptX,
          y: ptY,
          marker: { color, size: 6 },
          showlegend: true,
          hovertemplate: `${label}<br>x: %{x:.4g}<br>y: %{y:.4g}<extra></extra>`,
        });
      }

      // Fitted sigmoid
      const logMin = Math.log10(xMin);
      const logMax = Math.log10(xMax);
      const lineX: number[] = [];
      const lineY: number[] = [];
      for (let i = 0; i <= COMPACT_DR_CHART.POINTS; i++) {
        const logX = logMin + (logMax - logMin) * (i / COMPACT_DR_CHART.POINTS);
        const x = 10 ** logX;
        const y =
          bestCurve.bottom +
          (bestCurve.top - bestCurve.bottom) /
            (1 + (x / bestCurve.fitted_value) ** bestCurve.hill_slope);
        lineX.push(x);
        lineY.push(y);
      }
      traces.push({
        type: "scatter",
        mode: "lines",
        name: `${label} fit`,
        legendgroup: label,
        x: lineX,
        y: lineY,
        line: { color, width: 2 },
        showlegend: false,
        hoverinfo: "skip",
      });

      colorIdx++;
    }
    return traces;
  }, [multiCurves, selectedRows]);

  // Fallback bar chart for single-point-only selection
  const barChartData = useMemo(() => {
    if (hasDRCurves || selectedRows.length < 2 || selectedRows.length > 5) return null;
    const firstReadout = readoutDefs[0];
    if (!firstReadout) return null;
    return [
      {
        type: "bar" as const,
        x: selectedRows.map((r) => r.registration_number),
        y: selectedRows.map((r) => r.readouts?.[firstReadout.name]?.best ?? 0),
        marker: { color: CHART_COLORS.primary },
        hoverinfo: "x+y",
      },
    ];
  }, [selectedRows, readoutDefs, hasDRCurves]);

  const comparisonLayout = useMemo(() => {
    const firstReadout = readoutDefs[0];
    const unitSuffix = firstReadout?.unit ? ` (${firstReadout.unit})` : "";
    const isDR = firstReadout?.data_type === "dose_response";
    return {
      height: 350,
      autosize: true,
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: CHART_AXIS.label },
      xaxis: {
        title: { text: isDR ? "Concentration" : "Compound" },
        type: isDR ? ("log" as const) : undefined,
        gridcolor: CHART_AXIS.grid,
        ...(isDR ? {} : { tickangle: -45 }),
      },
      yaxis: {
        title: {
          text: isDR ? "Response (%)" : `Best ${firstReadout?.name ?? "Value"}${unitSuffix}`,
        },
        gridcolor: CHART_AXIS.grid,
      },
      legend: {
        orientation: "h" as const,
        y: -0.25,
        font: { color: CHART_AXIS.label },
      },
      margin: { l: 60, r: 20, t: 20, b: 80 },
      bargap: 0.3,
    };
  }, [readoutDefs]);

  // ---------------------------------------------------------------------------
  // Excel enhancer — sparkline images + raw data sheet
  // ---------------------------------------------------------------------------
  const excelEnhancer: ExcelEnhancer = useCallback(
    async (workbook, worksheet, rows: CompoundActivity[]) => {
      // Helper: find column index (0-based) by header text
      const findCol = (name: string) => {
        const row1 = worksheet.getRow(1);
        for (let c = 1; c <= worksheet.columnCount; c++) {
          if (row1.getCell(c).value === name) return c - 1;
        }
        return -1;
      };

      // Batch-fetch structure images from backend
      const allSmiles = rows.map((r) => r.smiles).filter(Boolean) as string[];
      const structImages = await fetchStructureImages(allSmiles, 150, 100);

      // Fill existing "Structure" column with images (grid exported it empty)
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
          const drReadout = Object.values(rows[r].readouts).find((rv) => rv.curve_params);
          if (!drReadout?.curve_params) continue;
          const base64 = renderCurveToBase64(drReadout.curve_params, drReadout.data_points);
          if (!base64) continue;
          const imageId = workbook.addImage({ base64, extension: "png" });
          worksheet.addImage(imageId, {
            tl: { col: curveColIdx, row: r + 1 },
            ext: { width: 200, height: 60 },
          });
        }
      }

      // Set consistent row heights for images
      for (let r = 2; r <= rows.length + 1; r++) {
        worksheet.getRow(r).height = 65;
      }

      // Append SMILES and Synonyms as new columns at the end
      const lastCol = worksheet.columnCount;
      const smilesCol = lastCol + 1;
      const synonymsCol = lastCol + 2;
      worksheet.getRow(1).getCell(smilesCol).value = "SMILES";
      worksheet.getRow(1).getCell(synonymsCol).value = "Synonyms";
      for (let r = 0; r < rows.length; r++) {
        worksheet.getRow(r + 2).getCell(smilesCol).value = rows[r].smiles ?? "";
        worksheet.getRow(r + 2).getCell(synonymsCol).value = (rows[r].synonyms ?? []).join("; ");
      }
      worksheet.getColumn(smilesCol).width = 40;
      worksheet.getColumn(synonymsCol).width = 30;

      // Add raw data points sheet
      const rawSheet = workbook.addWorksheet("Raw Data Points");
      rawSheet.addRow(["Compound", "SMILES", "Concentration", "Response"]);

      for (const row of rows) {
        const name = row.registration_number || row.molecule_name || row.molecule_id;
        for (const rv of Object.values(row.readouts)) {
          if (rv.data_points) {
            for (const pt of rv.data_points) {
              rawSheet.addRow([name, row.smiles ?? "", pt.x, pt.y]);
            }
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

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (!activity || activity.items.length === 0) {
    return (
      <EmptyState
        icon={FlaskConical}
        title="No activity data"
        description="Complete some runs with readout data to see compound activity here."
      />
    );
  }

  const hasCriteria = savedCriteria.length > 0 || activeCriteria.length > 0;

  return (
    <div className="space-y-4">
      {/* Hit Criteria CTA or Filter Bar */}
      {!hasCriteria ? (
        <Card className="border-2 border-dashed">
          <CardContent className="flex items-center justify-between p-4">
            <div>
              <p className="font-medium">No hit criteria defined</p>
              <p className="text-sm text-muted-foreground">
                Define recommended criteria so your team knows which compounds qualify as hits.
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
              activeCriteria.map((rule, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
                <Badge key={i} variant="secondary">
                  {criterionLabel(rule)}
                </Badge>
              ))
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
              <Button
                variant={showFlaggedOnly ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setShowFlaggedOnly((v) => !v)}
              >
                <Star
                  className={`mr-1 h-3.5 w-3.5 ${
                    showFlaggedOnly ? "fill-yellow-400 text-yellow-400" : ""
                  }`}
                />
                Flagged
              </Button>
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
                <Settings2 className="mr-1 h-3.5 w-3.5" />
                Edit Criteria
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filtered count indicator */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {filteredItems.length} of {activity.items.length} compound
          {activity.items.length !== 1 ? "s" : ""}
          {activeCriteria.length > 0 ? " match criteria" : ""}
        </span>
        <div className="flex items-center gap-2">
          {selectedRows.length > 0 && (
            <>
              <Button variant="outline" size="sm" onClick={() => setCollectionDialogOpen(true)}>
                <FolderPlus className="mr-1.5 h-3.5 w-3.5" />
                Add to Collection
              </Button>
              <span>{selectedRows.length} selected</span>
            </>
          )}
        </div>
      </div>

      {/* AG Grid with dynamic columns */}
      <DataGrid<CompoundActivity>
        rowData={filteredItems}
        columnDefs={columnDefs}
        height="auto"
        domLayout="autoHeight"
        rowHeight={115}
        onRowClick={(row) => setViewingId(row.molecule_id)}
        enableMultiSelect
        suppressSelectColumn
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.molecule_id}
        exportFilename={`${protocol.name}-activity`}
        excelEnhancer={excelEnhancer}
        emptyState={
          <EmptyState
            icon={Filter}
            title="No compounds match"
            description="Adjust or remove hit criteria to see more compounds."
          />
        }
      />

      {/* Compound detail sheet — driven by row click, independent from selection */}
      <Sheet
        open={!!viewing}
        onOpenChange={(open) => {
          if (!open) setViewingId(null);
        }}
      >
        <SheetContent
          side="right"
          className="w-[55vw] sm:max-w-[55vw] p-0 flex flex-col"
          showCloseButton
        >
          {viewing && (
            <>
              <SheetHeader className="px-4 pt-4 pb-2 pr-12 shrink-0 flex flex-row items-center justify-between">
                <div>
                  <SheetTitle>{viewing.registration_number}</SheetTitle>
                  {viewing.molecule_name && (
                    <p className="text-sm text-muted-foreground">{viewing.molecule_name}</p>
                  )}
                </div>
                <CurveNavigator
                  currentIndex={selectedIndex}
                  total={filteredItems.length}
                  onPrev={handlePrev}
                  onNext={handleNext}
                />
              </SheetHeader>
              <ScrollArea className="flex-1 min-h-0 px-4 pb-6">
                <div className="space-y-4">
                  {curvesLoading ? (
                    <Skeleton className="h-[300px] w-full" />
                  ) : compoundCurves && compoundCurves.length > 0 ? (
                    (() => {
                      const drDef = protocol.readout_definitions.find(
                        (rd) => rd.dose_response_config != null,
                      );
                      const yName = drDef?.dose_response_config?.y_readout_name;
                      const yDef = yName
                        ? protocol.readout_definitions.find((r) => r.name === yName)
                        : undefined;
                      return (
                        <>
                          <DoseResponseChart
                            curves={compoundCurves}
                            isInteractive={false}
                            protocolConfig={drDef?.dose_response_config ?? null}
                            yReadoutNormalization={
                              drDef?.dose_response_config?.y_normalization ??
                              yDef?.normalizations?.find((n) => n !== "none") ??
                              null
                            }
                          />
                          <div className="rounded-lg border">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b bg-muted/50">
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                                    Run
                                  </th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                                    Batch
                                  </th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                                    Fitted Value
                                  </th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                                    R²
                                  </th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                                    Class
                                  </th>
                                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">
                                    Hill Slope
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {compoundCurves.map((curve) => (
                                  <tr key={curve.id} className="border-b last:border-0">
                                    <td className="px-3 py-2 font-mono text-xs">
                                      {curve.run_id.slice(0, 8)}
                                    </td>
                                    <td className="px-3 py-2 text-xs text-muted-foreground">
                                      {curve.batch_number ?? curve.batch_id.slice(0, 8)}
                                    </td>
                                    <td className="px-3 py-2 font-mono">
                                      {curve.fitted_value.toPrecision(4)} {curve.fitted_unit}
                                    </td>
                                    <td className="px-3 py-2 font-mono">
                                      {curve.r_squared.toFixed(3)}
                                    </td>
                                    <td className="px-3 py-2">
                                      {curve.curve_class
                                        ? curveClassBadge(curve.curve_class)
                                        : "--"}
                                    </td>
                                    <td className="px-3 py-2 font-mono">
                                      {curve.hill_slope.toFixed(2)}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      );
                    })()
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No dose-response curves available for this compound.
                    </p>
                  )}
                </div>
              </ScrollArea>
            </>
          )}
        </SheetContent>
      </Sheet>

      {/* Curve overlay — 2-5 selected with DR data */}
      {overlayTraces && selectedRows.length >= 2 && selectedRows.length <= 5 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Dose-Response Comparison ({selectedRows.length} compounds)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {multiCurvesLoading ? (
              <Skeleton className="h-[350px] w-full" />
            ) : (
              <Plot
                data={overlayTraces}
                layout={comparisonLayout}
                config={{ displayModeBar: false, responsive: true }}
                useResizeHandler
                style={{ width: "100%", height: "350px" }}
              />
            )}
            {multiCurves && multiCurves.length > 0 && (
              <div className="mt-4">
                <ComparisonTable
                  rows={buildComparisonRows(
                    multiCurves,
                    new Map(
                      selectedRows.map((r) => [
                        r.molecule_id,
                        { label: r.registration_number, batch: r.batch_number },
                      ]),
                    ),
                  )}
                />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Fallback bar chart — 2-5 selected, no DR data */}
      {barChartData && !hasDRCurves && selectedRows.length >= 2 && selectedRows.length <= 5 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Comparison ({selectedRows.length} compounds)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Plot
              data={barChartData}
              layout={comparisonLayout}
              config={{ displayModeBar: false, responsive: true }}
              useResizeHandler
              style={{ width: "100%", height: "350px" }}
            />
          </CardContent>
        </Card>
      )}

      {/* >5 selected — count text */}
      {selectedRows.length > 5 && (
        <p className="text-sm text-muted-foreground">
          {selectedRows.length} compounds selected. Select 5 or fewer to see a comparison chart, or
          1 to see dose-response curves.
        </p>
      )}

      {/* Hit criteria dialog */}
      <HitCriteriaDialog
        protocolId={protocolId}
        readoutDefinitions={protocol.readout_definitions}
        currentCriteria={protocol.recommended_hit_criteria}
        open={criteriaDialogOpen}
        onOpenChange={setCriteriaDialogOpen}
      />

      {/* Collection picker dialog */}
      <CollectionPickerDialog
        open={collectionDialogOpen}
        onOpenChange={setCollectionDialogOpen}
        moleculeIds={selectedRows.map((r) => r.molecule_id)}
        simple
      />
    </div>
  );
}
