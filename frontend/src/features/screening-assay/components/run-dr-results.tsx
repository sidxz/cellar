"use client";

import { CollectionPickerDialog } from "@/shared/components/collection-picker-dialog";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { MemberName } from "@/shared/components/entity-name";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { formatDate } from "@/shared/lib/format-date";

import type { SelectionChangedEvent } from "ag-grid-community";
import {
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
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useProtocol } from "../hooks/use-protocols";
import { useSetRunHitCriteria } from "../hooks/use-runs";
import { runRulesOf } from "../lib/melt-hits";
import type { DoseResponseCurve, HitCriterion, Run } from "../types";
import { ComparisonTable } from "./comparison-table";
import { CurveNavigator } from "./curve-navigator";
import { criterionLabel } from "./detail-tabs/use-activity-tab";
import { DoseResponseChart } from "./dose-response-chart";
import { RunHitCriteriaDialog } from "./hit-criteria-dialog";
import { buildColumnDefs } from "./run-dr-results-columns";
import { applyHitFilter, buildCompoundRows } from "./run-dr-results-transforms";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

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

  // Curve navigation (prev/next of the currently viewed compound)
  const viewing = useMemo(
    () => displayedRows.find((r) => r.molecule_id === viewingId) ?? null,
    [displayedRows, viewingId],
  );
  const selectedIndex = viewing
    ? displayedRows.findIndex((r) => r.molecule_id === viewing.molecule_id)
    : -1;

  const navigateTo = useCallback(
    (index: number) => {
      const target = displayedRows[index];
      if (target) setViewingId(target.molecule_id);
    },
    [displayedRows],
  );

  const handlePrev = useCallback(() => {
    const newIdx = selectedIndex <= 0 ? displayedRows.length - 1 : selectedIndex - 1;
    navigateTo(newIdx);
  }, [selectedIndex, displayedRows.length, navigateTo]);

  const handleNext = useCallback(() => {
    const newIdx = selectedIndex >= displayedRows.length - 1 ? 0 : selectedIndex + 1;
    navigateTo(newIdx);
  }, [selectedIndex, displayedRows.length, navigateTo]);

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

  const columnDefs = useMemo(() => buildColumnDefs(protocolIntercepts), [protocolIntercepts]);

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
    <div className="space-y-2">
      {/* Keep the screening outcome and tools together, directly above the data. */}
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-2"
        aria-label="Compound results toolbar"
      >
        <div className="flex items-center gap-2 text-sm tabular-nums">
          {hasThreshold && (
            <Badge variant="outline" className="border-success/40 text-success">
              {hitRows.length} hit{hitRows.length !== 1 ? "s" : ""}
            </Badge>
          )}
          <span className="text-muted-foreground">
            {allRows.length} compound{allRows.length !== 1 ? "s" : ""}
          </span>
        </div>
        {selectedRows.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">{selectedRows.length} selected</span>
            <Button variant="outline" size="sm" onClick={() => setCollectionDialogOpen(true)}>
              <FolderPlus className="size-4" />
              Add to Collection
            </Button>
          </div>
        )}
        <div className="ml-auto flex w-full flex-wrap items-center gap-2 sm:w-auto">
          <div className="relative min-w-0 flex-1 sm:w-64 sm:flex-none">
            <Search className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
            <Input
              aria-label="Filter compounds"
              placeholder="Find compound, alias or batch…"
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              className="h-8 pl-8"
            />
          </div>
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

      {/* The scientific decision stays visible; its provenance is available on demand. */}
      {!isSet ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-dashed px-4 py-3 text-sm">
          <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
          {recommendation.length > 0 ? (
            <>
              <span className="font-medium">Protocol recommends</span>
              {recommendation.map((rule, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
                <Badge key={i} variant="secondary" className="py-1 text-sm">
                  {criterionLabel(rule)}
                </Badge>
              ))}
              <span className="text-xs text-muted-foreground">Not yet applied</span>
              <div className="ml-auto flex items-center gap-2">
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
              <span className="text-muted-foreground">No hit criteria set for this run</span>
              <Button
                className="ml-auto"
                variant="ghost"
                size="sm"
                onClick={() => setCriteriaDialogOpen(true)}
                disabled={run.is_locked}
              >
                <Settings2 className="size-4" /> Set hit criteria
              </Button>
            </>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border bg-muted/20 px-4 py-3 text-sm">
          <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="font-medium">Hit criteria</span>
          {hasThreshold ? (
            (runCriteria ?? []).map((rule, i) =>
              isOtherTabRule(rule) ? (
                // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
                <span key={i} className="text-sm text-muted-foreground">
                  {criterionLabel(rule)} (evaluated on another tab)
                </span>
              ) : (
                // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
                <Badge key={i} variant="secondary" className="py-1 text-sm">
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
            <span className="text-xs text-muted-foreground">Viewing all · criteria retained</span>
          )}
          <Button
            className="ml-auto"
            variant="outline"
            size="sm"
            onClick={() => setCriteriaDialogOpen(true)}
            disabled={run.is_locked}
          >
            <Pencil className="size-4" /> Edit criteria
          </Button>
        </div>
      )}

      {/* AG Grid */}
      <DataGrid<CompoundCurveRow>
        searchPlaceholder={false}
        quickFilterText={quickFilter}
        rowData={displayedRows}
        columnDefs={columnDefs}
        height="auto"
        domLayout="autoHeight"
        rowHeight={115}
        onRowClick={(row) => setViewingId(row.molecule_id)}
        enableMultiSelect
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.molecule_id}
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
                  total={displayedRows.length}
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
                        isInteractive
                        runIsLocked={run.is_locked}
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
    </div>
  );
}
