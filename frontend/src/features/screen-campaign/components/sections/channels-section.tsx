"use client";

/**
 * ChannelsSection — Task 2.5
 *
 * Uppercase-header section block that lists campaign channels, grouped by
 * their source protocol (a sub-heading per protocol — two protocols can
 * each define a readout named "IC50", so the group disambiguates which is
 * which, matching the grid's protocol-grouped columns). Each protocol is one
 * wrapping line of chips — one chip per channel. Dose-response chips carry a
 * "DR" mark; the selection rule is shown only when it differs from the
 * default (latest approved run), the full description lives in the chip's
 * title. Non-read-only mode shows a "+ Readout" pill (add) and makes each
 * chip a button (edit) — both open ChannelPopoverForm in a Popover.
 */

import { useProtocol, useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
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
import {
  useMirrorProtocolChannelsApiV1CampaignsCampaignIdChannelsMirrorProtocolPost,
  useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch,
} from "@/shared/lib/api/campaigns/campaigns";
import { groupBy } from "@/shared/lib/group-by";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Copy, Plus } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { campaignKeys } from "../../hooks/use-campaigns";
import { protocolColorById } from "../../lib/protocol-colors";
import type { CampaignChannelResponse, CampaignResponse, CampaignStageResponse } from "../../types";
import { ChannelPopoverForm } from "../channel-popover";
import { ROOT_SENTINEL } from "../stage-popover";

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
  const colorByProtocol = useMemo(() => protocolColorById(channels), [channels]);

  const qc = useQueryClient();
  const reorderMutation = useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch();

  /**
   * Swap a readout's `display_order` with its neighbour in the same protocol
   * row — the order the grid's columns and the criteria pickers follow.
   *
   * The two PATCHes are sequential, not concurrent: both load-modify-save the
   * same optimistic-concurrency Campaign aggregate, so firing them together
   * would drop one with a version conflict.
   */
  async function swapWithNeighbour(row: CampaignChannelResponse[], index: number, delta: number) {
    const from = row[index];
    const to = row[index + delta];
    if (!from || !to) return;
    try {
      await reorderMutation.mutateAsync({
        campaignId: campaign.id,
        channelId: from.id,
        data: { display_order: to.display_order },
      });
      await reorderMutation.mutateAsync({
        campaignId: campaign.id,
        channelId: to.id,
        data: { display_order: from.display_order },
      });
    } catch {
      showError("Couldn't reorder readouts");
    } finally {
      void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
    }
  }

  return (
    <section className="border-b px-6 py-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className={SECTION_HEADING}>Readouts</h2>
        {!readOnly && (
          <div className="flex items-center gap-1.5">
            <MirrorProtocolPopover
              campaignId={campaign.id}
              projectId={projectId}
              stages={campaign.stages}
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
        <div className="grid grid-cols-[max-content_1fr] items-baseline gap-x-5 gap-y-2">
          {[...groupedChannels].map(([protocolId, protocolChannels]) => (
            <Fragment key={protocolId}>
              <h3
                className="text-xs font-medium whitespace-nowrap"
                style={{ color: colorByProtocol.get(protocolId) }}
              >
                {protocolNameById.get(protocolId) ?? "Protocol"}
              </h3>
              <ul className="flex flex-wrap gap-1.5">
                {protocolChannels.map((c, i) => (
                  <ChannelChip
                    key={c.id}
                    channel={c}
                    campaign={campaign}
                    projectId={projectId}
                    readOnly={readOnly}
                    canMoveEarlier={i > 0}
                    canMoveLater={i < protocolChannels.length - 1}
                    reorderPending={reorderMutation.isPending}
                    onMove={(delta) => void swapWithNeighbour(protocolChannels, i, delta)}
                  />
                ))}
              </ul>
            </Fragment>
          ))}
        </div>
      )}
    </section>
  );
}

// ── ChannelChip ───────────────────────────────────────────────────────────────

const CHIP =
  "inline-flex items-center gap-1.5 rounded-md border border-border bg-muted px-2 py-0.5 text-[13px] font-medium leading-snug";
const CHIP_EDITABLE =
  "cursor-pointer transition-colors hover:border-primary/40 hover:bg-primary/10 focus-visible:outline-2 focus-visible:outline-primary";

const DEFAULT_RULE = "latest_approved_run";

function ChannelChip({
  channel,
  campaign,
  projectId,
  readOnly,
  canMoveEarlier,
  canMoveLater,
  reorderPending,
  onMove,
}: {
  channel: CampaignChannelResponse;
  campaign: CampaignResponse;
  projectId: string;
  readOnly: boolean;
  canMoveEarlier: boolean;
  canMoveLater: boolean;
  reorderPending: boolean;
  /** -1 moves the readout one slot earlier in its protocol row, +1 later. */
  onMove: (delta: -1 | 1) => void;
}) {
  const [editOpen, setEditOpen] = useState(false);

  const isDR = channel.source_kind === "dose_response_curve";
  const rule = channel.selection_rule.replace(/_/g, " ");
  const title = `${isDR ? "Dose-response curve" : "Readout data"} · ${rule}`;

  const content = (
    <>
      {channel.label}
      {isDR && (
        <span className="self-start text-[9px] font-bold tracking-wider leading-none text-violet-700 dark:text-violet-300">
          DR
        </span>
      )}
      {channel.selection_rule !== DEFAULT_RULE && (
        <span className="text-xs font-normal text-muted-foreground">· {rule}</span>
      )}
    </>
  );

  if (readOnly) {
    return (
      <li className={CHIP} title={title}>
        {content}
      </li>
    );
  }

  return (
    <li className="inline-flex items-center gap-0.5">
      <Popover open={editOpen} onOpenChange={setEditOpen}>
        <PopoverTrigger asChild>
          <button type="button" className={`${CHIP} ${CHIP_EDITABLE}`} title={title}>
            {content}
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
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
      <ReorderButton
        label={channel.label}
        delta={-1}
        disabled={!canMoveEarlier || reorderPending}
        onMove={onMove}
      />
      <ReorderButton
        label={channel.label}
        delta={1}
        disabled={!canMoveLater || reorderPending}
        onMove={onMove}
      />
    </li>
  );
}

/** One arrow beside a chip — moves the readout a slot within its protocol row. */
function ReorderButton({
  label,
  delta,
  disabled,
  onMove,
}: {
  label: string;
  delta: -1 | 1;
  disabled: boolean;
  onMove: (delta: -1 | 1) => void;
}) {
  const Icon = delta === -1 ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      aria-label={`Move ${label} ${delta === -1 ? "earlier" : "later"}`}
      disabled={disabled}
      onClick={() => onMove(delta)}
      className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
    >
      <Icon className="h-3 w-3" />
    </button>
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
 * — the funnel's first stage usually mirrors the protocol's own SOP cutoff —
 * optionally hung under an existing stage (`parent_stage_id`).
 */
function MirrorProtocolPopover({
  campaignId,
  projectId,
  stages,
  open,
  onOpenChange,
}: {
  campaignId: string;
  projectId: string;
  /** This campaign's stages: their names default "also create a stage" off
   *  (and block Mirror) when the auto-derived name collides
   *  (case-insensitive), and they fill the parent picker. */
  stages: CampaignStageResponse[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const setOpen = onOpenChange;
  const [protocolId, setProtocolId] = useState<string>("");
  // Inert until a protocol is chosen (handleProtocolChange derives the real
  // default below) — the checkbox isn't shown before then.
  const [createStage, setCreateStage] = useState(false);
  const [stageName, setStageName] = useState("");
  // ROOT_SENTINEL = "no parent" (Radix Select forbids an empty item value).
  const [parentStageId, setParentStageId] = useState<string>(ROOT_SENTINEL);
  const existingStageNames = useMemo(() => stages.map((s) => s.name), [stages]);
  const parentOptions = useMemo(
    () => [...stages].sort((a, b) => a.display_order - b.display_order),
    [stages],
  );
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
        setCreateStage(false);
        setStageName("");
        setParentStageId(ROOT_SENTINEL);
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
    const defaultName = proto ? `${proto.name} hits` : "";
    setStageName(defaultName);
    // Off by default when the auto-derived name already exists on this
    // campaign — re-mirroring the same protocol (the documented idempotent
    // path) would otherwise submit a duplicate stage_name and 422.
    setCreateStage(
      defaultName !== "" &&
        !existingStageNames.some((n) => n.toLowerCase() === defaultName.toLowerCase()),
    );
  }

  const handleMirror = () => {
    if (!protocolId) return;
    mutation.mutate({
      campaignId,
      data: {
        protocol_id: protocolId,
        stage_name:
          hasRecommendedCriteria && createStage && stageName.trim() ? stageName.trim() : undefined,
        parent_stage_id:
          hasRecommendedCriteria && createStage && parentStageId !== ROOT_SENTINEL
            ? parentStageId
            : undefined,
      },
    });
  };

  const trimmedStageName = stageName.trim();
  const stageNameMissing = hasRecommendedCriteria && createStage && !trimmedStageName;
  const stageNameCollides =
    hasRecommendedCriteria &&
    createStage &&
    trimmedStageName !== "" &&
    existingStageNames.some((n) => n.toLowerCase() === trimmedStageName.toLowerCase());

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
              <>
                <div className="space-y-1">
                  <Label className="text-xs">Stage name</Label>
                  <Input
                    value={stageName}
                    onChange={(e) => setStageName(e.target.value)}
                    placeholder="e.g. Screening Hits"
                  />
                  {stageNameCollides && (
                    <p className="text-xs text-destructive">
                      A stage named "{trimmedStageName}" already exists on this campaign.
                    </p>
                  )}
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Parent stage</Label>
                  <Select value={parentStageId} onValueChange={setParentStageId}>
                    <SelectTrigger aria-label="Parent stage">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ROOT_SENTINEL}>None (root)</SelectItem>
                      {parentOptions.map((st) => (
                        <SelectItem key={st.id} value={st.id}>
                          {st.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
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
            disabled={!protocolId || stageNameMissing || stageNameCollides || mutation.isPending}
          >
            {mutation.isPending ? "Mirroring…" : "Mirror"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
