"use client";

/**
 * ResultsGrid — Task 8.4
 *
 * AG Grid pivot-style view of campaign results × channels.
 *
 * Columns:
 *   pinned-left: molecule (primary_id / reg number)
 *   per channel: value + qualifier + hit_call chip + override badge
 *   pinned-right: decision chip
 *
 * Row click → sets selectedResultId for the decision panel.
 * Cell click on a channel column → opens OverrideModal.
 */

import { useMemo, useState, useCallback } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AllCommunityModule, ModuleRegistry } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { ChevronRight } from "lucide-react";

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

import { useOverrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys, useMoleculesByIds } from "../lib/hooks";
import { useQueryClient } from "@tanstack/react-query";
import type {
  CampaignResponse,
  CampaignResultResponse,
  CampaignMeasurementResponse,
  CampaignChannelResponse,
} from "../types";

ModuleRegistry.registerModules([AllCommunityModule]);

// ── Decision chip ─────────────────────────────────────────────────────────────

const DECISION_COLORS: Record<string, string> = {
  selected: "bg-green-100 text-green-800 border-green-200",
  deferred: "bg-yellow-100 text-yellow-800 border-yellow-200",
  rejected: "bg-red-100 text-red-800 border-red-200",
  pending: "bg-gray-100 text-gray-600 border-gray-200",
};

function DecisionChip({ decision }: { decision: string }) {
  const cls = DECISION_COLORS[decision] ?? DECISION_COLORS.pending;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}>
      {decision}
    </span>
  );
}

// ── Hit call chip ─────────────────────────────────────────────────────────────

const HIT_COLORS: Record<string, string> = {
  hit: "bg-orange-100 text-orange-800",
  confirmed_hit: "bg-orange-200 text-orange-900",
  inactive: "bg-blue-50 text-blue-700",
  inconclusive: "bg-gray-100 text-gray-600",
};

function HitCallChip({ hitCall }: { hitCall: string }) {
  const cls = HIT_COLORS[hitCall] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}>
      {hitCall.replace("_", " ")}
    </span>
  );
}

// ── Override modal ─────────────────────────────────────────────────────────────

interface OverrideModalProps {
  open: boolean;
  onClose: () => void;
  campaignId: string;
  result: CampaignResultResponse;
  channel: CampaignChannelResponse;
  measurement?: CampaignMeasurementResponse;
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
  const [qualifier, setQualifier] = useState(measurement?.value_qualifier ?? "=");
  const [unit, setUnit] = useState(measurement?.unit ?? "");
  const [hitCall, setHitCall] = useState<string>(measurement?.hit_call ?? "");

  const overrideMutation =
    useOverrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch({
      mutation: {
        onSuccess: () => {
          void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
          onClose();
        },
      },
    });

  const handleSubmit = () => {
    overrideMutation.mutate({
      campaignId,
      resultId: result.id,
      channelId: channel.id,
      data: {
        value: value !== "" ? Number(value) : undefined,
        value_qualifier: qualifier,
        unit,
        hit_call: hitCall || undefined,
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
            <p className="text-xs text-muted-foreground font-medium">Auto-resolved value</p>
            <p>
              {measurement.value_qualifier}
              {measurement.value} {measurement.unit}
              {measurement.hit_call && (
                <span className="ml-2"><HitCallChip hitCall={measurement.hit_call as string} /></span>
              )}
              {measurement.is_manual_override && (
                <Badge variant="secondary" className="ml-2 text-xs">overridden</Badge>
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              {measurement.protocol_name_snapshot} v{measurement.protocol_version_snapshot}
            </p>
          </div>
        )}

        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label>Qualifier</Label>
              <Select value={qualifier} onValueChange={setQualifier}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[
                    { v: "=", label: "= (exact)" },
                    { v: "<", label: "< (less than)" },
                    { v: ">", label: "> (greater than)" },
                    { v: "nd", label: "nd (not determined)" },
                    { v: "excluded", label: "excluded" },
                  ].map((q) => (
                    <SelectItem key={q.v} value={q.v}>{q.label}</SelectItem>
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
              />
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                placeholder="µM"
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label>Hit call (optional)</Label>
            <Select value={hitCall} onValueChange={setHitCall}>
              <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">None</SelectItem>
                {["hit", "miss", "inconclusive"].map((h) => (
                  <SelectItem key={h} value={h}>{h}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={handleSubmit} disabled={overrideMutation.isPending}>
            {overrideMutation.isPending ? "Saving..." : "Save Override"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Row type ──────────────────────────────────────────────────────────────────

interface ResultRow {
  result: CampaignResultResponse;
  /** molecule_id used as primary display (full molecule lookup is a TODO) */
  molecule_id: string;
  decision: string;
  /** channel_id → measurement */
  cells: Record<string, CampaignMeasurementResponse | undefined>;
}

// ── Main grid ─────────────────────────────────────────────────────────────────

interface ResultsGridProps {
  campaign: CampaignResponse;
  selectedResultId: string | null;
  onRowSelect: (result: CampaignResultResponse | null) => void;
  /** When true, disables cell overrides and row selection (closed/superseded view). */
  readOnly?: boolean;
}

export function ResultsGrid({ campaign, selectedResultId, onRowSelect, readOnly = false }: ResultsGridProps) {
  const [overrideTarget, setOverrideTarget] = useState<{
    result: CampaignResultResponse;
    channel: CampaignChannelResponse;
    measurement?: CampaignMeasurementResponse;
  } | null>(null);

  // Bulk-fetch molecule identifiers so we can show registration_number (CVT-XXXXXX)
  // instead of a raw UUID in the compound column.
  const moleculeIds = useMemo(
    () => [...new Set(campaign.results.map((r) => r.molecule_id))],
    [campaign.results],
  );
  const { data: moleculesPage } = useMoleculesByIds(moleculeIds);
  const moleculeById = useMemo(
    () =>
      new Map(
        (moleculesPage?.items ?? []).map((m) => [m.id, m]),
      ),
    [moleculesPage],
  );

  const rowData = useMemo<ResultRow[]>(
    () =>
      campaign.results.map((r) => ({
        result: r,
        molecule_id: r.molecule_id,
        decision: r.decision,
        cells: Object.fromEntries(
          r.measurements.map((m) => [m.channel_id, m]),
        ),
      })),
    [campaign.results],
  );

  const columnDefs = useMemo<ColDef<ResultRow>[]>(() => {
    const sorted = [...campaign.channels].sort(
      (a, b) => a.display_order - b.display_order,
    );

    const channelCols: ColDef<ResultRow>[] = sorted.map((ch) => ({
      colId: ch.id,
      headerName: ch.label,
      width: 160,
      cellRenderer: (params: ICellRendererParams<ResultRow>) => {
        if (!params.data) return null;
        const m = params.data.cells[ch.id];
        if (!m) return <span className="text-muted-foreground text-xs">—</span>;
        return (
          <div className="flex items-center gap-1 text-xs">
            <span>
              {m.value_qualifier !== "=" ? m.value_qualifier : ""}
              {m.value != null ? String(m.value) : "ND"}
              {m.unit && m.unit !== "-" ? <span className="text-muted-foreground ml-0.5">{m.unit}</span> : null}
            </span>
            {m.hit_call && <HitCallChip hitCall={m.hit_call as string} />}
            {m.is_manual_override && (
              <Badge variant="secondary" className="text-[9px] px-1 py-0">OVR</Badge>
            )}
            {!readOnly && (
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5 opacity-0 group-hover:opacity-100 ml-auto"
                onClick={(e) => {
                  e.stopPropagation();
                  const result = params.data!.result;
                  setOverrideTarget({ result, channel: ch, measurement: m });
                }}
              >
                <ChevronRight className="h-3 w-3" />
              </Button>
            )}
          </div>
        );
      },
    }));

    return [
      {
        colId: "__molecule__",
        headerName: "Compound",
        pinned: "left" as const,
        width: 180,
        cellClass: "font-mono text-xs",
        cellRenderer: (params: ICellRendererParams<ResultRow>) => {
          if (!params.data) return null;
          const isSelected = params.data.result.id === selectedResultId;
          const mol = moleculeById.get(params.data.molecule_id);
          const label =
            mol?.registration_number ??
            mol?.name ??
            `${params.data.molecule_id.slice(0, 8)}…`;
          return (
            <span className={`font-mono text-xs${isSelected ? " font-semibold text-primary" : ""}`}>
              {label}
            </span>
          );
        },
      },
      ...channelCols,
      {
        colId: "__decision__",
        headerName: "Decision",
        pinned: "right" as const,
        width: 110,
        cellRenderer: (params: ICellRendererParams<ResultRow>) => {
          if (!params.data) return null;
          return <DecisionChip decision={params.data.decision} />;
        },
      },
    ];
  // selectedResultId and moleculeById intentional: re-renders when row is selected
  // or when molecule identifiers load.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaign.channels, selectedResultId, moleculeById]);

  const handleRowClicked = useCallback(
    (event: { data?: ResultRow }) => {
      if (!event.data || readOnly) return;
      onRowSelect(
        event.data.result.id === selectedResultId ? null : event.data.result,
      );
    },
    [onRowSelect, selectedResultId, readOnly],
  );

  if (rowData.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
        No compounds — add some via the compound list pane.
      </div>
    );
  }

  return (
    <>
      <div style={{ height: "100%", width: "100%" }} className="group">
        <AgGridReact<ResultRow>
          theme={chemVaultTheme}
          rowData={rowData}
          columnDefs={columnDefs}
          defaultColDef={{ sortable: true, resizable: true, minWidth: 80 }}
          onRowClicked={handleRowClicked}
          rowClass="cursor-pointer"
          getRowId={(p) => p.data.result.id}
          animateRows={false}
          suppressCellFocus
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
