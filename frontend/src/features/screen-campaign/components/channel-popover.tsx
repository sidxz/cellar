"use client";

/**
 * ChannelPopoverForm — extracted from channel-strip.tsx (Task 8.3 → Task 2.5).
 *
 * Renders the add / edit channel form that lives inside a Popover.
 * Used by both the legacy ChannelStrip chip-strip and the new ChannelsSection.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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
import {
  interceptKeyId,
  interceptLabel,
  parseInterceptKeyId,
} from "@/features/screening-assay/lib/intercept-label";
import {
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
  /** Stringified `${kind}:${level}` id of the dose-response intercept this
   *  channel surfaces. "" = primary (also covers non-DR / single-intercept
   *  readouts, which have nothing to choose). Create-mode only — intercept
   *  identity is locked after creation, like source_kind. */
  intercept_key_id: z.string(),
  // Normalization layer for readout_data channels. "raw" sentinel maps to the
  // raw layer (NULL on the wire); any other value selects that formula.
  // Locked at create-time — Radix Select forbids empty-string values, hence
  // the explicit sentinel.
  normalization_applied: z.string(),
});

type ChannelFormValues = z.infer<typeof channelSchema>;

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
      // Create-mode only (see the Intercept field below) — edit mode never
      // reads or writes this, so there's no existing-channel default to derive.
      intercept_key_id: "",
      normalization_applied: existing?.normalization_applied ?? "raw",
    },
  });

  const watchedProtocol = watch("protocol_id");
  const watchedReadoutId = watch("readout_definition_id");

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

    if (isEdit && existing) {
      updateMutation.mutate({
        campaignId,
        channelId: existing.id,
        data: {
          label: values.label,
          selection_rule: values.selection_rule,
          qc_filter: qcFilter ?? null,
        },
      });
      return;
    }

    // Resolve the intercept_key for the new channel. Only meaningful for
    // dose-response channels — otherwise no curve exists to look up an
    // intercept on. The primary intercept is stored as `null` (terse wire
    // shape); only a chosen secondary intercept persists an explicit
    // `{kind, level}`.
    const computeInterceptKey = (): InterceptKey | null => {
      if (values.source_kind !== "dose_response_curve") return null;
      const parsed = parseInterceptKeyId(values.intercept_key_id);
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
        normalization_applied: normalizationApplied,
        // Channel-level intercept identity (Option A). Locked after
        // creation — a chemist wanting a different intercept creates a new
        // channel.
        intercept_key: computeInterceptKey(),
      },
    });
  };

  const isPending = addMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  const readouts = fullProtocol?.readout_definitions ?? [];
  const existingReadoutName = readouts.find((r) => r.id === existing?.readout_definition_id)?.name;

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

      {/* Which protocol readout this channel reads from — never editable
          after creation, so this is a plain locked line rather than a picker. */}
      {isEdit && existing && (
        <div className="text-xs text-muted-foreground">
          Protocol:{" "}
          <span className="font-medium text-foreground">
            {fullProtocol?.name ?? "…"} › {existingReadoutName ?? "…"}
          </span>
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

      {/* Intercept — create-mode only, DR-curve channels whose readout
          declares ≥2 intercepts (e.g. EC50 + EC90). Single-intercept and
          non-DR readouts have nothing to choose and implicitly target the
          primary. Locked after creation like source_kind: a chemist wanting
          a different intercept creates a new channel. */}
      {!isEdit &&
        (() => {
          const rd = readouts.find((r) => r.id === watchedReadoutId);
          const intercepts: InterceptSpec[] = rd?.dose_response_config?.intercepts ?? [];
          if (
            watch("source_kind") !== "dose_response_curve" ||
            rd?.data_type !== "dose_response" ||
            intercepts.length < 2
          ) {
            return null;
          }
          return (
            <div className="space-y-1">
              <Label>Intercept</Label>
              <Controller
                name="intercept_key_id"
                control={control}
                render={({ field }) => (
                  <Select
                    value={field.value || interceptKeyId(intercepts[0])}
                    onValueChange={field.onChange}
                  >
                    <SelectTrigger className="w-40">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {intercepts.map((spec, idx) => {
                        const id = interceptKeyId(spec);
                        return (
                          <SelectItem key={id} value={id}>
                            {interceptLabel(spec)}
                            {idx === 0 && (
                              <span className="ml-1 text-xs text-muted-foreground">(primary)</span>
                            )}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                )}
              />
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
