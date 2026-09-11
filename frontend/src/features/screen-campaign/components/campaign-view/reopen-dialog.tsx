"use client";

/**
 * ReopenDialog — Task 16 (spec §4).
 *
 * Moves a CLOSED campaign back to DRAFT. Requires a reason (audited via
 * `CampaignReopened`). Mirrors the shape of the run "Unlock" dialog in
 * `screening-assay/components/run-detail.tsx`.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

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
import { Textarea } from "@/shared/components/ui/textarea";
import { showSuccess } from "@/shared/lib/toast";

import { useReopenCampaignApiV1CampaignsCampaignIdReopenPost } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../../hooks/use-campaigns";
import type { CampaignResponse } from "../../types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface ReopenDialogProps {
  campaign: CampaignResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ReopenDialog({ campaign, open, onOpenChange }: ReopenDialogProps) {
  const router = useRouter();
  const qc = useQueryClient();
  const [reason, setReason] = useState("");

  const reopenMutation = useReopenCampaignApiV1CampaignsCampaignIdReopenPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        setReason("");
        onOpenChange(false);
        showSuccess("Campaign reopened");
        // Navigate to same route — campaign.status will be "draft", rendering the builder
        router.refresh();
      },
    },
  });

  const handleReopen = () => {
    if (!reason.trim()) return;
    reopenMutation.mutate({ campaignId: campaign.id, data: { reason: reason.trim() } });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reopen campaign</DialogTitle>
          <DialogDescription>
            Provide a reason for reopening this campaign. It moves back to draft and becomes
            editable again.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Reason</Label>
            <Textarea
              placeholder="Reason for reopening…"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
        </div>

        {reopenMutation.error && (
          <p className="text-xs text-destructive">
            {String((reopenMutation.error as { message?: string }).message ?? "An error occurred.")}
          </p>
        )}

        <DialogFooter>
          <Button onClick={handleReopen} disabled={!reason.trim() || reopenMutation.isPending}>
            {reopenMutation.isPending ? "Reopening…" : "Reopen campaign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
