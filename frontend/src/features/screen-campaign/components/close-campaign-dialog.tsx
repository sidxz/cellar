"use client";

/**
 * CloseCampaignDialog — Task 16 (soft close, spec §4/§5).
 *
 * Confirms client-side: ≥1 result, ≥1 channel — mirrors the aggregate's own
 * `close()` guard so the chemist sees why before round-tripping a 422.
 * Just an optional note; no signature, no publish toggle.
 */

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Lock } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/shared/components/ui/badge";
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
import { Separator } from "@/shared/components/ui/separator";
import { Textarea } from "@/shared/components/ui/textarea";

import { useCloseCampaignApiV1CampaignsCampaignIdClosePost } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../hooks/use-campaigns";
import type { CampaignResponse } from "../types";

// ── Component ─────────────────────────────────────────────────────────────────

interface CloseCampaignDialogProps {
  campaign: CampaignResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CloseCampaignDialog({ campaign, open, onOpenChange }: CloseCampaignDialogProps) {
  const router = useRouter();
  const qc = useQueryClient();

  const [note, setNote] = useState("");

  const closeMutation = useCloseCampaignApiV1CampaignsCampaignIdClosePost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        onOpenChange(false);
        // Navigate to same route — campaign.status will be "closed", rendering CampaignView
        router.refresh();
      },
    },
  });

  const hasResults = campaign.results.length > 0;
  const hasChannels = campaign.channels.length > 0;
  const canClose = hasResults && hasChannels;

  const decisionCounts = campaign.results.reduce<Record<string, number>>((acc, r) => {
    acc[r.decision] = (acc[r.decision] ?? 0) + 1;
    return acc;
  }, {});

  const handleClose = () => {
    if (!canClose) return;
    closeMutation.mutate({
      campaignId: campaign.id,
      data: { note: note.trim() || null },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Lock className="h-5 w-5" />
            Close campaign
          </DialogTitle>
          <DialogDescription>
            Closing makes the campaign read-only. You can reopen it later with a reason.
          </DialogDescription>
        </DialogHeader>

        {/* Validation warnings */}
        {(!hasResults || !hasChannels) && (
          <div className="flex items-start gap-2 rounded bg-destructive/10 text-destructive p-3 text-sm">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              {!hasResults && <p>Campaign has no compound results.</p>}
              {!hasChannels && <p>Campaign has no readouts.</p>}
              <p className="mt-1 text-xs">
                Add at least one readout and one compound before closing.
              </p>
            </div>
          </div>
        )}

        {/* Summary card */}
        <div className="rounded border p-3 space-y-2 text-sm">
          <p className="font-semibold">{campaign.name}</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-muted-foreground text-xs">
            <span>Compounds</span>
            <span className="text-foreground font-medium">{campaign.results.length}</span>
            <span>Readouts</span>
            <span className="text-foreground font-medium">{campaign.channels.length}</span>
            <span>Source protocols</span>
            <span className="text-foreground font-medium">{campaign.source_protocols.length}</span>
          </div>

          {/* Decision breakdown */}
          {Object.entries(decisionCounts).length > 0 && (
            <>
              <Separator />
              <div className="flex flex-wrap gap-1">
                {Object.entries(decisionCounts).map(([d, count]) => (
                  <Badge key={d} variant="secondary" className="text-xs">
                    {count} {d}
                  </Badge>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Optional note */}
        <div className="space-y-1">
          <Label htmlFor="close-note">Note (optional)</Label>
          <Textarea
            id="close-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional context for whoever reopens or reviews this campaign…"
            rows={3}
          />
        </div>

        {closeMutation.error && (
          <p className="text-xs text-destructive">
            {String((closeMutation.error as { message?: string }).message ?? "An error occurred.")}
          </p>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!canClose || closeMutation.isPending}
            onClick={handleClose}
          >
            <Lock className="mr-2 h-4 w-4" />
            {closeMutation.isPending ? "Closing…" : "Close campaign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
