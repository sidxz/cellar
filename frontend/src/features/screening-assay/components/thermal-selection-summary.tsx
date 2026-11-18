"use client";

import { EntityLink } from "@/shared/components/entity-link";
import { type ApplicableRule, limitsFor } from "../lib/melt-hits";
import { type ResultRow, formatDelta, formatTm } from "../lib/melt-results";

/** Identity and measured shifts precede the evidence, including when filtered out of the table. */
export function ThermalSelectionSummary({
  row,
  windowNames,
  applicable,
  doseUnit,
  selectedCount,
}: {
  row: ResultRow;
  windowNames: readonly string[];
  applicable: readonly ApplicableRule[];
  doseUnit: string;
  selectedCount: number;
}) {
  return (
    <div aria-label="Selected sample" className="space-y-2 border-b pb-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 className="text-base font-semibold">
          {row.identity.moleculeId ? (
            <EntityLink type="compound" id={row.identity.moleculeId} label={row.sampleText} />
          ) : (
            row.sampleText
          )}
        </h3>
        {row.identity.batchSuffix && (
          <span className="text-xs text-muted-foreground">·{row.identity.batchSuffix}</span>
        )}
        <span className="text-xs text-muted-foreground">
          {row.position}
          {row.concentration != null && ` · ${row.concentration} ${doseUnit}`}
        </span>
        {selectedCount > 1 && (
          <span className="text-xs text-muted-foreground">{selectedCount} positions selected</span>
        )}
      </div>
      {windowNames.map((name) => {
        const cell = row.cells[name];
        const review =
          cell?.review === "provisional"
            ? "Unreviewed"
            : cell?.review === "reviewed"
              ? "Reviewed"
              : cell?.status === "several_steps"
                ? "Several peaks"
                : cell?.status === "no_step"
                  ? "No peak"
                  : "Not evaluated";
        return (
          <div
            key={name}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm tabular-nums"
          >
            {windowNames.length > 1 && (
              <span className="text-xs text-muted-foreground">{name}</span>
            )}
            {cell?.deltaTm != null && row.wellType !== "reference" && (
              <span className="text-lg font-semibold">
                ΔTm {formatDelta(cell.deltaTm, limitsFor(applicable, name, "delta_tm"))} °C
              </span>
            )}
            <span className="text-muted-foreground">
              {cell?.tm != null
                ? `Tm ${formatTm(cell.tm, limitsFor(applicable, name, "tm"))} °C`
                : "No Tm"}
            </span>
            <span className="text-xs text-muted-foreground">{review}</span>
          </div>
        );
      })}
    </div>
  );
}
