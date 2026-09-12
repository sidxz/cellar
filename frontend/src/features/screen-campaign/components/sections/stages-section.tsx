"use client";

/**
 * StagesSection — Task 14.
 *
 * Uppercase-header section block (mirrors ChannelsSection) that renders the
 * campaign's hit-stage funnel as a row of tiles — "All <n>" plus one tile
 * per stage sorted by display_order. Each tile shows the hit count as the
 * big number, the population it was drawn from ("of N"), the hit rate, and
 * the stage's criteria as a one-line summary, all tallied from
 * `stage_outcomes` regardless of selection. A child stage's tile carries
 * "↳ after <parent name>" as its eyebrow. Selecting a tile is purely a
 * notify-parent affordance (`onSelectStage`).
 *
 * The panel below the tabs shows the *selected* stage's criteria (read-only
 * rows) plus its parent and, when editable, a MoreHorizontal menu opening
 * the same StagePopoverForm used for "+ Stage". Selecting "All" shows
 * nothing below the tabs.
 */

import { useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { MoreHorizontal, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { protocolColorById } from "../../lib/protocol-colors";
import { tallyStage } from "../../lib/stage-outcomes";
import type { CampaignResponse, StageCriterionDTO } from "../../types";
import { StagePopoverForm } from "../stage-popover";

// ── Props ─────────────────────────────────────────────────────────────────────

interface StagesSectionProps {
  campaign: CampaignResponse;
  selectedStageId: string | null;
  onSelectStage: (id: string | null) => void;
  readOnly: boolean;
}

// ── Style constants ───────────────────────────────────────────────────────────
// Same header style as ChannelsSection's "Readouts" heading, and the same
// "+ X" pill used for "+ Readout" / "Mirror protocol".

const SECTION_HEADING = "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

const ADD_PILL =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors";

const TILE_BASE =
  "grid min-w-[160px] gap-0.5 rounded-lg border px-3.5 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:outline-primary";
const TILE_INACTIVE = "bg-muted/50 border-border hover:border-primary/40";
const TILE_ACTIVE = "bg-primary/10 border-primary ring-1 ring-inset ring-primary";

// ── Operator formatting ───────────────────────────────────────────────────────

const OPERATOR_SYMBOLS: Record<string, string> = {
  lt: "<",
  lte: "<=",
  gt: ">",
  gte: ">=",
};

function criterionValueText(c: StageCriterionDTO): string {
  if (c.operator === "between" && Array.isArray(c.value)) {
    const [lo, hi] = c.value;
    return `${lo} – ${hi}`;
  }
  const symbol = OPERATOR_SYMBOLS[c.operator] ?? c.operator;
  const value = Array.isArray(c.value) ? c.value.join(", ") : c.value;
  return `${symbol} ${value}`;
}

// ── Main component ────────────────────────────────────────────────────────────

export function StagesSection({
  campaign,
  selectedStageId,
  onSelectStage,
  readOnly,
}: StagesSectionProps) {
  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  const stages = useMemo(
    () => [...(campaign.stages ?? [])].sort((a, b) => a.display_order - b.display_order),
    [campaign.stages],
  );
  const stageById = useMemo(() => new Map(stages.map((s) => [s.id, s] as const)), [stages]);
  const results = campaign.results ?? [];
  const tallies = useMemo(
    () => new Map(stages.map((s) => [s.id, tallyStage(results, s.id)] as const)),
    [stages, results],
  );

  // Protocol name lookup for criteria rows — same rationale as ChannelsSection:
  // resolve any protocol referenced by a channel regardless of project scope.
  const { data: protocolSummaries } = useProtocolSummaries(undefined, { includeAll: true });
  const protocolNameById = useMemo(
    () => new Map((protocolSummaries ?? []).map((p) => [p.id, p.name] as const)),
    [protocolSummaries],
  );
  const channelById = useMemo(
    () => new Map((campaign.channels ?? []).map((c) => [c.id, c] as const)),
    [campaign.channels],
  );
  const colorByProtocol = useMemo(
    () => protocolColorById(campaign.channels ?? []),
    [campaign.channels],
  );
  // Unit lives on measurements, not the channel/criterion — same derivation
  // as stage-popover.tsx's channelOptions.
  const unitForChannel = (channelId: string) =>
    results
      .map((r) => r.measurements?.find((m) => m.channel_id === channelId)?.unit ?? "")
      .find((u) => u && u !== "-");
  const criterionText = (c: StageCriterionDTO) => {
    const unit = unitForChannel(c.channel_id);
    return `${channelById.get(c.channel_id)?.label ?? "Unknown readout"} ${criterionValueText(c)}${unit ? ` ${unit}` : ""}`;
  };

  const selectedStage = selectedStageId ? (stageById.get(selectedStageId) ?? null) : null;
  const selectedParent = selectedStage?.parent_stage_id
    ? (stageById.get(selectedStage.parent_stage_id) ?? null)
    : null;

  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Hit stages</h2>
        {!readOnly && (
          <Popover open={addOpen} onOpenChange={setAddOpen}>
            <PopoverTrigger asChild>
              <button type="button" className={ADD_PILL}>
                <Plus className="h-3 w-3" /> Stage
              </button>
            </PopoverTrigger>
            <PopoverContent
              align="end"
              className="w-[500px] p-4 max-h-[var(--radix-popover-content-available-height)] overflow-y-auto"
            >
              <h4 className="text-sm font-semibold mb-3">Add stage</h4>
              <StagePopoverForm
                campaignId={campaign.id}
                campaign={campaign}
                onClose={() => setAddOpen(false)}
              />
            </PopoverContent>
          </Popover>
        )}
      </div>

      <div className="flex flex-wrap items-stretch gap-2.5">
        <button
          type="button"
          onClick={() => onSelectStage(null)}
          className={`${TILE_BASE} min-w-[120px] ${selectedStageId == null ? TILE_ACTIVE : TILE_INACTIVE}`}
        >
          <span className="text-sm font-semibold leading-tight">All</span>
          <span className="text-2xl font-semibold leading-none tabular-nums">{results.length}</span>
        </button>

        {stages.map((stage) => {
          const parent = stage.parent_stage_id ? stageById.get(stage.parent_stage_id) : undefined;
          const tally = tallies.get(stage.id);
          const hit = tally?.hit ?? 0;
          const population = tally?.population ?? 0;
          const summary = stage.criteria.map(criterionText).join(" · ");
          return (
            <button
              key={stage.id}
              type="button"
              onClick={() => onSelectStage(stage.id)}
              className={`${TILE_BASE} ${selectedStageId === stage.id ? TILE_ACTIVE : TILE_INACTIVE}`}
            >
              {parent && (
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  ↳ after {parent.name}
                </span>
              )}
              <span className="text-sm font-semibold leading-tight">{stage.name}</span>
              <span className="flex items-baseline gap-1.5 tabular-nums">
                <span className="text-2xl font-semibold leading-none">{hit}</span>
                <span className="text-xs text-muted-foreground">of {population}</span>
                {population > 0 && (
                  <span className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
                    {Math.round((hit / population) * 100)}%
                  </span>
                )}
              </span>
              {summary && (
                <span
                  className="mt-0.5 max-w-[240px] truncate font-mono text-[11px] text-muted-foreground"
                  title={summary}
                >
                  {summary}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {selectedStage && (
        <div className="mt-3 rounded-md border bg-card px-3 py-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {selectedParent ? `after ${selectedParent.name}` : "root"}
            </span>
            {!readOnly && (
              <Popover open={editOpen} onOpenChange={setEditOpen}>
                <PopoverTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0">
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent
                  align="end"
                  className="w-[500px] p-4 max-h-[var(--radix-popover-content-available-height)] overflow-y-auto"
                >
                  <h4 className="text-sm font-semibold mb-3">Edit stage</h4>
                  <StagePopoverForm
                    campaignId={campaign.id}
                    campaign={campaign}
                    existing={selectedStage}
                    onClose={() => setEditOpen(false)}
                  />
                </PopoverContent>
              </Popover>
            )}
          </div>

          {selectedStage.criteria.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No criteria yet — this stage passes its whole population.
            </p>
          ) : (
            <ul className="space-y-1">
              {selectedStage.criteria.map((c, i) => {
                const channel = channelById.get(c.channel_id);
                const protocolName = channel
                  ? (protocolNameById.get(channel.protocol_id) ?? "Protocol")
                  : null;
                const unit = unitForChannel(c.channel_id);
                return (
                  <li
                    // Criteria are frozen values with no id of their own —
                    // index is stable because this list only changes via a
                    // whole-campaign refetch (add/remove always replaces it).
                    // biome-ignore lint/suspicious/noArrayIndexKey: see above
                    key={i}
                    className="flex items-center justify-between rounded-md border bg-background px-3 py-1.5 text-sm"
                  >
                    <span>
                      <span className="font-medium">{channel?.label ?? "Unknown readout"}</span>
                      {protocolName && channel && (
                        <span style={{ color: colorByProtocol.get(channel.protocol_id) }}>
                          {" "}
                          · {protocolName}
                        </span>
                      )}
                    </span>
                    <span className="font-mono tabular-nums text-muted-foreground">
                      {criterionValueText(c)}
                      {unit ? ` ${unit}` : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
