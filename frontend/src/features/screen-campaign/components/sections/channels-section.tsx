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
import { useQueryClient } from "@tanstack/react-query";
import { Copy, MoreHorizontal, Plus } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/shared/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import { useMirrorProtocolChannelsApiV1CampaignsCampaignIdChannelsMirrorProtocolPost } from "@/shared/lib/api/campaigns/campaigns";
import { showError, showSuccess } from "@/shared/lib/toast";
import type { CampaignResponse, CampaignChannelResponse } from "../../types";
import { ChannelPopoverForm, parseHitThreshold } from "../channel-popover";
import { campaignKeys } from "../../hooks/use-campaigns";
import {
  interceptKeyLabel,
  narrowInterceptKey,
} from "@/features/screening-assay/lib/intercept-label";

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
          <div className="flex items-center gap-1.5">
            <MirrorProtocolPopover campaignId={campaign.id} projectId={projectId} />
            <Popover open={addOpen} onOpenChange={setAddOpen}>
              <PopoverTrigger asChild>
                <button type="button" className={ADD_PILL}>
                  <Plus className="h-3 w-3" /> Channel
                </button>
              </PopoverTrigger>
              <PopoverContent
                align="end"
                className="w-[420px] p-4 max-h-[var(--radix-popover-content-available-height)] overflow-y-auto"
              >
                <h4 className="text-sm font-semibold mb-3">Add channel</h4>
                <ChannelPopoverForm
                  campaignId={campaign.id}
                  projectId={projectId}
                  onClose={() => setAddOpen(false)}
                />
              </PopoverContent>
            </Popover>
          </div>
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

function formatThreshold(channel: CampaignChannelResponse): string {
  const parsed = parseHitThreshold(channel.hit_threshold);
  if (!parsed) return "";
  const opLabel = OPERATOR_LABEL[parsed.operator] ?? parsed.operator;
  // Channel-level intercept_key wins (Option A). Falls back to the
  // threshold's intercept_key for legacy rows saved before the top-level
  // field existed. Primary (`null` in both) stays implicit — every
  // channel has *some* primary, naming it everywhere is noise.
  const effectiveIk =
    narrowInterceptKey(channel.intercept_key) ?? parsed.intercept_key;
  const ik = effectiveIk ? `${interceptKeyLabel(effectiveIk)} ` : "";
  if (Array.isArray(parsed.value)) {
    const [lo, hi] = parsed.value;
    return `hit if ${ik}${lo} – ${hi}`;
  }
  return `hit if ${ik}${opLabel} ${parsed.value}`;
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

  const thresholdLabel = formatThreshold(channel);

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
          <PopoverContent
            align="end"
            className="w-[420px] p-4 max-h-[var(--radix-popover-content-available-height)] overflow-y-auto"
          >
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

// ── MirrorProtocolPopover ─────────────────────────────────────────────────────

/**
 * One-click shortcut to bulk-create channels mirroring a protocol's readouts.
 *
 * Backend endpoint POST /channels/mirror-protocol does the iteration
 * (multi-intercept DR readouts emit one channel per intercept, see commit
 * #14's add-from-runs split). Idempotent: existing matching channels are
 * skipped, so re-mirror after a protocol edit doesn't duplicate columns.
 */
function MirrorProtocolPopover({
  campaignId,
  projectId,
}: {
  campaignId: string;
  projectId: string;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [protocolId, setProtocolId] = useState<string>("");
  const { data: protocols } = useProtocolSummaries([projectId]);

  const mutation = useMirrorProtocolChannelsApiV1CampaignsCampaignIdChannelsMirrorProtocolPost({
    mutation: {
      onSuccess: (data) => {
        const created = data.channels_created;
        const skipped = data.channels_skipped;
        if (created === 0 && skipped === 0) {
          showError("Protocol has no readouts to mirror");
        } else if (created === 0) {
          showSuccess(`No new channels — ${skipped} already mirrored`);
        } else {
          showSuccess(
            skipped > 0
              ? `Created ${created} channels (${skipped} already existed)`
              : `Created ${created} channels`,
          );
        }
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        setOpen(false);
        setProtocolId("");
      },
      onError: (err: unknown) => {
        const msg =
          err && typeof err === "object" && "message" in err
            ? String((err as { message: unknown }).message)
            : "Failed to mirror protocol";
        showError(msg);
      },
    },
  });

  const handleMirror = () => {
    if (!protocolId) return;
    mutation.mutate({ campaignId, data: { protocol_id: protocolId } });
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={ADD_PILL}>
          <Copy className="h-3 w-3" /> Mirror protocol
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[340px] p-4 space-y-3">
        <div>
          <h4 className="text-sm font-semibold">Mirror protocol</h4>
          <p className="text-xs text-muted-foreground mt-1">
            Creates one channel per readout. Multi-intercept dose-response
            readouts emit one channel per intercept (EC50, EC90, …). Existing
            channels with a matching key are skipped.
          </p>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Protocol</Label>
          <Select value={protocolId} onValueChange={setProtocolId}>
            <SelectTrigger>
              <SelectValue placeholder="Select protocol..." />
            </SelectTrigger>
            <SelectContent>
              {(protocols ?? []).map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setOpen(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleMirror}
            disabled={!protocolId || mutation.isPending}
          >
            {mutation.isPending ? "Mirroring…" : "Mirror"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
