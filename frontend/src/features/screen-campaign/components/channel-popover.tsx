"use client";

/**
 * ChannelPopoverForm — extracted from channel-strip.tsx (Task 8.3 → Task 2.5).
 *
 * Renders the add / edit channel form that lives inside a Popover.
 * Used by both the legacy ChannelStrip chip-strip and the new ChannelsSection.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";

import { useProtocol, useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import { channelUnit } from "@/features/screening-assay/lib/channel-unit";
import { deriveChannelHitDefaults } from "@/features/screening-assay/lib/hit-criteria-defaults";
import {
  interceptKeyId,
  interceptLabel,
  narrowInterceptKey,
  parseInterceptKeyId,
} from "@/features/screening-assay/lib/intercept-label";
import {
  type HitCriterion,
  type InterceptKey,
  type InterceptSpec,
  READOUT_NORMALIZATION_LABELS,
} from "@/features/screening-assay/types";
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
import {
  useAddCampaignChannelApiV1CampaignsCampaignIdChannelsPost,
  useRemoveCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdDelete,
  useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch,
} from "@/shared/lib/api/campaigns/campaigns";
import { Trash2 } from "lucide-react";
import { campaignKeys } from "../hooks/use-campaigns";
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
  qualifier_handling: z.enum(["include_qualified", "exclude_qualified", "treat_as_limit"]),
  require_approved: z.boolean(),
  min_z_prime: z.number().min(0).max(1),
  // Hit threshold — operator "none" means "no threshold". For between, low/high; otherwise single value.
  // (Radix Select forbids empty-string values, hence the explicit "none" sentinel.)
  hit_operator: z.enum(["none", "lt", "lte", "gt", "gte", "between"]),
  hit_value: z.string(),
  hit_value_low: z.string(),
  hit_value_high: z.string(),
  /** Stringified `${kind}:${level}` id of the dose-response intercept the
   *  threshold compares against. Empty string when the readout has no
   *  intercepts (legacy / non-DR). Resolved to the primary's id at form
   *  init when no existing channel state is present. */
  hit_intercept_key: z.string(),
  // Normalization layer for readout_data channels. "raw" sentinel maps to the
  // raw layer (NULL on the wire); any other value selects that formula.
  // Locked at create-time — Radix Select forbids empty-string values, hence
  // the explicit sentinel.
  normalization_applied: z.string(),
});

type ChannelFormValues = z.infer<typeof channelSchema>;

// ── Helper ────────────────────────────────────────────────────────────────────

export function parseHitThreshold(
  t: unknown,
): { operator: string; value: number | number[]; intercept_key: InterceptKey | null } | null {
  if (!t || typeof t !== "object") return null;
  const obj = t as {
    operator?: string;
    value?: unknown;
    intercept_key?: { kind?: unknown; level?: unknown } | null;
  };
  if (!obj.operator) return null;

  // Defensive parse of intercept_key — legacy channels saved before
  // Surface #7 (commit db04e938) have no field at all; primary-targeting
  // channels store explicit null; secondary-targeting channels store
  // `{kind, level}`. Treat the first two cases identically.
  let intercept_key: InterceptKey | null = null;
  if (obj.intercept_key && typeof obj.intercept_key === "object") {
    const ik = obj.intercept_key;
    if ((ik.kind === "ec" || ik.kind === "ic") && typeof ik.level === "number") {
      intercept_key = { kind: ik.kind, level: ik.level };
    }
  }

  if (typeof obj.value === "number") {
    return { operator: obj.operator, value: obj.value, intercept_key };
  }
  if (Array.isArray(obj.value) && obj.value.every((v) => typeof v === "number")) {
    return { operator: obj.operator, value: obj.value as number[], intercept_key };
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
  const [selectedProtocolId, setSelectedProtocolId] = useState<string>(existing?.protocol_id ?? "");
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
  const deleteMutation = useRemoveCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdDelete({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
    },
  });
  const [confirmDelete, setConfirmDelete] = useState(false);

  const isEdit = !!existing;

  // Parse existing qc_filter — it's typed as `{ [key: string]: unknown } | null`
  const existingQc = existing?.qc_filter as Record<string, unknown> | null | undefined;
  // Parse existing hit_threshold once per `existing` ref change. Memoizing
  // gives us a stable identity so the edit-mode useEffect below can take
  // it as a dep without re-firing every render (parseHitThreshold returns
  // a fresh object each call).
  const existingHit = useMemo(() => parseHitThreshold(existing?.hit_threshold), [existing]);
  const defaultHitOperator: ChannelFormValues["hit_operator"] =
    (existingHit?.operator as ChannelFormValues["hit_operator"] | undefined) ?? "none";
  const defaultHitValue =
    existingHit && typeof existingHit.value === "number" ? String(existingHit.value) : "";
  const defaultHitLow =
    existingHit && Array.isArray(existingHit.value) ? String(existingHit.value[0]) : "";
  const defaultHitHigh =
    existingHit && Array.isArray(existingHit.value) ? String(existingHit.value[1]) : "";
  // Default to the channel's own intercept_key (post-Option-A: top-level
  // field). Falls back to the threshold's intercept_key for legacy data
  // saved before the channel-level field existed. Primary-targeting
  // channels carry null in both — those fall through to "" here and get
  // resolved to the protocol's primary intercept id by the useEffect
  // below once fullProtocol arrives.
  const persistedInterceptKey =
    narrowInterceptKey(existing?.intercept_key) ?? existingHit?.intercept_key ?? null;
  const defaultHitInterceptKey = persistedInterceptKey ? interceptKeyId(persistedInterceptKey) : "";

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
        (existing?.source_kind as "readout_data" | "dose_response_curve") ?? "readout_data",
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
      hit_intercept_key: defaultHitInterceptKey,
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
      (defaults.hit_operator === ""
        ? "none"
        : defaults.hit_operator) as ChannelFormValues["hit_operator"],
    );
    setValue("hit_value", defaults.hit_value);
    setValue("hit_value_low", defaults.hit_value_low);
    setValue("hit_value_high", defaults.hit_value_high);

    // Intercept picker: prefer the carried-forward key from the matching
    // recommendation; fall back to the readout's primary intercept so the
    // picker isn't blank. Empty when the readout declares no intercepts.
    const intercepts = rd.dose_response_config?.intercepts ?? [];
    if (intercepts.length === 0) {
      setValue("hit_intercept_key", "");
    } else if (defaults.intercept_key) {
      setValue("hit_intercept_key", interceptKeyId(defaults.intercept_key));
    } else {
      setValue("hit_intercept_key", interceptKeyId(intercepts[0]));
    }
  }, [watchedReadoutId, existing, fullProtocol, setValue]);

  // Edit mode: once fullProtocol resolves, fill `hit_intercept_key` with
  // the channel's persisted key (post-Option-A: top-level; falls back to
  // the threshold's for legacy) OR the readout's primary — needed because
  // we can't compute the primary's id at defaultValues time (the protocol
  // fetch is async).
  useEffect(() => {
    if (!existing) return;
    if (!fullProtocol?.readout_definitions) return;
    const rd = fullProtocol.readout_definitions.find(
      (r) => r.id === existing.readout_definition_id,
    );
    const intercepts = rd?.dose_response_config?.intercepts ?? [];
    if (intercepts.length === 0) {
      setValue("hit_intercept_key", "");
      return;
    }
    const persisted =
      narrowInterceptKey(existing.intercept_key) ?? existingHit?.intercept_key ?? null;
    setValue(
      "hit_intercept_key",
      persisted ? interceptKeyId(persisted) : interceptKeyId(intercepts[0]),
    );
  }, [fullProtocol, existing, existingHit, setValue]);

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

  // Auto-derive source_kind from the readout's data_type (create mode only).
  // A DR-typed readout means the chemist wants the fitted curve (EC50/EC90);
  // anything else (numeric / pick_list / ...) means the raw readout value.
  // The previous "Source" dropdown asked chemists a redundant question — the
  // answer is determined by the readout they picked one step up. Single
  // edge case (chemist wants the raw % inhibition layer of a DR readout)
  // is served by creating a separate non-DR readout for that snapshot view.
  useEffect(() => {
    if (existing) return;
    if (!watchedReadoutId || !fullProtocol?.readout_definitions) return;
    const rd = fullProtocol.readout_definitions.find((r) => r.id === watchedReadoutId);
    if (!rd) return;
    setValue(
      "source_kind",
      rd.data_type === "dose_response" ? "dose_response_curve" : "readout_data",
    );
  }, [watchedReadoutId, existing, fullProtocol, setValue]);

  const onSubmit = (values: ChannelFormValues) => {
    const qcFilter =
      values.require_approved || values.min_z_prime > 0
        ? { require_approved: values.require_approved, min_z_prime: values.min_z_prime }
        : undefined;

    // Resolve the intercept_key for the persisted threshold. Only meaningful
    // when the channel reads from a dose-response curve — otherwise no curve
    // exists to look up an intercept on. Per Surface #7's convention, the
    // primary intercept is stored as `null` (terse wire shape); only
    // secondary intercepts persist an explicit `{kind, level}`. This keeps
    // legacy channels coherent and tracks the protocol's current primary
    // if intercepts are reordered later.
    const computeInterceptKey = (): InterceptKey | null => {
      if (values.source_kind !== "dose_response_curve") return null;
      const parsed = parseInterceptKeyId(values.hit_intercept_key);
      if (!parsed) return null;
      const rd = fullProtocol?.readout_definitions?.find(
        (r) => r.id === values.readout_definition_id,
      );
      const primary = rd?.dose_response_config?.intercepts?.[0];
      if (primary && parsed.kind === primary.kind && parsed.level === primary.level) {
        return null;
      }
      return parsed;
    };

    // Build hit_threshold from split form fields. "" = no threshold.
    let hitThreshold: {
      readout_name: string;
      operator: string;
      value: number | number[];
      intercept_key: InterceptKey | null;
    } | null = null;
    if (values.hit_operator === "between") {
      const low = values.hit_value_low === "" ? null : Number(values.hit_value_low);
      const high = values.hit_value_high === "" ? null : Number(values.hit_value_high);
      if (
        low !== null &&
        !Number.isNaN(low) &&
        high !== null &&
        !Number.isNaN(high) &&
        low <= high
      ) {
        hitThreshold = {
          readout_name: values.label,
          operator: "between",
          value: [low, high],
          intercept_key: computeInterceptKey(),
        };
      }
    } else if (values.hit_operator !== "none") {
      const num = values.hit_value === "" ? null : Number(values.hit_value);
      if (num !== null && !Number.isNaN(num)) {
        hitThreshold = {
          readout_name: values.label,
          operator: values.hit_operator,
          value: num,
          intercept_key: computeInterceptKey(),
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
          // Channel-level intercept identity (Option A). Survives the wire
          // even when hit_threshold is null (display-only channel for a
          // secondary intercept).
          intercept_key: computeInterceptKey(),
        },
      });
    }
  };

  const isPending = addMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

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
            {errors.protocol_id && (
              <p className="text-xs text-destructive">{errors.protocol_id.message}</p>
            )}
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

      {/* Source is auto-derived from the readout's data_type — DR-typed
          readouts route to the fitted curve, everything else to readout
          data. The dropdown was redundant noise. Edit mode shows the
          frozen value as a hint so chemists know what's locked in. */}
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
      {!isEdit &&
        watch("source_kind") === "readout_data" &&
        (() => {
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
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="raw">Raw (no normalization)</SelectItem>
                      {norms.map((n) => (
                        <SelectItem key={n} value={n}>
                          {READOUT_NORMALIZATION_LABELS[
                            n as keyof typeof READOUT_NORMALIZATION_LABELS
                          ] ?? n}
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
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="latest_approved_run">Latest approved run</SelectItem>
                <SelectItem value="mean_across_runs">Mean across runs</SelectItem>
                <SelectItem value="geometric_mean">Geometric mean</SelectItem>
                <SelectItem value="manual_pick">Manual pick</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
      </div>

      {/* Hit threshold — operator + value(s). Drives the hit/miss chip on each cell.
          Show the channel's unit suffix + a "Hit if … > N %" caption so chemists
          can see at a glance what value the threshold compares against. */}
      {(() => {
        const rd = fullProtocol?.readout_definitions?.find((r) => r.id === watchedReadoutId);
        const sourceKind = watch("source_kind");
        const normValue = watch("normalization_applied");
        const normalization =
          sourceKind === "readout_data" && normValue && normValue !== "raw" ? normValue : null;
        const unit = channelUnit({
          sourceKind,
          rawUnit: rd?.unit ?? null,
          normalization,
          doseUnit: fullProtocol?.dose_unit ?? null,
        });
        const label = watch("label");
        const op = watch("hit_operator");
        const opSym: Record<string, string> = {
          lt: "<",
          lte: "≤",
          gt: ">",
          gte: "≥",
        };
        const single = watch("hit_value");
        const lo = watch("hit_value_low");
        const hi = watch("hit_value_high");

        // Intercept picker — DR-curve channels with ≥2 declared intercepts
        // get a "EC50 / EC90 / IC10" selector inline with the operator
        // dropdown. Single-intercept readouts implicitly target the primary
        // (= the only one) so no picker is needed. Non-DR channels read raw
        // values; intercepts don't apply.
        const intercepts: InterceptSpec[] = rd?.dose_response_config?.intercepts ?? [];
        const showInterceptPicker =
          op !== "none" &&
          sourceKind === "dose_response_curve" &&
          rd?.data_type === "dose_response" &&
          intercepts.length >= 2;
        const interceptKeyVal = watch("hit_intercept_key");
        const selectedSpec = (() => {
          const parsed = parseInterceptKeyId(interceptKeyVal);
          if (!parsed) return null;
          return intercepts.find((s) => s.kind === parsed.kind && s.level === parsed.level) ?? null;
        })();
        const interceptText =
          showInterceptPicker && selectedSpec ? ` ${interceptLabel(selectedSpec)}` : "";

        let caption: string | null = null;
        if (op === "between") {
          if (lo.trim() && hi.trim() && !Number.isNaN(Number(lo)) && !Number.isNaN(Number(hi))) {
            caption = `Hit if ${label || "value"}${interceptText} is between ${lo} and ${hi}${unit ? ` ${unit}` : ""}`;
          }
        } else if (op !== "none" && single.trim() && !Number.isNaN(Number(single))) {
          const sym = opSym[op] ?? op;
          caption = `Hit if ${label || "value"}${interceptText} ${sym} ${single}${unit ? ` ${unit}` : ""}`;
        }
        return (
          <div className="space-y-1">
            <Label>Hit threshold</Label>
            <div className="flex items-end gap-2 flex-wrap">
              {showInterceptPicker && (
                <Controller
                  name="hit_intercept_key"
                  control={control}
                  render={({ field }) => (
                    <Select
                      value={field.value || interceptKeyId(intercepts[0])}
                      onValueChange={field.onChange}
                    >
                      <SelectTrigger className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {intercepts.map((spec, idx) => {
                          const id = interceptKeyId(spec);
                          return (
                            <SelectItem key={id} value={id}>
                              {interceptLabel(spec)}
                              {idx === 0 && (
                                <span className="ml-1 text-xs text-muted-foreground">
                                  (primary)
                                </span>
                              )}
                            </SelectItem>
                          );
                        })}
                      </SelectContent>
                    </Select>
                  )}
                />
              )}
              <Controller
                name="hit_operator"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger className="w-36">
                      <SelectValue />
                    </SelectTrigger>
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
              {op === "between" ? (
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
                  {unit && <span className="text-muted-foreground text-xs pb-2.5">{unit}</span>}
                </div>
              ) : op !== "none" ? (
                <div className="flex items-end gap-1 flex-1 min-w-0">
                  <Input
                    {...register("hit_value")}
                    placeholder="threshold"
                    type="number"
                    className="h-9 text-sm flex-1 min-w-0"
                  />
                  {unit && <span className="text-muted-foreground text-xs pb-2.5">{unit}</span>}
                </div>
              ) : null}
            </div>
            {caption && <p className="text-[11px] text-muted-foreground italic">{caption}</p>}
          </div>
        );
      })()}

      {/* Qualifier handling — only at create time. */}
      {!isEdit && (
        <div className="space-y-1">
          <Label>Qualifier handling</Label>
          <Controller
            name="qualifier_handling"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="include_qualified">Include qualified (&lt;, &gt;)</SelectItem>
                  <SelectItem value="exclude_qualified">Exclude qualified</SelectItem>
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
            {isPending ? "Saving..." : isEdit ? "Update" : "Add Readout"}
          </Button>
        </div>
      </div>

      {/* Deleting a channel drops every measurement under it across all
          results. Reversible only by re-adding (with a different id) +
          re-resolving — make the chemist confirm explicitly. */}
      {isEdit && existing && (
        <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete readout "{existing.label}"?</AlertDialogTitle>
              <AlertDialogDescription>
                This removes the readout and every measurement it produced across all results in
                this campaign. You can re-add the same readout afterwards, but the new one will have
                a fresh id — manual overrides on it will not carry over.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={() =>
                  deleteMutation.mutate({
                    campaignId,
                    channelId: existing.id,
                  })
                }
              >
                Delete channel
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </form>
  );
}
