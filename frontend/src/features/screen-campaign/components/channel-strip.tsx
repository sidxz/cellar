"use client";

/**
 * ChannelStrip — Task 8.3
 *
 * Horizontal flex of channel chips + "+" button that opens a Popover for
 * adding / editing channels via AddChannelRequest / UpdateChannelRequest.
 */

import { useState } from "react";
import { Plus, Settings2, Trash2 } from "lucide-react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Checkbox } from "@/shared/components/ui/checkbox";
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog";

import { useProtocolSummaries, useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import {
  useAddCampaignChannelApiV1CampaignsCampaignIdChannelsPost,
  useUpdateCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdPatch,
  useRemoveCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdDelete,
} from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../lib/hooks";
import type { CampaignResponse, CampaignChannelResponse } from "../types";

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
  // Hit threshold — operator "" means "no threshold". For between, low/high; otherwise single value.
  hit_operator: z.enum(["", "lt", "lte", "gt", "gte", "between"]),
  hit_value: z.string(),
  hit_value_low: z.string(),
  hit_value_high: z.string(),
});

type ChannelFormValues = z.infer<typeof channelSchema>;

function parseHitThreshold(t: unknown):
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

// ── Channel form popover ──────────────────────────────────────────────────────

interface ChannelFormProps {
  campaignId: string;
  projectId: string;
  existing?: CampaignChannelResponse;
  onClose: () => void;
}

function ChannelForm({ campaignId, existing, onClose, projectId }: ChannelFormProps) {
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
    (existingHit?.operator as ChannelFormValues["hit_operator"] | undefined) ?? "";
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
    },
  });

  const watchedProtocol = watch("protocol_id");

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
    } else if (values.hit_operator) {
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
                <SelectTrigger className="w-36"><SelectValue placeholder="(no threshold)" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="">(no threshold)</SelectItem>
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
          ) : watch("hit_operator") ? (
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

// ── Main strip ────────────────────────────────────────────────────────────────

interface ChannelStripProps {
  campaign: CampaignResponse;
}

export function ChannelStrip({ campaign }: ChannelStripProps) {
  const qc = useQueryClient();
  const [openChipId, setOpenChipId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  const removeMutation = useRemoveCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdDelete({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
      },
    },
  });

  const sorted = [...campaign.channels].sort((a, b) => a.display_order - b.display_order);

  return (
    <div className="border-b px-3 py-2 flex items-center gap-2 flex-wrap min-h-[52px] bg-muted/30">
      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Channels
      </span>

      {sorted.map((ch) => (
        <Popover
          key={ch.id}
          open={openChipId === ch.id}
          onOpenChange={(o) => setOpenChipId(o ? ch.id : null)}
        >
          <PopoverTrigger asChild>
            <button
              className="inline-flex items-center gap-1 px-2 py-1 rounded-full border text-xs font-medium bg-background hover:bg-muted transition-colors"
              title={`${ch.label} — click to edit`}
            >
              <Settings2 className="h-3 w-3 text-muted-foreground" />
              {ch.label}
              <Badge variant="outline" className="text-[10px] px-1 py-0">
                {ch.source_kind === "dose_response_curve" ? "DR" : "Raw"}
              </Badge>
            </button>
          </PopoverTrigger>
          <PopoverContent className="p-4" align="start">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold">Edit channel</h4>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-7 w-7">
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Remove channel?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will delete &ldquo;{ch.label}&rdquo; and all its
                      measurements from the campaign.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      className="bg-destructive text-destructive-foreground"
                      onClick={() =>
                        removeMutation.mutate({ campaignId: campaign.id, channelId: ch.id })
                      }
                    >
                      Remove
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
            <ChannelForm
              campaignId={campaign.id}
              projectId={campaign.project_id}
              existing={ch}
              onClose={() => setOpenChipId(null)}
            />
          </PopoverContent>
        </Popover>
      ))}

      {/* Add channel */}
      <Popover open={addOpen} onOpenChange={setAddOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="icon" className="h-7 w-7 rounded-full">
            <Plus className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="p-4" align="start">
          <h4 className="text-sm font-semibold mb-3">Add channel</h4>
          <ChannelForm
            campaignId={campaign.id}
            projectId={campaign.project_id}
            onClose={() => setAddOpen(false)}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
