"use client";

/**
 * SupersedeDialog — Task 9.2
 *
 * Two-action supersede flow:
 *   Option A — Create a new campaign that supersedes this one
 *              → opens CreateCampaignDialog with defaultSupersedesCampaignId prefilled.
 *   Option B — Mark as superseded by an existing closed campaign
 *              → campaign search/select (closed only), then POST /supersede.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Search } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Separator } from "@/shared/components/ui/separator";

import { CreateCampaignDialog } from "../create-campaign-dialog";
import { CampaignStatusChip } from "../campaign-status-chip";
import { campaignKeys } from "../../lib/hooks";

import {
  useSupersedeCampaignApiV1CampaignsCampaignIdSupersedePost,
  useListCampaignsApiV1CampaignsGet,
} from "@/shared/lib/api/campaigns/campaigns";

import type { CampaignResponse } from "../../types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface SupersedeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaign: CampaignResponse;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function SupersedeDialog({
  open,
  onOpenChange,
  campaign,
}: SupersedeDialogProps) {
  const router = useRouter();
  const qc = useQueryClient();

  // Sub-dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [markStep, setMarkStep] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNewId, setSelectedNewId] = useState<string | null>(null);

  // Fetch closed campaigns for option B picker
  const { data: closedCampaigns = [] } = useListCampaignsApiV1CampaignsGet(
    { project_id: campaign.project_id },
    {
      query: {
        enabled: markStep,
        select: (list) =>
          list.filter(
            (c) => c.status === "closed" && c.id !== campaign.id,
          ),
      },
    },
  );

  const supersedeMutation =
    useSupersedeCampaignApiV1CampaignsCampaignIdSupersedePost({
      mutation: {
        onSuccess: () => {
          void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
          onOpenChange(false);
          // Reload to reflect superseded status
          router.refresh();
        },
      },
    });

  const handleMarkSuperseded = () => {
    if (!selectedNewId) return;
    supersedeMutation.mutate({
      campaignId: campaign.id,
      data: { new_campaign_id: selectedNewId },
    });
  };

  const handleClose = () => {
    setMarkStep(false);
    setSearchQuery("");
    setSelectedNewId(null);
    onOpenChange(false);
  };

  const filteredClosed = closedCampaigns.filter((c) =>
    searchQuery.trim() === "" ||
    c.name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  return (
    <>
      <Dialog open={open && !createOpen} onOpenChange={handleClose}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Supersede campaign</DialogTitle>
            <DialogDescription>
              Choose how to supersede &ldquo;{campaign.name}&rdquo;.
            </DialogDescription>
          </DialogHeader>

          {!markStep ? (
            /* ── Option selection ── */
            <div className="space-y-3 py-2">
              {/* Option A */}
              <button
                type="button"
                className="w-full text-left rounded-lg border p-4 hover:bg-accent transition-colors"
                onClick={() => {
                  onOpenChange(false);
                  // Open create dialog in next tick so this dialog unmounts cleanly
                  setTimeout(() => setCreateOpen(true), 50);
                }}
              >
                <div className="flex items-center gap-2 font-medium text-sm">
                  <ArrowRight className="h-4 w-4 text-primary" />
                  Create a new campaign that supersedes this one
                </div>
                <p className="text-xs text-muted-foreground mt-1 ml-6">
                  Opens the campaign builder pre-linked to this campaign.
                </p>
              </button>

              <Separator />

              {/* Option B */}
              <button
                type="button"
                className="w-full text-left rounded-lg border p-4 hover:bg-accent transition-colors"
                onClick={() => setMarkStep(true)}
              >
                <div className="flex items-center gap-2 font-medium text-sm">
                  <Search className="h-4 w-4 text-primary" />
                  Mark as superseded by an existing closed campaign
                </div>
                <p className="text-xs text-muted-foreground mt-1 ml-6">
                  Select a campaign that has already been closed.
                </p>
              </button>
            </div>
          ) : (
            /* ── Mark step ── */
            <div className="space-y-3 py-2">
              <div className="space-y-1.5">
                <Label>Find closed campaign</Label>
                <Input
                  placeholder="Search by name…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <div className="max-h-52 overflow-y-auto space-y-1 rounded-md border p-1">
                {filteredClosed.length === 0 ? (
                  <p className="text-sm text-muted-foreground p-3 text-center">
                    No closed campaigns found.
                  </p>
                ) : (
                  filteredClosed.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className={`w-full text-left rounded px-3 py-2 text-sm flex items-center justify-between gap-2 transition-colors ${
                        selectedNewId === c.id
                          ? "bg-primary/10 font-medium"
                          : "hover:bg-accent"
                      }`}
                      onClick={() => setSelectedNewId(c.id)}
                    >
                      <span className="truncate">{c.name}</span>
                      <CampaignStatusChip status={c.status} />
                    </button>
                  ))
                )}
              </div>

              {supersedeMutation.error && (
                <p className="text-xs text-destructive">
                  {String(
                    (supersedeMutation.error as { message?: string }).message ??
                      "An error occurred",
                  )}
                </p>
              )}

              <div className="flex justify-between gap-2 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setMarkStep(false)}
                >
                  Back
                </Button>
                <Button
                  size="sm"
                  onClick={handleMarkSuperseded}
                  disabled={!selectedNewId || supersedeMutation.isPending}
                >
                  {supersedeMutation.isPending
                    ? "Marking…"
                    : "Mark as superseded"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Option A — CreateCampaignDialog with prefill */}
      {createOpen && (
        <CreateCampaignDialog
          projectId={campaign.project_id}
          open={createOpen}
          onOpenChange={setCreateOpen}
          defaultSupersedesCampaignId={campaign.id}
        />
      )}
    </>
  );
}
