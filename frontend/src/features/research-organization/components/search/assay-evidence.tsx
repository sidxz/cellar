"use client";

import {
  CompoundCurvesButton,
  type CompoundCurvesTarget,
} from "@/features/screening-assay/components/compound-curves-dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import type { ReactNode } from "react";
import {
  AGGREGATION_LABELS,
  type AggregationMode,
  wireToAggregationMode,
} from "../../lib/use-aggregation-mode";
import type { ActivityValue, InterceptKey } from "../../types";
import { RunHistoryTooltip } from "./run-history-tooltip";

export function AssayEvidence({
  av,
  interceptKey = null,
  mode,
  curves,
  children,
}: {
  av: ActivityValue;
  interceptKey?: InterceptKey | null;
  mode: AggregationMode;
  /** The compound's curves in this protocol, offered at the bottom. */
  curves?: CompoundCurvesTarget | null;
  children: ReactNode;
}) {
  const count = av.run_count;
  const rule = av.selection_rule
    ? AGGREGATION_LABELS[wireToAggregationMode(av.selection_rule)]
    : null;
  const date = count === 1 ? av.runs?.[0]?.run_date : null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="flex max-w-full flex-col items-start gap-1 rounded text-left hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-ring"
          aria-label="Show run history and assay evidence"
          onClick={(event) => event.stopPropagation()}
        >
          {children}
          <span className="text-[10px] leading-tight text-muted-foreground underline decoration-dotted underline-offset-2">
            {date ||
              (count
                ? `${count} run${count === 1 ? "" : "s"} · ${rule ?? "Evidence"}`
                : "Assay evidence")}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="max-h-[65vh] w-[440px] max-w-[calc(100vw-2rem)] overflow-auto p-4"
        align="start"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 space-y-1 text-xs">
          <p className="font-semibold text-sm">Assay evidence</p>
          <p>
            {av.source === "dose_response" ? "Fitted dose response" : "Reported readout"} · Unit:{" "}
            {av.unit ?? "not supplied"}
          </p>
          <p>
            Aggregation:{" "}
            {rule ?? (av.source === "dose_response" ? AGGREGATION_LABELS[mode] : "not supplied")}
          </p>
          <p className="text-muted-foreground">
            ND = not determined; &lt; / &gt; indicate a bound, not an exact potency.
          </p>
        </div>
        <RunHistoryTooltip
          av={av}
          interceptKey={interceptKey}
          unit={av.unit ?? "(unit unavailable)"}
        />
        <CompoundCurvesButton target={curves} className="mt-3" />
      </PopoverContent>
    </Popover>
  );
}
