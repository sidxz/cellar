"use client";

import { Button } from "@/shared/components/ui/button";
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
}: {
  runId: string;
  analysis: MeltingAnalysis;
  channel: string | null;
}) {
  const accept = useAcceptMeltingSteps(runId);
  const steps = peaksToAccept(analysis, channel);
  const note = accept.isError ? apiReason(accept.error) : accept.data?.compute_warning;
  if (steps.length === 0 && !note) return null;
  return (
    <span className="ml-auto inline-flex flex-wrap items-center justify-end gap-2">
      {note && <span className="text-xs text-amber-700 dark:text-amber-400">{note}</span>}
      {steps.length > 0 && (
        <>
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
            Mark all reviewed
          </Button>
          <span className="text-muted-foreground tabular-nums">
            {steps.length === 1 ? "1 peak" : `${steps.length} peaks`}
          </span>
        </>
      )}
    </span>
  );
}
