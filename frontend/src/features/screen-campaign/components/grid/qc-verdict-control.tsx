"use client";

/** QC verdict on one campaign cell: the mark beside the value, and the "QC" row in its facts. */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Textarea } from "@/shared/components/ui/textarea";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut } from "@/shared/lib/api/campaigns/campaigns";
import type { SetQcVerdictsRequest } from "@/shared/lib/api/model";
import { showError } from "@/shared/lib/toast";

import { campaignKeys } from "../../hooks/use-campaigns";
import { QC_LABEL } from "../../lib/qc-verdicts";
import type { CampaignMeasurementResponse } from "../../types";

type Verdict = CampaignMeasurementResponse["qc_verdict"];
const VERDICTS: Verdict[] = ["not_tested", "verified", "failed"];

/** "by <name> · <date>" for a marked cell. */
function useQcStamp(m: CampaignMeasurementResponse): string {
  const nameOf = useMemberNames();
  const when = m.qc_verdict_at ? new Date(m.qc_verdict_at).toLocaleDateString() : "";
  return `by ${nameOf(m.qc_verdict_by)} · ${when}`;
}

export function QcMark({ measurement: m }: { measurement: CampaignMeasurementResponse }) {
  const stamp = useQcStamp(m);
  if (m.qc_verdict === "not_tested") return null;
  const title = `${QC_LABEL[m.qc_verdict]} ${stamp}${
    m.qc_verdict_note ? ` · ${m.qc_verdict_note}` : ""
  }`;
  return (
    <span
      role="img"
      aria-label={`QC ${m.qc_verdict}`}
      title={title}
      className={`text-xs font-medium ${m.qc_verdict === "verified" ? "text-emerald-600" : "text-red-600"}`}
    >
      {m.qc_verdict === "verified" ? "✓" : "✕"}
    </span>
  );
}

interface QcVerdictControlProps {
  campaignId: string;
  measurement: CampaignMeasurementResponse;
  resultId: string;
  readOnly: boolean;
}

export function QcVerdictControl({
  campaignId,
  measurement: m,
  resultId,
  readOnly,
}: QcVerdictControlProps) {
  const qc = useQueryClient();
  const stored = m.qc_verdict_note ?? "";
  const [note, setNote] = useState(stored);
  // A saved verdict or note replaces what was typed: the box shows what is stored.
  const [shown, setShown] = useState(`${m.qc_verdict}|${stored}`);
  if (shown !== `${m.qc_verdict}|${stored}`) {
    setShown(`${m.qc_verdict}|${stored}`);
    setNote(stored);
  }
  const stamp = useQcStamp(m);
  // On the hook, not per call: the card may close before the save lands.
  const mutation = useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut({
    mutation: {
      onSuccess: () => void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) }),
      onError: () => showError("Could not save the QC verdict."),
    },
  });

  if (!m.holds_result) return null;
  const stampEl = m.qc_verdict !== "not_tested" && (
    <span className="text-muted-foreground">{stamp}</span>
  );
  if (readOnly) {
    return (
      <div className="mt-2 flex gap-3 border-t pt-2 text-xs">
        <span className="text-muted-foreground">QC</span>
        <span>{QC_LABEL[m.qc_verdict]}</span>
        {stampEl}
      </div>
    );
  }

  // A person changing one cell means it, hence overwrite. A verdict button names no note
  // (a changed verdict starts without one); Save names the box's note, blank = none.
  const send = (verdict: Verdict, withNote: boolean) => {
    const data: SetQcVerdictsRequest = {
      verdict,
      targets: [{ channel_ids: [m.channel_id], result_ids: [resultId] }],
      overwrite: true,
      ...(withNote ? { note: note.trim() || null } : {}),
    };
    mutation.mutate({ campaignId, data });
  };

  return (
    <div className="mt-2 space-y-1.5 border-t pt-2 text-xs">
      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-1 text-muted-foreground">QC</span>
        {VERDICTS.map((v) => (
          <Button
            key={v}
            type="button"
            size="sm"
            variant={m.qc_verdict === v ? "default" : "outline"}
            className="h-6 px-2 text-[11px]"
            disabled={mutation.isPending}
            onClick={() => send(v, false)}
          >
            {QC_LABEL[v]}
          </Button>
        ))}
        {stampEl}
      </div>
      {m.qc_verdict !== "not_tested" && (
        <>
          <Textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
            rows={2}
            placeholder="Note (optional)"
            className="text-xs"
          />
          <Button
            type="button"
            size="sm"
            className="h-6 px-2 text-[11px]"
            disabled={mutation.isPending}
            onClick={() => send(m.qc_verdict, true)}
          >
            Save
          </Button>
        </>
      )}
    </div>
  );
}
