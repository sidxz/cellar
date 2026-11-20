"use client";

import { CollectionPickerDialog } from "@/shared/components/collection-picker-dialog";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { MemberName } from "@/shared/components/entity-name";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Input } from "@/shared/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { formatDate } from "@/shared/lib/format-date";
import { cn } from "@/shared/lib/utils";

import type { GridApi, IRowNode, SelectionChangedEvent } from "ag-grid-community";
import {
  ChartNoAxesCombined,
  Check,
  Eye,
  EyeOff,
  Filter,
  FlaskConical,
  FolderPlus,
  Info,
  Pencil,
  Search,
  Settings2,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useProtocol } from "../hooks/use-protocols";
import { useSetRunHitCriteria } from "../hooks/use-runs";
import { curveFrame, curveLayer } from "../lib/curve-frame";
import { isPercentNormalization } from "../lib/dose-response-math";
import { runRulesOf } from "../lib/melt-hits";
import type { DoseResponseCurve, HitCriterion, Run } from "../types";
import { ComparisonTable } from "./comparison-table";
import { CurveNavigator } from "./curve-navigator";
import { criterionLabel } from "./detail-tabs/use-activity-tab";
import { DoseResponseChart } from "./dose-response-chart";
import { RunHitCriteriaDialog } from "./hit-criteria-dialog";
import { RUN_DIAGNOSTIC_COLUMNS, buildColumnDefs } from "./run-dr-results-columns";
import {
  type RunCurveClassFilter,
  type RunPotencyFilter,
  matchesRunViewFilters,
} from "./run-dr-results-filtering";
import { RunCurveClassFilterMenu, RunPotencyFilterControl } from "./run-dr-results-filters";
import { applyHitFilter, buildCompoundRows } from "./run-dr-results-transforms";
import type { CompoundCurveRow } from "./run-dr-results-transforms";
import {
  displayDoseUnit,
  isConvertibleDoseUnit,
  normalizeDoseUnit,
  useRunResultsView,
} from "./run-dr-results-view";
import { useRunResultsFocus } from "./use-run-results-focus";
import "./run-dr-results.css";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

  // Per-run hit criteria — the run's persisted decision is the source of truth.
  // The protocol's recommended_hit_criteria is only a *suggestion*, surfaced
  // when the run is unset; it is never applied to the run automatically.
  const recommendation: HitCriterion[] = protocol?.recommended_hit_criteria ?? [];
  // null = unset (show recommendation, no hit count); [] = recorded "show all";
  // [rules] = recorded threshold. (`?? null` leaves [] intact since it's not nullish.)
  const runCriteria: HitCriterion[] | null = run.hit_criteria ?? null;
  const isSet = runCriteria !== null;
  const hasThreshold = runCriteria !== null && runCriteria.length > 0;

  const setHitCriteria = useSetRunHitCriteria();
  const [criteriaDialogOpen, setCriteriaDialogOpen] = useState(false);
  // Non-destructive, view-only bypass of the run's filter — lets a screener peek
  // at every compound without altering the recorded decision or its provenance.
  const [showAll, setShowAll] = useState(false);
  const [quickFilter, setQuickFilter] = useState("");
  const [classFilter, setClassFilter] = useState<RunCurveClassFilter[]>([]);
  const [potencyFilter, setPotencyFilter] = useState<RunPotencyFilter | null>(null);
  const hasViewFilters = classFilter.length > 0 || potencyFilter !== null;
  const [view, setView] = useRunResultsView(run.protocol_id);
  const gridApi = useRef<GridApi<CompoundCurveRow> | null>(null);
  const [filteredCount, setFilteredCount] = useState<number | null>(null);
  const [navigationRows, setNavigationRows] = useState<CompoundCurveRow[] | null>(null);
  // Keep the grid mounted so focus mode retains its sort, filters, selection and scroll.
  const {
    expanded: focusResults,
    setExpanded: setFocusResults,
    resultsRef,
    buttonRef: focusButtonRef,
  } = useRunResultsFocus();
  const comparisonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (gridApi.current && !gridApi.current.isDestroyed()) {
      gridApi.current.setColumnsVisible(RUN_DIAGNOSTIC_COLUMNS, view.diagnostics);
    }
  }, [view.diagnostics]);

  // Collection picker (bulk action on the checkbox selection)
  const [collectionDialogOpen, setCollectionDialogOpen] = useState(false);

  // Selection state (checkbox-driven, for multi-compound comparison)
  const [selectedRows, setSelectedRows] = useState<CompoundCurveRow[]>([]);

  const handleSelectionChanged = useCallback((event: SelectionChangedEvent<CompoundCurveRow>) => {
    setSelectedRows(event.api.getSelectedRows());
  }, []);

  // Viewing state (row-click-driven, for single-compound detail sheet)
  const [viewingId, setViewingId] = useState<string | null>(null);

  // Build rows from curves (already enriched with reg#, smiles, synonyms).
  const allRows = useMemo(() => buildCompoundRows(curves), [curves]);
  const commonUnit = useMemo(() => {
    const units = new Set(allRows.map((row) => normalizeDoseUnit(row.fitted_unit)));
    const unit = [...units][0];
    return units.size === 1 && unit ? unit : null;
  }, [allRows]);
  const canConvertUnits = commonUnit != null && isConvertibleDoseUnit(commonUnit);
  const displayUnit = canConvertUnits && view.unit !== "native" ? view.unit : commonUnit;
  const matchesViewFilter = useCallback(
    (node: IRowNode<CompoundCurveRow>) =>
      !!node.data && matchesRunViewFilters(node.data, classFilter, potencyFilter),
    [classFilter, potencyFilter],
  );
  useEffect(() => {
    const api = gridApi.current;
    if (api && !api.isDestroyed()) {
      api.setGridOption("isExternalFilterPresent", () => hasViewFilters);
      api.setGridOption("doesExternalFilterPass", matchesViewFilter);
      api.onFilterChanged();
    }
  }, [hasViewFilters, matchesViewFilter]);
  // The true hit set (threshold applied) — drives the "N hits" count regardless
  // of the view-only bypass below.
  // This tab evaluates rules on dose-response readouts (and Curve Class); a
  // run's rule on another readout (a thermal shift ΔTm) is listed, not applied.
  const drReadoutNames = useMemo(
    () =>
      new Set(
        (protocol?.readout_definitions ?? [])
          .filter((rd) => rd.dose_response_config)
          .map((rd) => rd.name),
      ),
    [protocol],
  );
  const isOtherTabRule = (rule: HitCriterion) =>
    rule.readout_name !== "Curve Class" && !drReadoutNames.has(rule.readout_name);
  const hitRows = useMemo(
    () =>
      runCriteria && runCriteria.length > 0
        ? applyHitFilter(allRows, runCriteria, drReadoutNames)
        : allRows,
    [allRows, runCriteria, drReadoutNames],
  );
  // Rows the grid actually shows: the hit set when a threshold is active, unless
  // the screener has toggled the non-destructive "Show all" bypass.
  const displayedRows = hasThreshold && !showAll ? hitRows : allRows;
  const navigableRows = navigationRows ?? displayedRows;
  const updateGridView = useCallback((api: GridApi<CompoundCurveRow>) => {
    gridApi.current = api;
    const rows: CompoundCurveRow[] = [];
    api.forEachNodeAfterFilterAndSort((node) => {
      if (node.data) rows.push(node.data);
    });
    setFilteredCount(rows.length);
    setNavigationRows((previous) =>
      previous?.length === rows.length && previous.every((row, index) => row === rows[index])
        ? previous
        : rows,
    );
  }, []);

  // Curve navigation (prev/next of the currently viewed compound)
  const viewing = useMemo(
    () => navigableRows.find((r) => r.molecule_id === viewingId) ?? null,
    [navigableRows, viewingId],
  );
  const selectedIndex = viewing
    ? navigableRows.findIndex((r) => r.molecule_id === viewing.molecule_id)
    : -1;

  const navigateTo = useCallback(
    (index: number) => {
      const target = navigableRows[index];
      if (target) setViewingId(target.molecule_id);
    },
    [navigableRows],
  );

  const handlePrev = useCallback(() => {
    const newIdx = selectedIndex <= 0 ? navigableRows.length - 1 : selectedIndex - 1;
    navigateTo(newIdx);
  }, [selectedIndex, navigableRows.length, navigateTo]);

  const handleNext = useCallback(() => {
    const newIdx = selectedIndex >= navigableRows.length - 1 ? 0 : selectedIndex + 1;
    navigateTo(newIdx);
  }, [selectedIndex, navigableRows.length, navigateTo]);

  // Column set is driven by the protocol's intercept specs — one column
  // per declared intercept (EC50, EC90, IC10, ...). When the protocol
  // declares multiple DOSE_RESPONSE readout-defs (e.g. target + counter-
  // screen) we use the first one's intercepts; per-readout column groups
  // are a separate UX (see spec §"Multi-readout-def disambiguation").
  const protocolIntercepts = useMemo(() => {
    const drDef = protocol?.readout_definitions.find(
      (r) => r.data_type === "dose_response" && r.dose_response_config,
    );
    return drDef?.dose_response_config?.intercepts ?? [];
  }, [protocol]);

  // The layer a curve fits: the one it names, else (a payload without it) the protocol's.
  // One frame every thumbnail shares (all rows, so it stays put when the hit filter changes).
  const protocolLayer = useMemo(() => curveLayer(protocol?.readout_definitions ?? []), [protocol]);
  const layerOf = useCallback(
    (c: { fitted_layer?: string | null } | undefined) =>
      c?.fitted_layer === undefined ? protocolLayer : c.fitted_layer,
    [protocolLayer],
  );
  const frame = useMemo(
    () =>
      curveFrame(
        allRows.map((r) => r.data_points),
        {
          percent: allRows.length > 0 && allRows.every((r) => isPercentNormalization(layerOf(r))),
        },
      ),
    [allRows, layerOf],
  );
  const columnDefs = useMemo(
    () =>
      buildColumnDefs(protocolIntercepts, frame, {
        query: quickFilter,
        compact: view.compact,
        diagnostics: view.diagnostics,
        unit: displayUnit,
        onView: setViewingId,
        expanded: focusResults,
        onToggleFocus: () => setFocusResults((expanded) => !expanded),
        focusButtonRef,
      }),
    [
      protocolIntercepts,
      frame,
      quickFilter,
      view.compact,
      view.diagnostics,
      displayUnit,
      focusResults,
      setFocusResults,
      focusButtonRef,
    ],
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

  return (
    <section
      ref={resultsRef}
      aria-label="Dose-response results"
      tabIndex={-1}
      className={cn(
        "min-w-0 space-y-2 outline-none",
        focusResults &&
          "fixed inset-0 z-40 flex flex-col gap-3 space-y-0 overflow-y-auto bg-background p-4 sm:p-6",
      )}
    >
      {focusResults && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 className="text-lg font-semibold">Dose-response results</h2>
          <span className="text-sm text-muted-foreground">{protocol?.name}</span>
        </div>
      )}
      {/* Keep the screening outcome and tools together, directly above the data. */}
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-2"
        aria-label="Compound results toolbar"
      >
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5">
          <div className="flex shrink-0 items-center gap-2 text-sm tabular-nums">
            {hasThreshold && (
              <Badge variant="outline" className="border-success/40 text-success">
                {hitRows.length} hit{hitRows.length !== 1 ? "s" : ""}
              </Badge>
            )}
            <span className="font-medium text-foreground">
              {quickFilter.trim() || hasThreshold || hasViewFilters
                ? `${filteredCount ?? displayedRows.length} of ${allRows.length}`
                : allRows.length}{" "}
              compound{allRows.length !== 1 ? "s" : ""}
            </span>
          </div>
          <span aria-hidden="true" className="hidden h-4 w-px bg-border sm:block" />
          {/* The scientific decision stays visible; its provenance is available on demand. */}
          {!isSet ? (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
              <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
              {recommendation.length > 0 ? (
                <>
                  <span className="font-medium">Protocol recommends</span>
                  {recommendation.map((rule) => (
                    <Badge
                      key={JSON.stringify(rule)}
                      variant="secondary"
                      className="max-w-full whitespace-normal py-0.5 text-xs"
                    >
                      {criterionLabel(rule)}
                    </Badge>
                  ))}
                  <span className="text-xs text-muted-foreground">Not yet applied</span>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        setHitCriteria.mutate({
                          runId: run.id,
                          criteria: runRulesOf(recommendation, protocol?.readout_definitions ?? [])
                            .kept,
                        })
                      }
                      disabled={setHitCriteria.isPending || run.is_locked}
                    >
                      <Check className="size-4" /> Apply to this run
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCriteriaDialogOpen(true)}
                      disabled={run.is_locked}
                    >
                      <Settings2 className="size-4" /> Customize…
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <span className="text-muted-foreground">Hit criteria not set</span>
                  <Button
                    className="h-7 px-2"
                    variant="ghost"
                    size="sm"
                    onClick={() => setCriteriaDialogOpen(true)}
                    disabled={run.is_locked}
                  >
                    <Settings2 className="size-3.5" /> Set criteria
                  </Button>
                </>
              )}
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
              <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="font-medium">Hit criteria</span>
              {hasThreshold ? (
                (runCriteria ?? []).map((rule) =>
                  isOtherTabRule(rule) ? (
                    <span key={JSON.stringify(rule)} className="text-sm text-muted-foreground">
                      {criterionLabel(rule)} (evaluated on another tab)
                    </span>
                  ) : (
                    <Badge
                      key={JSON.stringify(rule)}
                      variant="secondary"
                      className="max-w-full whitespace-normal py-0.5 text-xs"
                    >
                      {criterionLabel(rule)}
                    </Badge>
                  ),
                )
              ) : (
                <span className="text-muted-foreground">No threshold · all compounds</span>
              )}
              {run.hit_criteria_set_by && (
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      aria-label="Hit criteria provenance"
                    >
                      <Info className="h-4 w-4" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-72 text-sm" align="start">
                    Set by <MemberName id={run.hit_criteria_set_by} />
                    {run.hit_criteria_set_at ? ` on ${formatDate(run.hit_criteria_set_at)}` : ""}
                  </PopoverContent>
                </Popover>
              )}
              {hasThreshold && showAll && (
                <span className="text-xs text-muted-foreground">
                  Viewing all · criteria retained
                </span>
              )}
              <Button
                className="h-7 px-2"
                variant="ghost"
                size="sm"
                onClick={() => setCriteriaDialogOpen(true)}
                disabled={run.is_locked}
              >
                <Pencil className="size-4" /> Edit criteria
              </Button>
            </div>
          )}
        </div>
        <div className="ml-auto flex w-full flex-wrap items-center gap-2 sm:w-auto">
          <div className="relative min-w-0 flex-1 sm:w-72 sm:flex-none">
            <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
            <Input
              aria-label="Filter compounds"
              placeholder="Find compound, alias or batch…"
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              className="h-8 pr-8 pl-8"
            />
            {quickFilter && (
              <button
                type="button"
                aria-label="Clear compound search"
                onClick={() => setQuickFilter("")}
                className="absolute right-2 top-2 rounded-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
          <RunPotencyFilterControl
            intercepts={protocolIntercepts}
            unit={displayUnit}
            value={potencyFilter}
            onChange={setPotencyFilter}
          />
          <RunCurveClassFilterMenu
            selected={classFilter}
            onChange={setClassFilter}
            hasUnclassified={allRows.some((row) => row.curve_class == null)}
          />
          {hasViewFilters && (
            <Button
              variant="ghost"
              size="sm"
              aria-label="Clear view filters"
              onClick={() => {
                setClassFilter([]);
                setPotencyFilter(null);
              }}
            >
              <X className="size-3.5" />
              Clear filters
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant={view.diagnostics ? "secondary" : "outline"}
                size="sm"
                aria-label="Table options"
              >
                <SlidersHorizontal className="size-4" />
                View
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuLabel>Columns</DropdownMenuLabel>
              <DropdownMenuCheckboxItem
                checked={view.diagnostics}
                onCheckedChange={(checked) => setView({ ...view, diagnostics: checked })}
              >
                Fit diagnostics
              </DropdownMenuCheckboxItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Row density</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={view.compact ? "compact" : "comfortable"}
                onValueChange={(value) => setView({ ...view, compact: value === "compact" })}
              >
                <DropdownMenuRadioItem value="comfortable">Comfortable</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="compact">Compact</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              {canConvertUnits && commonUnit && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>Potency display units</DropdownMenuLabel>
                  <DropdownMenuRadioGroup
                    value={view.unit}
                    onValueChange={(value) => {
                      if (value === "native" || value === "uM" || value === "nM") {
                        setView({ ...view, unit: value });
                      }
                    }}
                  >
                    <DropdownMenuRadioItem value="native">
                      Run units ({displayDoseUnit(commonUnit)})
                    </DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="uM">µM</DropdownMenuRadioItem>
                    <DropdownMenuRadioItem value="nM">nM</DropdownMenuRadioItem>
                  </DropdownMenuRadioGroup>
                </>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => {
                  gridApi.current?.resetColumnState();
                  gridApi.current?.setColumnsVisible(RUN_DIAGNOSTIC_COLUMNS, view.diagnostics);
                }}
              >
                Reset table layout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {hasThreshold && (
            <Button
              variant={showAll ? "outline" : "secondary"}
              size="sm"
              aria-pressed={!showAll}
              onClick={() => setShowAll(!showAll)}
            >
              {showAll ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
              {showAll ? "All compounds" : "Hits only"}
            </Button>
          )}
        </div>
      </div>

      {selectedRows.length > 0 && (
        <div
          className="flex flex-wrap items-center gap-2 rounded-md border bg-accent/30 px-3 py-2 text-sm"
          aria-label="Selected compounds"
        >
          <span className="mr-1 font-medium tabular-nums">{selectedRows.length} selected</span>
          <Button
            variant="outline"
            size="sm"
            disabled={selectedRows.length < 2 || selectedRows.length > 5}
            onClick={() =>
              comparisonRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
          >
            <ChartNoAxesCombined className="size-4" /> Compare
          </Button>
          <Button variant="outline" size="sm" onClick={() => setCollectionDialogOpen(true)}>
            <FolderPlus className="size-4" /> Add to Collection
          </Button>
          {selectedRows.length > 5 && (
            <span className="text-xs text-muted-foreground">Compare up to 5 compounds</span>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => gridApi.current?.deselectAll()}
          >
            Clear selection
          </Button>
        </div>
      )}

      {/* Rows grow with the page; the grid's own headers stay frozen while it scrolls. */}
      <div className="run-dose-response-table" data-maximized={focusResults}>
        <DataGrid<CompoundCurveRow>
          searchPlaceholder={false}
          suppressFilters
          isExternalFilterPresent={() => hasViewFilters}
          doesExternalFilterPass={matchesViewFilter}
          quickFilterText={quickFilter}
          rowData={displayedRows}
          columnDefs={columnDefs}
          height="auto"
          domLayout="autoHeight"
          rowHeight={view.compact ? 200 : 240}
          headerHeight={44}
          preferencesKey={`run-dose-response-v2-${run.protocol_id}`}
          onFirstDataRendered={(event) => {
            gridApi.current = event.api;
            event.api.setColumnsVisible(RUN_DIAGNOSTIC_COLUMNS, view.diagnostics);
            updateGridView(event.api);
          }}
          onModelUpdated={(event) => updateGridView(event.api)}
          noRowsOverlayComponent={RunResultsEmptyOverlay}
          noRowsOverlayComponentParams={{
            hasSearch: quickFilter.trim().length > 0,
            hasViewFilters,
            criteriaEmpty: hasThreshold && !showAll && displayedRows.length === 0,
          }}
          onRowClick={(row) => setViewingId(row.molecule_id)}
          enableMultiSelect
          onSelectionChanged={handleSelectionChanged}
          getRowId={(params) => params.data.molecule_id}
        />
      </div>

      {/* Detail sheet — driven by row click, independent from selection */}
      <Sheet
        open={!!viewing}
        onOpenChange={(open) => {
          if (!open) setViewingId(null);
        }}
      >
        <SheetContent
          side="right"
          className="flex w-full flex-col p-0 sm:w-[min(820px,85vw)] sm:max-w-[min(820px,85vw)]"
        >
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
                  total={navigableRows.length}
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
                    return (
                      <DoseResponseChart
                        curves={viewingCurves}
                        isInteractive
                        runIsLocked={run.is_locked}
                        protocolConfig={drDef?.dose_response_config ?? null}
                        yReadoutNormalization={layerOf(viewingCurves[0])}
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
        <Card ref={comparisonRef}>
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
                raw_data: row.data_points,
                intercept_values: row.intercept_values,
              }))}
            />
          </CardContent>
        </Card>
      )}

      {/* Hit criteria dialog */}
      {protocol && (
        <RunHitCriteriaDialog
          runId={run.id}
          readoutDefinitions={protocol.readout_definitions}
          currentCriteria={runCriteria}
          recommendation={protocol.recommended_hit_criteria}
          open={criteriaDialogOpen}
          onOpenChange={setCriteriaDialogOpen}
        />
      )}

      {/* Collection picker — full flow so the run's selected compounds can seed a
          brand-new collection or be added to an existing one. */}
      <CollectionPickerDialog
        open={collectionDialogOpen}
        onOpenChange={setCollectionDialogOpen}
        moleculeIds={selectedRows.map((r) => r.molecule_id)}
      />
    </section>
  );
}

function RunResultsEmptyOverlay({
  hasSearch,
  criteriaEmpty,
  hasViewFilters,
}: { hasSearch: boolean; criteriaEmpty: boolean; hasViewFilters: boolean }) {
  return (
    <output className="block space-y-1 p-6 text-center">
      <p className="text-sm font-medium">
        {criteriaEmpty
          ? "No compounds meet hit criteria"
          : hasSearch
            ? "No compounds match your search"
            : "No compounds match these filters"}
      </p>
      <p className="text-xs text-muted-foreground">
        {criteriaEmpty
          ? "Adjust the hit criteria or show all compounds."
          : hasSearch
            ? "Try another identifier or clear the search."
            : hasViewFilters
              ? "Change the potency or curve class filters, or clear them to see more compounds."
              : "Clear the filters to see more compounds."}
      </p>
    </output>
  );
}
