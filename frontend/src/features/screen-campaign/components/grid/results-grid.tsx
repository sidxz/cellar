"use client";

/**
 * ResultsGridV2 — the campaign's results, laid out as DAIKON's Hits table.
 *
 * Columns, left to right:
 *   - # (pinned) — row number; the row checkbox for editors who can remove rows
 *   - Structure (pinned, 236) — right-click for the compound's shortcuts
 *   - Compound (pinned) — reg#, name, other identifiers ("+N more" expands);
 *     right-click as Structure
 *   - per stage (funnel order, then "Other columns"; only the selected stage
 *     when one is) → per protocol (name + ⓘ "how measured") → per column:
 *       - Value — right-aligned, its QC (verdict, who, when, note) under it;
 *         click for its facts, right-click to set QC or its note
 *       - Curve (DR, once per readout definition) — <DoseResponseSparkline>
 *     A column with no value anywhere (unfilled, or all ND) is hidden (its Curve
 *     with it); the stage's header carries a "+N" chip that shows
 *     them again, remembered per campaign in this browser.
 *   - Stage (only while a stage is selected) — <StageOutcomeCell>
 *   - Notes — the note, who and when, versions; right-click or click to edit;
 *     takes the spare width
 *   - ⋯ (pinned right) — every right-click action in one menu
 *
 * Override editing stays inline in the value cell (OVR badge + hover pencil →
 * OverrideModal). External chip filters wire through CampaignFilterBar helpers.
 */

import { useQueryClient } from "@tanstack/react-query";
import type {
  ColDef,
  ColGroupDef,
  GridApi,
  ICellRendererParams,
  IRowNode,
  SortChangedEvent,
} from "ag-grid-community";
import { History, Info, Pencil, StickyNote, TestTubes, Trash2 } from "lucide-react";
import { type ReactNode, useCallback, useMemo, useRef, useState } from "react";

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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
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
  drawnPoints,
} from "@/features/screening-assay/lib/curve-frame";
import { isPercentNormalization } from "@/features/screening-assay/lib/dose-response-math";
import type { CurveClass } from "@/features/screening-assay/types";

import { showError, showSuccess } from "@/shared/lib/toast";

import { useBatchesByMolecule } from "@/features/inventory/hooks/use-batches";
import { useCampaignCurves } from "../../hooks/use-campaign-curves";
import { useCampaignMolecules } from "../../hooks/use-campaign-molecules";
import { useCampaignRunLabels } from "../../hooks/use-campaign-run-labels";
import { campaignKeys } from "../../hooks/use-campaigns";
import { columnTooltip, concentrationText } from "../../lib/column-description";
import { protocolColorById } from "../../lib/protocol-colors";
import { groupColumnsByStage } from "../../lib/stage-column-groups";
import { outcomeFor } from "../../lib/stage-outcomes";
import { type CampaignFilters, filtersActive, rowPassesFilters } from "../campaign-filter-bar";
import { OverrideModal } from "../override-modal";
import { NotesPopover } from "../popovers/notes-popover";

import { QcBulkMenu } from "../qc-bulk-menu";
import { StageBulkMenu } from "../stage-bulk-menu";
import { CurveExpandDialog, type ExpandedCurve } from "./curve-expand-dialog";
import {
  CompoundIdentity,
  MoleculeContextMenu,
  RowActionsMenu,
  type Shortcut,
  moleculeShortcuts,
} from "./molecule-menu";
import { NotesCell, noteTracked } from "./notes-cell";
import { QcMenu, QcSummary, QcVerdictControl } from "./qc-verdict-control";
import {
  type ColumnGroup,
  type GridSort,
  type ReadoutOption,
  ResultsToolbar,
} from "./results-toolbar";
import { SelectionHeader } from "./selection-header";
import { selectionText } from "./selection-text";
import { StageOutcomeCell } from "./stage-outcome-cell";
import { useColumnVisibility } from "./use-column-visibility";
import { useMaximize } from "./use-maximize";

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
    const snapshots = results.map((r) => {
      const m = r.measurements?.find((mm) => mm.channel_id === ch.id);
      return m ? curveSnapshotFromMeasurement(m, liveById) : null;
    });
    // The layer a snapshot names (null: raw); one frozen before the key existed asks the
    // channel's protocol.
    const named = snapshots.find((s) => s != null && "fitted_layer" in s) as
      | { fitted_layer?: string | null }
      | undefined;
    const readouts = protocolsById.get(ch.protocol_id)?.readout_definitions ?? [];
    const curveName = readouts.find((r) => r.id === ch.readout_definition_id)?.name;
    const layer = named ? named.fitted_layer : curveName ? curveLayer(readouts, curveName) : null;
    const points = snapshots.flatMap(drawnPoints);
    frames.set(ch.id, curveFrame(points, { percent: isPercentNormalization(layer) }));
  }
  return frames;
}

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
  /** The value's QC lines, under it. */
  qc?: ReactNode;
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
  qc,
}: CompoundValueCellProps) {
  // "-" is how a dimensionless readout (LogD) records "no unit".
  const shownUnit = unit && unit.trim() !== "-" ? unit : null;
  const text = `${prefix}${formatMeasurementValue(value)}${shownUnit ? ` ${shownUnit}` : ""}`;
  return (
    <div className="group flex h-full items-center justify-end gap-1 py-1">
      {!readOnly && (
        <button
          type="button"
          onClick={onEdit}
          aria-label="Edit measurement"
          className="mr-1 text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <Pencil className="h-3 w-3" />
        </button>
      )}
      <div className="flex flex-col items-end leading-tight tabular-nums">
        {facts ? (
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="whitespace-nowrap text-base font-medium underline-offset-4 decoration-dotted hover:underline"
              >
                {text}
              </button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72 p-3">
              {facts}
            </PopoverContent>
          </Popover>
        ) : (
          <span className="whitespace-nowrap text-base font-medium">{text}</span>
        )}
        {/* Verdict + override markers sit on their own line so they never
            push past the value column (a "pass" chip inline after
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
          <div className="text-xs text-muted-foreground">n={replicates}</div>
        )}
        {qc && <div className="mt-1 max-w-full">{qc}</div>}
      </div>
    </div>
  );
}

// ── Column header ─────────────────────────────────────────────────────────────

/** Inner header of a value column (AG Grid keeps its own sort/resize around
 *  it): the column's own name and the dose it was read at, with the full
 *  label and its parts on hover. How it was measured is behind the protocol's ⓘ. */
export function ReadoutColumnHeader({
  label,
  at,
  tooltip,
}: {
  label: string;
  at?: string;
  tooltip: string;
}) {
  return (
    <span
      title={tooltip}
      className="flex min-w-0 flex-wrap items-baseline justify-end gap-x-1.5 whitespace-normal py-1 leading-tight"
    >
      <span className="font-medium">{label}</span>
      {at && <span className="text-xs font-normal text-muted-foreground">at {at}</span>}
    </span>
  );
}

/** Inner header of a protocol's columns: its name in its colour, and an ⓘ
 *  that says how each of its columns was measured. */
export function ProtocolGroupHeader({
  name,
  color,
  channels,
}: {
  name: string;
  color?: string;
  channels: CampaignChannelResponse[];
}) {
  const described = channels.filter((c) => c.description?.short_label);
  return (
    <span className="flex min-w-0 items-center gap-1 py-1">
      <span className="flex min-w-0 items-center gap-1.5 font-medium" style={{ color }}>
        <TestTubes className="size-3.5 shrink-0" aria-hidden="true" />
        {/* Two lines before it clips: one value column is narrower than most names. */}
        <span className="line-clamp-2 whitespace-normal leading-tight" title={name}>
          {name}
        </span>
      </span>
      {described.length > 0 && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={`How ${name} was measured`}
              className="shrink-0 rounded-sm text-muted-foreground hover:text-foreground"
            >
              <Info className="size-3.5" aria-hidden="true" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80 max-w-[calc(100vw-2rem)] space-y-2">
            <h4 className="text-sm font-semibold">{name}</h4>
            <dl className="space-y-2 text-xs">
              {described.map((c) => (
                <div key={c.id}>
                  <dt className="font-medium">{c.label}</dt>
                  <dd className="text-muted-foreground">{c.description?.short_label}</dd>
                </div>
              ))}
            </dl>
          </PopoverContent>
        </Popover>
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

// ── Untested cell ─────────────────────────────────────────────────────────────

const UNRESOLVED_REASON_TEXT: Record<string, string> = {
  several_concentrations: "Measured at several concentrations — choose one for this column",
  no_runs_at_stage: "No runs at this stage yet",
};

/** ND, with the reason it is untested on hover when the column knows it. A tested ND can
 *  carry a QC verdict, so it opens the same facts card as a value. */
export function NotDeterminedCell({
  unresolvedReason,
  facts,
  qc,
}: {
  unresolvedReason?: string | null;
  facts?: ReactNode;
  /** The value's QC lines, under it. */
  qc?: ReactNode;
}) {
  const reason = unresolvedReason ? UNRESOLVED_REASON_TEXT[unresolvedReason] : undefined;
  const title = reason ?? "ND = Not Determined. No reportable result is available for this cell.";
  const cls = `font-mono text-muted-foreground ${reason ? "cursor-help" : ""}`;
  return (
    <span className="flex h-full flex-col items-end justify-center gap-1">
      {facts ? (
        <Popover>
          <PopoverTrigger asChild>
            <button type="button" className={`${cls} hover:underline`} title={title}>
              ND
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-72 p-3">
            {facts}
          </PopoverContent>
        </Popover>
      ) : (
        <span className={cls} title={title}>
          ND
        </span>
      )}
      {qc}
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
  /** QC verdicts are an editor's call; defaults to ``readOnly``. */
  qcReadOnly?: boolean;
  /** Notes are an editor's to write on any campaign status; defaults to ``readOnly``. */
  notesReadOnly?: boolean;
  /** Compound rows are the managing app's to add and remove (curation stays on readOnly). */
  rowsLocked?: boolean;
  /** The toolbar's search and readout conditions write here. */
  onFiltersChange: (next: CampaignFilters) => void;
  /** Rendered above the toolbar (the outcome chips, the bulk menus), so Maximize takes them too. */
  header?: ReactNode;
}

/** A value column's id is its channel's plus this. */
const VALUE_SUFFIX = "_value";

/** The column-picker id of a curve column: its readout's first channel, plus ":curve". */
export const curveColumnId = (channelId: string) => `${channelId}:curve`;

/** The channels that own a curve column: per stage, the first dose-response channel of each
 *  readout definition — sibling intercept channels (EC50 + EC90 on one fit) share its drawing. */
export function curveOwnerIds(groups: { channels: CampaignChannelResponse[] }[]): Set<string> {
  const owners = new Set<string>();
  for (const g of groups) {
    const seen = new Set<string>();
    for (const ch of g.channels) {
      if (seen.has(ch.readout_definition_id)) continue;
      seen.add(ch.readout_definition_id);
      if (ch.source_kind === "dose_response_curve") owners.add(ch.id);
    }
  }
  return owners;
}

/** Each channel's unit: the one most of its exact values are stored in. */
export function unitsByChannel(results: readonly CampaignResultResponse[]): Map<string, string> {
  const counts = new Map<string, Map<string, number>>();
  for (const r of results) {
    for (const m of r.measurements ?? []) {
      if (m.value_qualifier !== "=" || m.value == null) continue;
      const byUnit = counts.get(m.channel_id) ?? new Map<string, number>();
      byUnit.set(m.unit ?? "", (byUnit.get(m.unit ?? "") ?? 0) + 1);
      counts.set(m.channel_id, byUnit);
    }
  }
  return new Map(
    [...counts].map(([id, byUnit]) => [id, [...byUnit].sort((a, b) => b[1] - a[1])[0]?.[0] ?? ""]),
  );
}

/** Sorts numbers, with ND and blank last in either direction. */
export function blanksLast(
  a: number | null,
  b: number | null,
  _na: unknown,
  _nb: unknown,
  isDescending: boolean,
): number {
  if (a == null && b == null) return 0;
  // AG Grid flips the result for a descending sort, so a blank's side flips with it.
  if (a == null) return isDescending ? -1 : 1;
  if (b == null) return isDescending ? 1 : -1;
  return a - b;
}

// A first guess at a row's height: the structure and compound columns size
// each row to their content (a long identifier list grows it), never below the
// 152-px structure box (the 144-px drawing), which also fits the 140-px sparkline.
const ROW_HEIGHT = 160;
// With no structure or curve shown: a value with its QC lines.
const SHORT_ROW_HEIGHT = 96;

// Large enough that atom labels read at a glance.
const STRUCTURE = { width: 220, height: 144 };
const STRUCTURE_COLUMN = 236;

// A header beside the stage/protocol rows spans them; its label sits on the
// bottom row with the column labels.
// AG Grid's own styles are unlayered, so these need !important to win.
const SPAN_HEADER = "[&_.ag-header-cell-label]:!items-end [&_.ag-cell-label-container]:!pb-2";

/** Every cell's content centred in its row's height (AG Grid tops it by
 *  default); right-aligned cells keep to the right. The structure and compound
 *  columns size the row and centre themselves. */
function centred<T>(c: ColDef<T> | ColGroupDef<T>): ColDef<T> | ColGroupDef<T> {
  if ("children" in c) return { ...c, children: c.children.map(centred) };
  if (c.autoHeight) return c;
  const cls = typeof c.cellClass === "string" ? c.cellClass : "";
  const end = cls.includes("ag-right-aligned-cell") ? "!justify-end" : "";
  return { ...c, cellClass: `!flex !items-center ${end} ${cls}`.trim() };
}

export function ResultsGridV2({
  campaign,
  filters,
  selectedStageId,
  readOnly,
  qcReadOnly = readOnly,
  notesReadOnly = readOnly,
  rowsLocked = false,
  onFiltersChange,
  header,
}: ResultsGridV2Props) {
  const [overrideTarget, setOverrideTarget] = useState<{
    result: CampaignResultResponse;
    channel: CampaignChannelResponse;
    measurement?: CampaignMeasurementResponse;
  } | null>(null);
  const [expandedCurve, setExpandedCurve] = useState<ExpandedCurve | null>(null);
  const [noteTarget, setNoteTarget] = useState<{ resultId: string; history: boolean } | null>(null);
  const [qcNoteTarget, setQcNoteTarget] = useState<{
    resultId: string;
    channelId: string;
  } | null>(null);
  // Editors who can remove rows tick them; the checkbox sits in the # column.
  // Anyone with a bulk gesture ticks rows in the # column; the bulk bar acts on the ticks.
  const selectable = !readOnly || !qcReadOnly;
  const removable = !readOnly && !rowsLocked;
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const { ref: workspaceRef, maximized, setMaximized } = useMaximize();

  // ── Bulk fetches ────────────────────────────────────────────────────────────

  const moleculesById = useCampaignMolecules(campaign);
  const moleculeLabel = (moleculeId: string) =>
    moleculesById.get(moleculeId)?.registration_number ?? shortId(moleculeId);

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

  // ── Columns in view, and which the viewer hides ─────────────────────────────

  const sortedChannels = useMemo(
    () => [...(campaign.channels ?? [])].sort((a, b) => a.display_order - b.display_order),
    [campaign.channels],
  );
  const allStageGroups = useMemo(
    () => groupColumnsByStage(sortedChannels, campaign.stages ?? []),
    [sortedChannels, campaign.stages],
  );
  // A selected stage shows its own columns only; "All" shows every stage.
  const stageGroups = useMemo(
    () => allStageGroups.filter((g) => !selectedStage || g.stageId === selectedStage.id),
    [allStageGroups, selectedStage],
  );
  const curveOwners = useMemo(() => curveOwnerIds(allStageGroups), [allStageGroups]);
  const emptyIds = useMemo(
    () =>
      sortedChannels
        .filter((ch) => isEmptyColumn(ch))
        .flatMap((ch) => (curveOwners.has(ch.id) ? [ch.id, curveColumnId(ch.id)] : [ch.id])),
    [sortedChannels, curveOwners],
  );
  const { hidden, setVisible } = useColumnVisibility(campaign.id, emptyIds);

  const toolbarData = useMemo(() => {
    const unitOf = unitsByChannel(campaign.results ?? []);
    const protocolOf = (ch: CampaignChannelResponse) =>
      protocolNameById.get(ch.protocol_id) ?? "Protocol";
    const inView = new Set(stageGroups.flatMap((g) => g.channels.map((ch) => ch.id)));
    const fullLabel = new Map<string, string>();
    const readouts: ReadoutOption[] = [];
    for (const g of allStageGroups) {
      for (const ch of g.channels) {
        fullLabel.set(ch.id, `${g.title} · ${protocolOf(ch)} · ${ch.label}`);
        if (inView.has(ch.id)) {
          readouts.push({
            id: ch.id,
            // The stage only when several show.
            label: selectedStage ? `${protocolOf(ch)} · ${ch.label}` : (fullLabel.get(ch.id) ?? ""),
            unit: unitOf.get(ch.id) ?? "",
          });
        }
      }
    }
    const columns: ColumnGroup[] = [
      {
        title: "Compound",
        columns: [
          { id: "structure", label: "Structure" },
          { id: "notes", label: "Notes" },
        ],
      },
      ...stageGroups.map((g) => ({
        title: g.title,
        columns: g.channels.flatMap((ch) => {
          const empty = isEmptyColumn(ch);
          const label = `${ch.label} · ${protocolOf(ch)}`;
          return [
            { id: ch.id, label, empty },
            ...(curveOwners.has(ch.id)
              ? [{ id: curveColumnId(ch.id), label: `${ch.label} curve`, empty }]
              : []),
          ];
        }),
      })),
    ];
    return {
      readouts,
      labelOf: (id: string) =>
        readouts.find((r) => r.id === id)?.label ?? fullLabel.get(id) ?? "Readout not in campaign",
      columns,
    };
  }, [campaign.results, protocolNameById, stageGroups, allStageGroups, selectedStage, curveOwners]);
  const sortable = useMemo(
    () => toolbarData.readouts.filter((r) => !hidden.has(r.id)),
    [toolbarData.readouts, hidden],
  );

  // ── Sort ────────────────────────────────────────────────────────────────────

  const apiRef = useRef<GridApi<RowData> | null>(null);
  const [sort, setSort] = useState<GridSort | null>(null);
  // A header click sorts too; either way the toolbar reads the grid's own sort.
  const onSortChanged = useCallback((e: SortChangedEvent<RowData>) => {
    const col = e.api.getColumnState().find((c) => c.sort);
    setSort(
      col?.colId.endsWith(VALUE_SUFFIX)
        ? { channelId: col.colId.slice(0, -VALUE_SUFFIX.length), desc: col.sort === "desc" }
        : null,
    );
    e.api.refreshCells({ columns: ["row"], force: true });
  }, []);
  const applySort = useCallback((next: GridSort | null) => {
    apiRef.current?.applyColumnState({
      state: next
        ? [{ colId: `${next.channelId}${VALUE_SUFFIX}`, sort: next.desc ? "desc" : "asc" }]
        : [],
      defaultState: { sort: null },
    });
  }, []);

  // ── Column defs ─────────────────────────────────────────────────────────────

  // The structure box sets a row's height; without it a row keeps room for a curve, else for a
  // value's QC lines.
  const tallRows = useMemo(
    () =>
      !hidden.has("structure") ||
      stageGroups.some((g) =>
        g.channels.some((ch) => curveOwners.has(ch.id) && !hidden.has(curveColumnId(ch.id))),
      ),
    [hidden, stageGroups, curveOwners],
  );

  const columnDefs = useMemo<(ColDef<RowData> | ColGroupDef<RowData>)[]>(() => {
    const colorByProtocol = protocolColorById(sortedChannels);
    const labelOf = (moleculeId: string) =>
      moleculesById.get(moleculeId)?.registration_number ?? shortId(moleculeId);

    const cols: (ColDef<RowData> | ColGroupDef<RowData>)[] = [];

    // 1-3. #, Structure and Compound stay put while the readouts scroll beside them.
    //      Editors who can remove rows tick them in the # column.
    cols.push({
      headerName: "#",
      headerTooltip: "Row number",
      colId: "row",
      pinned: "left",
      width: selectable ? 76 : 48,
      minWidth: selectable ? 76 : 48,
      suppressSizeToFit: true,
      resizable: false,
      sortable: false,
      valueGetter: (p) => (p.node?.rowIndex ?? 0) + 1,
      cellClass: "ag-right-aligned-cell text-xs tabular-nums text-muted-foreground",
      headerClass: `ag-right-aligned-header ${SPAN_HEADER}`,
      ...(selectable ? { checkboxSelection: true, headerComponent: SelectionHeader } : {}),
    });
    if (!hidden.has("structure"))
      cols.push({
        headerName: "Structure",
        colId: "structure",
        headerClass: SPAN_HEADER,
        pinned: "left",
        width: STRUCTURE_COLUMN,
        minWidth: STRUCTURE_COLUMN,
        suppressSizeToFit: true,
        resizable: false,
        sortable: false,
        autoHeight: true,
        cellRenderer: (params: ICellRendererParams<RowData>) => {
          const r = params.data?.result;
          if (!r) return null;
          const m = moleculesById.get(r.molecule_id);
          const smiles = m?.structure?.smiles ?? null;
          return (
            <MoleculeContextMenu moleculeId={r.molecule_id} molecule={m}>
              <div className="flex h-[152px] items-center justify-center">
                {smiles ? (
                  <StructureThumbnail
                    smiles={smiles}
                    size={STRUCTURE.width}
                    height={STRUCTURE.height}
                  />
                ) : (
                  <span className="text-xs text-muted-foreground">No structure</span>
                )}
              </div>
            </MoleculeContextMenu>
          );
        },
      });
    cols.push({
      headerName: "Compound",
      colId: "compound",
      headerClass: SPAN_HEADER,
      pinned: "left",
      width: 180,
      minWidth: 150,
      suppressSizeToFit: true,
      sortable: false,
      autoHeight: true,
      cellRenderer: (params: ICellRendererParams<RowData>) => {
        const r = params.data?.result;
        if (!r) return null;
        const m = moleculesById.get(r.molecule_id);
        return (
          <MoleculeContextMenu moleculeId={r.molecule_id} molecule={m}>
            <div className={`flex items-center ${tallRows ? "min-h-[152px]" : "min-h-[88px]"}`}>
              <CompoundIdentity moleculeId={r.molecule_id} molecule={m} />
            </div>
          </MoleculeContextMenu>
        );
      },
    });

    // 4. Per stage (funnel order, then "Other columns"; only the selected stage
    //    when one is), per protocol: each column's value (its QC under it), and
    //    the curve once per readout — less what the viewer hid (empty columns
    //    start hidden; see useColumnVisibility).
    for (const group of stageGroups) {
      const groupKey = group.stageId ?? "other";
      const factsFor = (r: CampaignResultResponse, m: CampaignMeasurementResponse) => (
        <>
          <MeasurementFacts measurement={m} moleculeId={r.molecule_id} campaign={campaign} />
          <QcVerdictControl
            campaignId={campaign.id}
            measurement={m}
            resultId={r.id}
            readOnly={qcReadOnly}
          />
        </>
      );
      const byProtocol = new Map<string, CampaignChannelResponse[]>();
      for (const ch of group.channels) {
        byProtocol.set(ch.protocol_id, [...(byProtocol.get(ch.protocol_id) ?? []), ch]);
      }

      const protocolGroups: (ColDef<RowData> | ColGroupDef<RowData>)[] = [];
      for (const [protocolId, channels] of byProtocol) {
        const protocolName = protocolNameById.get(protocolId);
        const children: ColDef<RowData>[] = [];
        for (const ch of channels) {
          const isDR = ch.source_kind === "dose_response_curve";
          const readout = ch.description?.readout_label ?? ch.label;
          // One curve per readout, on its first channel (see curveOwnerIds).
          const showCurve = curveOwners.has(ch.id) && !hidden.has(curveColumnId(ch.id));

          if (!hidden.has(ch.id))
            children.push({
              headerName: ch.label,
              colId: `${ch.id}_value`,
              // Wide enough that a protocol's name wraps between words over one column.
              width: 150,
              minWidth: 110,
              suppressSizeToFit: true,
              wrapHeaderText: true,
              autoHeaderHeight: true,
              cellClass: "ag-right-aligned-cell",
              headerClass: "ag-right-aligned-header",
              headerComponentParams: {
                innerHeaderComponent: ReadoutColumnHeader,
                innerHeaderComponentParams: {
                  label: ch.label, // the scientist's own name for the column
                  at: ch.test_concentration ? concentrationText(ch.test_concentration) : undefined,
                  tooltip: columnTooltip(ch, protocolName),
                },
              },
              valueGetter: (p) => {
                const r = p.data?.result;
                const m = r?.measurements?.find((mm) => mm.channel_id === ch.id);
                return m?.value ?? null;
              },
              comparator: blanksLast,
              cellRenderer: (params: ICellRendererParams<RowData>) => {
                const r = params.data?.result;
                if (!r) return null;
                const m = r.measurements?.find((mm) => mm.channel_id === ch.id);
                if (!m) {
                  return <span className="text-muted-foreground">--</span>;
                }
                const q = m.value_qualifier;
                // The whole cell is the QC right-click target; its lines sit under the value.
                const withQc = (cell: ReactNode) => (
                  <QcMenu
                    campaignId={campaign.id}
                    measurement={m}
                    resultId={r.id}
                    readOnly={qcReadOnly}
                    onEditNote={() => setQcNoteTarget({ resultId: r.id, channelId: ch.id })}
                  >
                    <div className="absolute inset-0 flex items-center justify-end px-2">
                      {cell}
                    </div>
                  </QcMenu>
                );
                const qcLines = <QcSummary measurement={m} />;
                // "ND" uppercase font-mono with a "Not Determined" tooltip, as on
                // every other DR grid surface.
                if (q === "nd") {
                  return withQc(
                    <NotDeterminedCell
                      unresolvedReason={m.unresolved_reason}
                      facts={m.holds_result ? factsFor(r, m) : undefined}
                      qc={qcLines}
                    />,
                  );
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
                return withQc(
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
                    facts={factsFor(r, m)}
                    qc={qcLines}
                  />,
                );
              },
            });

          if (showCurve) {
            children.push({
              headerName: "Curve",
              headerTooltip: `Curve · ${readout}`,
              colId: `${ch.id}_curve`,
              width: 240,
              // Never below the 220px figure, which would clip its right edge —
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
                return (
                  <button
                    type="button"
                    className="block rounded hover:bg-muted/50 focus:bg-muted/60 focus:outline-none"
                    title="Click to expand"
                    onClick={() =>
                      setExpandedCurve({
                        ...snapshot,
                        unit: m.unit ?? null,
                        moleculeLabel: labelOf(r.molecule_id),
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
        if (children.length === 0) continue;
        const name = protocolName ?? "Protocol";
        protocolGroups.push({
          headerName: name,
          groupId: `stage_${groupKey}_protocol_${protocolId}`,
          wrapHeaderText: true,
          autoHeaderHeight: true,
          headerGroupComponentParams: {
            innerHeaderGroupComponent: ProtocolGroupHeader,
            innerHeaderGroupComponentParams: {
              name,
              color: colorByProtocol.get(protocolId),
              channels,
            },
          },
          children,
        });
      }

      // Every column hidden: the stage leaves the grid; Columns brings it back.
      if (protocolGroups.length === 0) continue;
      cols.push({
        headerName: group.title,
        // A long stage name over one narrow column clips; DataGrid only adds
        // automatic tooltips to top-level leaf columns.
        headerTooltip: group.title,
        groupId: `stage_${groupKey}`,
        children: protocolGroups,
      });
    }

    // 5. Stage — only while a stage is selected. The outcome chip doubles as
    //    the override affordance.
    if (selectedStage) {
      cols.push({
        headerName: "Stage",
        colId: "stage",
        width: 110,
        suppressSizeToFit: true,
        sortable: false,
        headerClass: SPAN_HEADER,
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

    // 6. Notes — after every readout, so evidence reads first.
    if (!hidden.has("notes"))
      cols.push({
        headerName: "Notes",
        colId: "notes",
        // The spare width, so the data packs to the left and a long note has room.
        flex: 1,
        minWidth: 200,
        sortable: false,
        headerClass: SPAN_HEADER,
        cellRenderer: (params: ICellRendererParams<RowData>) => {
          const r = params.data?.result;
          if (!r) return null;
          return (
            <NotesCell
              result={r}
              readOnly={notesReadOnly}
              onEdit={() => setNoteTarget({ resultId: r.id, history: false })}
              onHistory={() => setNoteTarget({ resultId: r.id, history: true })}
            />
          );
        },
      });

    // 7. The row's "⋯": every right-click action, for the keyboard. Pinned, so
    //    it is in reach however wide the readouts run.
    cols.push({
      headerName: "",
      colId: "actions",
      headerClass: SPAN_HEADER,
      pinned: "right",
      width: 48,
      minWidth: 48,
      suppressSizeToFit: true,
      resizable: false,
      sortable: false,
      cellClass: "ag-right-aligned-cell",
      cellRenderer: (params: ICellRendererParams<RowData>) => {
        const r = params.data?.result;
        if (!r) return null;
        const hasNote = !!r.notes?.trim();
        const noteActions: Shortcut[] = [
          ...(notesReadOnly
            ? []
            : [
                {
                  label: hasNote ? "Edit note…" : "Add note…",
                  icon: <StickyNote />,
                  run: () => setNoteTarget({ resultId: r.id, history: false }),
                },
              ]),
          ...(noteTracked(r)
            ? [
                {
                  label: "Note history…",
                  icon: <History />,
                  run: () => setNoteTarget({ resultId: r.id, history: true }),
                },
              ]
            : []),
        ];
        return (
          <div className="flex h-full items-center justify-end">
            <RowActionsMenu
              label={labelOf(r.molecule_id)}
              groups={[
                ...moleculeShortcuts(r.molecule_id, moleculesById.get(r.molecule_id)),
                noteActions,
              ]}
            />
          </div>
        );
      },
    });

    return cols.map(centred);
  }, [
    protocolNameById,
    campaign,
    curveMap,
    moleculesById,
    curveFrames,
    readOnly,
    qcReadOnly,
    notesReadOnly,
    selectable,
    // Every input the cell renderers read has to be here or the memoised
    // column defs keep rendering the previous stage's verdicts/chips.
    selectedStage,
    channelLabelById,
    sortedChannels,
    stageGroups,
    curveOwners,
    hidden,
    tallRows,
  ]);

  // ── External (chip) filters ─────────────────────────────────────────────────

  const isExternalFilterPresent = useCallback(
    () => filtersActive(filters, selectedStageId),
    [filters, selectedStageId],
  );

  const doesExternalFilterPass = useCallback(
    (node: IRowNode<RowData>) => {
      const r = node.data?.result;
      return r ? rowPassesFilters(r, filters, selectedStageId, moleculesById) : true;
    },
    [filters, selectedStageId, moleculesById],
  );

  // The ticks still on the campaign, and how many of them the filters hide.
  // And how many rows the filters leave visible, for the bulk bar's select links.
  const { ticked, hiddenTicked, visibleCount } = useMemo(() => {
    const results = campaign.results ?? [];
    const visible = new Set(
      results
        .filter((r) => rowPassesFilters(r, filters, selectedStageId, moleculesById))
        .map((r) => r.id),
    );
    const known = new Set(results.map((r) => r.id));
    const live = selectedIds.filter((id) => known.has(id));
    return {
      ticked: live,
      hiddenTicked: live.filter((id) => !visible.has(id)).length,
      visibleCount: visible.size,
    };
  }, [selectedIds, campaign.results, filters, selectedStageId, moleculesById]);
  const totalCount = campaign.results?.length ?? 0;

  // Row numbers follow the order on screen.
  const renumber = useCallback(
    (e: { api: { refreshCells: (p: { columns: string[]; force: boolean }) => void } }) =>
      e.api.refreshCells({ columns: ["row"], force: true }),
    [],
  );

  // ── Empty state ─────────────────────────────────────────────────────────────

  if (!campaign.results || campaign.results.length === 0) {
    return (
      <>
        {header}
        <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
          No compounds yet — add via the +Add pills above.
        </div>
      </>
    );
  }

  // The dialogs read the row as it is now, so a save shows at once.
  const noteResult = noteTarget
    ? campaign.results.find((r) => r.id === noteTarget.resultId)
    : undefined;
  const qcResult = qcNoteTarget
    ? campaign.results.find((r) => r.id === qcNoteTarget.resultId)
    : undefined;
  const qcMeasurement = qcResult?.measurements?.find(
    (m) => m.channel_id === qcNoteTarget?.channelId,
  );

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <>
      <section
        ref={workspaceRef}
        aria-label="Results"
        className={
          maximized ? "fixed inset-0 z-40 flex flex-col overflow-hidden bg-background" : undefined
        }
      >
        {header}
        {selectable && (
          <div className="flex flex-wrap items-center gap-1.5 border-b bg-muted/10 px-3 py-1.5">
            <span className="text-xs text-muted-foreground">
              {ticked.length === 0
                ? "Bulk:"
                : `Bulk (${selectionText(ticked.length, hiddenTicked)}):`}
            </span>
            <SelectLinks
              visible={visibleCount}
              total={totalCount}
              // Offered only where they would change the ticks.
              allVisibleTicked={ticked.length === visibleCount && hiddenTicked === 0}
              allTicked={ticked.length === totalCount}
              anyTicked={ticked.length > 0}
              onSelectVisible={() => {
                apiRef.current?.deselectAll();
                apiRef.current?.selectAll("filtered");
              }}
              onSelectAll={() => apiRef.current?.selectAll("all")}
              onClear={() => apiRef.current?.deselectAll()}
            />
            <StageBulkMenu
              campaign={campaign}
              resultIds={ticked}
              hiddenCount={hiddenTicked}
              selectedStageId={selectedStageId}
              readOnly={readOnly}
            />
            <QcBulkMenu
              campaign={campaign}
              resultIds={ticked}
              hiddenCount={hiddenTicked}
              selectedStageId={selectedStageId}
              readOnly={qcReadOnly}
            />
            {removable && (
              <RemoveSelectedButton
                campaignId={campaign.id}
                resultIds={ticked}
                hiddenCount={hiddenTicked}
              />
            )}
          </div>
        )}
        <ResultsToolbar
          filters={filters}
          onFiltersChange={onFiltersChange}
          readouts={toolbarData.readouts}
          labelOf={toolbarData.labelOf}
          sortable={sortable}
          sort={sort}
          onSortChange={applySort}
          columns={toolbarData.columns}
          hidden={hidden}
          onColumnsChange={setVisible}
          maximized={maximized}
          onMaximizedChange={setMaximized}
        />
        <div className={maximized ? "min-h-0 flex-1" : undefined}>
          <DataGrid<RowData>
            rowData={rowData}
            columnDefs={columnDefs}
            height={600}
            fill={maximized}
            rowHeight={tallRows ? ROW_HEIGHT : SHORT_ROW_HEIGHT}
            columnBorders
            getRowId={(p) => p.data.result.id}
            isExternalFilterPresent={isExternalFilterPresent}
            doesExternalFilterPass={doesExternalFilterPass}
            onGridReady={(e) => {
              apiRef.current = e.api;
            }}
            onSortChanged={onSortChanged}
            onFilterChanged={renumber}
            searchPlaceholder={false}
            // The chip bar is the only filter surface on this grid: AG Grid's own
            // column menus would hide rows `rowPassesFilters` still counts as
            // visible, and the bulk gestures read that predicate.
            suppressFilters
            // The checkbox lives in the # column; the bulk bar above acts on the ticks.
            enableMultiSelect={selectable}
            suppressSelectColumn
            onSelectionChanged={(e) =>
              setSelectedIds(e.api.getSelectedRows().map((row) => row.result.id))
            }
            suppressCellFocus
            animateRows={false}
          />
        </div>
      </section>

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

      <Dialog open={!!noteResult} onOpenChange={(o) => !o && setNoteTarget(null)}>
        {noteResult && noteTarget && (
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>
                {noteTarget.history
                  ? "Note history"
                  : noteResult.notes?.trim()
                    ? "Edit note"
                    : "Add note"}
              </DialogTitle>
              <DialogDescription>{moleculeLabel(noteResult.molecule_id)}</DialogDescription>
            </DialogHeader>
            <NotesPopover
              key={`${noteResult.id}-${noteTarget.history}`}
              campaignId={campaign.id}
              result={noteResult}
              onClose={() => setNoteTarget(null)}
              readOnly={notesReadOnly || noteTarget.history}
              initialHistory={noteTarget.history}
            />
          </DialogContent>
        )}
      </Dialog>

      <Dialog open={!!qcMeasurement} onOpenChange={(o) => !o && setQcNoteTarget(null)}>
        {qcResult && qcMeasurement && (
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>QC note</DialogTitle>
              <DialogDescription>
                {moleculeLabel(qcResult.molecule_id)} ·{" "}
                {channelLabelById.get(qcMeasurement.channel_id)}
              </DialogDescription>
            </DialogHeader>
            {qcMeasurement.qc_verdict === "not_tested" && (
              <p className="text-sm text-muted-foreground">
                A note goes with a verdict. Choose one first.
              </p>
            )}
            <QcVerdictControl
              campaignId={campaign.id}
              measurement={qcMeasurement}
              resultId={qcResult.id}
              readOnly={false}
            />
          </DialogContent>
        )}
      </Dialog>
    </>
  );
}

// ── Bulk bar ──────────────────────────────────────────────────────────────────

const LINK =
  "text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:pointer-events-none";

/** The bulk bar's ways to tick rows without hunting the # column: every visible row, every row in
 *  the table, or none. Each shows only where it would change the ticks. */
export function SelectLinks({
  visible,
  total,
  allVisibleTicked,
  allTicked,
  anyTicked,
  onSelectVisible,
  onSelectAll,
  onClear,
}: {
  visible: number;
  total: number;
  allVisibleTicked: boolean;
  allTicked: boolean;
  anyTicked: boolean;
  onSelectVisible: () => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  const links = [
    visible > 0 && !allVisibleTicked && visible < total && (
      <button key="visible" type="button" className={LINK} onClick={onSelectVisible}>
        Select all {visible} visible
      </button>
    ),
    total > 0 && !allTicked && (
      <button key="all" type="button" className={LINK} onClick={onSelectAll}>
        Select all {total}
        {visible < total ? " in the table" : ""}
      </button>
    ),
    anyTicked && (
      <button key="clear" type="button" className={LINK} onClick={onClear}>
        Clear selection
      </button>
    ),
  ].filter(Boolean);
  if (links.length === 0) return null;
  return (
    <span className="mr-1 flex items-center gap-2">
      {links.flatMap((link, i) => [
        i > 0 && (
          <span key={`sep-${i}`} aria-hidden="true" className="text-muted-foreground/50">
            ·
          </span>
        ),
        link,
      ])}
    </span>
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
  resultIds: ids,
  hiddenCount,
}: {
  campaignId: string;
  /** The ticked rows. */
  resultIds: string[];
  /** How many of them the filters hide, said in the confirmation. */
  hiddenCount: number;
}) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
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
              {hiddenCount > 0 && `${selectionText(n, hiddenCount)}. `}
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
