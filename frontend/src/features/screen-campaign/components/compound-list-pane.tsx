"use client";

/**
 * CompoundListPane — Task 8.6 (updated for per-result attribution model)
 *
 * Left pane. Searchable list, "Add compounds" dropdown, per-row "Remove".
 * The Re-seed toolbar button is removed — wipe-and-replace no longer fits
 * the curated-workspace model. Compounds are added incrementally via:
 *   - Manual (single compound search)
 *   - From a Collection
 *   - From another Campaign
 */

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2, Search, ChevronDown } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";

import { useMoleculeSearch } from "@/features/chemical-registration/hooks/use-molecules";
import {
  useAddResultRowApiV1CampaignsCampaignIdResultsPost,
  useRemoveResultRowApiV1CampaignsCampaignIdResultsResultIdDelete,
} from "@/shared/lib/api/campaigns/campaigns";
import { campaignKeys, useMoleculesByIds } from "../lib/hooks";
import { AddFromCollectionDialog } from "./add-from-collection-dialog";
import { AddFromCampaignDialog } from "./add-from-campaign-dialog";
import { AddFromRunsDialog } from "./add-from-runs-dialog";
import type { CampaignResponse, CampaignResultResponse } from "../types";

// ── Add compound dialog (single / manual) ────────────────────────────────────

interface AddCompoundDialogProps {
  campaignId: string;
  open: boolean;
  onClose: () => void;
}

function AddCompoundDialog({ campaignId, open, onClose }: AddCompoundDialogProps) {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const { data: results, isLoading } = useMoleculeSearch(search);

  const addMutation = useAddResultRowApiV1CampaignsCampaignIdResultsPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
        onClose();
      },
    },
  });

  const handleSelect = (moleculeId: string) => {
    addMutation.mutate({
      campaignId,
      data: { molecule_id: moleculeId },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Compound</DialogTitle>
          <DialogDescription>
            Search for a compound to add to this campaign.
          </DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-8"
            placeholder="Search by name or reg number..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            autoFocus
          />
        </div>

        <div className="max-h-52 overflow-y-auto border rounded divide-y text-sm">
          {search.length < 2 && (
            <p className="p-2 text-muted-foreground text-xs">Type at least 2 characters</p>
          )}
          {isLoading && <p className="p-2 text-muted-foreground text-xs">Searching…</p>}
          {!isLoading && search.length >= 2 && !results?.length && (
            <p className="p-2 text-muted-foreground text-xs">No results</p>
          )}
          {results?.map((mol) => (
            <button
              key={mol.id}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/50 text-left"
              onClick={() => handleSelect(mol.id)}
              disabled={addMutation.isPending}
            >
              <span className="font-mono text-xs text-muted-foreground">
                {mol.registration_number}
              </span>
              <span className="truncate">{mol.name}</span>
            </button>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main pane ─────────────────────────────────────────────────────────────────

interface CompoundListPaneProps {
  campaign: CampaignResponse;
  selectedResultId: string | null;
  onSelectResult: (result: CampaignResultResponse | null) => void;
}

export function CompoundListPane({
  campaign,
  selectedResultId,
  onSelectResult,
}: CompoundListPaneProps) {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [manualOpen, setManualOpen] = useState(false);
  const [fromCollectionOpen, setFromCollectionOpen] = useState(false);
  const [fromCampaignOpen, setFromCampaignOpen] = useState(false);
  const [fromRunsOpen, setFromRunsOpen] = useState(false);

  const removeMutation = useRemoveResultRowApiV1CampaignsCampaignIdResultsResultIdDelete({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
      },
    },
  });

  const moleculeIds = useMemo(
    () => [...new Set(campaign.results.map((r) => r.molecule_id))],
    [campaign.results],
  );
  const { data: molLookup } = useMoleculesByIds(moleculeIds);
  const moleculeById = useMemo(
    () =>
      new Map((molLookup?.items ?? []).map((m) => [m.id, m] as const)),
    [molLookup],
  );

  const filtered = campaign.results.filter((r) => {
    if (search.length === 0) return true;
    const term = search.toLowerCase();
    if (r.molecule_id.toLowerCase().includes(term)) return true;
    const m = moleculeById.get(r.molecule_id);
    return (
      (m?.registration_number?.toLowerCase().includes(term) ?? false) ||
      (m?.name?.toLowerCase().includes(term) ?? false)
    );
  });

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-3 py-2 border-b flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" className="shrink-0">
              + Add compounds
              <ChevronDown className="ml-1 h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={() => setManualOpen(true)}>
              Manual (single compound)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setFromCollectionOpen(true)}>
              From a collection…
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setFromCampaignOpen(true)}>
              From another campaign…
            </DropdownMenuItem>
            <DropdownMenuItem disabled>
              From a saved search (coming soon)
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setFromRunsOpen(true)}>
              From protocol run(s)…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="relative flex-1 min-w-0">
          <Search className="absolute left-2 top-1.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            className="h-7 pl-6 text-xs"
            placeholder="Filter…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span className="text-xs text-muted-foreground shrink-0">
          {filtered.length}
        </span>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto divide-y">
        {filtered.length === 0 && (
          <p className="text-xs text-muted-foreground p-3 text-center">
            {campaign.results.length === 0
              ? "No compounds yet. Click Add compounds to start."
              : "No matches."}
          </p>
        )}
        {filtered.map((r) => (
          <div
            key={r.id}
            className={`flex items-center gap-2 px-3 py-2 text-xs cursor-pointer group hover:bg-muted/50 transition-colors ${
              r.id === selectedResultId ? "bg-muted" : ""
            }`}
            onClick={() =>
              onSelectResult(r.id === selectedResultId ? null : r)
            }
          >
            <span className="font-mono text-muted-foreground truncate flex-1 min-w-0">
              {moleculeById.get(r.molecule_id)?.registration_number ??
                moleculeById.get(r.molecule_id)?.name ??
                "…"}
            </span>
            <span
              className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full ${
                r.decision === "selected"
                  ? "bg-green-100 text-green-800"
                  : r.decision === "rejected"
                    ? "bg-red-100 text-red-800"
                    : r.decision === "deferred"
                      ? "bg-yellow-100 text-yellow-800"
                      : "bg-gray-100 text-gray-600"
              }`}
            >
              {r.decision.slice(0, 3).toUpperCase()}
            </span>

            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5 opacity-0 group-hover:opacity-100 shrink-0"
                  onClick={(e) => e.stopPropagation()}
                  title="Remove compound"
                >
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Remove compound?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will delete the result row and all its measurements.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-destructive-foreground"
                    onClick={() =>
                      removeMutation.mutate({ campaignId: campaign.id, resultId: r.id })
                    }
                  >
                    Remove
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        ))}
      </div>

      {/* Dialogs */}
      <AddCompoundDialog
        campaignId={campaign.id}
        open={manualOpen}
        onClose={() => setManualOpen(false)}
      />
      <AddFromCollectionDialog
        campaignId={campaign.id}
        open={fromCollectionOpen}
        onClose={() => setFromCollectionOpen(false)}
      />
      <AddFromCampaignDialog
        campaignId={campaign.id}
        open={fromCampaignOpen}
        onClose={() => setFromCampaignOpen(false)}
      />
      <AddFromRunsDialog
        campaignId={campaign.id}
        open={fromRunsOpen}
        onClose={() => setFromRunsOpen(false)}
      />
    </div>
  );
}
