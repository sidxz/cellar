"use client";

/**
 * ChannelsSection — Task 2.5
 *
 * Uppercase-header section block that lists campaign channels, grouped by
 * their source protocol (a sub-heading per protocol — two protocols can
 * each define a readout named "IC50", so the group disambiguates which is
 * which, matching the grid's protocol-grouped columns). Each channel is a
 * detail row with label, source badge, and selection rule. Non-read-only
 * mode shows a "+ Channel" pill (add) and a MoreHorizontal icon per row
 * (edit) — both open ChannelPopoverForm in a Popover.
 */

import { useProtocol, useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useMirrorProtocolChannelsApiV1CampaignsCampaignIdChannelsMirrorProtocolPost } from "@/shared/lib/api/campaigns/campaigns";
import { groupBy } from "@/shared/lib/group-by";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useQueryClient } from "@tanstack/react-query";
import { Copy, MoreHorizontal, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { campaignKeys } from "../../hooks/use-campaigns";
import type { CampaignChannelResponse, CampaignResponse } from "../../types";
import { ChannelPopoverForm } from "../channel-popover";

// ── Props ─────────────────────────────────────────────────────────────────────

interface ChannelsSectionProps {
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
}

// ── Style constants ───────────────────────────────────────────────────────────

const SECTION_HEADING = "text-sm font-semibold uppercase tracking-wide text-muted-foreground";

const ADD_PILL =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors";

// ── Main component ────────────────────────────────────────────────────────────

export function ChannelsSection({ campaign, projectId, readOnly }: ChannelsSectionProps) {
  const [addOpen, setAddOpen] = useState(false);
  // Mirror-protocol open-state is lifted here so the empty-state
  // "Mirror protocol" link can open the same popover.
  const [mirrorOpen, setMirrorOpen] = useState(false);
  const channels = (campaign.channels ?? [])
    .slice()
    .sort((a, b) => a.display_order - b.display_order);

  // Protocol name lookup for the group sub-headings. `includeAll` is on so
  // we resolve any protocol referenced by a channel regardless of project
  // scope (campaigns sometimes mix protocols across programs) — mirrors
  // grid/results-grid.tsx's column-group headers exactly.
  const { data: protocolSummaries } = useProtocolSummaries(undefined, { includeAll: true });
  const protocolNameById = useMemo(
    () => new Map((protocolSummaries ?? []).map((p) => [p.id, p.name] as const)),
    [protocolSummaries],
  );
  const groupedChannels = groupBy(channels, (ch) => ch.protocol_id);

  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Readouts</h2>
        {!readOnly && (
          <div className="flex items-center gap-1.5">
            <MirrorProtocolPopover
              campaignId={campaign.id}
              projectId={projectId}
              open={mirrorOpen}
              onOpenChange={setMirrorOpen}
            />
            <Popover open={addOpen} onOpenChange={setAddOpen}>
              <PopoverTrigger asChild>
                <button type="button" className={ADD_PILL}>
                  <Plus className="h-3 w-3" /> Readout
                </button>
              </PopoverTrigger>
              <PopoverContent
                align="end"
                className="w-[420px] p-4 max-h-[var(--radix-popover-content-available-height)] overflow-y-auto"
              >
                <h4 className="text-sm font-semibold mb-3">Add readout</h4>
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
        readOnly ? (
          <p className="text-sm text-muted-foreground">
            No readouts were configured for this campaign.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            No readouts yet —{" "}
            <button
              type="button"
              onClick={() => setMirrorOpen(true)}
              className="font-medium text-primary underline underline-offset-2 hover:opacity-80"
            >
              Mirror protocol
            </button>
          </p>
        )
      ) : (
        <div className="space-y-3">
          {[...groupedChannels].map(([protocolId, protocolChannels]) => (
            <div key={protocolId}>
              <h3 className="text-xs font-medium text-muted-foreground mb-1">
                {protocolNameById.get(protocolId) ?? "Protocol"}
              </h3>
              <ul className="space-y-1">
                {protocolChannels.map((c) => (
                  <ChannelRow
                    key={c.id}
                    channel={c}
                    campaign={campaign}
                    projectId={projectId}
                    readOnly={readOnly}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ── ChannelRow ────────────────────────────────────────────────────────────────

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

  const sourceKind = channel.source_kind === "dose_response_curve" ? "DR" : "RD";

  const rule = channel.selection_rule.replace(/_/g, " ");

  return (
    <li className="flex items-center justify-between rounded-md border bg-card px-3 py-1.5">
      <span className="text-sm flex items-center gap-1.5 flex-wrap">
        <span className="font-medium">{channel.label}</span>
        <Badge variant="secondary" className="text-[10px]">
          {sourceKind}
        </Badge>
        <span className="text-muted-foreground">{rule}</span>
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
            <h4 className="text-sm font-semibold mb-3">Edit readout</h4>
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
 *
 * When the chosen protocol declares `recommended_hit_criteria`, offers to
 * also create a CampaignStage from them in the same request (`stage_name`)
 * — the funnel's first stage usually mirrors the protocol's own SOP cutoff.
 */
function MirrorProtocolPopover({
  campaignId,
  projectId,
  open,
  onOpenChange,
}: {
  campaignId: string;
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const setOpen = onOpenChange;
  const [protocolId, setProtocolId] = useState<string>("");
  const [createStage, setCreateStage] = useState(true);
  const [stageName, setStageName] = useState("");
  const { data: protocols } = useProtocolSummaries([projectId]);
  const { data: chosenProtocol } = useProtocol(protocolId, {
    enabled: !!protocolId,
  } as Parameters<typeof useProtocol>[1]);
  const hasRecommendedCriteria = (chosenProtocol?.recommended_hit_criteria?.length ?? 0) > 0;

  const mutation = useMirrorProtocolChannelsApiV1CampaignsCampaignIdChannelsMirrorProtocolPost({
    mutation: {
      onSuccess: (data) => {
        const created = data.channels_created;
        const skipped = data.channels_skipped;
        const stageNote = data.stage_created ? " and created a hit stage" : "";
        if (created === 0 && skipped === 0) {
          showError("Protocol has no readouts to mirror");
        } else if (created === 0) {
          showSuccess(`No new readouts — ${skipped} already mirrored${stageNote}`);
        } else {
          showSuccess(
            (skipped > 0
              ? `Created ${created} readouts (${skipped} already existed)`
              : `Created ${created} readouts`) + stageNote,
          );
        }
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        setOpen(false);
        setProtocolId("");
        setCreateStage(true);
        setStageName("");
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

  function handleProtocolChange(id: string) {
    setProtocolId(id);
    const proto = protocols?.find((p) => p.id === id);
    setStageName(proto ? `${proto.name} hits` : "");
    setCreateStage(true);
  }

  const handleMirror = () => {
    if (!protocolId) return;
    mutation.mutate({
      campaignId,
      data: {
        protocol_id: protocolId,
        stage_name:
          hasRecommendedCriteria && createStage && stageName.trim() ? stageName.trim() : undefined,
      },
    });
  };

  const stageNameMissing = hasRecommendedCriteria && createStage && !stageName.trim();

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
            Adds a readout here for each of the protocol's readouts. Multi-intercept dose-response
            readouts emit one per intercept (EC50, EC90, …). Matching readouts already present are
            skipped.
          </p>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Protocol</Label>
          <Select value={protocolId} onValueChange={handleProtocolChange}>
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

        {hasRecommendedCriteria && (
          <div className="space-y-2 border-t pt-2">
            <div className="flex items-center gap-2">
              <Checkbox
                id="mirror-create-stage"
                checked={createStage}
                onCheckedChange={(v) => setCreateStage(v === true)}
              />
              <Label htmlFor="mirror-create-stage" className="text-xs cursor-pointer">
                Also create a stage from the protocol's hit criteria
              </Label>
            </div>
            {createStage && (
              <div className="space-y-1">
                <Label className="text-xs">Stage name</Label>
                <Input
                  value={stageName}
                  onChange={(e) => setStageName(e.target.value)}
                  placeholder="e.g. Screening Hits"
                />
              </div>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleMirror}
            disabled={!protocolId || stageNameMissing || mutation.isPending}
          >
            {mutation.isPending ? "Mirroring…" : "Mirror"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
