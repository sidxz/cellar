"use client";

/**
 * Marker for a dose-response cell whose number came from a *reported*
 * endpoint — a summary-imported `readout_data` row for the DR readout-def —
 * rather than from a curve this workspace fitted. Chemists need to see the
 * difference: there is no Hill fit, no R², no dose points behind it, so the
 * usual "click the cell to inspect the curve" affordances are empty.
 *
 * Rendered by the campaign results grid, the search results grid and the
 * compound Activity tab so the three surfaces can't drift on wording.
 */

import { cn } from "@/shared/lib/utils";

export const REPORTED_ENDPOINT_TITLE = "Reported endpoint — no fitted curve for this compound";

export function ReportedEndpointBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "rounded-sm border border-muted px-1 py-px text-[10px] font-normal text-muted-foreground",
        className,
      )}
      title={REPORTED_ENDPOINT_TITLE}
    >
      reported
    </span>
  );
}
