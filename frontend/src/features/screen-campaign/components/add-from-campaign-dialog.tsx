"use client";

/**
 * AddFromCampaignDialog
 *
 * Lets the user pick a source campaign (any status) and a decision filter
 * (selected / deferred / rejected), then bulk-adds matching compounds to
 * the current campaign. Shows {added, skipped} in a toast on success.
 */

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
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
import { campaignKeys, useCampaigns } from "../hooks/use-campaigns";

const DECISION_OPTIONS = [
  { value: "selected", label: "Selected" },
  { value: "deferred", label: "Deferred" },
  { value: "rejected", label: "Rejected" },
] as const;

interface AddFromCampaignDialogProps {
  campaignId: string;
  projectId: string;
  open: boolean;
  onClose: () => void;
}

export function AddFromCampaignDialog({
  campaignId,
  projectId,
  open,
  onClose,
}: AddFromCampaignDialogProps) {
  const qc = useQueryClient();
  const [sourceCampaignId, setSourceCampaignId] = useState("");
  const [decisionFilter, setDecisionFilter] = useState<string[]>(["selected"]);
  const [description, setDescription] = useState("");

  const { data: allCampaigns, isLoading: campaignsLoading } = useCampaigns(projectId, {
    enabled: open,
  });

  // Exclude current campaign from picker
  const sourceCampaigns = allCampaigns?.filter((c) => c.id !== campaignId) ?? [];

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
    setDecisionFilter(["selected"]);
    setDescription("");
    onClose();
  };

  const toggleDecision = (value: string) => {
    setDecisionFilter((prev) =>
      prev.includes(value) ? prev.filter((d) => d !== value) : [...prev, value],
    );
  };

  const handleSubmit = () => {
    if (!sourceCampaignId || decisionFilter.length === 0) return;
    mutation.mutate({
      campaignId,
      data: {
        source_campaign_id: sourceCampaignId,
        decision_filter: decisionFilter,
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
            Pick a source campaign and which decisions to include. Duplicates are skipped
            automatically.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Source campaign *</Label>
            <Select
              value={sourceCampaignId}
              onValueChange={setSourceCampaignId}
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

          <div className="space-y-2">
            <Label>Include compounds with decision</Label>
            <div className="flex gap-4">
              {DECISION_OPTIONS.map((opt) => (
                <div key={opt.value} className="flex items-center gap-1.5">
                  <Checkbox
                    id={`decision-${opt.value}`}
                    checked={decisionFilter.includes(opt.value)}
                    onCheckedChange={() => toggleDecision(opt.value)}
                  />
                  <label htmlFor={`decision-${opt.value}`} className="text-sm cursor-pointer">
                    {opt.label}
                  </label>
                </div>
              ))}
            </div>
            {decisionFilter.length === 0 && (
              <p className="text-xs text-destructive">Select at least one decision type.</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="add-campaign-desc">Note (optional)</Label>
            <Textarea
              id="add-campaign-desc"
              placeholder="e.g. Selected hits from EGFR round 1"
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
            disabled={!sourceCampaignId || decisionFilter.length === 0 || mutation.isPending}
            onClick={handleSubmit}
          >
            {mutation.isPending ? "Adding…" : "Add compounds"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
