"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { MemberName } from "@/shared/components/entity-name";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/components/ui/sheet";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { GROUP_PALETTE } from "@/shared/lib/chart-colors";
import { formatDate } from "@/shared/lib/format-date";

import type { SelectionChangedEvent } from "ag-grid-community";
import { Check, Eye, EyeOff, Filter, FlaskConical, Pencil, Settings2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useProtocol } from "../hooks/use-protocols";
import { useSetRunHitCriteria } from "../hooks/use-runs";
import { worstZPrime } from "../lib/qc-metrics";
import type { DoseResponseCurve, HitCriterion, Run } from "../types";
import { ComparisonTable } from "./comparison-table";
import { CurveNavigator } from "./curve-navigator";
import { DoseResponseChart } from "./dose-response-chart";
import { RunHitCriteriaDialog } from "./hit-criteria-dialog";
import { buildColumnDefs } from "./run-dr-results-columns";
import { applyHitFilter, buildCompoundRows } from "./run-dr-results-transforms";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const OPERATOR_SYMBOLS: Record<string, string> = {
  gt: ">",
  lt: "<",
  gte: ">=",
  lte: "<=",
  in: "in",
};

/** Compact chip text for a single rule, e.g. "% Inhibition > 50". */
function criterionChipText(rule: HitCriterion): string {
  const op = OPERATOR_SYMBOLS[rule.operator] ?? rule.operator;
  const val = Array.isArray(rule.value) ? rule.value.join(", ") : rule.value;
  return `${rule.readout_name} ${op} ${val}`;
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
  const hitRows = useMemo(
    () => (runCriteria && runCriteria.length > 0 ? applyHitFilter(allRows, runCriteria) : allRows),
    [allRows, runCriteria],
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
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center gap-4 text-sm">
        <Badge variant="secondary">
          {allRows.length} compound{allRows.length !== 1 ? "s" : ""}
        </Badge>
        {hasThreshold && (
          <Badge variant="outline" className="border-success/40 text-success">
            {hitRows.length} hit{hitRows.length !== 1 ? "s" : ""}
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

      {/* Hit Criteria — a per-run decision. Unset → recommend (never auto-apply);
          set → show the recorded decision + who/when. */}
      {!isSet ? (
        <Card className="border-2 border-dashed">
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            {recommendation.length > 0 ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">Protocol recommends</span>
                  <span className="text-muted-foreground">|</span>
                  {recommendation.map((rule, i) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
                    <Badge key={i} variant="secondary">
                      {criterionChipText(rule)}
                    </Badge>
                  ))}
                </div>
                <p className="w-full text-xs text-muted-foreground">Not yet applied</p>
                <div className="ml-auto flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      setHitCriteria.mutate({ runId: run.id, criteria: recommendation })
                    }
                    disabled={setHitCriteria.isPending || run.is_locked}
                  >
                    <Check className="mr-1 h-3.5 w-3.5" /> Apply to this run
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCriteriaDialogOpen(true)}
                    disabled={run.is_locked}
                  >
                    <Settings2 className="mr-1 h-3.5 w-3.5" /> Customize…
                  </Button>
                </div>
              </>
            ) : (
              <>
                <div>
                  <p className="font-medium">No hit criteria set for this run</p>
                  <p className="text-sm text-muted-foreground">
                    Define criteria to identify hits in this run.
                  </p>
                </div>
                <Button
                  className="ml-auto"
                  size="sm"
                  onClick={() => setCriteriaDialogOpen(true)}
                  disabled={run.is_locked}
                >
                  <Settings2 className="mr-1 h-3.5 w-3.5" /> Set hit criteria
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2 p-3">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">Hit Criteria</span>
            <span className="text-muted-foreground">|</span>

            {hasThreshold ? (
              (runCriteria ?? []).map((rule, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: criteria have no stable id
                <Badge key={i} variant="secondary">
                  {criterionChipText(rule)}
                </Badge>
              ))
            ) : (
              <span className="text-sm text-muted-foreground italic">
                No threshold — showing all compounds (recorded)
              </span>
            )}

            {run.hit_criteria_set_by && (
              <span className="text-xs text-muted-foreground">
                · Set by <MemberName id={run.hit_criteria_set_by} />
                {run.hit_criteria_set_at ? ` on ${formatDate(run.hit_criteria_set_at)}` : ""}
              </span>
            )}

            {hasThreshold && showAll && (
              <span className="text-xs italic text-muted-foreground">
                · showing all (filter bypassed)
              </span>
            )}

            <div className="ml-auto flex items-center gap-2">
              {/* View-only bypass — does not change the recorded decision. */}
              {hasThreshold &&
                (showAll ? (
                  <Button variant="ghost" size="sm" onClick={() => setShowAll(false)}>
                    <EyeOff className="mr-1 h-3.5 w-3.5" /> Show hits only
                  </Button>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => setShowAll(true)}>
                    <Eye className="mr-1 h-3.5 w-3.5" /> Show all
                  </Button>
                ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCriteriaDialogOpen(true)}
                disabled={run.is_locked}
              >
                <Pencil className="mr-1 h-3.5 w-3.5" /> Edit
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* AG Grid */}
      <DataGrid<CompoundCurveRow>
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
    </div>
  );
}
