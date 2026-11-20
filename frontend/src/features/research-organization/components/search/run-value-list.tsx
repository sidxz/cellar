"use client";

import type { CompoundCurvesTarget } from "@/features/screening-assay/components/compound-curves-dialog";
import { boundText } from "@/features/screening-assay/lib/intercept-label";
import { EntityLink } from "@/shared/components/entity-link";
import { overlayColor } from "@structflo/components/dose-response";
import type { ReactNode } from "react";

import { sameUnit } from "../../lib/assay-evidence";
import type { AggregationMode } from "../../lib/use-aggregation-mode";
import type { ActivityValue, InterceptKey } from "../../types";
import { AssayEvidence } from "./assay-evidence";
import { findInterceptValue } from "./run-history-tooltip";

type RunValue = ReturnType<typeof findInterceptValue>;

/** A run's reported value as the cell headline writes it: "0.2600", "> 500", "ND". */
function runValueText(iv: RunValue): string {
  if (iv?.qualifier === "nd") return "ND";
  if (iv?.value == null) return "—";
  if (iv.qualifier === ">" || iv.qualifier === "<") return `${iv.qualifier} ${boundText(iv.value)}`;
  return iv.value.toPrecision(4);
}

interface RunValueListProps {
  av: ActivityValue;
  /** The column's intercept; null reads each run's first value. */
  interceptKey: InterceptKey | null;
  /** The unit the column header states; a value in it leaves it out. */
  headerUnit?: string | null;
  mode: AggregationMode;
  /** The compound's curves in this protocol, offered in the evidence popover. */
  curves?: CompoundCurvesTarget | null;
  /** Spread line under the list (gmean ×fold), inside the run-history control. */
  summary?: ReactNode;
}

/**
 * "List all runs": every run's value for this column, newest first, each with
 * its run date linking to the run. A fitted run carries a dot in the colour its
 * curve takes in the plot (same order, so IC50 and IC90 columns line up). The
 * list scrolls inside the row; the run-history control stays at the bottom.
 */
export function RunValueList({
  av,
  interceptKey,
  headerUnit,
  mode,
  curves,
  summary,
}: RunValueListProps) {
  const runs = av.runs ?? [];
  const total = av.run_count ?? runs.length;
  const unit = av.unit && !sameUnit(av.unit, headerUnit) ? ` ${av.unit}` : "";
  const dotted = runs.some((r) => r.curve_snapshot);
  return (
    <div className="flex h-full min-w-0 flex-col gap-1">
      <ul className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        {runs.map((r, i) => (
          <li
            key={`${r.run_id}:${r.curve_id}`}
            className="flex items-center gap-1.5 whitespace-nowrap text-xs leading-5"
          >
            {dotted && (
              <span
                aria-hidden
                data-run-colour={r.curve_snapshot ? i : undefined}
                className="size-2 shrink-0 rounded-full"
                style={r.curve_snapshot ? { backgroundColor: overlayColor(i) } : undefined}
              />
            )}
            <span className="font-mono tabular-nums">
              {runValueText(findInterceptValue(r.intercept_values, interceptKey))}
              {unit}
            </span>
            <EntityLink
              type="run"
              id={r.run_id}
              label={r.run_date}
              className="text-[10px] text-muted-foreground tabular-nums"
            />
          </li>
        ))}
      </ul>
      {runs.length < total && (
        <p className="text-[10px] text-muted-foreground">
          Newest {runs.length} of {total}
        </p>
      )}
      <AssayEvidence av={av} interceptKey={interceptKey} mode={mode} curves={curves}>
        {summary}
      </AssayEvidence>
    </div>
  );
}
