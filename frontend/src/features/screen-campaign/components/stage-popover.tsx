"use client";

/**
 * StagePopoverForm — add/edit form for one CampaignStage, mirroring
 * ChannelPopoverForm (react-hook-form + zod, one explicit Save, AlertDialog
 * delete). Lives inside a Popover opened by StagesSection.
 *
 * A stage is either `criteria` (evaluated from its own rules) or `manual`
 * (hand-picked — every row starts `pending` until an override promotes or
 * demotes it). A manual stage carries no criteria and is always submitted
 * with `criteria: []`; the backend rejects manual + criteria with a 422.
 *
 * The criteria list is a react-hook-form field array — each row picks one of
 * the campaign's own channels (never a raw protocol readout: a stage checks
 * a *channel*, the same value the grid and filters already key off) plus an
 * operator and one or two numeric bounds. The whole criteria list is sent on
 * every save, per the backend's "replace whole" PATCH contract.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import {
  useAddCampaignStageApiV1CampaignsCampaignIdStagesPost,
  useRemoveCampaignStageApiV1CampaignsCampaignIdStagesStageIdDelete,
  useUpdateCampaignStageApiV1CampaignsCampaignIdStagesStageIdPatch,
} from "@/shared/lib/api/campaigns/campaigns";
import { showError } from "@/shared/lib/toast";
import { Plus, Trash2 } from "lucide-react";
import { campaignKeys } from "../hooks/use-campaigns";
import type {
  CampaignResponse,
  CampaignStageResponse,
  StageCriterionDTO,
  StageKind,
} from "../types";

// ── Sentinel ──────────────────────────────────────────────────────────────────
// Radix Select forbids an empty-string item value, hence the explicit
// sentinel for "no parent" (mirrors ChannelPopoverForm's normalization_applied
// "raw" sentinel).
export const ROOT_SENTINEL = "__root__";

/** Shown wherever a manual stage would otherwise explain its criteria. */
export const MANUAL_STAGE_HELP =
  "Hand-picked: compounds start pending; promote the ones to take forward.";

// ── Schema ────────────────────────────────────────────────────────────────────

const criterionRowSchema = z
  .object({
    channel_id: z.string().min(1, "Select a readout"),
    operator: z.string().min(1),
    value: z.string().min(1, "Required"),
    /** Only meaningful when operator === "between"; low bound lives in `value`. */
    high: z.string(),
  })
  .superRefine((row, ctx) => {
    if (Number.isNaN(Number(row.value))) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["value"], message: "Enter a number" });
    }
    if (row.operator === "between") {
      if (row.high.trim() === "" || Number.isNaN(Number(row.high))) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["high"], message: "Enter a number" });
      } else if (Number(row.value) > Number(row.high)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["high"], message: "Must be ≥ low" });
      }
    }
  });

const stageFormSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120, "Max 120 characters"),
  parent_stage_id: z.string().min(1),
  kind: z.enum(["criteria", "manual"]),
  criteria: z.array(criterionRowSchema).max(10, "At most 10 criteria per stage"),
});

type StageFormValues = z.infer<typeof stageFormSchema>;

function emptyCriterionRow(): StageFormValues["criteria"][number] {
  return { channel_id: "", operator: "lt", value: "", high: "" };
}

// ── Stage-tree helper ─────────────────────────────────────────────────────────

/** Every stage reachable by walking `parent_stage_id` links downward from
 *  `stageId` — the set a parent picker must exclude to avoid a cycle. */
function descendantIds(stages: CampaignStageResponse[], stageId: string): Set<string> {
  const childrenOf = new Map<string, string[]>();
  for (const s of stages) {
    if (!s.parent_stage_id) continue;
    const bucket = childrenOf.get(s.parent_stage_id) ?? [];
    bucket.push(s.id);
    childrenOf.set(s.parent_stage_id, bucket);
  }
  const result = new Set<string>();
  const stack = [...(childrenOf.get(stageId) ?? [])];
  while (stack.length > 0) {
    const id = stack.pop();
    if (!id || result.has(id)) continue;
    result.add(id);
    stack.push(...(childrenOf.get(id) ?? []));
  }
  return result;
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface StagePopoverFormProps {
  campaignId: string;
  campaign: CampaignResponse;
  existing?: CampaignStageResponse;
  onClose: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function StagePopoverForm({
  campaignId,
  campaign,
  existing,
  onClose,
}: StagePopoverFormProps) {
  const qc = useQueryClient();
  const isEdit = !!existing;
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Unscoped + includeAll, same rationale as ChannelsSection: a campaign can
  // mix protocols across programs, so resolve every protocol referenced by
  // any channel regardless of project scope.
  const { data: protocolSummaries } = useProtocolSummaries(undefined, { includeAll: true });
  const protocolNameById = useMemo(
    () => new Map((protocolSummaries ?? []).map((p) => [p.id, p.name] as const)),
    [protocolSummaries],
  );

  const channelOptions = useMemo(() => {
    return [...(campaign.channels ?? [])]
      .sort((a, b) => a.display_order - b.display_order)
      .map((ch) => {
        const protocolName = protocolNameById.get(ch.protocol_id) ?? "Protocol";
        // Unit lives on measurements, not the channel — same derivation as
        // results-grid.tsx's sampleUnit.
        const unit = (campaign.results ?? [])
          .map((r) => r.measurements?.find((m) => m.channel_id === ch.id)?.unit ?? "")
          .find((u) => u && u !== "-");
        return {
          id: ch.id,
          label: `${protocolName} › ${ch.label}${unit ? ` (${unit})` : ""}`,
        };
      });
  }, [campaign.channels, campaign.results, protocolNameById]);

  const parentOptions = useMemo(() => {
    const excluded = existing
      ? descendantIds(campaign.stages ?? [], existing.id)
      : new Set<string>();
    return [...(campaign.stages ?? [])]
      .filter((s) => !existing || s.id !== existing.id)
      .filter((s) => !excluded.has(s.id))
      .sort((a, b) => a.display_order - b.display_order);
  }, [campaign.stages, existing]);

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<StageFormValues>({
    resolver: zodResolver(stageFormSchema),
    defaultValues: {
      name: existing?.name ?? "",
      parent_stage_id: existing?.parent_stage_id ?? ROOT_SENTINEL,
      kind: existing?.kind ?? "criteria",
      criteria: (existing?.criteria ?? []).map((c) => ({
        channel_id: c.channel_id,
        operator: c.operator,
        value: Array.isArray(c.value) ? String(c.value[0] ?? "") : String(c.value ?? ""),
        high: Array.isArray(c.value) ? String(c.value[1] ?? "") : "",
      })),
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "criteria" });
  // useFieldArray's `fields` snapshot tracks row identity (add/remove), not
  // live values — the operator Select's own onChange doesn't update it, so
  // reading it here would show stale "between" layout. `watch` does.
  const criteriaValues = watch("criteria");
  const kind = watch("kind");
  const isManual = kind === "manual";

  function onMutationError(prefix: string) {
    return (err: unknown) => {
      const msg = err instanceof Error ? err.message : String(err);
      showError(`${prefix}: ${msg}`);
    };
  }

  const addMutation = useAddCampaignStageApiV1CampaignsCampaignIdStagesPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
      onError: onMutationError("Couldn't save stage"),
    },
  });
  const updateMutation = useUpdateCampaignStageApiV1CampaignsCampaignIdStagesStageIdPatch({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
      onError: onMutationError("Couldn't save stage"),
    },
  });
  const deleteMutation = useRemoveCampaignStageApiV1CampaignsCampaignIdStagesStageIdDelete({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
      onError: onMutationError("Couldn't delete stage"),
    },
  });

  const isPending = addMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  const onSubmit = (values: StageFormValues) => {
    // A manual stage never carries criteria — the backend 422s on the pair,
    // and the hidden field array can still hold rows typed before the
    // Criteria/Manual toggle was flipped.
    const criteria: StageCriterionDTO[] =
      values.kind === "manual"
        ? []
        : values.criteria.map((row) => ({
            channel_id: row.channel_id,
            operator: row.operator,
            value:
              row.operator === "between"
                ? [Number(row.value), Number(row.high)]
                : Number(row.value),
          }));
    const parent_stage_id =
      values.parent_stage_id === ROOT_SENTINEL ? null : values.parent_stage_id;

    if (isEdit && existing) {
      updateMutation.mutate({
        campaignId,
        stageId: existing.id,
        data: { name: values.name, parent_stage_id, kind: values.kind, criteria },
      });
    } else {
      addMutation.mutate({
        campaignId,
        data: { name: values.name, parent_stage_id, kind: values.kind, criteria },
      });
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3 w-[460px] max-w-full">
      <div className="space-y-1">
        <Label>Name</Label>
        <Input {...register("name")} placeholder="e.g. Screening Hits" />
        {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
      </div>

      <div className="space-y-1">
        <Label>Parent</Label>
        <Controller
          name="parent_stage_id"
          control={control}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ROOT_SENTINEL}>None (root)</SelectItem>
                {parentOptions.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
      </div>

      <div className="space-y-1">
        <Label>How compounds enter</Label>
        <Controller
          name="kind"
          control={control}
          render={({ field }) => (
            <div className="inline-flex rounded-md border" role="radiogroup">
              {(["criteria", "manual"] as StageKind[]).map((opt) => (
                <button
                  key={opt}
                  type="button"
                  role="radio"
                  aria-checked={field.value === opt}
                  onClick={() => field.onChange(opt)}
                  className={`px-3 py-1 text-xs capitalize first:rounded-l-md last:rounded-r-md ${
                    field.value === opt
                      ? "bg-primary text-primary-foreground"
                      : "bg-background hover:bg-muted"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
        />
      </div>

      {isManual ? (
        <p className="text-xs text-muted-foreground">{MANUAL_STAGE_HELP}</p>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Criteria</Label>
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {fields.length}/10
            </span>
          </div>

          {fields.length === 0 && (
            <p className="text-xs text-muted-foreground">
              No criteria — this stage passes its whole population.
            </p>
          )}

          {fields.map((field, index) => {
            const operator = criteriaValues[index]?.operator ?? field.operator;
            const rowError =
              errors.criteria?.[index]?.channel_id?.message ??
              errors.criteria?.[index]?.value?.message ??
              errors.criteria?.[index]?.high?.message;
            return (
              <div key={field.id} className="space-y-1 rounded-md border p-2">
                <div className="flex items-start gap-2">
                  <div className="flex-1 space-y-1 min-w-0">
                    <Label className="text-xs">Readout</Label>
                    <Controller
                      name={`criteria.${index}.channel_id`}
                      control={control}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger
                            className="h-8 w-full min-w-0 text-xs *:data-[slot=select-value]:block *:data-[slot=select-value]:truncate"
                            title={channelOptions.find((o) => o.id === f.value)?.label}
                          >
                            <SelectValue placeholder="Select readout..." />
                          </SelectTrigger>
                          <SelectContent>
                            {channelOptions.map((opt) => (
                              <SelectItem key={opt.id} value={opt.id}>
                                {opt.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>

                  <div className="w-[92px] space-y-1 shrink-0">
                    <Label className="text-xs">Operator</Label>
                    <Controller
                      name={`criteria.${index}.operator`}
                      control={control}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger className="h-8 w-full text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="lt">{"<"}</SelectItem>
                            <SelectItem value="lte">{"<="}</SelectItem>
                            <SelectItem value="gt">{">"}</SelectItem>
                            <SelectItem value="gte">{">="}</SelectItem>
                            <SelectItem value="between">between</SelectItem>
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>

                  {operator === "between" ? (
                    <>
                      <div className="w-[72px] space-y-1 shrink-0">
                        <Label className="text-xs">Low</Label>
                        <Input
                          className="h-8 text-xs"
                          type="number"
                          step="any"
                          {...register(`criteria.${index}.value`)}
                        />
                      </div>
                      <div className="w-[72px] space-y-1 shrink-0">
                        <Label className="text-xs">High</Label>
                        <Input
                          className="h-8 text-xs"
                          type="number"
                          step="any"
                          {...register(`criteria.${index}.high`)}
                        />
                      </div>
                    </>
                  ) : (
                    <div className="w-[72px] space-y-1 shrink-0">
                      <Label className="text-xs">Value</Label>
                      <Input
                        className="h-8 text-xs"
                        type="number"
                        step="any"
                        {...register(`criteria.${index}.value`)}
                      />
                    </div>
                  )}

                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                    onClick={() => remove(index)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                {rowError && <p className="text-[11px] text-destructive">{rowError}</p>}
              </div>
            );
          })}

          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => append(emptyCriterionRow())}
            disabled={fields.length >= 10}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" /> Criterion
          </Button>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-1">
        {isEdit ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            disabled={isPending}
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </Button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={isPending}>
            {isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      {/* Deleting a stage drops every override recorded against it. A stage
          with children can't be deleted server-side (409) until they're
          removed or re-parented — the popover surfaces that message via
          toast rather than pre-guessing it here. */}
      {isEdit && existing && (
        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete stage "{existing.name}"?</AlertDialogTitle>
              <AlertDialogDescription>
                This removes the stage and every override recorded against it for this campaign.
                Stages with children can't be deleted until the children are removed or re-parented.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => deleteMutation.mutate({ campaignId, stageId: existing.id })}
              >
                Delete stage
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </form>
  );
}
