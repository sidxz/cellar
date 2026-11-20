"use client";

import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { apiReason } from "../hooks/use-instrument-import-wizard";
import { useAcceptMeltingSteps } from "../hooks/use-melting-analysis";
import { peaksToAccept } from "../lib/accept-all";
import type { MeltingAnalysis } from "../types";

/** One click that records every peak giving a Tm on the signal shown as reviewed.
 *  Accepting changes no value, so it asks for no confirmation; each peak can be set
 *  back from its own row. Shown to editors while there is a peak to accept. */
export function AcceptAllPeaks({
  runId,
  analysis,
  channel,
  menu = false,
  channelLabel,
}: {
  runId: string;
  analysis: MeltingAnalysis;
  channel: string | null;
  menu?: boolean;
  channelLabel?: string;
}) {
  const accept = useAcceptMeltingSteps(runId);
  const steps = peaksToAccept(analysis, channel);
  const note = accept.isError ? apiReason(accept.error) : accept.data?.compute_warning;
  if (steps.length === 0 && !note) return null;
  const reviewLabel = accept.isPending
    ? "Marking…"
    : `Mark ${steps.length} ${steps.length === 1 ? "peak" : "peaks"} reviewed`;
  if (menu)
    return (
      <div className="text-xs">
        {note && <output className="block text-amber-700 dark:text-amber-400">{note}</output>}
        {steps.length > 0 && (
          <Popover>
            <PopoverTrigger asChild>
              <Button type="button" variant="ghost" size="sm">
                Review actions
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-80 space-y-3">
              <p className="text-sm font-medium">Bulk peak review</p>
              <p className="text-xs text-muted-foreground">{`Every unreviewed peak that gives a Tm on ${channelLabel ?? channel ?? "this signal"}, in all transitions, including the reference and controls. Positions with peak issues are left out.`}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={accept.isPending || !!analysis.edit_refusal}
                title={analysis.edit_refusal ?? undefined}
                onClick={() => accept.mutate({ steps })}
              >
                {reviewLabel}
              </Button>
            </PopoverContent>
          </Popover>
        )}
      </div>
    );
  return (
    <span className="ml-auto inline-flex flex-wrap items-center justify-end gap-2">
      {note && <span className="text-xs text-amber-700 dark:text-amber-400">{note}</span>}
      {steps.length > 0 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={accept.isPending || !!analysis.edit_refusal}
          title={
            analysis.edit_refusal ??
            "Marks every peak that gives a Tm on this signal as reviewed. Positions that need a look are left out."
          }
          onClick={() => accept.mutate({ steps })}
        >
          {reviewLabel}
        </Button>
      )}
    </span>
  );
}
