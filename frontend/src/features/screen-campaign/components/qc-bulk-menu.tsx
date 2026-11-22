"use client";

/**
 * QcBulkMenu — marks (or clears) the QC verdict on many campaign cells in one save.
 * Cells = the ticked rows x the ticked columns. Nothing applies until Apply; the count beside
 * it is the forecast. Renders only its controls: the grid's bulk bar holds it beside
 * StageBulkMenu.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut } from "@/shared/lib/api/campaigns/campaigns";
import type { QcVerdictCountsResponse, SetQcVerdictsRequest } from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";

import { campaignKeys } from "../hooks/use-campaigns";
import { QC_LABEL, qcForecast } from "../lib/qc-verdicts";
import { groupColumnsByStage } from "../lib/stage-column-groups";
import type { CampaignMeasurementResponse, CampaignResponse } from "../types";
import { selectionText } from "./grid/selection-text";

type Verdict = CampaignMeasurementResponse["qc_verdict"];

const BUTTON: Record<Verdict, string> = {
  verified: "Mark QC verified…",
  failed: "Mark QC failed…",
  not_tested: "Clear QC…",
};
const TITLE: Record<Verdict, string> = {
  verified: "Mark QC verified",
  failed: "Mark QC failed",
  not_tested: "Clear QC",
};
const cells = (n: number) => `${n} ${n === 1 ? "cell" : "cells"}`;

const DONE: Record<Verdict, (n: number) => string> = {
  verified: (n) => `Verified ${cells(n)}`,
  failed: (n) => `Marked ${cells(n)} Failed`,
  not_tested: (n) => `Cleared QC on ${cells(n)}`,
};

function toast(verdict: Verdict, r: QcVerdictCountsResponse) {
  const parts = [DONE[verdict](r.changed)];
  if (r.unchanged) parts.push(`${r.unchanged} already ${QC_LABEL[verdict]}`);
  if (r.kept) parts.push(`${r.kept} kept (already marked)`);
  if (r.no_result) parts.push(`${r.no_result} had no result`);
  showSuccess(parts.join(" · "));
}

interface QcBulkMenuProps {
  campaign: CampaignResponse;
  /** The ticked rows: what the verdict reaches, times the ticked columns. */
  resultIds: string[];
  /** How many of them the filters hide, said in the window. */
  hiddenCount: number;
  selectedStageId: string | null;
  readOnly: boolean;
}

export function QcBulkMenu({
  campaign,
  resultIds,
  hiddenCount,
  selectedStageId,
  readOnly,
}: QcBulkMenuProps) {
  const qc = useQueryClient();
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [columns, setColumns] = useState<Set<string>>(new Set());
  const [overwrite, setOverwrite] = useState(false);
  const [note, setNote] = useState("");
  // On the hook, not per call, so the refresh and toast never depend on what is mounted.
  const mutation = useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut({
    mutation: {
      onSuccess: (res, { data }) => {
        void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaign.id) });
        toast(data.verdict, res);
      },
      onError: (err) =>
        showError(`QC update failed: ${err instanceof Error ? err.message : String(err)}`),
    },
  });

  const channels = campaign.channels ?? [];
  const groups = groupColumnsByStage(channels, campaign.stages ?? []);
  const rows = useMemo(() => {
    const ids = new Set(resultIds);
    return (campaign.results ?? []).filter((r) => ids.has(r.id));
  }, [campaign.results, resultIds]);
  // A blank note names none, so cells already holding the verdict keep theirs.
  const sentNote = verdict !== "not_tested" && note.trim() ? note.trim() : undefined;
  const forecast = useMemo(
    () =>
      verdict
        ? qcForecast(
            rows.flatMap((r) => (r.measurements ?? []).filter((m) => columns.has(m.channel_id))),
            verdict,
            overwrite,
            sentNote,
          )
        : 0,
    [rows, columns, verdict, overwrite, sentNote],
  );

  if (readOnly) return null;

  function open(v: Verdict) {
    // A stage means exactly its own columns, even none; "All" means every column.
    const picked = selectedStageId
      ? channels.filter((c) => c.stage_id === selectedStageId)
      : channels;
    setColumns(new Set(picked.map((c) => c.id)));
    setOverwrite(false);
    setNote("");
    setVerdict(v);
  }

  function apply() {
    if (!verdict) return;
    const data: SetQcVerdictsRequest = {
      verdict,
      targets: [
        {
          channel_ids: channels.filter((c) => columns.has(c.id)).map((c) => c.id),
          // Always named: never "every row", which would reach rows nobody ticked.
          result_ids: rows.map((r) => r.id),
        },
      ],
      overwrite,
      ...(sentNote ? { note: sentNote } : {}),
    };
    mutation.mutate({ campaignId: campaign.id, data });
    setVerdict(null);
  }

  function toggle(id: string, on: boolean) {
    const next = new Set(columns);
    if (on) next.add(id);
    else next.delete(id);
    setColumns(next);
  }

  return (
    <>
      {(["verified", "failed", "not_tested"] as const).map((v) => (
        <Button
          key={v}
          size="sm"
          variant="outline"
          className="h-7 px-2 text-xs"
          disabled={rows.length === 0 || mutation.isPending}
          onClick={() => open(v)}
        >
          {BUTTON[v]}
        </Button>
      ))}

      <AlertDialog open={verdict !== null} onOpenChange={(o) => !o && setVerdict(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{verdict && TITLE[verdict]}</AlertDialogTitle>
            <AlertDialogDescription>
              {selectionText(rows.length, hiddenCount)}
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className="space-y-1">
            <span className="text-xs text-muted-foreground">Columns</span>
            <div className="max-h-64 space-y-2 overflow-y-auto">
              {groups.map((g) => (
                <div key={g.stageId ?? "campaign"} className="space-y-1">
                  <div className="text-xs font-medium">
                    {g.stageId ? g.title : "Whole campaign"}
                  </div>
                  {g.channels.map((c) => (
                    <div key={c.id} className="flex items-center gap-2 pl-2">
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
              ))}
            </div>
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
    </>
  );
}
