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
  source_kind: z.enum(["readout", "curve"]),
  selection_rule: z.enum(["best", "all", "most_recent"]),
  qualifier_handling: z.enum(["numeric", "threshold", "exclude"]),
  require_approved: z.boolean(),
  min_z_prime: z.number().min(0).max(1),
});

type ChannelFormValues = z.infer<typeof channelSchema>;

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
      source_kind: (existing?.source_kind as "readout" | "curve") ?? "readout",
      selection_rule: (existing?.selection_rule as "best" | "all" | "most_recent") ?? "best",
      qualifier_handling: (existing?.qualifier_handling as "numeric" | "threshold" | "exclude") ?? "numeric",
      require_approved: (existingQc?.require_approved as boolean | undefined) ?? false,
      min_z_prime: (existingQc?.min_z_prime as number | undefined) ?? 0,
    },
  });

  const watchedProtocol = watch("protocol_id");

  const onSubmit = (values: ChannelFormValues) => {
    const qcFilter = values.require_approved || values.min_z_prime > 0
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
        },
      });
    }
  };

  const isPending = addMutation.isPending || updateMutation.isPending;

  const readouts = fullProtocol?.readout_definitions ?? [];

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3 min-w-[300px]">
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

      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label>Source</Label>
          <Controller
            name="source_kind"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="readout">Readout data</SelectItem>
                  <SelectItem value="curve">Dose-response curve</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>
        <div className="space-y-1">
          <Label>Selection</Label>
          <Controller
            name="selection_rule"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="best">Best</SelectItem>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="most_recent">Most recent</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </div>
      </div>

      <div className="space-y-1">
        <Label>Qualifier handling</Label>
        <Controller
          name="qualifier_handling"
          control={control}
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="numeric">Numeric</SelectItem>
                <SelectItem value="threshold">Threshold</SelectItem>
                <SelectItem value="exclude">Exclude</SelectItem>
              </SelectContent>
            </Select>
          )}
        />
      </div>

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
          <Label className="text-xs">
            Min Z&apos; prime: {watch("min_z_prime").toFixed(2)}
          </Label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            {...register("min_z_prime", { valueAsNumber: true })}
            className="w-full"
          />
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
                {ch.source_kind === "curve" ? "DR" : "Raw"}
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
