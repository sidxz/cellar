"use client";

/**
 * ResultsGridV2 — V2 redesign (Phase 3, Task 3.8).
 *
 * AG Grid view with:
 *   - pinned-left chevron + molecule columns
 *   - one column-group per channel: { MeasurementCell, CampaignDoseResponseCell }
 *   - pinned-right decision chip column
 *   - row expansion via isFullWidthRow + RowDetailRenderer
 *   - external chip filters wired through CampaignFilterBar helpers
 *   - OverrideModal mounted controlled by local state
 *
 * Note: an extracted `override-modal.tsx` does not yet exist, so this file
 * inlines a minimal copy of the modal used by the legacy `results-grid.tsx`.
 * If/when the modal is extracted, swap the inline copy for the shared one.
 */

import { useMemo, useState, useCallback, useEffect } from "react";
import type {
  ColDef,
  ColGroupDef,
  ICellRendererParams,
  IRowNode,
  IsFullWidthRowParams,
  RowClassParams,
  RowHeightParams,
} from "ag-grid-community";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { ChevronRight, ChevronDown } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";

import { chemVaultTheme } from "@/shared/components/data-grid/ag-grid-theme";
import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { useOverrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch } from "@/shared/lib/api/campaigns/campaigns";

import { campaignKeys, useMoleculesByIds } from "../../lib/hooks";
import { useCampaignCurves } from "../../lib/use-campaign-curves";
import {
  type CampaignFilters,
  filtersActive,
  rowPassesFilters,
} from "../campaign-filter-bar";

import { CampaignDoseResponseCell } from "./dose-response-cell";
import { MeasurementCell } from "./measurement-cell";
import { DecisionChipCell } from "./decision-chip-cell";
import { RowDetailRenderer } from "./row-detail-renderer";

import type {
  CampaignResponse,
  CampaignResultResponse,
  CampaignChannelResponse,
  CampaignMeasurementResponse,
} from "../../types";

ModuleRegistry.registerModules([AllCommunityModule]);

// ── Row shape ─────────────────────────────────────────────────────────────────

interface RowData {
  /** Stable per-row id (`<resultId>` for main, `<resultId>:detail` for expansion). */
  id: string;
  result: CampaignResultResponse;
  campaign: CampaignResponse;
  /** True for the full-width expansion row immediately following a main row. */
  isDetail: boolean;
}

const COLLAPSED_HEIGHT = 60;
const EXPANDED_HEIGHT = 260;

// ── Component ─────────────────────────────────────────────────────────────────

interface ResultsGridV2Props {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  readOnly: boolean;
}

export function ResultsGridV2({
  campaign,
  filters,
  readOnly,
}: ResultsGridV2Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [overrideTarget, setOverrideTarget] = useState<{
    result: CampaignResultResponse;
    channel: CampaignChannelResponse;
    measurement?: CampaignMeasurementResponse;
  } | null>(null);

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // ── Bulk fetches ────────────────────────────────────────────────────────────

  const moleculeIds = useMemo(
    () => [...new Set((campaign.results ?? []).map((r) => r.molecule_id))],
    [campaign.results],
  );
  const { data: moleculesPage } = useMoleculesByIds(moleculeIds);
  const moleculeById = useMemo(
    () => new Map((moleculesPage?.items ?? []).map((m) => [m.id, m] as const)),
    [moleculesPage],
  );

  const curvesQuery = useCampaignCurves(campaign);
  const curveMap = curvesQuery.data ?? new Map();

  // ── Row data (main rows + detail rows) ──────────────────────────────────────

  const rowData = useMemo<RowData[]>(() => {
    const rows: RowData[] = [];
    for (const r of campaign.results ?? []) {
      rows.push({ id: r.id, result: r, campaign, isDetail: false });
      if (expanded.has(r.id)) {
        rows.push({
          id: `${r.id}:detail`,
          result: r,
          campaign,
          isDetail: true,
        });
      }
    }
    return rows;
  }, [campaign, expanded]);

  // ── Column defs ─────────────────────────────────────────────────────────────

  const columnDefs = useMemo<(ColDef<RowData> | ColGroupDef<RowData>)[]>(() => {
    const sortedChannels = [...(campaign.channels ?? [])].sort(
      (a, b) => a.display_order - b.display_order,
    );

    const channelGroups: ColGroupDef<RowData>[] = sortedChannels.map((ch) => ({
      headerName: ch.label,
      children: [
        {
          colId: `${ch.id}:value`,
          headerName: "Value",
          width: 160,
          cellRenderer: (params: ICellRendererParams<RowData>) => {
            const r = params.data?.result;
            if (!r) return null;
            const m = r.measurements?.find((mm) => mm.channel_id === ch.id);
            return (
              <MeasurementCell
                measurement={m}
                readOnly={readOnly}
                onEdit={() =>
                  setOverrideTarget({ result: r, channel: ch, measurement: m })
                }
              />
            );
          },
        },
        {
          colId: `${ch.id}:plot`,
          headerName: "Curve",
          width: 240,
          cellRenderer: (params: ICellRendererParams<RowData>) => {
            const r = params.data?.result;
            if (!r) return null;
            const m = r.measurements?.find((mm) => mm.channel_id === ch.id);
            return (
              <CampaignDoseResponseCell measurement={m} curveMap={curveMap} />
            );
          },
        },
      ],
    }));

    const defs: (ColDef<RowData> | ColGroupDef<RowData>)[] = [
      {
        colId: "__expand__",
        headerName: "",
        width: 36,
        minWidth: 36,
        pinned: "left",
        sortable: false,
        resizable: false,
        cellRenderer: (params: ICellRendererParams<RowData>) => {
          const r = params.data?.result;
          if (!r) return null;
          const isOpen = expanded.has(r.id);
          return (
            <button
              type="button"
              className="flex h-full w-full items-center justify-center text-muted-foreground hover:text-foreground"
              onClick={() => toggleExpand(r.id)}
              aria-label={isOpen ? "Collapse row" : "Expand row"}
            >
              {isOpen ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>
          );
        },
      },
      {
        colId: "__molecule__",
        headerName: "Compound",
        pinned: "left",
        width: 220,
        cellRenderer: (params: ICellRendererParams<RowData>) => {
          const r = params.data?.result;
          if (!r) return null;
          const mol = moleculeById.get(r.molecule_id);
          // Reg number → name → ellipsis. NEVER show a UUID.
          const label = mol?.registration_number ?? mol?.name ?? "…";
          const smiles = mol?.structure?.smiles ?? null;
          return (
            <div className="flex items-center gap-2 py-1">
              <MoleculeThumbnail smiles={smiles} size="sm" fallback={label} />
              <span className="font-mono text-xs">{label}</span>
            </div>
          );
        },
      },
      ...channelGroups,
      {
        colId: "__decision__",
        headerName: "Decision",
        pinned: "right",
        width: 160,
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
      },
    ];

    return defs;
  }, [
    campaign.channels,
    campaign.id,
    curveMap,
    expanded,
    moleculeById,
    readOnly,
    toggleExpand,
  ]);

  // ── Row height + full-width row wiring ──────────────────────────────────────

  const getRowHeight = useCallback(
    (params: RowHeightParams<RowData>): number | undefined => {
      return params.data?.isDetail ? EXPANDED_HEIGHT : COLLAPSED_HEIGHT;
    },
    [],
  );

  const isFullWidthRow = useCallback(
    (params: IsFullWidthRowParams<RowData>) => !!params.rowNode.data?.isDetail,
    [],
  );

  const getRowClass = useCallback((params: RowClassParams<RowData>) => {
    return params.data?.isDetail ? "ag-row-detail" : "";
  }, []);

  // ── External (chip) filters ─────────────────────────────────────────────────

  const isExternalFilterPresent = useCallback(
    () => filtersActive(filters),
    [filters],
  );

  const doesExternalFilterPass = useCallback(
    (node: IRowNode<RowData>) => {
      const data = node.data;
      if (!data) return true;
      // Detail rows always pass — they follow their parent.
      if (data.isDetail) return true;
      return rowPassesFilters(data.result, filters);
    },
    [filters],
  );

  // ── Empty state ─────────────────────────────────────────────────────────────

  if (!campaign.results || campaign.results.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        No compounds — add some via the compound list pane.
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
          getRowHeight={getRowHeight}
          isFullWidthRow={isFullWidthRow}
          fullWidthCellRenderer={RowDetailRenderer}
          getRowClass={getRowClass}
          getRowId={(p) => p.data.id}
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
    </>
  );
}

// ── Override modal (inlined copy of the legacy modal) ─────────────────────────
// TODO: extract to ../override-modal.tsx once a shared file lands.

interface OverrideModalProps {
  open: boolean;
  onClose: () => void;
  campaignId: string;
  result: CampaignResultResponse;
  channel: CampaignChannelResponse;
  measurement?: CampaignMeasurementResponse;
}

function HitCallChip({ hitCall }: { hitCall: string }) {
  const HIT_COLORS: Record<string, string> = {
    hit: "bg-orange-100 text-orange-800",
    confirmed_hit: "bg-orange-200 text-orange-900",
    inactive: "bg-blue-50 text-blue-700",
    inconclusive: "bg-gray-100 text-gray-600",
  };
  const cls = HIT_COLORS[hitCall] ?? "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}
    >
      {hitCall.replace("_", " ")}
    </span>
  );
}

function OverrideModal({
  open,
  onClose,
  campaignId,
  result,
  channel,
  measurement,
}: OverrideModalProps) {
  const qc = useQueryClient();
  const [value, setValue] = useState(String(measurement?.value ?? ""));
  const [qualifier, setQualifier] = useState(
    measurement?.value_qualifier ?? "=",
  );
  const [unit, setUnit] = useState(measurement?.unit ?? "");
  // Radix Select forbids empty-string item values, so use "none" as sentinel.
  const [hitCall, setHitCall] = useState<string>(
    (measurement?.hit_call as string | undefined) ?? "none",
  );
  const [reason, setReason] = useState(measurement?.override_reason ?? "");

  const isPlaceholderQualifier = qualifier === "nd" || qualifier === "excluded";

  // B7: when qualifier flips to ND/excluded, clear value + unit; backend
  // accepts empty unit for these qualifiers and forces value to null.
  useEffect(() => {
    if (isPlaceholderQualifier) {
      setValue("");
      setUnit("");
      setHitCall("none");
    }
  }, [isPlaceholderQualifier]);

  // B8: reason required when override changes the auto-resolved value.
  const valueDiffersFromAuto = (() => {
    if (!measurement) return true;
    const numValue = value !== "" ? Number(value) : null;
    return (
      numValue !== (measurement.value ?? null) ||
      qualifier !== measurement.value_qualifier ||
      (!isPlaceholderQualifier && unit !== measurement.unit) ||
      hitCall !== ((measurement.hit_call as string | undefined) ?? "none")
    );
  })();
  const reasonRequired = valueDiffersFromAuto;
  const reasonOk = !reasonRequired || reason.trim().length > 0;
  const unitOk = isPlaceholderQualifier || unit.trim().length > 0;

  const overrideMutation =
    useOverrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch(
      {
        mutation: {
          onSuccess: () => {
            void qc.invalidateQueries({
              queryKey: campaignKeys.detail(campaignId),
            });
            onClose();
          },
        },
      },
    );

  const handleSubmit = () => {
    if (!reasonOk || !unitOk) return;
    overrideMutation.mutate({
      campaignId,
      resultId: result.id,
      channelId: channel.id,
      data: {
        value: isPlaceholderQualifier
          ? null
          : value !== ""
            ? Number(value)
            : undefined,
        value_qualifier: qualifier,
        unit: isPlaceholderQualifier ? "" : unit,
        hit_call:
          isPlaceholderQualifier || hitCall === "none" ? undefined : hitCall,
        reason: reason.trim() || undefined,
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Override Cell — {channel.label}</DialogTitle>
        </DialogHeader>

        {measurement && (
          <div className="rounded bg-muted/50 p-3 text-sm space-y-1 mb-2">
            <p className="text-xs text-muted-foreground font-medium">
              Auto-resolved value
            </p>
            <p>
              {measurement.value_qualifier !== "="
                ? measurement.value_qualifier
                : ""}
              {formatMeasurementValue(measurement.value)} {measurement.unit}
              {measurement.hit_call && (
                <span className="ml-2">
                  <HitCallChip hitCall={measurement.hit_call as string} />
                </span>
              )}
              {measurement.is_manual_override && (
                <Badge variant="secondary" className="ml-2 text-xs">
                  overridden
                </Badge>
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              {measurement.protocol_name_snapshot} v
              {measurement.protocol_version_snapshot}
            </p>
            {measurement.override_reason && (
              <p className="text-xs text-muted-foreground italic">
                Previous reason: {measurement.override_reason}
              </p>
            )}
          </div>
        )}

        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label>Qualifier</Label>
              <Select value={qualifier} onValueChange={setQualifier}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[
                    { v: "=", label: "= (exact)" },
                    { v: "<", label: "< (less than)" },
                    { v: ">", label: "> (greater than)" },
                    { v: "nd", label: "nd (not determined)" },
                    { v: "excluded", label: "excluded" },
                  ].map((q) => (
                    <SelectItem key={q.v} value={q.v}>
                      {q.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Value</Label>
              <Input
                type="number"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="0.00"
                disabled={isPlaceholderQualifier}
              />
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                placeholder="µM"
                disabled={isPlaceholderQualifier}
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label>Hit call (optional)</Label>
            <Select
              value={hitCall}
              onValueChange={setHitCall}
              disabled={isPlaceholderQualifier}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {["hit", "miss", "inconclusive"].map((h) => (
                  <SelectItem key={h} value={h}>
                    {h}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>
              Reason{" "}
              {reasonRequired ? (
                <span className="text-destructive">*</span>
              ) : (
                <span className="text-muted-foreground text-xs">
                  (optional)
                </span>
              )}
            </Label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                reasonRequired
                  ? "Required — why are you changing the auto-resolved value?"
                  : "Optional rationale"
              }
            />
            {reasonRequired && !reasonOk && (
              <p className="text-xs text-destructive">
                Required: explain the deviation for audit trail.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={overrideMutation.isPending || !reasonOk || !unitOk}
          >
            {overrideMutation.isPending ? "Saving..." : "Save Override"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
