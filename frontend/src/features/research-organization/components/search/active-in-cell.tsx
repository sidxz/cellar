"use client";

import type { CurveClass } from "@/features/screening-assay/types";
import { cn } from "@/shared/lib/utils";
import type { AnyProtocolActivity, AnyProtocolEntry } from "../../types";

const MAX_ROWS = 3;

/** Curve-class dot: trustworthy → green, partial → amber, everything else grey. */
const DOT: Record<CurveClass, string> = {
  full: "bg-emerald-500",
  partial: "bg-amber-500",
  bell_shaped: "bg-muted-foreground/50",
  inactive: "bg-muted-foreground/50",
};

function formatValue(e: AnyProtocolEntry): string {
  if (e.value == null) return "—";
  const q = e.qualifier && e.qualifier !== "=" ? e.qualifier : "";
  return `${q}${Number(e.value.toPrecision(3))}${e.unit ? ` ${e.unit}` : ""}`;
}

/** One line per protocol the compound was measured in: name · label · native
 *  value · curve-class dot. Best first (server-sorted). Inactive curves are
 *  muted. No sparklines here — the detail sheet has the plots. */
export function ActiveInCell({ value }: { value: AnyProtocolActivity | undefined }) {
  const entries = value?.entries ?? [];
  if (entries.length === 0) return <span className="text-muted-foreground">&mdash;</span>;
  const shown = entries.slice(0, MAX_ROWS);
  const more = entries.length - shown.length;
  return (
    <div className="flex flex-col gap-0.5 py-1 text-xs leading-tight">
      {shown.map((e) => {
        const inactive = e.curve_class === "inactive";
        const singleTarget = e.target_names.length === 1 ? e.target_names[0] : null;
        return (
          <div
            key={`${e.protocol_id}:${e.readout_definition_id}`}
            data-testid="active-in-row"
            className={cn("flex min-w-0 items-center gap-1.5", inactive && "text-muted-foreground")}
          >
            {e.curve_class ? (
              <span
                className={cn("h-2 w-2 shrink-0 rounded-full", DOT[e.curve_class])}
                aria-hidden
              />
            ) : (
              <span className="h-2 w-2 shrink-0" aria-hidden />
            )}
            <span className="truncate">{e.protocol_name}</span>
            {singleTarget && (
              <span className="shrink-0 rounded bg-muted px-1 text-[10px] text-muted-foreground">
                {singleTarget}
              </span>
            )}
            <span className="ml-auto shrink-0 text-muted-foreground">{e.label}</span>
            <span className="shrink-0 font-mono">{formatValue(e)}</span>
          </div>
        );
      })}
      {more > 0 && <span className="text-muted-foreground">+{more} more</span>}
    </div>
  );
}
