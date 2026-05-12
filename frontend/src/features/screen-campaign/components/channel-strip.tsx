"use client";

/**
 * ChannelStrip — Task 8.3
 *
 * Horizontal flex of channel chips + "+" button that opens a Popover for
 * adding / editing channels via AddChannelRequest / UpdateChannelRequest.
 *
 * The form itself lives in channel-popover.tsx (ChannelPopoverForm).
 */

import { useState } from "react";
import { Plus, Settings2, Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/shared/components/ui/popover";
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

import {
  useRemoveCampaignChannelApiV1CampaignsCampaignIdChannelsChannelIdDelete,
} from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys } from "../lib/hooks";
import type { CampaignResponse } from "../types";
import { ChannelPopoverForm } from "./channel-popover";

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
            <ChannelPopoverForm
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
          <ChannelPopoverForm
            campaignId={campaign.id}
            projectId={campaign.project_id}
            onClose={() => setAddOpen(false)}
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}
