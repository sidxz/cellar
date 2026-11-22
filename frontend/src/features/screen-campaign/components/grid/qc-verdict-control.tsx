"use client";

/** QC verdict on one campaign cell: its lines under the value, its right-click menu, and the
 *  "QC" row in its facts. */

import { useQueryClient } from "@tanstack/react-query";
import { CircleCheck, TriangleAlert } from "lucide-react";
import { type ReactElement, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/shared/components/ui/context-menu";
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

/** Saves one cell's QC verdict. On the hook, not per call: a card or menu may close before the
 *  save lands. */
export function useSetQcVerdict(campaignId: string) {
  const qc = useQueryClient();
  const mutation = useSetQcVerdictsApiV1CampaignsCampaignIdQcVerdictsPut({
    mutation: {
      onSuccess: () => void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) }),
      onError: () => showError("Could not save the QC verdict."),
    },
  });
  // A person changing one cell means it, hence overwrite. Leaving `note` out names no note
  // (a changed verdict starts without one); a string names it, blank = none.
  const set = (resultId: string, channelId: string, verdict: Verdict, note?: string) => {
    const data: SetQcVerdictsRequest = {
      verdict,
      targets: [{ channel_ids: [channelId], result_ids: [resultId] }],
      overwrite: true,
      ...(note !== undefined ? { note: note.trim() || null } : {}),
    };
    mutation.mutate({ campaignId, data });
  };
  return { set, pending: mutation.isPending };
}

/** A value's QC under it: the verdict, who set it, when, and its note; nothing while nobody has
 *  checked it. */
export function QcSummary({ measurement: m }: { measurement: CampaignMeasurementResponse }) {
  const nameOf = useMemberNames();
  if (m.qc_verdict === "not_tested") return null;
  const failed = m.qc_verdict === "failed";
  return (
    <span className="flex max-w-full flex-col items-end text-xs leading-tight">
      <span
        className={`flex items-center gap-1 whitespace-nowrap font-medium ${failed ? "text-destructive" : "text-foreground"}`}
      >
        {failed ? (
          <TriangleAlert className="size-3 shrink-0" aria-hidden="true" />
        ) : (
          <CircleCheck className="size-3 shrink-0 text-emerald-600" aria-hidden="true" />
        )}
        QC {QC_LABEL[m.qc_verdict].toLowerCase()}
      </span>
      {m.qc_verdict_by && (
        <span className="max-w-full truncate text-muted-foreground">{nameOf(m.qc_verdict_by)}</span>
      )}
      {m.qc_verdict_at && (
        <span className="tabular-nums text-muted-foreground">
          {new Date(m.qc_verdict_at).toLocaleDateString()}
        </span>
      )}
      {m.qc_verdict_note && (
        <span
          className="line-clamp-1 max-w-full break-words italic text-muted-foreground"
          title={m.qc_verdict_note}
        >
          {m.qc_verdict_note}
        </span>
      )}
    </span>
  );
}

/** Right-click anywhere in ``children`` (a value's cell) to set or clear its QC verdict, or to
 *  open its QC note (``onEditNote``). ``readOnly`` offers no menu. */
export function QcMenu({
  campaignId,
  measurement: m,
  resultId,
  readOnly,
  onEditNote,
  children,
}: {
  campaignId: string;
  measurement: CampaignMeasurementResponse;
  resultId: string;
  readOnly: boolean;
  onEditNote: () => void;
  children: ReactElement;
}) {
  const write = useSetQcVerdict(campaignId);
  const verdict = m.qc_verdict;
  // Setting needs a result to judge; a verdict left on a value that lost its result can still go.
  const choices: Verdict[] = [
    ...(m.holds_result ? (["verified", "failed"] as const).filter((v) => v !== verdict) : []),
    ...(verdict !== "not_tested" ? (["not_tested"] as const) : []),
  ];
  if (readOnly || (choices.length === 0 && !m.holds_result)) return children;
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent>
        {choices.map((v) => (
          <ContextMenuItem
            key={v}
            disabled={write.pending}
            onSelect={() => write.set(resultId, m.channel_id, v)}
          >
            {v === "verified" ? "Mark QC verified" : v === "failed" ? "Mark QC failed" : "Clear QC"}
          </ContextMenuItem>
        ))}
        {m.holds_result && (
          <>
            {choices.length > 0 && <ContextMenuSeparator />}
            <ContextMenuItem onSelect={onEditNote}>
              {m.qc_verdict_note ? "Edit QC note…" : "Add QC note…"}
            </ContextMenuItem>
          </>
        )}
      </ContextMenuContent>
    </ContextMenu>
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
  const stored = m.qc_verdict_note ?? "";
  const [note, setNote] = useState(stored);
  // A saved verdict or note replaces what was typed: the box shows what is stored.
  const [shown, setShown] = useState(`${m.qc_verdict}|${stored}`);
  if (shown !== `${m.qc_verdict}|${stored}`) {
    setShown(`${m.qc_verdict}|${stored}`);
    setNote(stored);
  }
  const stamp = useQcStamp(m);
  const write = useSetQcVerdict(campaignId);

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

  // A verdict button names no note; Save names the box's note, blank = none.
  const send = (verdict: Verdict, withNote: boolean) =>
    write.set(resultId, m.channel_id, verdict, withNote ? note : undefined);

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
            disabled={write.pending}
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
            disabled={write.pending}
            onClick={() => send(m.qc_verdict, true)}
          >
            Save
          </Button>
        </>
      )}
    </div>
  );
}
