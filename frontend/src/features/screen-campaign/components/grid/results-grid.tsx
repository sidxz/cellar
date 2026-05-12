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

import { useCallback, useMemo, useState } from "react";
import type {
  ColDef,
  ColGroupDef,
  ICellRendererParams,
  IRowNode,
} from "ag-grid-community";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Pencil } from "lucide-react";

import { Badge } from "@/shared/components/ui/badge";
import { chemVaultTheme } from "@/shared/components/data-grid/ag-grid-theme";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { formatMeasurementValue } from "@/shared/lib/format-number";

import { DoseResponseSparkline } from "@/features/screening-assay/components/dose-response-sparkline";
import { CurveClassBadge } from "@/features/screening-assay/components/curve-class-badge";
import {
  READOUT_NORMALIZATION_LABELS,
  type CurveClass,
  type CurveParams,
} from "@/features/screening-assay/types";
import { useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";

import { useMoleculesByIds } from "../../lib/hooks";
import { useCampaignCurves } from "../../lib/use-campaign-curves";
import { OverrideModal } from "../override-modal";
import {
  type CampaignFilters,
  filtersActive,
  rowPassesFilters,
} from "../campaign-filter-bar";

import { DecisionChipCell } from "./decision-chip-cell";
import { CurveExpandDialog, type ExpandedCurve } from "./curve-expand-dialog";

import type {
  CampaignResponse,
  CampaignResultResponse,
  CampaignChannelResponse,
  CampaignMeasurementResponse,
} from "../../types";

ModuleRegistry.registerModules([AllCommunityModule]);

// ── Row shape ─────────────────────────────────────────────────────────────────

interface RowData {
  result: CampaignResultResponse;
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
  return (
    <span className={`ml-1 rounded-sm border px-1 py-px text-[10px] ${cls}`}>
      {call}
    </span>
  );
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
  const [hover, setHover] = useState(false);
  return (
    <div
      className="flex items-center gap-1 py-2"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
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
      {!readOnly && hover && (
        <button
          type="button"
          onClick={onEdit}
          aria-label="Edit measurement"
          className="ml-1 text-muted-foreground hover:text-foreground"
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

export function ResultsGridV2({
  campaign,
  filters,
  readOnly,
}: ResultsGridV2Props) {
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
        const label = m?.registration_number ?? r.molecule_id.slice(0, 8);
        // Stack id → name → synonyms vertically. Saves horizontal space and
        // makes use of the taller row. Synonyms are deduped against the
        // primary name so we don't repeat the same string.
        const synonyms =
          m?.identifiers
            ?.map((idn) => idn.identifier)
            .filter((s) => !!s && s !== m?.name && s !== m?.registration_number) ??
          [];
        const visibleSynonyms = synonyms.slice(0, 3);
        const extra = synonyms.length - visibleSynonyms.length;
        return (
          <div className="flex flex-col py-2 leading-tight">
            <span className="font-medium text-sm">{label}</span>
            {m?.name && (
              <span className="text-xs text-muted-foreground truncate">
                {m.name}
              </span>
            )}
            {visibleSynonyms.map((s) => (
              <span key={s} className="text-[11px] text-muted-foreground truncate">
                {s}
              </span>
            ))}
            {extra > 0 && (
              <span className="text-[10px] text-muted-foreground/70 italic">
                +{extra} more
              </span>
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
    const groupedChannels = new Map<string, typeof sortedChannels>();
    for (const ch of sortedChannels) {
      const arr = groupedChannels.get(ch.protocol_id) ?? [];
      arr.push(ch);
      groupedChannels.set(ch.protocol_id, arr);
    }

    for (const [protoId, channels] of groupedChannels) {
      const protoName = protocolNameById.get(protoId) ?? "Protocol";
      const groupChildren: ColDef<RowData>[] = [];
      for (const ch of channels) {
        const isDR = ch.source_kind === "dose_response_curve";
        // For non-DR channels the channel header includes the normalization
        // label (e.g. "Raw Data (% Inhibition)") so the chemist sees what
        // formula produced each cell.
        const norm = ch.normalization_applied ?? null;
        const normLabel = norm
          ? READOUT_NORMALIZATION_LABELS[
              norm as keyof typeof READOUT_NORMALIZATION_LABELS
            ] ?? norm
          : null;
        // Derive a representative unit from the first non-empty measurement
        // on this channel (CampaignChannelResponse has no `unit` field — the
        // unit lives on each measurement, derived per layer at resolve time).
        const sampleUnit =
          (campaign.results ?? [])
            .map(
              (r) =>
                r.measurements?.find((mm) => mm.channel_id === ch.id)?.unit ??
                "",
            )
            .find((u) => u && u !== "-") ?? "";
        // Pick which suffix to show — normalization label wins (more
        // chemist-meaningful than a raw "%" unit), else fall back to unit.
        const headerSuffix = normLabel
          ? ` (${normLabel})`
          : sampleUnit
            ? ` (${sampleUnit})`
            : "";

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
            if (q === "nd" || q === "excluded") {
              return <span className="text-muted-foreground italic">{q}</span>;
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
                onEdit={() =>
                  setOverrideTarget({ result: r, channel: ch, measurement: m })
                }
              />
            );
          },
        });

        if (isDR) {
          groupChildren.push({
            headerName: "Class",
            colId: `${ch.id}_class`,
            width: 90,
            sortable: false,
            cellRenderer: (params: ICellRendererParams<RowData>) => {
              const r = params.data?.result;
              const m = r?.measurements?.find((mm) => mm.channel_id === ch.id);
              const curve = m?.source_curve_id
                ? curveMap.get(m.source_curve_id)
                : null;
              return (
                <CurveClassBadge
                  curveClass={(curve?.curve_class as CurveClass | null) ?? null}
                />
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
              const curve = m?.source_curve_id
                ? curveMap.get(m.source_curve_id)
                : null;
              if (!r || !curve) {
                return <span className="text-muted-foreground">--</span>;
              }
              const curveParams: CurveParams = {
                top: curve.top,
                bottom: curve.bottom,
                hill_slope: curve.hill_slope,
                fitted_value: curve.fitted_value,
                r_squared: curve.r_squared,
              };
              const dataPoints =
                (curve.raw_data as Array<{ x: number; y: number }> | null) ??
                null;
              const mol = moleculesById.get(r.molecule_id);
              const moleculeLabel =
                mol?.registration_number ?? r.molecule_id.slice(0, 8);
              return (
                <button
                  type="button"
                  className="block rounded hover:bg-muted/50 focus:bg-muted/60 focus:outline-none"
                  title="Click to expand"
                  onClick={() =>
                    setExpandedCurve({
                      fitted_value: curve.fitted_value,
                      top: curve.top,
                      bottom: curve.bottom,
                      hill_slope: curve.hill_slope,
                      r_squared: curve.r_squared,
                      curve_class:
                        (curve.curve_class as CurveClass | null) ?? null,
                      raw_data: dataPoints,
                      unit: m?.unit ?? null,
                      moleculeLabel,
                      channelLabel: ch.label,
                    })
                  }
                >
                  <DoseResponseSparkline
                    params={curveParams}
                    dataPoints={dataPoints}
                    curveClass={(curve.curve_class as CurveClass | null) ?? null}
                    width={220}
                    height={140}
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
        return (
          <DecisionChipCell
            campaignId={campaign.id}
            result={r}
            readOnly={readOnly}
          />
        );
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

  const isExternalFilterPresent = useCallback(
    () => filtersActive(filters),
    [filters],
  );

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
      <div style={{ height: 600, width: "100%" }}>
        <AgGridReact<RowData>
          theme={chemVaultTheme}
          rowData={rowData}
          columnDefs={columnDefs}
          defaultColDef={{ sortable: true, resizable: true, minWidth: 80 }}
          rowHeight={ROW_HEIGHT}
          getRowId={(p) => p.data.result.id}
          isExternalFilterPresent={isExternalFilterPresent}
          doesExternalFilterPass={doesExternalFilterPass}
          suppressCellFocus
          animateRows={false}
        />
      </div>

      {overrideTarget && (
        <OverrideModal
          open
          onClose={() => setOverrideTarget(null)}
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
