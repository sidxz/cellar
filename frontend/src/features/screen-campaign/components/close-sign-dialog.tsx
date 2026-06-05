"use client";

/**
 * CloseSignDialog — Task 8.7
 *
 * Confirms client-side: ≥1 result, ≥1 channel.
 * Summary card + toggle for publishesCollection.
 *
 * E-signature step: useReauthenticate() does not exist in this codebase.
 * STUB: user types their name; signatureId = crypto.randomUUID().
 * TODO: replace with real re-authentication hook when available.
 */

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Lock } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/shared/components/ui/badge";
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
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Separator } from "@/shared/components/ui/separator";

import { useCloseCampaignApiV1CampaignsCampaignIdClosePost } from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../hooks/use-campaigns";
import type { CampaignResponse } from "../types";

// ── Component ─────────────────────────────────────────────────────────────────

interface CloseSignDialogProps {
  campaign: CampaignResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CloseSignDialog({ campaign, open, onOpenChange }: CloseSignDialogProps) {
  const router = useRouter();
  const qc = useQueryClient();

  const [publishCollection, setPublishCollection] = useState(campaign.publishes_collection);
  const [signerName, setSignerName] = useState("");
  const [sigMeaning, setSigMeaning] = useState(
    "I certify that this campaign data is accurate and complete.",
  );

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
  const canClose = hasResults && hasChannels && signerName.trim().length > 0;

  const decisionCounts = campaign.results.reduce<Record<string, number>>((acc, r) => {
    acc[r.decision] = (acc[r.decision] ?? 0) + 1;
    return acc;
  }, {});

  const handleClose = () => {
    if (!canClose) return;

    // STUB: useReauthenticate() is not available — generate a random signatureId.
    // TODO: replace with actual re-auth hook once implemented.
    const signatureId = crypto.randomUUID();

    closeMutation.mutate({
      campaignId: campaign.id,
      data: {
        signature_id: signatureId,
        signature_meaning: sigMeaning,
        // Override the campaign's stored value at sign time — chemists pick
        // this fresh on close instead of trying to remember the create-time
        // toggle.
        publishes_collection: publishCollection,
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Lock className="h-5 w-5" />
            Close &amp; Sign Campaign
          </DialogTitle>
          <DialogDescription>
            This action is irreversible. The campaign will be locked and a frozen Collection will be
            published if enabled.
          </DialogDescription>
        </DialogHeader>

        {/* Validation warnings */}
        {(!hasResults || !hasChannels) && (
          <div className="flex items-start gap-2 rounded bg-destructive/10 text-destructive p-3 text-sm">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              {!hasResults && <p>Campaign has no compound results.</p>}
              {!hasChannels && <p>Campaign has no channels.</p>}
              <p className="mt-1 text-xs">
                Add at least one channel and one compound before closing.
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
            <span>Channels</span>
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

        {/* Publish collection toggle */}
        <div className="flex items-center gap-2">
          <Checkbox
            id="publish-collection-close"
            checked={publishCollection}
            onCheckedChange={(v) => setPublishCollection(v === true)}
          />
          <Label htmlFor="publish-collection-close" className="cursor-pointer">
            Publish frozen Collection on close
          </Label>
        </div>

        {/* E-signature step (stub) */}
        <div className="space-y-2 rounded border p-3">
          <p className="text-xs font-semibold uppercase text-muted-foreground">
            Electronic Signature
          </p>
          <p className="text-xs text-muted-foreground">
            {/* TODO: replace with useReauthenticate() when available */}
            Type your full name to sign. A unique signature ID is generated client-side as a stub —
            integrate with the re-authentication service in a follow-up.
          </p>
          <div className="space-y-1">
            <Label htmlFor="signer-name">Full name</Label>
            <Input
              id="signer-name"
              value={signerName}
              onChange={(e) => setSignerName(e.target.value)}
              placeholder="Your full name"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="sig-meaning">Signature meaning</Label>
            <Input
              id="sig-meaning"
              value={sigMeaning}
              onChange={(e) => setSigMeaning(e.target.value)}
            />
          </div>
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
            {closeMutation.isPending ? "Closing…" : "Close & Sign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
