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
 * OverrideModal is shared — imported from ../override-modal.tsx.
 */

import { useMemo, useState, useCallback } from "react";
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
import { chemVaultTheme } from "@/shared/components/data-grid/ag-grid-theme";
import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";

import { useMoleculesByIds } from "../../lib/hooks";
import { OverrideModal } from "../override-modal";
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

const EXPANDED_HEIGHT = 260;
const COLLAPSED_HEIGHT = 60;

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
      // 1. Chevron (pinned left)
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
      // 2. Molecule (pinned left)
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
      // 3. Channel groups
      ...channelGroups,
      // 4. Decision (pinned right)
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


