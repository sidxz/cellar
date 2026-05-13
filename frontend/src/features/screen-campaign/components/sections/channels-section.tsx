"use client";

/**
 * ChannelsSection — Task 2.5
 *
 * Uppercase-header section block that lists campaign channels, each as a
 * detail row with label, source badge, hit threshold, and selection rule.
 * Non-read-only mode shows a "+ Channel" pill (add) and a MoreHorizontal
 * icon per row (edit) — both open ChannelPopoverForm in a Popover.
 */

import { useState } from "react";
import { MoreHorizontal, Plus } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/shared/components/ui/popover";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import type { CampaignResponse, CampaignChannelResponse } from "../../types";
import { ChannelPopoverForm, parseHitThreshold } from "../channel-popover";

// ── Props ─────────────────────────────────────────────────────────────────────

interface ChannelsSectionProps {
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
}

// ── Style constants ───────────────────────────────────────────────────────────

const SECTION_HEADING =
  "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

const ADD_PILL =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors";

// ── Main component ────────────────────────────────────────────────────────────

export function ChannelsSection({
  campaign,
  projectId,
  readOnly,
}: ChannelsSectionProps) {
  const [addOpen, setAddOpen] = useState(false);
  const channels = (campaign.channels ?? []).slice().sort(
    (a, b) => a.display_order - b.display_order,
  );

  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Channels</h2>
        {!readOnly && (
          <Popover open={addOpen} onOpenChange={setAddOpen}>
            <PopoverTrigger asChild>
              <button type="button" className={ADD_PILL}>
                <Plus className="h-3 w-3" /> Channel
              </button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-[420px] p-4">
              <h4 className="text-sm font-semibold mb-3">Add channel</h4>
              <ChannelPopoverForm
                campaignId={campaign.id}
                projectId={projectId}
                onClose={() => setAddOpen(false)}
              />
            </PopoverContent>
          </Popover>
        )}
      </div>

      {channels.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {readOnly
            ? "No channels were configured for this campaign."
            : "No channels yet — add via the pill above."}
        </p>
      ) : (
        <ul className="space-y-1">
          {channels.map((c) => (
            <ChannelRow
              key={c.id}
              channel={c}
              campaign={campaign}
              projectId={projectId}
              readOnly={readOnly}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

// ── ChannelRow ────────────────────────────────────────────────────────────────

/** Operator symbols for compact display. */
const OPERATOR_LABEL: Record<string, string> = {
  lt: "<",
  lte: "≤",
  gt: ">",
  gte: "≥",
  between: "between",
};

function formatThreshold(hit_threshold: CampaignChannelResponse["hit_threshold"]): string {
  const parsed = parseHitThreshold(hit_threshold);
  if (!parsed) return "";
  const opLabel = OPERATOR_LABEL[parsed.operator] ?? parsed.operator;
  if (Array.isArray(parsed.value)) {
    const [lo, hi] = parsed.value;
    return `hit if ${lo} – ${hi}`;
  }
  return `hit if ${opLabel} ${parsed.value}`;
}

function ChannelRow({
  channel,
  campaign,
  projectId,
  readOnly,
}: {
  channel: CampaignChannelResponse;
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
}) {
  const [editOpen, setEditOpen] = useState(false);

  const sourceKind =
    channel.source_kind === "dose_response_curve" ? "DR" : "RD";

  const thresholdLabel = formatThreshold(channel.hit_threshold);

  const rule = channel.selection_rule.replace(/_/g, " ");

  return (
    <li className="flex items-center justify-between rounded-md border bg-card px-3 py-1.5">
      <span className="text-sm flex items-center gap-1.5 flex-wrap">
        <span className="font-medium">{channel.label}</span>
        <Badge variant="secondary" className="text-[10px]">
          {sourceKind}
        </Badge>
        <span className="text-muted-foreground">
          {thresholdLabel ? `${thresholdLabel} · ` : ""}
          {rule}
        </span>
      </span>

      {!readOnly && (
        <Popover open={editOpen} onOpenChange={setEditOpen}>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0">
              <MoreHorizontal className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-[420px] p-4">
            <h4 className="text-sm font-semibold mb-3">Edit channel</h4>
            <ChannelPopoverForm
              campaignId={campaign.id}
              projectId={projectId}
              existing={channel}
              onClose={() => setEditOpen(false)}
            />
          </PopoverContent>
        </Popover>
      )}
    </li>
  );
}
