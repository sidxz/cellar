"use client";

/**
 * ResultsGridV2 — mirrors the layout of the protocol Activity tab.
 *
 * Columns:
 *   - Compound (pinned-left, flex, min 230) — reg# + molecule name
 *   - Structure (130) — <StructureThumbnail size={104}>
 *   - per channel, grouped under the stage that owns it (funnel order, then
 *     "Other columns"); the header reads the readout with the column's short
 *     label beneath and the full label + parts on hover:
 *       - Value (170) — formatMeasurementValue + n=replicate_count + the selected
 *         stage's pass/fail verdict chip + OVR badge; clicking the value opens
 *         its facts (concentration, n, runs, batches, basis)
 *       - Curve (150, DR only) — <DoseResponseSparkline>
 *     A column with no value anywhere (unfilled, or all ND) is hidden (its Curve with it); the stage
 *     group's header carries a "+N empty columns" chip that shows them again,
 *     remembered per campaign in this browser.
 *   - Stage (pinned-right, 150, only while a stage is selected) — <StageOutcomeCell>
 *   - Notes (pinned-right, 220) — <NotesCell>
 *
 * Override editing survives inline in the value cell: an OVR badge + a
 * hover pencil-edit affordance launch the shared OverrideModal. In draft,
 * checkbox multi-select surfaces a "Remove selected (n)" toolbar that drops
 * the picked compounds from the campaign in one save.
 *
 * External chip filters wire through CampaignFilterBar helpers. Row expansion
 * and the per-row detail renderer are removed.
 */

import { useQueryClient } from "@tanstack/react-query";
import type { ColDef, ColGroupDef, ICellRendererParams, IRowNode } from "ag-grid-community";
import { Pencil, Trash2 } from "lucide-react";
import { type ReactNode, useCallback, useMemo, useState } from "react";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useBulkRemoveResultRowsApiV1CampaignsCampaignIdResultsBulkRemovePost } from "@/shared/lib/api/campaigns/campaigns";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { shortId } from "@/shared/lib/utils";

import { DoseResponseSparkline, useProtocolSummaries } from "@/features/screening-assay";
import { ReportedEndpointBadge } from "@/features/screening-assay/components/reported-endpoint-badge";
import { useProtocolsByIds } from "@/features/screening-assay/hooks/use-protocols";
import {
  type CurveFrame,
  curveFrame,
  curveLayer,
} from "@/features/screening-assay/lib/curve-frame";
import { isPercentNormalization } from "@/features/screening-assay/lib/dose-response-math";
import type { CurveClass } from "@/features/screening-assay/types";

import { showError, showSuccess } from "@/shared/lib/toast";

import { useMoleculesByIds } from "@/features/chemical-registration";
import { useBatchesByMolecule } from "@/features/inventory/hooks/use-batches";
import { useCampaignCurves } from "../../hooks/use-campaign-curves";
import { useCampaignRunLabels } from "../../hooks/use-campaign-run-labels";
import { campaignKeys } from "../../hooks/use-campaigns";
import { columnTooltip } from "../../lib/column-description";
import { protocolColorById } from "../../lib/protocol-colors";
import { groupColumnsByStage } from "../../lib/stage-column-groups";
import { outcomeFor } from "../../lib/stage-outcomes";
import { type CampaignFilters, filtersActive, rowPassesFilters } from "../campaign-filter-bar";
import { OverrideModal } from "../override-modal";

import { CurveExpandDialog, type ExpandedCurve } from "./curve-expand-dialog";
import { NotesCell } from "./notes-cell";
import { StageOutcomeCell } from "./stage-outcome-cell";

import type {
  CampaignChannelResponse,
  CampaignMeasurementResponse,
  CampaignResponse,
  CampaignResultResponse,
  CheckVerdict,
} from "../../types";

import type { CurveSnapshot } from "@/features/screening-assay";
import type { DoseResponseCurveResponse } from "@/shared/lib/api/model";

// ── Row shape ─────────────────────────────────────────────────────────────────

interface RowData {
  result: CampaignResultResponse;
}

type FrameReadouts = ReadonlyArray<Parameters<typeof curveLayer>[0][number] & { id: string }>;

/** One frame per curve channel over every row, so a column's thumbnails compare at a glance.
 *  A channel's layer comes from its protocol (the curve's own config); until that protocol
 *  loads, the column frames its data. */
export function curveFramesByChannel(
  channels: readonly CampaignChannelResponse[],
  results: readonly CampaignResultResponse[],
  liveById: Map<string, DoseResponseCurveResponse>,
  protocolsById: ReadonlyMap<string, { readout_definitions: FrameReadouts }>,
): Map<string, CurveFrame> {
  const frames = new Map<string, CurveFrame>();
  for (const ch of channels) {
    if (ch.source_kind !== "dose_response_curve") continue;
    const readouts = protocolsById.get(ch.protocol_id)?.readout_definitions ?? [];
    const curveName = readouts.find((r) => r.id === ch.readout_definition_id)?.name;
    const percent = curveName ? isPercentNormalization(curveLayer(readouts, curveName)) : false;
    const points = results.map((r) => {
      const m = r.measurements?.find((mm) => mm.channel_id === ch.id);
      return m ? (curveSnapshotFromMeasurement(m, liveById)?.raw_data as FramePoints) : null;
    });
    frames.set(ch.id, curveFrame(points, { percent }));
  }
  return frames;
}

type FramePoints = Parameters<typeof curveFrame>[0][number];

/**
 * Resolve a CurveSnapshot for a measurement. Prefers the frozen
 * `curve_snapshot` field stamped onto the measurement at import / refresh
 * (migration 031). Falls back to the live FK lookup via useCampaignCurves
 * so pre-snapshot campaigns keep drawing; the snapshot is filled in on the
 * next Refresh on a draft campaign.
 */
function curveSnapshotFromMeasurement(
  m: CampaignMeasurementResponse,
  liveById: Map<string, DoseResponseCurveResponse>,
): CurveSnapshot | null {
  const snap = (m as unknown as { curve_snapshot?: CurveSnapshot | null }).curve_snapshot;
  if (snap && Number.isFinite(snap.fitted_value)) return snap;
  const live = m.source_curve_id ? liveById.get(m.source_curve_id) : null;
  if (!live) return null;
  return {
    fitted_value: live.fitted_value,
    top: live.top,
    bottom: live.bottom,
    hill_slope: live.hill_slope,
    r_squared: live.r_squared,
    curve_class: (live.curve_class as string | null) ?? null,
    raw_data: (live.raw_data as Array<{ x: number; y: number }> | null | undefined) ?? null,
    // The four chart fields. Pre-2026-05-14 snapshots didn't carry these,
    // so for measurements that fall back to the live FK we surface them
    // here. <DoseResponseChart>'s SummaryCard reads these to render the
    // intercept chip strip + CI strip + fit-warning badges. Read straight
    // off the typed `DoseResponseCurveResponse` — no casts.
    curve_type: live.curve_type ?? null,
    confidence_interval_low: live.confidence_interval_low ?? null,
    confidence_interval_high: live.confidence_interval_high ?? null,
    // CurveSnapshot.intercept_values is the loose JSONB record shape the chart
    // re-narrows at its binding edge; copy each typed InterceptValueResponse
    // into a plain record (no `as unknown` laundering — drift on `live` stays
    // checked).
    intercept_values: live.intercept_values?.map((iv) => ({ ...iv })) ?? null,
    fit_quality_warnings: live.fit_quality_warnings ?? null,
  };
}

// ── Inline verdict chip + value cell ─────────────────────────────────────────

/** The selected stage's verdict for this cell's channel. `untested` renders
 *  nothing — the cell already shows ND/excluded/blank, so a chip would only
 *  repeat it. */
function VerdictChip({ verdict }: { verdict: CheckVerdict | null }) {
  if (verdict !== "pass" && verdict !== "fail") return null;
  const cls =
    verdict === "pass"
      ? "border-success/40 bg-success/10 text-success"
      : "border-muted text-muted-foreground";
  return <span className={`rounded-sm border px-1 py-px text-[10px] ${cls}`}>{verdict}</span>;
}

/** True when a dose-response channel resolved this cell from a reported
 *  endpoint row instead of a fitted curve. Exported so the grid's own
 *  derivation is what the tests exercise. */
export function isReportedEndpoint(
  isDR: boolean,
  m: Pick<CampaignMeasurementResponse, "source_readout_id" | "source_curve_id">,
): boolean {
  return isDR && !!m.source_readout_id && !m.source_curve_id;
}

export interface CompoundValueCellProps {
  prefix: string;
  value: number | null;
  unit: string | null | undefined;
  replicates: number | null;
  verdict: CheckVerdict | null;
  overridden: boolean | undefined;
  overrideReason: string | null | undefined;
  /** True when a dose-response channel resolved this cell from a reported
   *  endpoint row instead of a fitted curve (source_readout_id set, no
   *  source_curve_id) — the curve affordances on this row are empty. */
  reported: boolean;
  readOnly: boolean;
  onEdit: () => void;
  /** The value's facts, opened by clicking the value. */
  facts?: ReactNode;
}

export function CompoundValueCell({
  prefix,
  value,
  unit,
  replicates,
  verdict,
  overridden,
  overrideReason,
  reported,
  readOnly,
  onEdit,
  facts,
}: CompoundValueCellProps) {
  const text = `${prefix}${formatMeasurementValue(value)}${unit ? ` ${unit}` : ""}`;
  return (
    <div className="group flex items-center gap-1 py-2">
      <div className="leading-tight">
        {facts ? (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="text-sm underline-offset-4 decoration-dotted hover:underline"
              >
                {text}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72 p-3">
              {facts}
            </PopoverContent>
          </Popover>
        ) : (
          <span className="text-sm">{text}</span>
        )}
        {/* Verdict + override markers sit on their own line so they never
            push past the 120px value column (a "pass" chip inline after
            "13.6 uM" clipped to "pa"). */}
        {(verdict === "pass" || verdict === "fail" || overridden || reported) && (
          <div className="mt-0.5 flex items-center gap-1">
            <VerdictChip verdict={verdict} />
            {overridden && (
              <Badge
                variant="outline"
                className="text-[10px]"
                title={overrideReason ?? "Manually overridden"}
              >
                OVR
              </Badge>
            )}
            {reported && <ReportedEndpointBadge />}
          </div>
        )}
        {replicates != null && replicates > 1 && (
          <div className="text-[10px] text-muted-foreground">n={replicates}</div>
        )}
      </div>
      {!readOnly && (
        <button
          type="button"
          onClick={onEdit}
          aria-label="Edit measurement"
          className="ml-1 text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <Pencil className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

// ── Column header ─────────────────────────────────────────────────────────────

/** Inner header of a value column (AG Grid keeps its own sort/resize around
 *  it): the readout, the column's short label beneath, the full label and its
 *  parts on hover, and the protocol's colour as a left accent. */
export function StageColumnHeader({
  readout,
  shortLabel,
  tooltip,
  color,
}: {
  readout: string;
  shortLabel?: string;
  tooltip: string;
  color?: string;
}) {
  return (
    <div
      title={tooltip}
      className="flex min-w-0 flex-col gap-0.5 whitespace-normal border-l-2 py-1.5 pl-1.5 leading-tight"
      style={{ borderColor: color ?? "transparent" }}
    >
      <span className="font-medium">{readout}</span>
      {shortLabel && (
        <span className="line-clamp-3 text-[11px] font-normal text-muted-foreground">
          {shortLabel}
        </span>
      )}
    </div>
  );
}

/** Inner header of a stage group: its name, and — when some of its columns
 *  have no values yet and are hidden — the chip that shows them again. */
export function StageGroupHeader({
  title,
  emptyCount,
  showingEmpty,
  onToggleEmpty,
}: {
  title: string;
  emptyCount: number;
  showingEmpty: boolean;
  onToggleEmpty: () => void;
}) {
  const columns = emptyCount === 1 ? "empty column" : "empty columns";
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="truncate">{title}</span>
      {emptyCount > 0 && (
        <button
          type="button"
          aria-pressed={showingEmpty}
          onClick={onToggleEmpty}
          title="Columns with no values at this stage: not filled yet, or every value ND"
          className="shrink-0 rounded-full border px-1.5 text-[10px] font-normal leading-4 text-muted-foreground hover:border-primary/40 hover:text-foreground"
        >
          {showingEmpty ? `Hide ${emptyCount} ${columns}` : `+${emptyCount} ${columns}`}
        </button>
      )}
    </span>
  );
}

/** A column with nothing to show: no cell anywhere in it holds a value — it is
 *  unfilled or every cell is ND (a hand-entered value counts) — and it isn't
 *  waiting for a concentration to be chosen. Cellar counts this stage-wide
 *  (`description.value_count`), so a paged reader like daikon agrees. */
export function isEmptyColumn(channel: CampaignChannelResponse): boolean {
  const d = channel.description;
  return d != null && d.value_count === 0 && !d.needs_concentration;
}

/** Stage groups (by stage id, "other" for campaign columns) whose empty
 *  columns this viewer chose to see, kept per campaign in this browser. */
function useShownEmptyGroups(campaignId: string): [Set<string>, (key: string) => void] {
  const storageKey = `campaign-empty-columns:${campaignId}`;
  const [shown, setShown] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(storageKey) ?? "[]") as string[]);
    } catch {
      return new Set();
    }
  });
  const toggle = useCallback(
    (key: string) =>
      setShown((prev) => {
        const next = new Set(prev);
        if (!next.delete(key)) next.add(key);
        try {
          localStorage.setItem(storageKey, JSON.stringify([...next]));
        } catch {
          // Storage unavailable: the choice holds for this visit only.
        }
        return next;
      }),
    [storageKey],
  );
  return [shown, toggle];
}

// ── Untested cell ─────────────────────────────────────────────────────────────

const UNRESOLVED_REASON_TEXT: Record<string, string> = {
  several_concentrations: "Measured at several concentrations — choose one for this column",
  no_runs_at_stage: "No runs at this stage yet",
};

/** ND, with the reason it is untested on hover when the column knows it. */
export function NotDeterminedCell({ unresolvedReason }: { unresolvedReason?: string | null }) {
  const reason = unresolvedReason ? UNRESOLVED_REASON_TEXT[unresolvedReason] : undefined;
  return (
    <span
      className={`font-mono text-muted-foreground ${reason ? "cursor-help" : ""}`}
      title={
        reason ??
        "ND = Not Determined. The curve has no tested dose to quote or no such intercept, or no candidate is available for this cell. An inactive curve reads as a bound above its top dose."
      }
    >
      ND
    </span>
  );
}

// ── Value facts ───────────────────────────────────────────────────────────────

const BASIS_TEXT: Record<string, string> = {
  measured: "measured",
  reported: "reported",
  mixed: "measured and reported",
};

/** What stands behind one value: concentration, n, basis, batches, runs. */
export function MeasurementFacts({
  measurement: m,
  moleculeId,
  campaign,
}: {
  measurement: CampaignMeasurementResponse;
  moleculeId: string;
  campaign: CampaignResponse;
}) {
  const runLabel = useCampaignRunLabels(campaign);
  const batchIds = m.batch_ids ?? [];
  const { data: batches } = useBatchesByMolecule(batchIds.length > 0 ? moleculeId : undefined);
  const batchNumber = new Map((batches ?? []).map((b) => [b.id, b.batch_number] as const));
  const runIds = m.contributing_run_ids ?? (m.source_run_id ? [m.source_run_id] : []);
  const concentration = m.concentration_series
    ? "concentration series"
    : m.test_concentration_value != null
      ? `${m.test_concentration_value} ${m.test_concentration_unit ?? ""}`.trim()
      : "not recorded";

  return (
    // minmax(0,1fr): a long run line wraps inside the card instead of widening it.
    <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
      {m.is_manual_override && (
        <>
          <dt className="text-muted-foreground">Hand-entered</dt>
          <dd>{m.override_reason || "yes"}</dd>
        </>
      )}
      <dt className="text-muted-foreground">Concentration</dt>
      <dd>{concentration}</dd>
      {!m.concentration_series && (
        <>
          <dt className="text-muted-foreground">n</dt>
          <dd className="tabular-nums">{m.replicate_count ?? "not recorded"}</dd>
        </>
      )}
      <dt className="text-muted-foreground">Basis</dt>
      <dd>{(m.basis && BASIS_TEXT[m.basis]) ?? "not recorded"}</dd>
      <dt className="text-muted-foreground">Batches</dt>
      <dd>
        {batchIds.length === 0
          ? "not recorded"
          : batchIds.map((id) => batchNumber.get(id) ?? shortId(id)).join(", ")}
      </dd>
      <dt className="text-muted-foreground">Runs</dt>
      <dd>
        <span className="tabular-nums">{runIds.length}</span>
        {runIds.length > 0 && (
          <ul className="mt-0.5 space-y-0.5">
            {runIds.map((id) => {
              const label = runLabel(id);
              return (
                <li key={id} className="break-words">
                  <span style={{ color: label.color }}>{label.protocolName}</span> ·{" "}
                  <EntityLink type="run" id={id} label={label.text} className="font-sans text-xs" />
                  {label.detail && (
                    <span className="ml-1 text-muted-foreground tabular-nums">{label.detail}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </dd>
    </dl>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

interface ResultsGridV2Props {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  /** Selected hit stage, or null for "All". Drives the per-cell verdict
   *  chips, the Stage column and the stage half of the chip filters. */
  selectedStageId: string | null;
  readOnly: boolean;
}

// Row height tuned to fit the search-default 104-px structure thumbnail and
// the wider 220-px sparkline (140 px tall) without clipping. The compound
// stack carries 3-4 lines vertically inside this space.
const ROW_HEIGHT = 170;

export function ResultsGridV2({
  campaign,
  filters,
  selectedStageId,
  readOnly,
}: ResultsGridV2Props) {
  const [overrideTarget, setOverrideTarget] = useState<{
    result: CampaignResultResponse;
    channel: CampaignChannelResponse;
    measurement?: CampaignMeasurementResponse;
  } | null>(null);
  const [expandedCurve, setExpandedCurve] = useState<ExpandedCurve | null>(null);
  const [shownEmptyGroups, toggleEmptyGroup] = useShownEmptyGroups(campaign.id);

  // ── Bulk fetches ────────────────────────────────────────────────────────────

  const moleculeIds = useMemo(
    () => [...new Set((campaign.results ?? []).map((r) => r.molecule_id))],
    [campaign.results],
  );
  const { data: moleculesPage } = useMoleculesByIds(moleculeIds);
  const moleculesById = useMemo(
    () => new Map((moleculesPage?.items ?? []).map((m) => [m.id, m] as const)),
    [moleculesPage],
  );

  const curvesQuery = useCampaignCurves(campaign);
  const curveMap = curvesQuery.data ?? new Map();

  // Protocol name lookup for the channel-group header. `includeAll` is on so
  // we resolve any protocol referenced by a channel regardless of project
  // scope (campaigns sometimes mix protocols across programs).
  const { data: protocolSummaries } = useProtocolSummaries(undefined, {
    includeAll: true,
  });
  const protocolNameById = useMemo(
    () => new Map((protocolSummaries ?? []).map((p) => [p.id, p.name] as const)),
    [protocolSummaries],
  );

  // Each curve channel's protocol gives the layer its column's one frame follows.
  const drProtocolIds = useMemo(
    () =>
      [
        ...new Set(
          (campaign.channels ?? [])
            .filter((ch) => ch.source_kind === "dose_response_curve")
            .map((ch) => ch.protocol_id),
        ),
      ].sort(),
    [campaign.channels],
  );
  const drProtocols = useProtocolsByIds(drProtocolIds);
  const curveFrames = useMemo(
    () =>
      curveFramesByChannel(
        campaign.channels ?? [],
        campaign.results ?? [],
        curveMap,
        new Map(drProtocols.map((p) => [p.id, p] as const)),
      ),
    [campaign.channels, campaign.results, curveMap, drProtocols],
  );

  // ── Row data ────────────────────────────────────────────────────────────────

  const rowData = useMemo<RowData[]>(
    () => (campaign.results ?? []).map((r) => ({ result: r })),
    [campaign.results],
  );

  // ── Selected stage ──────────────────────────────────────────────────────────

  const selectedStage = useMemo(
    () =>
      selectedStageId ? (campaign.stages.find((s) => s.id === selectedStageId) ?? null) : null,
    [campaign.stages, selectedStageId],
  );
  // Readout labels for the override popover's failing-check lines.
  const channelLabelById = useMemo(
    () => new Map((campaign.channels ?? []).map((c) => [c.id, c.label] as const)),
    [campaign.channels],
  );

  // ── Column defs ─────────────────────────────────────────────────────────────

  const columnDefs = useMemo<(ColDef<RowData> | ColGroupDef<RowData>)[]>(() => {
    const sortedChannels = [...(campaign.channels ?? [])].sort(
      (a, b) => a.display_order - b.display_order,
    );
    const colorByProtocol = protocolColorById(sortedChannels);

    const cols: (ColDef<RowData> | ColGroupDef<RowData>)[] = [];

    // 1. Compound (pinned left) — structure thumbnail beside the id/name
    //    stack, one cell instead of two so the drawing gets the row's full
    //    height while the pinned area stays narrow.
    cols.push({
      headerName: "Compound",
      field: "result.molecule_id",
      pinned: "left",
      width: 270,
      // DataGrid calls sizeColumnsToFit, which would otherwise squeeze this
      // column below the 160px structure drawing.
      minWidth: 270,
      suppressSizeToFit: true,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<RowData>) => {
        const r = params.data?.result;
        if (!r) return null;
        const m = moleculesById.get(r.molecule_id);
        const label = m?.registration_number ?? shortId(r.molecule_id);
        const smiles = m?.structure?.smiles ?? null;
        // Synonyms are deduped against the primary name so we don't repeat
        // the same string.
        const synonyms =
          m?.identifiers
            ?.map((idn) => idn.identifier)
            .filter((s) => !!s && s !== m?.name && s !== m?.registration_number) ?? [];
        const visibleSynonyms = synonyms.slice(0, 3);
        const extra = synonyms.length - visibleSynonyms.length;
        return (
          <div className="flex h-full items-center gap-2">
            <div className="flex h-[160px] w-[160px] shrink-0 items-center justify-center">
              {smiles ? (
                <StructureThumbnail smiles={smiles} size={160} />
              ) : (
                <span className="text-muted-foreground">--</span>
              )}
            </div>
            <div className="flex min-w-0 flex-col leading-tight">
              <EntityLink
                type="compound"
                id={r.molecule_id}
                label={label}
                className="text-sm font-medium"
              />
              {m?.name && (
                <span className="text-xs text-muted-foreground truncate" title={m.name}>
                  {m.name}
                </span>
              )}
              {visibleSynonyms.map((s) => (
                <span key={s} className="text-[11px] text-muted-foreground truncate" title={s}>
                  {s}
                </span>
              ))}
              {extra > 0 && (
                <span className="text-[10px] text-muted-foreground/70 italic">+{extra} more</span>
              )}
            </div>
          </div>
        );
      },
    });

    // 3. Per-channel, grouped under the stage that owns it in funnel order,
    //    then campaign columns under "Other columns". The protocol's colour
    //    stays as an accent on each column header. Columns with no values yet
    //    are hidden behind a chip on their group's header.
    const results = campaign.results ?? [];
    for (const group of groupColumnsByStage(sortedChannels, campaign.stages ?? [])) {
      const groupKey = group.stageId ?? "other";
      const empty = group.channels.filter((ch) => isEmptyColumn(ch));
      const showingEmpty = shownEmptyGroups.has(groupKey);
      const visible = showingEmpty
        ? group.channels
        : group.channels.filter((ch) => !empty.includes(ch));
      const groupChildren: ColDef<RowData>[] = [];
      // Class + Curve columns are emitted only for the FIRST channel of a
      // given (protocol, readout-def) within a stage — sibling intercept
      // channels (e.g. EC50 + EC90 on the same Resazurin curve) share the
      // same Hill fit, so duplicating the curve drawing is pure noise. Value
      // columns stay per-channel since each intercept has its own number.
      const seenReadoutDefs = new Set<string>();
      for (const ch of visible) {
        const isDR = ch.source_kind === "dose_response_curve";
        const isFirstForReadout = !seenReadoutDefs.has(ch.readout_definition_id);
        if (isFirstForReadout) {
          seenReadoutDefs.add(ch.readout_definition_id);
        }
        const readout = ch.description?.readout_label ?? ch.label;
        const protocolName = protocolNameById.get(ch.protocol_id);

        groupChildren.push({
          headerName: ch.label,
          colId: `${ch.id}_value`,
          width: 170,
          minWidth: 150,
          wrapHeaderText: true,
          autoHeaderHeight: true,
          headerComponentParams: {
            innerHeaderComponent: StageColumnHeader,
            innerHeaderComponentParams: {
              readout: ch.label, // the scientist's own name for the column
              shortLabel: ch.description?.short_label,
              tooltip: columnTooltip(ch, protocolName),
              color: colorByProtocol.get(ch.protocol_id),
            },
          },
          valueGetter: (p) => {
            const r = p.data?.result;
            const m = r?.measurements?.find((mm) => mm.channel_id === ch.id);
            return m?.value ?? null;
          },
          cellRenderer: (params: ICellRendererParams<RowData>) => {
            const r = params.data?.result;
            if (!r) return null;
            const m = r.measurements?.find((mm) => mm.channel_id === ch.id);
            if (!m) {
              return <span className="text-muted-foreground">--</span>;
            }
            const q = m.value_qualifier;
            // Match the ND treatment on every other DR grid surface:
            // "ND" uppercase font-mono with a "Not Determined" tooltip.
            // (Was lowercase italic "nd" — cosmetic inconsistency that
            // chemists would read as a different qualifier kind.)
            if (q === "nd") {
              return <NotDeterminedCell unresolvedReason={m.unresolved_reason} />;
            }
            if (q === "excluded") {
              return (
                <span
                  className="text-muted-foreground italic"
                  title="Excluded by hit-criteria filter or readout QC."
                >
                  excluded
                </span>
              );
            }
            const prefix = q === "<" || q === ">" ? `${q} ` : "";
            // Verdict for this cell under the selected stage — null when no
            // stage is selected or the stage doesn't check this readout.
            const verdict = selectedStage
              ? ((outcomeFor(r, selectedStage.id)?.checks.find((c) => c.channel_id === ch.id)
                  ?.verdict as CheckVerdict | undefined) ?? null)
              : null;
            return (
              <CompoundValueCell
                prefix={prefix}
                value={m.value ?? null}
                unit={m.unit}
                replicates={m.replicate_count ?? null}
                verdict={verdict}
                overridden={m.is_manual_override}
                overrideReason={m.override_reason}
                reported={isReportedEndpoint(isDR, m)}
                readOnly={readOnly}
                onEdit={() => setOverrideTarget({ result: r, channel: ch, measurement: m })}
                facts={
                  <MeasurementFacts
                    measurement={m}
                    moleculeId={r.molecule_id}
                    campaign={campaign}
                  />
                }
              />
            );
          },
        });

        if (isDR && isFirstForReadout) {
          groupChildren.push({
            headerName: "Curve",
            headerTooltip: `Curve · ${readout}`,
            colId: `${ch.id}_curve`,
            width: 240,
            // DataGrid calls sizeColumnsToFit, which would otherwise squeeze
            // this column below the 220px figure and clip its right edge —
            // including the intercept marker.
            minWidth: 240,
            suppressSizeToFit: true,
            sortable: false,
            cellRenderer: (params: ICellRendererParams<RowData>) => {
              const r = params.data?.result;
              const m = r?.measurements?.find((mm) => mm.channel_id === ch.id);
              if (!r || !m) {
                return <span className="text-muted-foreground">--</span>;
              }
              // Prefer the frozen curve_snapshot on the measurement (added
              // by migration 031); fall back to the live FK lookup for
              // pre-snapshot rows. Either way, we hand the same
              // CurveSnapshot shape to the shared figure component.
              const snapshot = curveSnapshotFromMeasurement(m, curveMap);
              if (!snapshot) {
                return <span className="text-muted-foreground">--</span>;
              }
              const mol = moleculesById.get(r.molecule_id);
              const moleculeLabel = mol?.registration_number ?? shortId(r.molecule_id);
              return (
                <button
                  type="button"
                  className="block rounded hover:bg-muted/50 focus:bg-muted/60 focus:outline-none"
                  title="Click to expand"
                  onClick={() =>
                    setExpandedCurve({
                      ...snapshot,
                      unit: m.unit ?? null,
                      moleculeLabel,
                      channelLabel: ch.label,
                      yRange: curveFrames.get(ch.id)?.yRange,
                    })
                  }
                >
                  <DoseResponseSparkline
                    params={{
                      top: snapshot.top,
                      bottom: snapshot.bottom,
                      hill_slope: snapshot.hill_slope,
                      fitted_value: snapshot.fitted_value,
                      r_squared: snapshot.r_squared ?? 0,
                    }}
                    dataPoints={
                      (snapshot.raw_data as Array<{ x: number; y: number }> | null) ?? null
                    }
                    curveClass={(snapshot.curve_class as CurveClass | null) ?? null}
                    interceptValues={snapshot.intercept_values}
                    width={220}
                    height={140}
                    additionalCurves={snapshot.additional_curves ?? null}
                    aggregate={snapshot.aggregate ?? null}
                    xRange={curveFrames.get(ch.id)?.xRange}
                    yRange={curveFrames.get(ch.id)?.yRange}
                  />
                </button>
              );
            },
          });
        }
      }

      // Every column hidden: one narrow placeholder keeps the stage (and the
      // chip that shows its columns) on the grid.
      if (groupChildren.length === 0) {
        groupChildren.push({
          headerName: "No values yet",
          colId: `${groupKey}_empty`,
          width: 150,
          sortable: false,
          valueGetter: () => null,
          cellRenderer: () => null,
        });
      }

      cols.push({
        headerName: group.title,
        // A long stage name over one narrow column clips; DataGrid only adds
        // automatic tooltips to top-level leaf columns.
        headerTooltip: group.title,
        groupId: `stage_${groupKey}`,
        headerGroupComponentParams: {
          innerHeaderGroupComponent: StageGroupHeader,
          innerHeaderGroupComponentParams: {
            title: group.title,
            emptyCount: empty.length,
            showingEmpty,
            onToggleEmpty: () => toggleEmptyGroup(groupKey),
          },
        },
        children: groupChildren,
      });
    }

    // 4. Stage (pinned right, before Notes) — only while a stage is
    //    selected. The outcome chip doubles as the override affordance.
    if (selectedStage) {
      cols.push({
        headerName: "Stage",
        colId: "stage",
        pinned: "right",
        width: 150,
        sortable: false,
        cellRenderer: (params: ICellRendererParams<RowData>) => {
          const r = params.data?.result;
          if (!r) return null;
          return (
            <StageOutcomeCell
              campaignId={campaign.id}
              result={r}
              stage={selectedStage}
              channelLabelById={channelLabelById}
              readOnly={readOnly}
            />
          );
        },
      });
    }

    // 5. Notes (pinned right) — clamped free text, click-to-edit in draft.
    cols.push({
      headerName: "Notes",
      colId: "notes",
      pinned: "right",
      width: 220,
      minWidth: 160,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<RowData>) => {
        const r = params.data?.result;
        if (!r) return null;
        return <NotesCell campaignId={campaign.id} result={r} readOnly={readOnly} />;
      },
    });

    return cols;
  }, [
    protocolNameById,
    campaign,
    campaign.channels,
    campaign.id,
    campaign.results,
    curveMap,
    moleculesById,
    curveFrames,
    readOnly,
    // Every input the cell renderers read has to be here or the memoised
    // column defs keep rendering the previous stage's verdicts/chips.
    selectedStage,
    channelLabelById,
    shownEmptyGroups,
    toggleEmptyGroup,
  ]);

  // ── External (chip) filters ─────────────────────────────────────────────────

  const isExternalFilterPresent = useCallback(
    () => filtersActive(filters, selectedStageId),
    [filters, selectedStageId],
  );

  const doesExternalFilterPass = useCallback(
    (node: IRowNode<RowData>) => {
      const r = node.data?.result;
      return r ? rowPassesFilters(r, filters, selectedStageId) : true;
    },
    [filters, selectedStageId],
  );

  // ── Empty state ─────────────────────────────────────────────────────────────

  if (!campaign.results || campaign.results.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        No compounds yet — add via the +Add pills above.
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <>
      <DataGrid<RowData>
        rowData={rowData}
        columnDefs={columnDefs}
        height={600}
        rowHeight={ROW_HEIGHT}
        getRowId={(p) => p.data.result.id}
        isExternalFilterPresent={isExternalFilterPresent}
        doesExternalFilterPass={doesExternalFilterPass}
        searchPlaceholder={false}
        // The chip bar is the only filter surface on this grid: AG Grid's own
        // column menus would hide rows `rowPassesFilters` still counts as
        // visible, and the bulk gestures read that predicate.
        suppressFilters
        selectionToolbar={
          readOnly
            ? undefined
            : (rows) => (
                <RemoveSelectedButton
                  campaignId={campaign.id}
                  rows={rows}
                  filters={filters}
                  selectedStageId={selectedStageId}
                />
              )
        }
        suppressCellFocus
        animateRows={false}
      />

      {overrideTarget && (
        <OverrideModal
          open
          onOpenChange={(o) => !o && setOverrideTarget(null)}
          campaignId={campaign.id}
          result={overrideTarget.result}
          channel={overrideTarget.channel}
          measurement={overrideTarget.measurement}
        />
      )}

      <CurveExpandDialog
        data={expandedCurve}
        onOpenChange={(open) => {
          if (!open) setExpandedCurve(null);
        }}
      />
    </>
  );
}

// ── Bulk remove ───────────────────────────────────────────────────────────────

/** Selection toolbar for the draft grid: drops the checked compounds from the
 *  campaign in one save. Removal only takes the rows out of *this* campaign —
 *  no molecule, batch or readout data is touched — but it's not undoable from
 *  here, hence the confirm.
 *
 *  AG Grid keeps filtered-out nodes selected, so the selection is re-filtered
 *  through the chip predicate: the count and the payload are the rows the
 *  chemist can actually see. */
export function RemoveSelectedButton({
  campaignId,
  rows,
  filters,
  selectedStageId,
}: {
  campaignId: string;
  rows: RowData[];
  filters: CampaignFilters;
  selectedStageId: string | null;
}) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const ids = rows
    .filter((r) => rowPassesFilters(r.result, filters, selectedStageId))
    .map((r) => r.result.id);
  const n = ids.length;

  const mutation = useBulkRemoveResultRowsApiV1CampaignsCampaignIdResultsBulkRemovePost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        showSuccess(`Removed ${n} ${n === 1 ? "compound" : "compounds"}`);
      },
      onError: (err) => {
        showError(`Couldn't remove rows: ${err instanceof Error ? err.message : String(err)}`);
      },
    },
  });

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className="h-7 px-2 text-xs text-destructive hover:text-destructive"
        disabled={n === 0 || mutation.isPending}
        onClick={() => setConfirming(true)}
      >
        <Trash2 className="mr-1.5 h-3.5 w-3.5" />
        Remove selected ({n})
      </Button>

      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Remove {n} {n === 1 ? "compound" : "compounds"} from this campaign?
            </AlertDialogTitle>
            <AlertDialogDescription>
              The rows leave this campaign along with any notes and overrides recorded on them. The
              molecules, batches and readout data behind them are untouched, and they can be added
              back from their source.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => mutation.mutate({ campaignId, data: { result_ids: ids } })}
            >
              Remove {n}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
