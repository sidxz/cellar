"use client";

/**
 * QcBulkMenu — marks (or clears) the QC verdict on many campaign cells in one save.
 * Cells = the visible rows (`rowPassesFilters`, same predicate as StageBulkMenu) x the
 * ticked columns. Nothing applies until Apply; the count beside it is the forecast.
 */

import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut } from "@/shared/lib/api/campaigns/campaigns";
import type { QcVerdictCountsResponse, SetQcVerdictsRequest } from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";

import { campaignKeys } from "../hooks/use-campaigns";
import { qcForecast } from "../lib/qc-verdicts";
import type { CampaignMeasurementResponse, CampaignResponse } from "../types";
import { type CampaignFilters, rowPassesFilters } from "./campaign-filter-bar";

type Verdict = CampaignMeasurementResponse["qc_verdict"];

const TITLE: Record<Verdict, string> = {
  verified: "Mark verified",
  failed: "Mark failed",
  not_tested: "Clear QC",
};
const DONE: Record<Verdict, string> = {
  verified: "Verified",
  failed: "Marked failed",
  not_tested: "Cleared",
};

const cells = (n: number) => `${n} ${n === 1 ? "cell" : "cells"}`;

function toast(verdict: Verdict, r: QcVerdictCountsResponse) {
  const parts = [`${DONE[verdict]} ${cells(r.changed)}`];
  if (r.kept) parts.push(`${r.kept} kept (already marked)`);
  if (r.no_result) parts.push(`${r.no_result} had no result`);
  showSuccess(parts.join(" · "));
}

interface QcBulkMenuProps {
  campaign: CampaignResponse;
  filters: CampaignFilters;
  selectedStageId: string | null;
  readOnly: boolean;
}

export function QcBulkMenu({ campaign, filters, selectedStageId, readOnly }: QcBulkMenuProps) {
  const qc = useQueryClient();
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [columns, setColumns] = useState<Set<string>>(new Set());
  const [overwrite, setOverwrite] = useState(false);
  const [note, setNote] = useState("");
  const mutation = useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut();

  const channels = campaign.channels ?? [];
  const rows = useMemo(
    () => (campaign.results ?? []).filter((r) => rowPassesFilters(r, filters, selectedStageId)),
    [campaign.results, filters, selectedStageId],
  );
  const forecast = useMemo(
    () =>
      verdict
        ? qcForecast(
            rows.flatMap((r) => (r.measurements ?? []).filter((m) => columns.has(m.channel_id))),
            verdict,
            overwrite,
          )
        : 0,
    [rows, columns, verdict, overwrite],
  );

  if (readOnly) return null;

  function open(v: Verdict) {
    const own = channels.filter((c) => c.stage_id === selectedStageId);
    setColumns(new Set((selectedStageId && own.length ? own : channels).map((c) => c.id)));
    setOverwrite(false);
    setNote("");
    setVerdict(v);
  }

  function apply() {
    if (!verdict) return;
    const text = note.trim();
    const data: SetQcVerdictsRequest = {
      verdict,
      targets: [
        {
          channel_ids: channels.filter((c) => columns.has(c.id)).map((c) => c.id),
          result_ids: rows.map((r) => r.id),
        },
      ],
      overwrite,
      ...(verdict !== "not_tested" && text ? { note: text } : {}),
    };
    mutation.mutate(
      { campaignId: campaign.id, data },
      {
        onSuccess: (res) => {
          void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
          toast(verdict, res);
        },
        onError: (err) =>
          showError(`QC update failed: ${err instanceof Error ? err.message : String(err)}`),
      },
    );
    setVerdict(null);
  }

  function toggle(id: string, on: boolean) {
    const next = new Set(columns);
    if (on) next.add(id);
    else next.delete(id);
    setColumns(next);
  }

  return (
    <div className="flex items-center gap-1.5 border-b bg-muted/10 px-3 py-1.5">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline" className="h-7 px-2 text-xs">
            QC <ChevronDown className="size-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={() => open("verified")}>Mark verified…</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => open("failed")}>Mark failed…</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => open("not_tested")}>Clear QC…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog open={verdict !== null} onOpenChange={(o) => !o && setVerdict(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{verdict && TITLE[verdict]}</AlertDialogTitle>
          </AlertDialogHeader>

          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">Columns</span>
            {channels.map((c) => (
              <div key={c.id} className="flex items-center gap-2">
                <Checkbox
                  id={`qc-col-${c.id}`}
                  checked={columns.has(c.id)}
                  onCheckedChange={(on) => toggle(c.id, on === true)}
                />
                <Label htmlFor={`qc-col-${c.id}`} className="text-sm">
                  {c.label}
                </Label>
              </div>
            ))}
          </div>

          {verdict !== "not_tested" && (
            <>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="qc-overwrite"
                  checked={overwrite}
                  onCheckedChange={(on) => setOverwrite(on === true)}
                />
                <Label htmlFor="qc-overwrite" className="text-sm">
                  Also change cells someone already marked
                </Label>
              </div>
              <Textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={2000}
                rows={2}
                placeholder="Note (optional)"
                className="text-sm"
              />
            </>
          )}

          <AlertDialogFooter className="items-center">
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <span className="text-xs text-muted-foreground">{cells(forecast)}</span>
            {/* Not AlertDialogAction: it would close the dialog regardless of the handler. */}
            <Button size="sm" disabled={forecast === 0 || mutation.isPending} onClick={apply}>
              Apply
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
