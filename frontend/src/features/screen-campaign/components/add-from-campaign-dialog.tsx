"use client";

/**
 * AddFromCampaignDialog
 *
 * Lets the user pick a source campaign (any status) and — optionally — one of
 * its hit stages, then bulk-adds the matching compounds to the current
 * campaign. No stage means every compound on the source; a stage means the
 * compounds whose evaluated outcome at that stage is a hit (overrides
 * honoured server-side). Shows {added, skipped} in a toast on success.
 */

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { useAddResultsFromCampaignApiV1CampaignsCampaignIdAddFromCampaignPost } from "@/shared/lib/api/campaigns/campaigns";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { campaignKeys, useCampaign, useCampaigns } from "../hooks/use-campaigns";

/** Sentinel for "no stage" — Radix <Select> forbids an empty-string value. */
const ALL_COMPOUNDS = "__all__";

interface AddFromCampaignDialogProps {
  campaignId: string;
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddFromCampaignDialog({
  campaignId,
  projectId,
  open,
  onOpenChange,
}: AddFromCampaignDialogProps) {
  const qc = useQueryClient();
  const [sourceCampaignId, setSourceCampaignId] = useState("");
  const [stageId, setStageId] = useState(ALL_COMPOUNDS);
  const [description, setDescription] = useState("");

  const { data: allCampaigns, isLoading: campaignsLoading } = useCampaigns(projectId, {
    enabled: open,
  });

  // Exclude current campaign from picker
  const sourceCampaigns = allCampaigns?.filter((c) => c.id !== campaignId) ?? [];

  // The source campaign's stages only arrive with its detail payload.
  const { data: sourceCampaign, isLoading: stagesLoading } = useCampaign(sourceCampaignId, {
    enabled: !!sourceCampaignId,
  });
  const stages = sourceCampaign?.stages ?? [];

  const mutation = useAddResultsFromCampaignApiV1CampaignsCampaignIdAddFromCampaignPost({
    mutation: {
      onSuccess: (result) => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        const sourceName =
          sourceCampaigns.find((c) => c.id === sourceCampaignId)?.name ?? "campaign";
        showSuccess(
          `Added ${result.added} compound${result.added !== 1 ? "s" : ""} from "${sourceName}". ` +
            `${result.skipped} were already on this campaign.`,
        );
        handleClose();
      },
      onError: () => {
        showError("Failed to add compounds from campaign.");
      },
    },
  });

  const handleClose = () => {
    setSourceCampaignId("");
    setStageId(ALL_COMPOUNDS);
    setDescription("");
    onOpenChange(false);
  };

  // A stage belongs to exactly one campaign — changing the source invalidates
  // the pick, so fall back to "all compounds" rather than send a 422.
  const handleSourceChange = (id: string) => {
    setSourceCampaignId(id);
    setStageId(ALL_COMPOUNDS);
  };

  const handleSubmit = () => {
    if (!sourceCampaignId) return;
    mutation.mutate({
      campaignId,
      data: {
        source_campaign_id: sourceCampaignId,
        stage_id: stageId === ALL_COMPOUNDS ? null : stageId,
        description: description.trim() || undefined,
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add compounds from another Campaign</DialogTitle>
          <DialogDescription>
            Pick a source campaign, and optionally a stage to take only its hits. Duplicates are
            skipped automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Source campaign *</Label>
            <Select
              value={sourceCampaignId}
              onValueChange={handleSourceChange}
              disabled={campaignsLoading}
            >
              <SelectTrigger>
                <SelectValue placeholder={campaignsLoading ? "Loading…" : "Select a campaign…"} />
              </SelectTrigger>
              <SelectContent>
                {sourceCampaigns.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                    <span className="ml-2 text-xs text-muted-foreground capitalize">
                      ({c.status})
                    </span>
                  </SelectItem>
                ))}
                {!campaignsLoading && sourceCampaigns.length === 0 && (
                  <SelectItem value="__none__" disabled>
                    No other campaigns in workspace
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>Compounds to include</Label>
            <Select
              value={stageId}
              onValueChange={setStageId}
              disabled={!sourceCampaignId || stagesLoading}
            >
              <SelectTrigger>
                <SelectValue placeholder={stagesLoading ? "Loading…" : "All compounds"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_COMPOUNDS}>All compounds</SelectItem>
                {stages.map((st) => (
                  <SelectItem key={st.id} value={st.id}>
                    Hits at "{st.name}"
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!!sourceCampaignId && !stagesLoading && stages.length === 0 && (
              <p className="text-xs text-muted-foreground">
                That campaign has no hit stages — all its compounds will be added.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="add-campaign-desc">Note (optional)</Label>
            <Textarea
              id="add-campaign-desc"
              placeholder="e.g. Confirmed hits from EGFR round 1"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!sourceCampaignId || mutation.isPending}
            onClick={handleSubmit}
          >
            {mutation.isPending ? "Adding…" : "Add compounds"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
