"use client";

import { CollectionPickerDialog } from "@/shared/components/collection-picker-dialog";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { TooltipProvider } from "@/shared/components/ui/tooltip";
import { CHART_AXIS, CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { groupBy } from "@/shared/lib/group-by";
import { Plot } from "@/shared/lib/plotly";
import { shortId } from "@/shared/lib/utils";
import { DoseResponseChartView } from "@structflo/components/dose-response";
import { Filter, FlaskConical, FolderPlus, Hexagon, Settings2, Star } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { activityCatalog, defaultSortColumn, visibleColumnIds } from "../../lib/activity-columns";
import { COMPACT_DR_CHART } from "../../lib/dose-response-display";
import type { CompoundActivity, CurveClass, Protocol } from "../../types";
import { ComparisonTable, buildComparisonRows } from "../comparison-table";
import { CurveClassBadge } from "../curve-class-badge";
import { CurveNavigator } from "../curve-navigator";
import { HitCriteriaDialog } from "../hit-criteria-dialog";
import { Segmented } from "../segmented";
import { ActivityColumnsMenu, useColumnChoices } from "./activity-columns-menu";
import { type Statistic, buildColumnDefs } from "./activity-tab-columns";
import { type StatusFilter, criterionLabel, useActivityTab } from "./use-activity-tab";

const STRUCTURES_KEY = "cellar.activity.structures";

/** Whether the grid draws structures (taller rows), kept per browser. */
function useStructuresChoice(): [boolean, (show: boolean) => void] {
  const [show, setShow] = useState(() => {
    try {
      return localStorage.getItem(STRUCTURES_KEY) === "1";
    } catch {
      return false;
    }
  });
  const save = useCallback((next: boolean) => {
    setShow(next);
    try {
      localStorage.setItem(STRUCTURES_KEY, next ? "1" : "0");
    } catch {
      // Storage unavailable: the choice holds for this visit only.
    }
  }, []);
  return [show, save];
}

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
    hits,
    statusCounts,
    statusFilter,
    setStatusFilter,
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

  // One column per result, grouped; what shows comes from the catalog's
  // defaults and the user's Columns-menu choices.
  const [statistic, setStatistic] = useState<Statistic>("best");
  const [showStructures, setShowStructures] = useStructuresChoice();
  const { choices, toggle: toggleColumn, reset: resetColumns } = useColumnChoices(protocolId);
  const items = activity?.items;
  const catalog = useMemo(
    () => activityCatalog(readoutDefs, items ?? [], savedCriteria),
    [readoutDefs, items, savedCriteria],
  );
  const visible = useMemo(() => visibleColumnIds(catalog, choices), [catalog, choices]);
  const sort = useMemo(
    () => defaultSortColumn(catalog, readoutDefs, savedCriteria),
    [catalog, readoutDefs, savedCriteria],
  );
  const columnDefs = useMemo(
    () =>
      buildColumnDefs({
        catalog,
        visible,
        readoutDefs,
        statistic,
        showStructures,
        hits,
        sort,
        flagsByMolecule,
        onToggleFlag: handleToggleFlag,
      }),
    [
      catalog,
      visible,
      readoutDefs,
      statistic,
      showStructures,
      hits,
      sort,
      flagsByMolecule,
      handleToggleFlag,
    ],
  );
  // The row-click detail sheet shows dose-response curves; other protocols
  // link to the compound page from the compound cell instead.
  const hasDoseResponse = readoutDefs.some((rd) => rd.data_type === "dose_response");
  const chartReadout =
    readoutDefs.find((rd) => rd.name === catalog.find((c) => c.colId === sort?.colId)?.readout) ??
    readoutDefs[0];

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
      const label = row?.registration_number ?? shortId(molId);
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
    const firstReadout = chartReadout;
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
  }, [selectedRows, chartReadout, hasDRCurves]);

  const comparisonLayout = useMemo(() => {
    const firstReadout = chartReadout;
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
  }, [chartReadout]);

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

  const hasCriteria = savedCriteria.length > 0;
  const total = activity.items.length;

  return (
    <div className="space-y-3">
      {/* The protocol's hit rule, or an invitation to set one */}
      {!hasCriteria ? (
        <Card className="border-dashed">
          <CardContent className="flex items-center justify-between gap-4 p-3">
            <p className="text-sm text-muted-foreground">
              No hit rule yet. Set one so your team knows which compounds qualify as hits.
            </p>
            <Button size="sm" onClick={() => setCriteriaDialogOpen(true)}>
              <Settings2 className="mr-1.5 h-3.5 w-3.5" /> Set hit criteria
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium">Hit rule</span>
          {savedCriteria.map((rule, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
            <Badge key={i} variant="secondary">
              {criterionLabel(rule)}
            </Badge>
          ))}
          <span className="text-xs text-muted-foreground">on each compound's best value</span>
          <Button variant="ghost" size="sm" onClick={() => setCriteriaDialogOpen(true)}>
            <Settings2 className="mr-1 h-3.5 w-3.5" /> Edit
          </Button>
        </div>
      )}

      {/* Toolbar: what to list, which statistic, how to show it */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {hits ? (
          <Segmented
            label="Hit status"
            value={statusFilter}
            options={[
              { value: "all", label: `All (${total})` },
              { value: "meets", label: `Meets criteria (${statusCounts.meets})` },
              { value: "fails", label: `Doesn't meet (${statusCounts.fails})` },
              { value: "no_data", label: `No data (${statusCounts.no_data})` },
            ]}
            onChange={(v) => setStatusFilter(v as StatusFilter)}
          />
        ) : (
          <span className="text-sm text-muted-foreground">
            {total} compound{total !== 1 ? "s" : ""}
          </span>
        )}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Summary across completed runs</span>
          <Segmented
            label="Summary"
            value={statistic}
            options={[
              { value: "best", label: "Best" },
              { value: "mean", label: "Mean" },
            ]}
            onChange={(v) => setStatistic(v as Statistic)}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {selectedRows.length > 0 && (
            <>
              <span className="text-sm text-muted-foreground">{selectedRows.length} selected</span>
              <Button variant="outline" size="sm" onClick={() => setCollectionDialogOpen(true)}>
                <FolderPlus className="mr-1.5 h-3.5 w-3.5" />
                Add to Collection
              </Button>
            </>
          )}
          <Button
            variant={showFlaggedOnly ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={showFlaggedOnly}
            onClick={() => setShowFlaggedOnly((v) => !v)}
          >
            <Star
              className={`mr-1 h-3.5 w-3.5 ${showFlaggedOnly ? "fill-yellow-400 text-yellow-400" : ""}`}
            />
            Flagged
          </Button>
          <Button
            variant={showStructures ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={showStructures}
            onClick={() => setShowStructures(!showStructures)}
          >
            <Hexagon className="mr-1 h-3.5 w-3.5" />
            Structures
          </Button>
          <ActivityColumnsMenu
            catalog={catalog}
            visible={visible}
            onToggle={toggleColumn}
            onReset={resetColumns}
          />
        </div>
      </div>

      {/* AG Grid with dynamic columns */}
      <TooltipProvider delayDuration={200}>
        <DataGrid<CompoundActivity>
          rowData={filteredItems}
          columnDefs={columnDefs}
          height="auto"
          domLayout="autoHeight"
          rowHeight={showStructures ? 115 : 44}
          suppressFilters
          onRowClick={hasDoseResponse ? (row) => setViewingId(row.molecule_id) : undefined}
          enableMultiSelect
          suppressSelectColumn
          onSelectionChanged={handleSelectionChanged}
          getRowId={(params) => params.data.molecule_id}
          emptyState={
            <EmptyState
              icon={Filter}
              title="No compounds match"
              description="Choose another hit status or turn off Flagged."
            />
          }
        />
      </TooltipProvider>

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
                    <>
                      <DoseResponseChartView curves={compoundCurves} plot={Plot} />
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
                                  {shortId(curve.run_id)}
                                </td>
                                <td className="px-3 py-2 text-xs text-muted-foreground">
                                  {curve.batch_number ?? shortId(curve.batch_id)}
                                </td>
                                <td className="px-3 py-2 font-mono">
                                  {curve.fitted_value.toPrecision(4)} {curve.fitted_unit}
                                </td>
                                <td className="px-3 py-2 font-mono">
                                  {curve.r_squared.toFixed(3)}
                                </td>
                                <td className="px-3 py-2">
                                  {curve.curve_class
                                    ? curveClassBadge(curve.curve_class as CurveClass)
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
