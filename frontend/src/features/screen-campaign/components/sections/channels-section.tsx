"use client";

/**
 * ChannelsSection — Task 2.5
 *
 * Uppercase-header section block that lists campaign channels under the stage
 * that owns them (funnel order, campaign columns last under "Other columns"),
 * matching the grid's column groups. Within a stage each protocol is one run
 * of chips, led by its coloured name — two protocols can each define a readout
 * named "IC50". Dose-response chips carry a "DR" mark; the selection rule is
 * shown only when it differs from the default (latest run), the full
 * description lives in the chip's title. A column measured at several
 * concentrations offers the choice inline under its stage. Non-read-only mode
 * shows a "+ Readout" pill (add) and makes each chip a button (edit) — both
 * open ChannelPopoverForm in a Popover.
 */

import { ProtocolOptionLabel } from "@/features/screening-assay";
import { useProtocol, useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import { Button } from "@/shared/components/ui/button";
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
import { campaignKeys, useSetColumnConcentration } from "../../hooks/use-campaigns";
import { concentrationText } from "../../lib/column-description";
import { protocolColorById } from "../../lib/protocol-colors";
import { groupColumnsByStage } from "../../lib/stage-column-groups";
import { stageNameNotice } from "../../lib/stage-name-notice";
import type { CampaignChannelResponse, CampaignResponse, CampaignStageResponse } from "../../types";
import { ChannelPopoverForm } from "../channel-popover";
import { ROOT_SENTINEL } from "../stage-popover";
import { NEW_STAGE, StageTargetSelect, stageIdOf } from "../stage-target-select";

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
  const stageGroups = groupColumnsByStage(channels, campaign.stages ?? []);
  const colorByProtocol = useMemo(() => protocolColorById(channels), [channels]);

  const qc = useQueryClient();
  const reorderMutation = useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch();

  /**
   * Swap a readout's `display_order` with its neighbour in the same
   * (stage, protocol) row — the order the grid's columns and the criteria
   * pickers follow.
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
                  stages={campaign.stages ?? []}
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
        <div className="grid grid-cols-[max-content_1fr] items-baseline gap-x-5 gap-y-3">
          {stageGroups.map((group) => (
            <Fragment key={group.stageId ?? "other"}>
              <h3 className="text-xs font-semibold whitespace-nowrap">{group.title}</h3>
              <div className="min-w-0 space-y-1.5">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                  {[...groupBy(group.channels, (ch) => ch.protocol_id)].map(([protocolId, row]) => (
                    <div key={protocolId} className="flex flex-wrap items-center gap-1.5">
                      <span
                        className="text-xs font-medium whitespace-nowrap"
                        style={{ color: colorByProtocol.get(protocolId) }}
                      >
                        {protocolNameById.get(protocolId) ?? "Protocol"}
                      </span>
                      <ul className="flex flex-wrap gap-1.5">
                        {row.map((c, i) => (
                          <ChannelChip
                            key={c.id}
                            channel={c}
                            campaign={campaign}
                            projectId={projectId}
                            readOnly={readOnly}
                            canMoveEarlier={i > 0}
                            canMoveLater={i < row.length - 1}
                            reorderPending={reorderMutation.isPending}
                            onMove={(delta) => void swapWithNeighbour(row, i, delta)}
                          />
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
                {!readOnly &&
                  group.channels.map((c) => (
                    <ConcentrationChoice key={c.id} campaignId={campaign.id} channel={c} />
                  ))}
              </div>
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

const DEFAULT_RULE = "latest_run";

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
      {/* Opted out of its run scope — reads every run of its protocol, not
          only the runs added to its stage (or, for other columns, the campaign). */}
      {channel.resolve_from_all_runs && (
        <span
          className="text-[10px] font-normal italic text-muted-foreground"
          title="Reads every run of the protocol, not only the runs added to its stage or campaign."
        >
          all runs
        </span>
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

// ── ConcentrationChoice ───────────────────────────────────────────────────────

/**
 * One line under a column whose runs hold it at several concentrations: one
 * button per concentration found (its compound count beside it), or — once
 * one is chosen — the way back to all of them. Renders nothing otherwise.
 */
function ConcentrationChoice({
  campaignId,
  channel,
}: {
  campaignId: string;
  channel: CampaignChannelResponse;
}) {
  const setConcentration = useSetColumnConcentration(campaignId);
  const d = channel.description;
  const chosen = channel.test_concentration;
  const name = d?.readout_label ?? channel.label;
  const choose = (testConcentration: { value: number; unit: string } | null) =>
    setConcentration.mutate({ channelId: channel.id, testConcentration });

  if (chosen) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          {name}: values at {concentrationText(chosen)}
        </span>
        <Button
          size="xs"
          variant="outline"
          disabled={setConcentration.isPending}
          onClick={() => choose(null)}
        >
          Show all concentrations
        </Button>
      </div>
    );
  }
  if (!d?.needs_concentration) return null;
  const found = d.concentrations.filter((c) => c.value != null && c.unit);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span>{name} was measured at several concentrations:</span>
      {found.map((c) => (
        <span key={`${c.value}${c.unit}`} className="inline-flex items-center gap-1.5">
          <Button
            size="xs"
            variant="outline"
            disabled={setConcentration.isPending}
            onClick={() => choose({ value: c.value as number, unit: c.unit as string })}
          >
            Show values at {concentrationText(c)}
          </Button>
          <span className="tabular-nums">
            {c.count} {c.count === 1 ? "compound" : "compounds"}
          </span>
        </span>
      ))}
    </div>
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
 * The columns go to a stage, picked by name (`stage_id`, which never touches
 * its criteria), to a new stage (`stage_name`, optionally under
 * `parent_stage_id`, taking the protocol's recommended hit criteria when some
 * map), or to "Other columns". A campaign with stages must pick; one with none
 * starts its first stage by default.
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
  /** This campaign's stages: they fill the stage and parent pickers and drive
   *  the reuse advisory under a new stage's name (a colliding name reuses that
   *  stage, except a manual one, which the backend refuses). */
  stages: CampaignStageResponse[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const setOpen = onOpenChange;
  const [protocolId, setProtocolId] = useState<string>("");
  const [pickedTarget, setPickedTarget] = useState<string | null>(null);
  const target = pickedTarget ?? (stages.length > 0 ? "" : NEW_STAGE);
  const [stageName, setStageName] = useState("");
  // ROOT_SENTINEL = "no parent" (Radix Select forbids an empty item value).
  const [parentStageId, setParentStageId] = useState<string>(ROOT_SENTINEL);
  const parentOptions = useMemo(
    () => [...stages].sort((a, b) => a.display_order - b.display_order),
    [stages],
  );
  const { data: protocols } = useProtocolSummaries([projectId]);
  const { data: chosenProtocol } = useProtocol(protocolId, {
    enabled: !!protocolId,
  } as Parameters<typeof useProtocol>[1]);
  const hasRecommendedCriteria = (chosenProtocol?.recommended_hit_criteria?.length ?? 0) > 0;

  function reset() {
    setProtocolId("");
    setPickedTarget(null);
    setStageName("");
    setParentStageId(ROOT_SENTINEL);
  }

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
        reset();
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
  }

  const isNew = target === NEW_STAGE;
  const trimmedStageName = stageName.trim();
  const nameNotice = isNew ? stageNameNotice(stages, stageName) : null;
  const handleMirror = () => {
    if (!protocolId) return;
    mutation.mutate({
      campaignId,
      data: {
        protocol_id: protocolId,
        stage_id: stageIdOf(target),
        stage_name: isNew ? trimmedStageName : null,
        parent_stage_id: isNew && parentStageId !== ROOT_SENTINEL ? parentStageId : null,
      },
    });
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
            Adds a readout here for each of the protocol's readouts. Multi-intercept dose-response
            readouts emit one per intercept (EC50, EC90, …). Matching readouts already present are
            skipped.
          </p>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Protocol</Label>
          <Select value={protocolId} onValueChange={handleProtocolChange}>
            <SelectTrigger aria-label="Protocol">
              <SelectValue placeholder="Select protocol..." />
            </SelectTrigger>
            <SelectContent>
              {(protocols ?? []).map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  <ProtocolOptionLabel code={p.code} name={p.name} />
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label className="text-xs">Stage</Label>
          <StageTargetSelect
            stages={stages}
            value={target}
            onChange={setPickedTarget}
            allowNewStage
          />
        </div>

        {isNew && (
          <div className="space-y-2">
            <div className="space-y-1">
              <Label className="text-xs">Stage name</Label>
              <Input
                value={stageName}
                onChange={(e) => setStageName(e.target.value)}
                placeholder="e.g. Screening Hits"
              />
              {nameNotice ? (
                <p
                  className={`text-xs ${nameNotice.blocking ? "text-destructive" : "text-muted-foreground"}`}
                >
                  {nameNotice.text}
                </p>
              ) : (
                hasRecommendedCriteria && (
                  <p className="text-xs text-muted-foreground">
                    Its criteria come from the protocol's recommended hit criteria.
                  </p>
                )
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
            disabled={
              !protocolId ||
              !target ||
              (isNew && !trimmedStageName) ||
              nameNotice?.blocking ||
              mutation.isPending
            }
          >
            {mutation.isPending ? "Mirroring…" : "Mirror"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
