"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { LIFECYCLE_LABELS } from "@/features/chemical-registration/types";
import { DoseResponseChart } from "@/features/screening-assay/components/dose-response-chart";
import type { CurveClass, CurveType, DoseResponseCurve } from "@/features/screening-assay/types";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/shared/components/ui/sheet";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { ChevronDown, ChevronUp, ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useMoleculeActivityDetail } from "../../hooks/use-molecule-activity-detail";
import {
  aggregateValue,
  filterCurvesByRunScope,
  pickRepresentative,
} from "../../lib/compound-detail-selection";
import {
  AGGREGATION_LABELS,
  collectRunScopesByProtocol,
  useAggregationMode,
} from "../../lib/use-aggregation-mode";
import type {
  CurveDetail,
  ProtocolCurveGroup,
  RunScope,
  SearchQuery,
} from "../../types";

// ─── Tabs ─────────────────────────────────────────────────────────────────

// Tabs removed — only Activity content shown for now.
// Inventory and History tabs will be added when those APIs are ready.

// ─── Props ────────────────────────────────────────────────────────────────

interface CompoundDetailSheetProps {
  molecule: Molecule | null;
  visibleProtocolIds: string[];
  currentIndex: number;
  totalCount: number;
  onNavigate: (direction: "prev" | "next") => void;
  onClose: () => void;
  /**
   * The executed search query. Used to derive per-protocol `run_scope`
   * filters so the drawer's curve list (fetched separately via
   * `useMoleculeActivityDetail`) honors the same narrowing that produced
   * the grid cell. Without this the drawer can show curves from runs the
   * search excluded — chemists noticed the mismatch the moment the
   * toolbar started saying "Single run per compound."
   */
  currentQuery: SearchQuery | null;
}

// ─── CurveDetail → DoseResponseCurve adapter ──────────────────────────────
//
// The search-detail panel and the protocol-runs page now share the same
// `<DoseResponseChart />` (run-page is the canonical renderer; the search
// detail simply passes `isInteractive={false}`). This adapter widens the
// activity-detail wire shape (`CurveDetail`) to the chart's expected
// `DoseResponseCurve` shape. Workspace-/molecule-id placeholders are fine —
// the chart uses them only for query-key uniqueness and never reads them.

function adaptCurve(
  curve: CurveDetail,
  protocolId: string,
  molecule: Molecule,
  overlay?: {
    additional_curves?: Array<Record<string, unknown>> | null;
    aggregate?: { marker_x: number; marker_label: string; unit: string } | null;
  },
): DoseResponseCurve {
  return {
    id: curve.curve_id,
    workspace_id: molecule.workspace_id,
    molecule_id: molecule.id,
    registration_number: molecule.registration_number ?? null,
    molecule_name: molecule.name ?? null,
    // Search-detail molecule shape doesn't carry the synonym list — the
    // chart's SummaryCard already falls back to registration_number /
    // molecule_name for the title, which is what chemists scan for.
    synonyms: [],
    smiles: molecule.structure?.smiles ?? null,
    batch_id: curve.batch_id,
    batch_number: null,
    protocol_id: protocolId,
    run_id: curve.run_id,
    readout_definition_id: curve.readout_definition_id,
    curve_type: curve.curve_type as CurveType,
    fitted_value: curve.fitted_value,
    fitted_unit: curve.fitted_unit,
    hill_slope: curve.hill_slope,
    top: curve.top,
    bottom: curve.bottom,
    r_squared: curve.r_squared,
    confidence_interval_low: curve.confidence_interval_low,
    confidence_interval_high: curve.confidence_interval_high,
    num_points: curve.num_points,
    curve_class: (curve.curve_class as CurveClass | null) ?? null,
    raw_data: curve.raw_data ?? null,
    excluded_points: curve.excluded_points ?? null,
    fit_quality_warnings: curve.fit_quality_warnings ?? [],
    intercept_values: curve.intercept_values ?? [],
    additional_curves: overlay?.additional_curves ?? null,
    aggregate: overlay?.aggregate ?? null,
  };
}


// ─── ProtocolCard ─────────────────────────────────────────────────────────

interface ProtocolCardProps {
  group: ProtocolCurveGroup;
  molecule: Molecule;
  /** Per-protocol `run_scope` from the search criterion; applied to the
   *  drawer's full curve list so the chart matches the grid cell. */
  scope?: RunScope;
  defaultExpanded?: boolean;
}

function ProtocolCard({
  group,
  molecule,
  scope,
  defaultExpanded = true,
}: ProtocolCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  // Drawer honors the toolbar's aggregation mode so the chart matches
  // the grid cell value end-to-end. Reads URL state directly via the
  // shared hook — no prop drilling.
  const { mode } = useAggregationMode();

  // Narrow to the in-scope curves BEFORE pickRepresentative / aggregateValue.
  // Without this the drawer's chart picks from runs the search criterion
  // excluded, contradicting the grid cell. Memoized so the chart doesn't
  // re-derive on every render — only when scope or curves actually change.
  const inScopeCurves = useMemo(
    () => filterCurvesByRunScope(group.curves, scope),
    [group.curves, scope],
  );

  const { adaptedCurve, repCurve, aggValue } = useMemo(() => {
    const rep = pickRepresentative(inScopeCurves, mode);
    if (!rep) return { adaptedCurve: null, repCurve: null, aggValue: null };

    // For aggregate modes, build the overlay (additional contributors +
    // amber marker) so the chart draws the same treatment as the grid
    // cell's sparkline (Step 3 of the multi-run work). Non-aggregate modes
    // get a plain rep-only chart.
    let agg: number | null = null;
    let overlay: Parameters<typeof adaptCurve>[3] | undefined;
    if (mode === "gmean" || mode === "mean") {
      agg = aggregateValue(inScopeCurves, mode);
      if (agg !== null) {
        const additional = inScopeCurves
          .filter((c) => c.curve_id !== rep.curve_id)
          .map((c) => ({
            fitted_value: c.fitted_value,
            top: c.top,
            bottom: c.bottom,
            hill_slope: c.hill_slope,
            r_squared: c.r_squared,
            curve_class: c.curve_class,
            raw_data: c.raw_data,
            intercept_values: c.intercept_values,
            curve_type: c.curve_type,
            run_date: c.run_date ?? "",
            run_id: c.run_id,
          }));
        overlay = {
          additional_curves: additional,
          aggregate: {
            marker_x: agg,
            marker_label: mode === "gmean" ? "gmean" : "mean",
            unit: rep.fitted_unit,
          },
        };
      }
    }
    return {
      adaptedCurve: adaptCurve(rep, group.protocol_id, molecule, overlay),
      repCurve: rep,
      aggValue: agg,
    };
  }, [inScopeCurves, group.protocol_id, molecule, mode]);

  if (!repCurve || !adaptedCurve) return null;

  // Header subtext describing what's drawn. The "in scope" prefix kicks in
  // whenever the search criterion's run_scope actually narrowed the
  // candidate list, so the chemist can see at a glance that the drawer is
  // honoring the same runs filter as the grid cell.
  const totalCurves = group.curves.length;
  const nScope = inScopeCurves.length;
  const scoped = scope !== undefined && nScope < totalCurves;
  const headerText = (() => {
    if (nScope === 0) return "No runs in scope";
    if (nScope === 1) {
      const d = repCurve.run_date ?? "—";
      return scoped
        ? `1 run in scope — Run ${d}`
        : `Run ${d}`;
    }
    const noun = scoped ? `${nScope} of ${totalCurves} runs in scope` : `${nScope} runs`;
    if (mode === "best_r2") {
      return `${noun} — showing best (R² = ${repCurve.r_squared.toFixed(3)})`;
    }
    if (mode === "latest") {
      const d = repCurve.run_date ?? "—";
      return `${noun} — showing latest run (${d})`;
    }
    if (aggValue !== null) {
      const label = AGGREGATION_LABELS[mode].toLowerCase();
      return `${noun} — ${label} = ${aggValue.toPrecision(3)} ${repCurve.fitted_unit}`;
    }
    return `${noun} — ${AGGREGATION_LABELS[mode].toLowerCase()}`;
  })();

  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/30"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="min-w-0 space-y-0.5">
          <p className="truncate text-sm font-medium">{group.protocol_name}</p>
          <p className="text-xs text-muted-foreground">{repCurve.curve_type}</p>
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        // `min-w-0` is the standard fix for flex children that would
        // otherwise refuse to shrink below their content width — without it
        // the side-panel chart pushes past the sheet's right edge.
        <div className="min-w-0 space-y-3 border-t border-border px-4 py-3">
          {headerText && (
            <p className="text-xs text-muted-foreground">{headerText}</p>
          )}
          <DoseResponseChart curves={[adaptedCurve]} isInteractive={false} />
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────

export function CompoundDetailSheet({
  molecule,
  visibleProtocolIds,
  currentIndex,
  totalCount,
  onNavigate,
  onClose,
  currentQuery,
}: CompoundDetailSheetProps) {
  const [othersExpanded, setOthersExpanded] = useState(false);

  const { data: activityDetail, isLoading } = useMoleculeActivityDetail(molecule?.id ?? null);

  // Per-protocol run_scope from the executed search. Derived once per query
  // change; ProtocolCard reads its own entry to filter the curves it draws.
  const runScopesByProtocol = useMemo(
    () => collectRunScopesByProtocol(currentQuery?.criteria ?? []),
    [currentQuery],
  );

  // Reset expanded state when molecule changes
  useEffect(() => {
    setOthersExpanded(false);
  }, [molecule?.id]);

  // Keyboard navigation: Arrow Up/Down to move between results
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!molecule) return;

      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        if (e.key === "ArrowUp" && currentIndex > 0) {
          onNavigate("prev");
        } else if (e.key === "ArrowDown" && currentIndex < totalCount - 1) {
          onNavigate("next");
        }
      }
    },
    [molecule, currentIndex, totalCount, onNavigate],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Split protocols into selected (visible columns) and others
  const { selected, others } = useMemo(() => {
    if (!activityDetail?.protocols) return { selected: [], others: [] };
    const visibleSet = new Set(visibleProtocolIds);
    const sel: ProtocolCurveGroup[] = [];
    const oth: ProtocolCurveGroup[] = [];
    for (const group of activityDetail.protocols) {
      if (visibleSet.has(group.protocol_id)) {
        sel.push(group);
      } else {
        oth.push(group);
      }
    }
    return { selected: sel, others: oth };
  }, [activityDetail, visibleProtocolIds]);

  const smiles = molecule?.structure?.smiles;
  const descriptors = molecule?.descriptors;

  return (
    <Sheet open={!!molecule} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-[60vw] max-w-[900px] min-w-[500px] gap-0 p-0 sm:max-w-none"
      >
        {/* Accessible title (visually hidden) */}
        <SheetTitle className="sr-only">
          Compound detail: {molecule?.registration_number ?? ""}
        </SheetTitle>
        <SheetDescription className="sr-only">
          Detailed activity data and properties for the selected compound.
        </SheetDescription>

        {molecule && (
          <div className="flex h-full flex-col">
            {/* ── Header ── */}
            <div className="flex items-start gap-4 border-b border-border px-5 py-4">
              {smiles && <StructureThumbnail smiles={smiles} size={80} />}
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold">
                      {molecule.registration_number}
                    </p>
                    {molecule.name && (
                      <p className="truncate text-sm text-muted-foreground">{molecule.name}</p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={onClose}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {molecule.molecular_formula && (
                  <p className="text-xs text-muted-foreground">{molecule.molecular_formula}</p>
                )}

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {descriptors?.molecular_weight != null && (
                    <span>
                      MW{" "}
                      <span className="font-mono tabular-nums">
                        {descriptors.molecular_weight.toFixed(1)}
                      </span>
                    </span>
                  )}
                  {descriptors?.logp != null && (
                    <span>
                      LogP{" "}
                      <span className="font-mono tabular-nums">{descriptors.logp.toFixed(2)}</span>
                    </span>
                  )}
                </div>

                <StatusBadge
                  status={molecule.lifecycle_stage}
                  label={LIFECYCLE_LABELS[molecule.lifecycle_stage]}
                />
              </div>
            </div>

            {/* ── Navigation bar ── */}
            {totalCount > 1 && (
              <div className="flex items-center justify-between border-b border-border px-5 py-2">
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    disabled={currentIndex === 0}
                    onClick={() => onNavigate("prev")}
                  >
                    <ChevronUp className="h-4 w-4" />
                  </Button>
                  <span className="font-mono text-sm tabular-nums text-muted-foreground">
                    {currentIndex + 1} / {totalCount}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    disabled={currentIndex === totalCount - 1}
                    onClick={() => onNavigate("next")}
                  >
                    <ChevronDown className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                  <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono">
                    &uarr;&darr;
                  </kbd>
                  <span>navigate</span>
                  <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono">
                    esc
                  </kbd>
                  <span>close</span>
                </div>
              </div>
            )}

            {/* ── Scrollable content ──
                `min-h-0` is required so `flex-1` actually constrains the
                ScrollArea's height instead of letting it grow to fit its
                content. Without it the content (chart + summary card)
                pushes the footer + ScrollArea bottom below the viewport
                and no scrollbar ever appears — the chart looks clipped
                at the screen edge. */}
            <ScrollArea className="min-h-0 flex-1">
              <div className="space-y-5 px-5 py-4">
                {/* Loading state */}
                {isLoading && (
                  <div className="space-y-4">
                    <Skeleton className="h-[260px] w-full rounded-lg" />
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                )}

                {/* No activity data */}
                {!isLoading && (!activityDetail || activityDetail.protocols.length === 0) && (
                  <p className="py-8 text-center text-sm text-muted-foreground">
                    No dose-response data available for this compound.
                  </p>
                )}

                {/* Selected protocol curves */}
                {!isLoading && selected.length > 0 && (
                  <div className="space-y-3">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Selected Protocols
                    </h4>
                    {molecule &&
                      selected.map((group) => (
                        <ProtocolCard
                          key={group.protocol_id}
                          group={group}
                          molecule={molecule}
                          scope={runScopesByProtocol.get(group.protocol_id)}
                          defaultExpanded
                        />
                      ))}
                  </div>
                )}

                {/* Other protocols (collapsible) */}
                {!isLoading && others.length > 0 && (
                  <div className="space-y-3">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-muted/50"
                      onClick={() => setOthersExpanded((v) => !v)}
                    >
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Also tested in {others.length} other protocol
                        {others.length > 1 ? "s" : ""}
                      </span>
                      {othersExpanded ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </button>

                    {othersExpanded &&
                      molecule &&
                      others.map((group) => (
                        <ProtocolCard
                          key={group.protocol_id}
                          group={group}
                          molecule={molecule}
                          // "Other" protocols weren't in the search query, so
                          // they carry no scope — chemist sees the full curve
                          // history for the drilldown.
                          scope={runScopesByProtocol.get(group.protocol_id)}
                          defaultExpanded={false}
                        />
                      ))}
                  </div>
                )}
              </div>
            </ScrollArea>

            {/* ── Footer ── */}
            <div className="border-t border-border px-5 py-3">
              <Link
                href={`/compounds/${molecule.id}`}
                target="_blank"
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
              >
                Open full detail
                <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
