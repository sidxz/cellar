"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { LIFECYCLE_LABELS } from "@/features/chemical-registration/types";
import { CompoundCurvesButton } from "@/features/screening-assay/components/compound-curves-dialog";
import type {
  CurveClass,
  CurveType,
  DoseResponseCurve,
  Protocol,
} from "@/features/screening-assay/types";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { EntityLink } from "@/shared/components/entity-link";
import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/shared/components/ui/sheet";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Plot } from "@/shared/lib/plotly";
import {
  DoseResponseSummaryCard,
  buildDoseResponsePlot,
} from "@structflo/components/dose-response";
import { ChevronDown, ChevronUp, ExternalLink, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useMoleculeActivityDetail } from "../../hooks/use-molecule-activity-detail";
import { type ComparisonChannel, comparisonChannels } from "../../lib/comparison-channels";
import { filterCurvesByRunScope, pickRepresentative } from "../../lib/compound-detail-selection";
import { compoundRef, curvesTarget } from "../../lib/curves-target";
import {
  AGGREGATION_LABELS,
  type AggregationMode,
  collectRunScopesByProtocol,
} from "../../lib/use-aggregation-mode";
import { anyProtocolActivity } from "../../types";
import type {
  ActivityValue,
  CurveDetail,
  ProtocolCurveGroup,
  RunScope,
  SearchQuery,
} from "../../types";
import { ActiveInCell } from "./active-in-cell";
import { AssayResult } from "./assay-result";

// ─── Tabs ─────────────────────────────────────────────────────────────────

// Tabs removed — only Activity content shown for now.
// Inventory and History tabs will be added when those APIs are ready.

// ─── Props ────────────────────────────────────────────────────────────────

interface CompoundDetailSheetProps {
  molecule: (Molecule & { activity?: Record<string, ActivityValue> }) | null;
  protocolColumns: string[];
  protocols: Protocol[];
  visibleProtocolIds: string[];
  currentIndex: number;
  totalCount: number;
  onNavigate: (direction: "prev" | "next") => void;
  onOpenChange: (open: boolean) => void;
  /**
   * The executed search query. Used to derive per-protocol `run_scope`
   * filters so the drawer's curve list (fetched separately via
   * `useMoleculeActivityDetail`) honors the same narrowing that produced
   * the grid cell. Without this the drawer can show curves from runs the
   * search excluded — chemists noticed the mismatch the moment the
   * toolbar started saying "Single run per compound."
   */
  currentQuery: SearchQuery | null;
  aggregationMode?: AggregationMode;
}

// Adapt one source fit for the shared diagnostic chart. Reported endpoints
// remain in the search snapshot above; no aggregation is recomputed here.

function adaptCurve(curve: CurveDetail, protocolId: string, molecule: Molecule): DoseResponseCurve {
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
    additional_curves: null,
    aggregate: null,
  };
}

// ─── ProtocolCard ─────────────────────────────────────────────────────────

type ReportedMolecule = Molecule & { activity?: Record<string, ActivityValue> };

interface ProtocolCardProps {
  group: Pick<ProtocolCurveGroup, "protocol_id" | "protocol_name" | "curves">;
  molecule: ReportedMolecule;
  scope?: RunScope;
  protocol?: Protocol;
  channels?: ComparisonChannel[];
  mode?: AggregationMode;
  defaultExpanded?: boolean;
  loading?: boolean;
}

/** Identify the snapshot's representative fit without inferring it from an aggregate value. */
export function findSearchSourceCurve(
  curves: CurveDetail[],
  av?: ActivityValue,
): CurveDetail | null {
  if (!av) return null;
  if (av.curve_params) {
    const params = av.curve_params;
    const matching = curves.filter(
      (curve) =>
        curve.top === params.top &&
        curve.bottom === params.bottom &&
        curve.hill_slope === params.hill_slope &&
        curve.r_squared === av.r_squared &&
        curve.curve_class === params.curve_class &&
        curve.confidence_interval_low === params.confidence_interval_low &&
        curve.confidence_interval_high === params.confidence_interval_high,
    );
    if (matching.length === 1) return matching[0];
  }
  if (av.run_count === 1 && av.runs?.length === 1) {
    return curves.find((curve) => curve.curve_id === av.runs?.[0].curve_id) ?? null;
  }
  return null;
}

function ReportedEndpoints({
  channels,
  molecule,
  mode,
}: { channels: ComparisonChannel[]; molecule: ReportedMolecule; mode: AggregationMode }) {
  if (!channels.length) return null;
  return (
    <section
      aria-label="Reported search results"
      className="min-w-0 space-y-2 rounded-lg bg-primary/5 p-3"
    >
      <div>
        <h4 className="text-xs font-semibold">Reported endpoints</h4>
        <p className="mt-1 text-xs text-muted-foreground">
          {AGGREGATION_LABELS[mode]} · Search values
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-1">
        {channels.map((channel) => (
          <div key={channel.id} className="min-w-0 space-y-1 border-t border-primary/10 pt-2">
            <dt className="text-xs font-medium">
              {channel.label}
              {channel.unit ? ` (${channel.unit})` : ""}
            </dt>
            <dd>
              <AssayResult
                av={molecule.activity?.[channel.activityKey]}
                channel={channel}
                mode={mode}
              />
            </dd>
          </div>
        ))}
      </dl>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        ND means no reportable potency.
      </p>
    </section>
  );
}

/** Keep the source plot visible; only numerical fit diagnostics need expansion. */
function SourceCurveCard({
  curves,
  protocolId,
  readoutName,
  molecule,
  channels,
  mode,
}: {
  curves: CurveDetail[];
  protocolId: string;
  readoutName: string;
  molecule: ReportedMolecule;
  channels: ComparisonChannel[];
  mode: AggregationMode;
}) {
  const [curveId, setCurveId] = useState("");
  const [inspecting, setInspecting] = useState(false);
  const sorted = useMemo(
    () => [...curves].sort((a, b) => (b.run_date ?? "").localeCompare(a.run_date ?? "")),
    [curves],
  );
  const av = channels.length ? molecule.activity?.[channels[0].activityKey] : undefined;
  const matched = findSearchSourceCurve(sorted, av);
  const curve =
    sorted.find((c) => c.curve_id === curveId) ?? matched ?? pickRepresentative(sorted, mode);
  const adapted = useMemo(
    () => (curve ? adaptCurve(curve, protocolId, molecule) : null),
    [curve, protocolId, molecule],
  );
  const figure = useMemo(
    () =>
      adapted
        ? buildDoseResponsePlot([adapted], { showCI: true, showMarker: true, showPlateaus: false })
        : null,
    [adapted],
  );
  if (!curve || !adapted || !figure) return null;
  const aggregate = mode === "gmean" || mode === "mean";
  const capturedTotal = (curve.raw_data?.length ?? 0) + (curve.excluded_points?.length ?? 0);
  const excludedCount = curve.excluded_points?.length ?? 0;
  return (
    <div className="min-w-0 space-y-3">
      <label className="flex flex-col gap-1 text-xs font-medium">
        Source curve · {readoutName}
        <select
          className="h-9 w-full min-w-0 rounded-md border bg-background px-2 text-sm"
          value={curve.curve_id}
          onChange={(event) => {
            setCurveId(event.target.value);
            setInspecting(false);
          }}
        >
          {sorted.map((c) => (
            <option key={c.curve_id} value={c.curve_id}>
              {c.run_date ?? "Date unavailable"} · {c.curve_type.toUpperCase()} ·{" "}
              {c.curve_class ?? "Unclassified"} · {c.curve_id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <EntityLink
          type="run"
          id={curve.run_id}
          label={`Open source run · ${curve.run_date ?? "date unavailable"}`}
          className="text-xs"
        />
        <span>
          R² {curve.r_squared.toFixed(3)} · {curve.curve_class ?? "Unclassified"}
        </span>
      </div>
      {channels.length > 0 && (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {aggregate
            ? `Individual source fit shown. Reported ${AGGREGATION_LABELS[mode].toLowerCase()} summarizes in-scope results and may differ from this curve’s fitted value.`
            : matched?.curve_id === curve.curve_id
              ? "Source of the search’s representative curve. Reported endpoints retain the search’s qualifiers."
              : curveId
                ? "Selected source fit. Reported search values remain unchanged."
                : "Source fit shown for reference; the reported source could not be uniquely identified."}
        </p>
      )}
      {curve.fit_quality_warnings && curve.fit_quality_warnings.length > 0 && (
        <p className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">
          Fit quality:{" "}
          {curve.fit_quality_warnings.map((warning) => warning.replaceAll("_", " ")).join(" · ")}
        </p>
      )}
      <div
        className={
          channels.length ? "grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_11rem]" : "min-w-0"
        }
      >
        {channels.length > 0 && (
          <div className="order-2">
            <ReportedEndpoints channels={channels} molecule={molecule} mode={mode} />
          </div>
        )}
        <figure
          aria-label={`Dose–response curve for ${readoutName}, source run ${curve.run_date ?? "date unavailable"}`}
          className="min-w-0 overflow-hidden rounded-lg border bg-background"
        >
          <Plot
            data={figure.traces}
            layout={{
              ...figure.layout,
              height: 300,
              autosize: true,
              margin: { l: 55, r: 15, t: 25, b: 50 },
            }}
            config={{ ...figure.config, responsive: true }}
            style={{ width: "100%", height: 300 }}
            useResizeHandler
          />
        </figure>
      </div>
      <details
        open={inspecting}
        onToggle={(event) => setInspecting(event.currentTarget.open)}
        className="rounded-lg border border-border/70 px-3 py-2"
      >
        <summary className="cursor-pointer text-xs font-medium">
          Fit parameters &amp; diagnostics
        </summary>
        {inspecting && (
          <div className="mt-3 space-y-2">
            <p className="text-xs text-muted-foreground">
              Individual fit diagnostics. Fitted values can be shown even for inactive or bounded
              curves; use reported search endpoints for potency and selectivity.
            </p>
            <DoseResponseSummaryCard
              curve={adapted}
              inFitCount={Math.max(0, capturedTotal - excludedCount)}
              capturedTotal={capturedTotal}
              excludedCount={excludedCount}
            />
          </div>
        )}
      </details>
    </div>
  );
}

function ProtocolCard({
  group,
  molecule,
  scope,
  protocol,
  channels = [],
  mode = "latest",
  defaultExpanded = true,
  loading = false,
}: ProtocolCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const inScopeCurves = useMemo(
    () => filterCurvesByRunScope(group.curves, scope),
    [group.curves, scope],
  );
  const readouts = useMemo(() => {
    const map = new Map<string, CurveDetail[]>();
    for (const curve of inScopeCurves) {
      const curves = map.get(curve.readout_definition_id) ?? [];
      curves.push(curve);
      map.set(curve.readout_definition_id, curves);
    }
    return [...map.entries()].sort(
      ([a], [b]) =>
        Number(channels.some((c) => c.readoutId === b)) -
        Number(channels.some((c) => c.readoutId === a)),
    );
  }, [inScopeCurves, channels]);
  const unmatched = channels.filter(
    (channel) => !channel.doseResponse || !readouts.some(([id]) => id === channel.readoutId),
  );
  return (
    <div className="min-w-0 overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 bg-primary/5 pr-3">
        <button
          type="button"
          aria-expanded={expanded}
          className="flex min-w-0 flex-1 items-center justify-between gap-3 px-4 py-3 text-left hover:bg-primary/10"
          onClick={() => setExpanded((value) => !value)}
        >
          <div className="min-w-0">
            <p className="break-words text-sm font-semibold">{group.protocol_name}</p>
            <p className="text-xs text-muted-foreground">
              {loading
                ? "Loading source curves…"
                : `${inScopeCurves.length} source fit${inScopeCurves.length === 1 ? "" : "s"} in scope`}
            </p>
          </div>
          {expanded ? (
            <ChevronUp className="size-4 shrink-0" />
          ) : (
            <ChevronDown className="size-4 shrink-0" />
          )}
        </button>
        {/* Beside the expand button, not inside it. */}
        <CompoundCurvesButton target={curvesTarget(protocol, [compoundRef(molecule)])} />
      </div>
      {expanded && (
        <div className="min-w-0 space-y-4 p-3 sm:p-4">
          <ReportedEndpoints channels={unmatched} molecule={molecule} mode={mode} />
          {readouts.length === 0 && !loading && (
            <p className="text-xs text-muted-foreground">
              No source curves available in this search’s run scope.
            </p>
          )}
          {readouts.map(([readoutId, curves]) => (
            <SourceCurveCard
              key={readoutId}
              curves={curves}
              protocolId={group.protocol_id}
              readoutName={
                protocol?.readout_definitions?.find((r) => r.id === readoutId)?.name ??
                curves[0].curve_type.toUpperCase()
              }
              molecule={molecule}
              channels={channels.filter(
                (channel) => channel.doseResponse && channel.readoutId === readoutId,
              )}
              mode={mode}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────

export function CompoundDetailSheet({
  molecule,
  visibleProtocolIds,
  protocolColumns,
  protocols,
  currentIndex,
  totalCount,
  onNavigate,
  onOpenChange,
  currentQuery,
  aggregationMode = "latest",
}: CompoundDetailSheetProps) {
  const [othersExpanded, setOthersExpanded] = useState(false);

  const {
    data: activityDetail,
    isLoading,
    isError,
    refetch,
  } = useMoleculeActivityDetail(molecule?.id ?? null);

  // Per-protocol run_scope from the executed search. Derived once per query
  // change; ProtocolCard reads its own entry to filter the curves it draws.
  const runScopesByProtocol = useMemo(
    () => collectRunScopesByProtocol(currentQuery?.criteria ?? []),
    [currentQuery],
  );

  // Keyboard navigation: Arrow Up/Down to move between results
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!molecule || e.defaultPrevented) return;
      const target = e.target as HTMLElement | null;
      if (
        target?.closest(
          "input, select, textarea, button, a, summary, [role='combobox'], [role='listbox'], [data-slot='popover-content'], [contenteditable='true']",
        )
      )
        return;

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

  const channels = useMemo(
    () => comparisonChannels(protocolColumns, protocols),
    [protocolColumns, protocols],
  );
  const reportGroups = useMemo(() => {
    const ids = [
      ...new Set([
        ...channels.map((channel) => channel.protocolId),
        ...selected.map((group) => group.protocol_id),
      ]),
    ];
    return ids.map((id) => ({
      group: selected.find((group) => group.protocol_id === id) ?? {
        protocol_id: id,
        protocol_name:
          channels.find((channel) => channel.protocolId === id)?.protocolName ?? "Assay",
        curves: [],
      },
      channels: channels.filter((channel) => channel.protocolId === id),
    }));
  }, [channels, selected]);
  const crossAssay = molecule ? anyProtocolActivity(molecule) : undefined;
  const smiles = molecule?.structure?.smiles;
  const descriptors = molecule?.descriptors;

  return (
    <Sheet open={!!molecule} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-full gap-0 p-0 sm:w-[70vw] sm:max-w-[900px]"
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
            <div className="flex items-start gap-3 border-b border-border px-4 py-3">
              {smiles && <StructureThumbnail smiles={smiles} size={64} />}
              <div className="min-w-0 flex-1 space-y-1">
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
                    aria-label="Close compound detail"
                    onClick={() => onOpenChange(false)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {molecule.molecular_formula && <span>{molecule.molecular_formula}</span>}
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
                  <StatusBadge
                    status={molecule.lifecycle_stage}
                    label={LIFECYCLE_LABELS[molecule.lifecycle_stage]}
                  />
                </div>
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
                    aria-label="Previous compound"
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
                    aria-label="Next compound"
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
              <div className="space-y-4 px-3 py-3 sm:px-4">
                {crossAssay && (
                  <section aria-label="Reported search results" className="rounded-lg border p-3">
                    <ActiveInCell value={crossAssay} />
                  </section>
                )}
                {reportGroups.map(({ group, channels: groupChannels }) => (
                  <ProtocolCard
                    key={group.protocol_id}
                    group={group}
                    molecule={molecule}
                    protocol={protocols.find((p) => p.id === group.protocol_id)}
                    scope={runScopesByProtocol.get(group.protocol_id)}
                    channels={groupChannels}
                    mode={aggregationMode}
                    loading={isLoading}
                  />
                ))}
                {isError && (
                  <div role="alert" className="rounded-lg border p-4 text-sm">
                    Source curves could not be loaded. Reported search results remain available.
                    <Button
                      variant="outline"
                      size="sm"
                      className="ml-2"
                      onClick={() => void refetch()}
                    >
                      Retry source curves
                    </Button>
                  </div>
                )}
                {/* Loading state */}
                {isLoading && (
                  <div className="space-y-4">
                    <Skeleton className="h-[260px] w-full rounded-lg" />
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                )}

                {/* No activity data */}
                {!isLoading &&
                  !isError &&
                  (!activityDetail || activityDetail.protocols.length === 0) && (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      No dose-response data available for this compound.
                    </p>
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
                          protocol={protocols.find((p) => p.id === group.protocol_id)}
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
