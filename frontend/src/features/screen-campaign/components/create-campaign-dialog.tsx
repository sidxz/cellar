"use client";

/**
 * CreateCampaignDialog — Task 8.1
 *
 * RHF + Zod form. Fields: name, description, publishes_collection,
 * compound_source (via CompoundSourcePicker tabs).
 * On submit: POSTs to /api/v1/campaigns and navigates to the builder.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Textarea } from "@/shared/components/ui/textarea";

import { useCreateCampaignApiV1CampaignsPost } from "@/shared/lib/api/campaigns/campaigns";
import { CompoundSourcePicker, type CompoundSourceValue } from "./compound-source-picker";

// ── Schema ────────────────────────────────────────────────────────────────────

const schema = z.object({
  name: z.string().min(1, "Name is required").max(200),
  description: z.string().max(2000).optional(),
  publishes_collection: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

// ── Props ─────────────────────────────────────────────────────────────────────

interface CreateCampaignDialogProps {
  projectId: string;
  trigger?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Pre-fill the supersedes_campaign_id field (e.g. when opened from SupersedeDialog). */
  defaultSupersedesCampaignId?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CreateCampaignDialog({
  projectId,
  trigger,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
  defaultSupersedesCampaignId,
}: CreateCampaignDialogProps) {
  const router = useRouter();
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const [source, setSource] = useState<CompoundSourceValue | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);

  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;
  const setOpen = isControlled
    ? (controlledOnOpenChange ?? (() => {}))
    : setUncontrolledOpen;

  const mutation = useCreateCampaignApiV1CampaignsPost();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      description: "",
      publishes_collection: true,
    },
  });

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      reset();
      setSource(null);
      setSourceError(null);
    }
    setOpen(next);
  };

  const onSubmit = async (values: FormValues) => {
    if (!source) {
      setSourceError("Please select a compound source.");
      return;
    }
    setSourceError(null);

    const result = await mutation.mutateAsync({
      data: {
        name: values.name,
        description: values.description || undefined,
        project_id: projectId,
        compound_source: source as Parameters<typeof mutation.mutateAsync>[0]["data"]["compound_source"],
        publishes_collection: values.publishes_collection,
        supersedes_campaign_id: defaultSupersedesCampaignId ?? undefined,
      },
    });

    handleOpenChange(false);
    router.push(`/projects/${projectId}/campaigns/${result.id}`);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}

      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Campaign</DialogTitle>
          <DialogDescription>
            Define a screening campaign by naming it and selecting its compound
            source. Channels are added in the builder.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="campaign-name">Name *</Label>
            <Input
              id="campaign-name"
              placeholder="e.g. Kinase Panel Q2 2026"
              {...register("name")}
            />
            {errors.name && (
              <p className="text-xs text-destructive">{errors.name.message}</p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label htmlFor="campaign-desc">Description</Label>
            <Textarea
              id="campaign-desc"
              placeholder="Optional campaign description..."
              rows={2}
              {...register("description")}
            />
          </div>

          {/* Publishes collection */}
          <div className="flex items-center gap-2">
            <Controller
              name="publishes_collection"
              control={control}
              render={({ field }) => (
                <Checkbox
                  id="publishes-collection"
                  checked={field.value}
                  onCheckedChange={(v) => field.onChange(v === true)}
                />
              )}
            />
            <Label htmlFor="publishes-collection" className="cursor-pointer">
              Publish a frozen Collection on close
            </Label>
          </div>

          {/* Source picker */}
          <div className="space-y-1.5">
            <Label>Compound source *</Label>
            <CompoundSourcePicker
              projectId={projectId}
              value={source}
              onChange={(v) => {
                setSource(v);
                if (v) setSourceError(null);
              }}
            />
            {sourceError && (
              <p className="text-xs text-destructive">{sourceError}</p>
            )}
          </div>

          {mutation.error && (
            <p className="text-xs text-destructive">
              {String((mutation.error as { message?: string }).message ?? "An error occurred")}
            </p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || mutation.isPending}>
              {mutation.isPending ? "Creating..." : "Create Campaign"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
