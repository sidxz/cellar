"use client";

import { cn } from "@/shared/lib/utils";
import { Fragment } from "react";
import { plateCellSizePx, plateDimensionsTuple, rowLabel } from "../lib/plate-dimensions";
import type { PlateFormat, WellDesignation } from "../types";
import { WELL_DESIGNATION_LABELS } from "../types";

const WELL_COLORS: Record<WellDesignation, string> = {
  compound: "bg-primary",
  positive_control: "bg-green-500",
  negative_control: "bg-destructive",
  empty: "bg-gray-300 dark:bg-gray-700",
};

interface PlateMapViewProps {
  format: PlateFormat;
  templateMap: Record<string, WellDesignation>;
  /** Optional override for the cell side-length in px. Default scales by
   *  format (28px for 96, 18px for 384, 10px for 1536). */
  cellSize?: number;
  /** Hide row/col labels for an even more compact thumbnail. */
  compact?: boolean;
  className?: string;
}

/** Read-only static plate grid renderer. Use for surfacing a configured
 *  control layout on the Design tab, in protocol viewers, and anywhere
 *  else we need a non-interactive preview of a `template_map`. The
 *  editable counterpart is `PlateMapEditor`.
 */
export function PlateMapView({
  format,
  templateMap,
  cellSize,
  compact = false,
  className,
}: PlateMapViewProps) {
  const [rows, cols] = plateDimensionsTuple(format);
  const size = cellSize ?? plateCellSizePx(format);
  const labelSize = size >= 28 ? "text-xs" : size >= 18 ? "text-[10px]" : "text-[8px]";

  // Count designations for the legend.
  const counts: Record<WellDesignation, number> = {
    compound: 0,
    positive_control: 0,
    negative_control: 0,
    empty: 0,
  };
  for (const d of Object.values(templateMap)) {
    counts[d] = (counts[d] ?? 0) + 1;
  }
  // Total wells in the format.
  const totalWells = rows * cols;
  // Anything not in the map is implicitly empty.
  counts.empty = totalWells - (counts.compound + counts.positive_control + counts.negative_control);

  return (
    <div className={cn("space-y-2", className)}>
      <div className="overflow-auto">
        <div
          className="inline-grid"
          style={{
            gridTemplateColumns: compact
              ? `repeat(${cols}, ${size}px)`
              : `${size + 8}px repeat(${cols}, ${size}px)`,
            gridTemplateRows: compact
              ? `repeat(${rows}, ${size}px)`
              : `${size}px repeat(${rows}, ${size}px)`,
            gap: "1px",
          }}
        >
          {!compact && (
            <>
              {/* Top-left corner */}
              <div />
              {/* Column headers */}
              {Array.from({ length: cols }, (_, c) => (
                <div
                  key={`col-${c}`}
                  className={cn(
                    "flex items-center justify-center",
                    labelSize,
                    "text-muted-foreground font-medium",
                  )}
                >
                  {c + 1}
                </div>
              ))}
            </>
          )}
          {Array.from({ length: rows }, (_, r) => {
            const rLabel = rowLabel(r);
            return (
              <Fragment key={`row-${r}`}>
                {!compact && (
                  <div
                    className={cn(
                      "flex items-center justify-center",
                      labelSize,
                      "text-muted-foreground font-medium",
                    )}
                  >
                    {rLabel}
                  </div>
                )}
                {Array.from({ length: cols }, (_, c) => {
                  const wellKey = `${rLabel}${c + 1}`;
                  const designation = templateMap[wellKey] ?? "empty";
                  return (
                    <div
                      key={wellKey}
                      className={cn("rounded-sm", WELL_COLORS[designation])}
                      title={`${wellKey}: ${WELL_DESIGNATION_LABELS[designation]}`}
                      style={{ width: size, height: size }}
                    />
                  );
                })}
              </Fragment>
            );
          })}
        </div>
      </div>
      {/* Legend — only show designations that actually appear. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {(Object.keys(WELL_COLORS) as WellDesignation[])
          .filter((d) => counts[d] > 0 && d !== "empty")
          .map((d) => (
            <span key={d} className="flex items-center gap-1.5">
              <span className={cn("h-2.5 w-2.5 rounded-full", WELL_COLORS[d])} />
              {WELL_DESIGNATION_LABELS[d]}
              <span className="opacity-60">({counts[d]})</span>
            </span>
          ))}
        {counts.empty > 0 && <span className="opacity-60">{counts.empty} unassigned</span>}
      </div>
    </div>
  );
}
