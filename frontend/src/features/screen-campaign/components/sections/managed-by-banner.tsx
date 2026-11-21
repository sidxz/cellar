"use client";

import { useAuthzHasRole } from "@duar-auth/nextjs";
import { ExternalLink, Lock } from "lucide-react";
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
import { useAppConfig } from "@/shared/lib/app-config";
import { trustedReturnTarget } from "@/shared/lib/return-to";
import { useReleaseCampaign } from "../../hooks/use-release-campaign";
import type { CampaignResponse } from "../../types";

/** "Locked by <app>": another app manages this campaign and its structure is changed there.
 *  Links to the campaign there when the address is trusted; lets an admin release it.
 *  Same dark strip and lime accent as the way-back bar: both mean "the other app". */
export function ManagedByBanner({ campaign }: { campaign: CampaignResponse }) {
  const label = campaign.managed_label ?? campaign.managed_by ?? "another app";
  const { returnOrigins } = useAppConfig();
  const target = trustedReturnTarget(campaign.managed_url ?? null, returnOrigins);
  const isAdmin = useAuthzHasRole("admin");
  const [releasing, setReleasing] = useState(false);

  return (
    <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg bg-foreground px-4 py-2.5 text-sm text-background shadow-sm">
      <span className="inline-flex items-center gap-2 font-medium">
        <Lock className="size-4" aria-hidden />
        <span>Locked by {label}</span>
      </span>
      <div className="flex shrink-0 items-center gap-2">
        {isAdmin && (
          <Button
            variant="ghost"
            size="sm"
            className="text-background hover:bg-background/10 hover:text-background"
            onClick={() => setReleasing(true)}
          >
            Release from {label}…
          </Button>
        )}
        {target && (
          <Button
            asChild
            size="sm"
            className="bg-lime-400 font-semibold text-black shadow-[0_0_12px_rgba(163,230,53,0.6)] hover:bg-lime-300"
          >
            <a href={target.url} target="_blank" rel="noopener noreferrer">
              Open in {label} <ExternalLink className="size-4" />
            </a>
          </Button>
        )}
      </div>
      {isAdmin && (
        <ReleaseDialog
          campaignId={campaign.id}
          label={label}
          open={releasing}
          onOpenChange={setReleasing}
        />
      )}
    </div>
  );
}

function ReleaseDialog({
  campaignId,
  label,
  open,
  onOpenChange,
}: {
  campaignId: string;
  label: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [reason, setReason] = useState("");
  const release = useReleaseCampaign();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Release from {label}</DialogTitle>
          <DialogDescription>
            ChemCellar manages the campaign again: anyone who can edit it can change its stages,
            runs, columns and compounds here, and {label} no longer can. The reason is recorded.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor="release-reason">Reason</Label>
          <Textarea
            id="release-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. the round was abandoned in Daikon"
          />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!reason.trim() || release.isPending}
            onClick={() =>
              release.mutate(
                { campaignId, reason: reason.trim() },
                { onSuccess: () => onOpenChange(false) },
              )
            }
          >
            Release
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
