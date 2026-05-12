"use client";

/**
 * ChannelPopoverForm — extracted from channel-strip.tsx (Task 8.3 → Task 2.5).
 *
 * Renders the add / edit channel form that lives inside a Popover.
 * Used by both the legacy ChannelStrip chip-strip and the new ChannelsSection.
 */

import { useState, useEffect } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";

import { useProtocolSummaries, useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import {
  READOUT_NORMALIZATION_LABELS,
  type HitCriterion,
} from "@/features/screening-assay/types";
import { deriveChannelHitDefaults } from "@/features/screening-assay/lib/hit-criteria-defaults";
import {
  useAddCampaignChannelApiV1CampaignsCampaignIdChannelsPost,
  useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch,
} from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../lib/hooks";
import type { CampaignChannelResponse } from "../types";

// ── Schema ────────────────────────────────────────────────────────────────────

const channelSchema = z.object({
  label: z.string().min(1, "Label is required"),
  protocol_id: z.string().min(1, "Protocol is required"),
  readout_definition_id: z.string().min(1, "Readout is required"),
  source_kind: z.enum(["readout_data", "dose_response_curve"]),
  selection_rule: z.enum([
    "latest_approved_run",
    "mean_across_runs",
    "geometric_mean",
    "manual_pick",
  ]),
  qualifier_handling: z.enum([
    "include_qualified",
    "exclude_qualified",
    "treat_as_limit",
  ]),
  require_approved: z.boolean(),
  min_z_prime: z.number().min(0).max(1),
  // Hit threshold — operator "none" means "no threshold". For between, low/high; otherwise single value.
  // (Radix Select forbids empty-string values, hence the explicit "none" sentinel.)
  hit_operator: z.enum(["none", "lt", "lte", "gt", "gte", "between"]),
  hit_value: z.string(),
  hit_value_low: z.string(),
  hit_value_high: z.string(),
  // Normalization layer for readout_data channels. "raw" sentinel maps to the
  // raw layer (NULL on the wire); any other value selects that formula.
  // Locked at create-time — Radix Select forbids empty-string values, hence
  // the explicit sentinel.
  normalization_applied: z.string(),
});

type ChannelFormValues = z.infer<typeof channelSchema>;

// ── Helper ────────────────────────────────────────────────────────────────────

export function parseHitThreshold(t: unknown):
  | { operator: string; value: number | number[] }
  | null {
  if (!t || typeof t !== "object") return null;
  const obj = t as { operator?: string; value?: unknown };
  if (!obj.operator) return null;
  if (typeof obj.value === "number") return { operator: obj.operator, value: obj.value };
  if (Array.isArray(obj.value) && obj.value.every((v) => typeof v === "number")) {
    return { operator: obj.operator, value: obj.value as number[] };
  }
  return null;
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface ChannelPopoverFormProps {
  campaignId: string;
  projectId: string;
  existing?: CampaignChannelResponse;
  onClose: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ChannelPopoverForm({
  campaignId,
  existing,
  onClose,
  projectId,
}: ChannelPopoverFormProps) {
  const qc = useQueryClient();
  const { data: protocols } = useProtocolSummaries([projectId]);
  const [selectedProtocolId, setSelectedProtocolId] = useState<string>(
    existing?.protocol_id ?? "",
  );
  // Fetch full protocol to get readout_definitions
  const { data: fullProtocol } = useProtocol(selectedProtocolId, {
    enabled: !!selectedProtocolId,
  } as Parameters<typeof useProtocol>[1]);

  const addMutation = useAddCampaignChannelApiV1CampaignsCampaignIdChannelsPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
    },
  });
  const updateMutation = useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
    },
  });

  const isEdit = !!existing;

  // Parse existing qc_filter — it's typed as `{ [key: string]: unknown } | null`
  const existingQc = existing?.qc_filter as Record<string, unknown> | null | undefined;
  // Parse existing hit_threshold into the form's split fields.
  const existingHit = parseHitThreshold(existing?.hit_threshold);
  const defaultHitOperator: ChannelFormValues["hit_operator"] =
    (existingHit?.operator as ChannelFormValues["hit_operator"] | undefined) ?? "none";
  const defaultHitValue =
    existingHit && typeof existingHit.value === "number" ? String(existingHit.value) : "";
  const defaultHitLow =
    existingHit && Array.isArray(existingHit.value) ? String(existingHit.value[0]) : "";
  const defaultHitHigh =
    existingHit && Array.isArray(existingHit.value) ? String(existingHit.value[1]) : "";

  const {
    register,
    handleSubmit,
    control,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ChannelFormValues>({
    resolver: zodResolver(channelSchema),
    defaultValues: {
      label: existing?.label ?? "",
      protocol_id: existing?.protocol_id ?? "",
      readout_definition_id: existing?.readout_definition_id ?? "",
      source_kind:
        (existing?.source_kind as "readout_data" | "dose_response_curve") ??
        "readout_data",
      selection_rule:
        (existing?.selection_rule as
          | "latest_approved_run"
          | "mean_across_runs"
          | "geometric_mean"
          | "manual_pick") ?? "latest_approved_run",
      qualifier_handling:
        (existing?.qualifier_handling as
          | "include_qualified"
          | "exclude_qualified"
          | "treat_as_limit") ?? "include_qualified",
      require_approved: (existingQc?.require_approved as boolean | undefined) ?? false,
      min_z_prime: (existingQc?.min_z_prime as number | undefined) ?? 0,
      hit_operator: defaultHitOperator,
      hit_value: defaultHitValue,
      hit_value_low: defaultHitLow,
      hit_value_high: defaultHitHigh,
      normalization_applied: existing?.normalization_applied ?? "raw",
    },
  });

  const watchedProtocol = watch("protocol_id");
  const watchedReadoutId = watch("readout_definition_id");

  // Pre-fill hit threshold from protocol recommendations when a readout is
  // selected in create mode. Shares the same carry-forward rules as the
  // "Add from runs" dialog (see deriveChannelHitDefaults). Never fires when
  // editing an existing channel.
  useEffect(() => {
    if (existing) return;
    if (!watchedReadoutId || !fullProtocol?.readout_definitions) return;
    const rd = fullProtocol.readout_definitions.find((r) => r.id === watchedReadoutId);
    if (!rd?.name) return;

    const defaults = deriveChannelHitDefaults(
      (fullProtocol.recommended_hit_criteria ?? []) as unknown as HitCriterion[],
      { name: rd.name, data_type: rd.data_type },
    );

    setValue(
      "hit_operator",
      (defaults.hit_operator === "" ? "none" : defaults.hit_operator) as ChannelFormValues["hit_operator"],
    );
    setValue("hit_value", defaults.hit_value);
    setValue("hit_value_low", defaults.hit_value_low);
    setValue("hit_value_high", defaults.hit_value_high);
  }, [watchedReadoutId, existing, fullProtocol, setValue]);

  // Auto-pick the readout's primary normalization layer when the readout is
  // chosen (create mode only). Chemists want "% Inhibition" by default, not
  // raw absorbance — but they can still flip back to "raw" with the picker.
  useEffect(() => {
    if (existing) return;
    if (!watchedReadoutId || !fullProtocol?.readout_definitions) return;
    const rd = fullProtocol.readout_definitions.find((r) => r.id === watchedReadoutId);
    if (!rd) return;
    const primary = rd.normalizations?.find((n) => n !== "none");
    setValue("normalization_applied", primary ?? "raw");
  }, [watchedReadoutId, existing, fullProtocol, setValue]);

  const onSubmit = (values: ChannelFormValues) => {
    const qcFilter = values.require_approved || values.min_z_prime > 0
      ? { require_approved: values.require_approved, min_z_prime: values.min_z_prime }
      : undefined;

    // Build hit_threshold from split form fields. "" = no threshold.
    let hitThreshold:
      | { readout_name: string; operator: string; value: number | number[] }
      | null = null;
    if (values.hit_operator === "between") {
      const low = values.hit_value_low === "" ? null : Number(values.hit_value_low);
      const high = values.hit_value_high === "" ? null : Number(values.hit_value_high);
      if (
        low !== null && !Number.isNaN(low) &&
        high !== null && !Number.isNaN(high) &&
        low <= high
      ) {
        hitThreshold = {
          readout_name: values.label,
          operator: "between",
          value: [low, high],
        };
      }
    } else if (values.hit_operator !== "none") {
      const num = values.hit_value === "" ? null : Number(values.hit_value);
      if (num !== null && !Number.isNaN(num)) {
        hitThreshold = {
          readout_name: values.label,
          operator: values.hit_operator,
          value: num,
        };
      }
    }

    if (isEdit && existing) {
      updateMutation.mutate({
        campaignId,
        channelId: existing.id,
        data: {
          label: values.label,
          selection_rule: values.selection_rule,
          qc_filter: qcFilter ?? null,
          hit_threshold: hitThreshold,
        },
      });
    } else {
      // "raw" sentinel → wire NULL so the resolver picks the raw layer. DR-curve
      // channels ignore the field entirely on the backend, so we send null.
      const normalizationApplied =
        values.source_kind === "readout_data" && values.normalization_applied !== "raw"
          ? values.normalization_applied
          : null;
      addMutation.mutate({
        campaignId,
        data: {
          label: values.label,
          protocol_id: values.protocol_id,
          readout_definition_id: values.readout_definition_id,
          source_kind: values.source_kind,
          selection_rule: values.selection_rule,
          qualifier_handling: values.qualifier_handling,
          qc_filter: qcFilter ?? null,
          hit_threshold: hitThreshold,
          normalization_applied: normalizationApplied,
        },
      });
    }
  };

  const isPending = addMutation.isPending || updateMutation.isPending;

  const readouts = fullProtocol?.readout_definitions ?? [];

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3 w-[360px] max-w-full">
      <div className="space-y-1">
        <Label>Label</Label>
        <Input {...register("label")} placeholder="e.g. Primary IC50" />
        {errors.label && <p className="text-xs text-destructive">{errors.label.message}</p>}
      </div>

      {!isEdit && (
        <>
          <div className="space-y-1">
            <Label>Protocol</Label>
            <Controller
              name="protocol_id"
              control={control}
              render={({ field }) => (
                <Select
                  value={field.value}
                  onValueChange={(v) => {
                    field.onChange(v);
                    setSelectedProtocolId(v);
                    setValue("readout_definition_id", "");
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select protocol..." />
                  </SelectTrigger>
                  <SelectContent>
                    {protocols?.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.protocol_id && <p className="text-xs text-destructive">{errors.protocol_id.message}</p>}
          </div>

          <div className="space-y-1">
            <Label>Readout</Label>
            <Controller
              name="readout_definition_id"
              control={control}
              render={({ field }) => (
                <Select
                  value={field.value}
                  onValueChange={field.onChange}
                  disabled={!watchedProtocol || readouts.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select readout..." />
                  </SelectTrigger>
                  <SelectContent>
                    {readouts.map((r) => (
                      <SelectItem key={r.id} value={r.id}>
                        {r.name}
                        {r.unit && (
                          <span className="ml-1 text-xs text-muted-foreground">({r.unit})</span>
                        )}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.readout_definition_id && (
              <p className="text-xs text-destructive">{errors.readout_definition_id.message}</p>
            )}
          </div>
        </>
      )}

      {/* Source — only editable at create time. Changing it on an existing
          channel would invalidate every measurement. */}
      {!isEdit && (
        <div className="space-y-1">
          <Label>Source</Label>
          <Controller
            name="source_kind"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="readout_data">Readout data</SelectItem>
                  <SelectItem value="dose_response_curve">
                    Dose-response curve
                  </SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>
      )}
      {isEdit && existing && (
        <div className="text-xs text-muted-foreground">
          Source:{" "}
          <span className="font-medium text-foreground">
            {existing.source_kind === "dose_response_curve"
              ? "Dose-response curve"
              : "Readout data"}
          </span>{" "}
          <span className="text-muted-foreground/70">(locked after creation)</span>
        </div>
      )}

      {/* Normalization layer — only for readout_data, create mode, when the
          chosen readout actually emits normalizations. Locked after creation
          for the same reason source_kind is: changing it would invalidate
          every existing measurement. */}
      {!isEdit && watch("source_kind") === "readout_data" && (() => {
        const rd = readouts.find((r) => r.id === watchedReadoutId);
        const norms = rd?.normalizations?.filter((n) => n !== "none") ?? [];
        if (norms.length === 0) return null;
        return (
          <div className="space-y-1">
            <Label>Normalization</Label>
            <Controller
              name="normalization_applied"
              control={control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="raw">Raw (no normalization)</SelectItem>
                    {norms.map((n) => (
                      <SelectItem key={n} value={n}>
                        {READOUT_NORMALIZATION_LABELS[n as keyof typeof READOUT_NORMALIZATION_LABELS] ?? n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
        );
      })()}
      {isEdit && existing && existing.normalization_applied && (
        <div className="text-xs text-muted-foreground">
          Normalization:{" "}
          <span className="font-medium text-foreground">
            {READOUT_NORMALIZATION_LABELS[
              existing.normalization_applied as keyof typeof READOUT_NORMALIZATION_LABELS
            ] ?? existing.normalization_applied}
          </span>{" "}
          <span className="text-muted-foreground/70">(locked after creation)</span>
        </div>
      )}

      <div className="space-y-1">
        <Label>Selection rule</Label>
        <Controller
          name="selection_rule"
          control={control}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="latest_approved_run">
                  Latest approved run
                </SelectItem>
                <SelectItem value="mean_across_runs">
                  Mean across runs
                </SelectItem>
                <SelectItem value="geometric_mean">
                  Geometric mean
                </SelectItem>
                <SelectItem value="manual_pick">Manual pick</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
      </div>

      {/* Hit threshold — operator + value(s). Drives the hit/miss chip on each cell. */}
      <div className="space-y-1">
        <Label>Hit threshold</Label>
        <div className="flex items-end gap-2 flex-wrap">
          <Controller
            name="hit_operator"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">(no threshold)</SelectItem>
                  <SelectItem value="lt">&lt; less than</SelectItem>
                  <SelectItem value="lte">≤ at most</SelectItem>
                  <SelectItem value="gt">&gt; greater than</SelectItem>
                  <SelectItem value="gte">≥ at least</SelectItem>
                  <SelectItem value="between">between (range)</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
          {watch("hit_operator") === "between" ? (
            <div className="flex items-end gap-1 flex-1 min-w-0">
              <Input
                {...register("hit_value_low")}
                placeholder="low"
                type="number"
                className="h-9 text-sm"
              />
              <span className="text-muted-foreground text-xs pb-2.5">and</span>
              <Input
                {...register("hit_value_high")}
                placeholder="high"
                type="number"
                className="h-9 text-sm"
              />
            </div>
          ) : watch("hit_operator") !== "none" ? (
            <Input
              {...register("hit_value")}
              placeholder="threshold"
              type="number"
              className="h-9 text-sm flex-1 min-w-0"
            />
          ) : null}
        </div>
      </div>

      {/* Qualifier handling — only at create time. */}
      {!isEdit && (
        <div className="space-y-1">
          <Label>Qualifier handling</Label>
          <Controller
            name="qualifier_handling"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="include_qualified">
                    Include qualified (&lt;, &gt;)
                  </SelectItem>
                  <SelectItem value="exclude_qualified">
                    Exclude qualified
                  </SelectItem>
                  <SelectItem value="treat_as_limit">Treat as limit</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>
      )}

      <div className="space-y-2 border rounded p-2">
        <Label className="text-xs uppercase text-muted-foreground">QC Filter</Label>
        <div className="flex items-center gap-2">
          <Controller
            name="require_approved"
            control={control}
            render={({ field }) => (
              <Checkbox
                checked={field.value}
                onCheckedChange={(v) => field.onChange(v === true)}
                id="require-approved"
              />
            )}
          />
          <label htmlFor="require-approved" className="text-sm cursor-pointer">
            Require approved run
          </label>
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <Label className="text-xs">Min Z&apos; prime</Label>
            <span className="text-xs font-mono tabular-nums text-muted-foreground">
              {watch("min_z_prime").toFixed(2)}{" "}
              {watch("min_z_prime") === 0 && (
                <span className="text-[10px] italic">(no filter)</span>
              )}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            {...register("min_z_prime", { valueAsNumber: true })}
            className="w-full"
          />
          <div className="flex justify-between text-[10px] text-muted-foreground tabular-nums">
            <span>0</span>
            <span>0.5</span>
            <span>1</span>
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={isPending}>
          {isPending ? "Saving..." : isEdit ? "Update" : "Add Channel"}
        </Button>
      </div>
    </form>
  );
}
