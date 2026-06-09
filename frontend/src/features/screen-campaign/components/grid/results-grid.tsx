"use client";

/**
 * ResultsGridV2 — mirrors the layout of the protocol Activity tab.
 *
 * Columns:
 *   - Compound (pinned-left, flex, min 230) — reg# + molecule name
 *   - Structure (130) — <StructureThumbnail size={104}>
 *   - per channel:
 *       - Value (120) — formatMeasurementValue + n=replicate_count + inline hit chip + OVR badge
 *       - Class (90, DR only) — curve-class badge
 *       - Curve (150, DR only) — <DoseResponseSparkline>
 *   - Decision (pinned-right, 160) — <DecisionChipCell>
 *
 * Override editing survives inline in the value cell: an OVR badge + a
 * hover pencil-edit affordance launch the shared OverrideModal.
 *
 * External chip filters wire through CampaignFilterBar helpers. Row expansion
 * and the per-row detail renderer are removed.
 */

import type { ColDef, ColGroupDef, ICellRendererParams, IRowNode } from "ag-grid-community";
import { Pencil } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EntityLink } from "@/shared/components/entity-link";
import { Badge } from "@/shared/components/ui/badge";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { groupBy } from "@/shared/lib/group-by";
import { shortId } from "@/shared/lib/utils";

import {
  CurveClassBadge,
  DoseResponseSparkline,
  useProtocolSummaries,
} from "@/features/screening-assay";
import { type CurveClass, READOUT_NORMALIZATION_LABELS } from "@/features/screening-assay/types";

import { useMoleculesByIds } from "@/features/chemical-registration";
import { useCampaignCurves } from "../../hooks/use-campaign-curves";
import { type CampaignFilters, filtersActive, rowPassesFilters } from "../campaign-filter-bar";
import { OverrideModal } from "../override-modal";

import { CurveExpandDialog, type ExpandedCurve } from "./curve-expand-dialog";
import { DecisionChipCell } from "./decision-chip-cell";

import type {
  CampaignChannelResponse,
  CampaignMeasurementResponse,
  CampaignResponse,
  CampaignResultResponse,
} from "../../types";

import type { CurveSnapshot } from "@/features/screening-assay";
import type { DoseResponseCurveResponse } from "@/shared/lib/api/model";

// ── Row shape ─────────────────────────────────────────────────────────────────

interface RowData {
  result: CampaignResultResponse;
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

// ── Inline hit chip + value cell ─────────────────────────────────────────────

function HitChip({ call }: { call: string | null | undefined }) {
  if (!call) return null;
  const cls =
    call === "hit"
      ? "border-success/40 bg-success/10 text-success"
      : call === "miss"
        ? "border-muted text-muted-foreground"
        : "border-warning/40 bg-warning/10 text-warning";
  return <span className={`ml-1 rounded-sm border px-1 py-px text-[10px] ${cls}`}>{call}</span>;
}

interface CompoundValueCellProps {
  prefix: string;
  value: number | null;
  unit: string | null | undefined;
  replicates: number | null;
  hitCall: string | null | undefined;
  overridden: boolean | undefined;
  overrideReason: string | null | undefined;
  readOnly: boolean;
  onEdit: () => void;
}

function CompoundValueCell({
  prefix,
  value,
  unit,
  replicates,
  hitCall,
  overridden,
  overrideReason,
  readOnly,
  onEdit,
}: CompoundValueCellProps) {
  return (
    <div className="group flex items-center gap-1 py-2">
      <div className="leading-tight">
        <span className="text-sm">
          {prefix}
          {formatMeasurementValue(value)}
          {unit ? ` ${unit}` : ""}
        </span>
        <HitChip call={hitCall} />
        {overridden && (
          <Badge
            variant="outline"
            className="ml-1 text-[10px]"
            title={overrideReason ?? "Manually overridden"}
          >
            OVR
          </Badge>
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

// ── Component ─────────────────────────────────────────────────────────────────

interface ResultsGridV2Props {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  readOnly: boolean;
}

// Row height tuned to fit the search-default 104-px structure thumbnail and
// the wider 220-px sparkline (140 px tall) without clipping. The compound
// stack carries 3-4 lines vertically inside this space.
const ROW_HEIGHT = 170;

export function ResultsGridV2({ campaign, filters, readOnly }: ResultsGridV2Props) {
  const [overrideTarget, setOverrideTarget] = useState<{
    result: CampaignResultResponse;
    channel: CampaignChannelResponse;
    measurement?: CampaignMeasurementResponse;
  } | null>(null);
  const [expandedCurve, setExpandedCurve] = useState<ExpandedCurve | null>(null);

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

  // ── Row data ────────────────────────────────────────────────────────────────

  const rowData = useMemo<RowData[]>(
    () => (campaign.results ?? []).map((r) => ({ result: r })),
    [campaign.results],
  );

  // ── Column defs ─────────────────────────────────────────────────────────────

  const columnDefs = useMemo<(ColDef<RowData> | ColGroupDef<RowData>)[]>(() => {
    const sortedChannels = [...(campaign.channels ?? [])].sort(
      (a, b) => a.display_order - b.display_order,
    );

    const cols: (ColDef<RowData> | ColGroupDef<RowData>)[] = [];

    // 1. Compound (pinned left, flex)
    cols.push({
      headerName: "Compound",
      field: "result.molecule_id",
      pinned: "left",
      width: 180,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<RowData>) => {
        const r = params.data?.result;
        if (!r) return null;
        const m = moleculesById.get(r.molecule_id);
        const label = m?.registration_number ?? shortId(r.molecule_id);
        // Stack id → name → synonyms vertically. Saves horizontal space and
        // makes use of the taller row. Synonyms are deduped against the
        // primary name so we don't repeat the same string.
        const synonyms =
          m?.identifiers
            ?.map((idn) => idn.identifier)
            .filter((s) => !!s && s !== m?.name && s !== m?.registration_number) ?? [];
        const visibleSynonyms = synonyms.slice(0, 3);
        const extra = synonyms.length - visibleSynonyms.length;
        return (
          <div className="flex flex-col py-2 leading-tight">
            <EntityLink
              type="compound"
              id={r.molecule_id}
              label={label}
              className="text-sm font-medium"
            />
            {m?.name && <span className="text-xs text-muted-foreground truncate">{m.name}</span>}
            {visibleSynonyms.map((s) => (
              <span key={s} className="text-[11px] text-muted-foreground truncate">
                {s}
              </span>
            ))}
            {extra > 0 && (
              <span className="text-[10px] text-muted-foreground/70 italic">+{extra} more</span>
            )}
          </div>
        );
      },
    });

    // 2. Structure — matches the search-page default thumbnail size (104px).
    cols.push({
      headerName: "Structure",
      colId: "structure",
      width: 150,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<RowData>) => {
        const r = params.data?.result;
        if (!r) return null;
        const m = moleculesById.get(r.molecule_id);
        const smiles = m?.structure?.smiles ?? null;
        if (!smiles) {
          return <span className="text-muted-foreground">--</span>;
        }
        return (
          <div className="flex h-full items-center justify-center py-1">
            <StructureThumbnail smiles={smiles} size={130} />
          </div>
        );
      },
    });

    // 3. Per-channel grouped by protocol — mirrors the search-results layout
    //    so chemists comparing multiple protocols can scan "NadD-Sumo HTS"
    //    columns separately from "NadD Dose Response".
    const groupedChannels = groupBy(sortedChannels, (ch) => ch.protocol_id);

    for (const [protoId, channels] of groupedChannels) {
      const protoName = protocolNameById.get(protoId) ?? "Protocol";
      const groupChildren: ColDef<RowData>[] = [];
      // Class + Curve columns are emitted only for the FIRST channel of a
      // given (protocol, readout-def) — sibling intercept channels (e.g.
      // EC50 + EC90 on the same Resazurin curve) share the same Hill fit,
      // so duplicating Class and the curve drawing is pure noise. Value
      // columns stay per-channel since each intercept has its own number.
      const seenReadoutDefs = new Set<string>();
      for (const ch of channels) {
        const isDR = ch.source_kind === "dose_response_curve";
        const isFirstForReadout = !seenReadoutDefs.has(ch.readout_definition_id);
        if (isFirstForReadout) {
          seenReadoutDefs.add(ch.readout_definition_id);
        }
        // For non-DR channels the channel header includes the normalization
        // label (e.g. "Raw Data (% Inhibition)") so the chemist sees what
        // formula produced each cell.
        const norm = ch.normalization_applied ?? null;
        const normLabel = norm
          ? (READOUT_NORMALIZATION_LABELS[norm as keyof typeof READOUT_NORMALIZATION_LABELS] ??
            norm)
          : null;
        // Derive a representative unit from the first non-empty measurement
        // on this channel (CampaignChannelResponse has no `unit` field — the
        // unit lives on each measurement, derived per layer at resolve time).
        const sampleUnit =
          (campaign.results ?? [])
            .map((r) => r.measurements?.find((mm) => mm.channel_id === ch.id)?.unit ?? "")
            .find((u) => u && u !== "-") ?? "";
        // Pick which suffix to show — normalization label wins (more
        // chemist-meaningful than a raw "%" unit), else fall back to unit.
        const headerSuffix = normLabel ? ` (${normLabel})` : sampleUnit ? ` (${sampleUnit})` : "";

        groupChildren.push({
          headerName: `${ch.label}${headerSuffix}`,
          colId: `${ch.id}_value`,
          width: 120,
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
              return (
                <span
                  className="font-mono text-muted-foreground"
                  title="ND = Not Determined. The source curve was inactive, the intercept wasn't reached within the tested range, or no candidate is available for this cell."
                >
                  ND
                </span>
              );
            }
            if (q === "excluded") {
              return (
                <span
                  className="text-muted-foreground italic"
                  title="Excluded by hit-criteria filter or channel QC."
                >
                  excluded
                </span>
              );
            }
            const prefix = q === "<" || q === ">" ? `${q} ` : "";
            return (
              <CompoundValueCell
                prefix={prefix}
                value={m.value ?? null}
                unit={m.unit}
                replicates={m.replicate_count ?? null}
                hitCall={m.hit_call}
                overridden={m.is_manual_override}
                overrideReason={m.override_reason}
                readOnly={readOnly}
                onEdit={() => setOverrideTarget({ result: r, channel: ch, measurement: m })}
              />
            );
          },
        });

        if (isDR && isFirstForReadout) {
          groupChildren.push({
            headerName: "Class",
            colId: `${ch.id}_class`,
            width: 90,
            sortable: false,
            cellRenderer: (params: ICellRendererParams<RowData>) => {
              const r = params.data?.result;
              const m = r?.measurements?.find((mm) => mm.channel_id === ch.id);
              const curve = m?.source_curve_id ? curveMap.get(m.source_curve_id) : null;
              return (
                <CurveClassBadge curveClass={(curve?.curve_class as CurveClass | null) ?? null} />
              );
            },
          });

          groupChildren.push({
            headerName: "Curve",
            colId: `${ch.id}_curve`,
            width: 240,
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
                    width={220}
                    height={140}
                    additionalCurves={snapshot.additional_curves ?? null}
                    aggregate={snapshot.aggregate ?? null}
                  />
                </button>
              );
            },
          });
        }
      }

      cols.push({
        headerName: protoName,
        headerClass: "ag-protocol-group-header",
        children: groupChildren,
      });
    }

    // 4. Decision (pinned right) — wider than a bare chip would need so the
    //    inline reason/notes strip in DecisionChipCell has room to breathe.
    cols.push({
      headerName: "Decision",
      colId: "decision",
      pinned: "right",
      width: 240,
      sortable: false,
      cellRenderer: (params: ICellRendererParams<RowData>) => {
        const r = params.data?.result;
        if (!r) return null;
        return <DecisionChipCell campaignId={campaign.id} result={r} readOnly={readOnly} />;
      },
    });

    return cols;
  }, [
    protocolNameById,
    campaign.channels,
    campaign.id,
    campaign.results,
    curveMap,
    moleculesById,
    readOnly,
  ]);

  // ── External (chip) filters ─────────────────────────────────────────────────

  const isExternalFilterPresent = useCallback(() => filtersActive(filters), [filters]);

  const doesExternalFilterPass = useCallback(
    (node: IRowNode<RowData>) => {
      const r = node.data?.result;
      return r ? rowPassesFilters(r, filters) : true;
    },
    [filters],
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
