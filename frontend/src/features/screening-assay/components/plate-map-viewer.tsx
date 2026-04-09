"use client";

import { Fragment, useState } from "react";
import { cn } from "@/shared/lib/utils";
import type { PlateMapResponse, PlateMapWell } from "../types";

// ─── Constants ────────────────────────────────────────────────────────────────

const TRACE_COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#a855f7",
  "#06b6d4",
  "#ec4899",
  "#84cc16",
  "#f97316",
  "#14b8a6",
  "#8b5cf6",
  "#d946ef",
];

const CONTROL_COLORS: Record<string, string> = {
  positive_control: "#22c55e",
  negative_control: "#ef4444",
  blank: "#6b7280",
  reference: "#f59e0b",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Row label: A, B, ..., Z, AA, AB, ... */
function rowLabel(index: number): string {
  if (index < 26) return String.fromCharCode(65 + index);
  return (
    String.fromCharCode(65 + Math.floor(index / 26) - 1) +
    String.fromCharCode(65 + (index % 26))
  );
}

function plateDimensions(format: string): [number, number] {
  switch (format) {
    case "6": return [2, 3];
    case "12": return [3, 4];
    case "24": return [4, 6];
    case "48": return [6, 8];
    case "96": return [8, 12];
    case "384": return [16, 24];
    case "1536": return [32, 48];
    default: return [8, 12];
  }
}

function cellSize(format: string): number {
  switch (format) {
    case "6":
    case "12":
    case "24":
    case "48":
    case "96": return 28;
    case "384": return 18;
    case "1536": return 10;
    default: return 28;
  }
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

interface WellTooltipProps {
  well: PlateMapWell;
}

function WellTooltip({ well }: WellTooltipProps) {
  return (
    <div className="absolute bottom-full left-1/2 z-50 mb-1 -translate-x-1/2 whitespace-nowrap rounded-md border bg-popover px-2 py-1 text-[10px] shadow-md pointer-events-none">
      <p className="font-medium">{well.position}</p>
      {well.molecule_name && <p>Compound: {well.molecule_name}</p>}
      {well.batch_number && <p>Batch: {well.batch_number}</p>}
      {well.concentration != null && (
        <p>
          Conc: {well.concentration} {well.concentration_unit ?? ""}
        </p>
      )}
      <p className="text-muted-foreground capitalize">
        {well.well_type.replace(/_/g, " ")}
      </p>
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

interface PlateMapViewerProps {
  plateMap: PlateMapResponse;
  className?: string;
}

export function PlateMapViewer({ plateMap, className }: PlateMapViewerProps) {
  const [hoveredWell, setHoveredWell] = useState<string | null>(null);

  const [rows, cols] = plateDimensions(plateMap.format);
  const size = cellSize(plateMap.format);
  const showLabel = size >= 18;

  // Build a map: position -> well
  const wellMap = new Map<string, PlateMapWell>();
  for (const well of plateMap.wells) {
    wellMap.set(well.position, well);
  }

  // Assign stable colors to unique compound molecules
  const compoundIds = [
    ...new Set(
      plateMap.wells
        .filter((w) => w.well_type === "sample" && w.molecule_id)
        .map((w) => w.molecule_id as string)
    ),
  ];
  const compoundColorMap = new Map<string, string>();
  compoundIds.forEach((id, i) => {
    compoundColorMap.set(id, TRACE_COLORS[i % TRACE_COLORS.length]);
  });

  function getWellStyle(well: PlateMapWell | undefined): {
    background: string;
    border?: string;
    opacity?: number;
  } {
    if (!well) return { background: "#27272a" };

    if (well.well_type === "sample") {
      const color = well.molecule_id
        ? (compoundColorMap.get(well.molecule_id) ?? "#3b82f6")
        : "#3b82f6";
      return { background: color };
    }

    const controlColor = CONTROL_COLORS[well.well_type];
    if (controlColor) {
      return {
        background: "transparent",
        border: `2px solid ${controlColor}`,
      };
    }

    return { background: "#27272a" };
  }

  const labelSize =
    size >= 28 ? "text-xs" : size >= 18 ? "text-[10px]" : "text-[8px]";

  const { summary } = plateMap;

  return (
    <div className={cn("space-y-4", className)}>
      {/* Summary bar */}
      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span>
          <span className="font-medium text-foreground">{summary.compounds}</span> compounds
        </span>
        <span>
          <span className="font-medium text-foreground">{summary.sample_wells}</span> sample wells
        </span>
        <span>
          <span className="font-medium text-foreground">{summary.control_wells}</span> control wells
        </span>
        {summary.concentrations_per_compound > 0 && (
          <span>
            <span className="font-medium text-foreground">
              {summary.concentrations_per_compound}
            </span>{" "}
            conc / compound
          </span>
        )}
        {summary.replicates > 1 && (
          <span>
            <span className="font-medium text-foreground">{summary.replicates}</span>x replicates
          </span>
        )}
      </div>

      {/* Compound legend */}
      {compoundIds.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {compoundIds.map((id) => {
            const well = plateMap.wells.find((w) => w.molecule_id === id);
            const color = compoundColorMap.get(id) ?? "#3b82f6";
            return (
              <div key={id} className="flex items-center gap-1.5 text-xs">
                <span
                  className="h-3 w-3 rounded-full inline-block"
                  style={{ background: color }}
                />
                {well?.molecule_name ?? id}
              </div>
            );
          })}
          {Object.entries(CONTROL_COLORS).map(([type, color]) => {
            const hasType = plateMap.wells.some((w) => w.well_type === type);
            if (!hasType) return null;
            return (
              <div key={type} className="flex items-center gap-1.5 text-xs">
                <span
                  className="h-3 w-3 rounded-full inline-block border-2"
                  style={{ borderColor: color, background: "transparent" }}
                />
                {type.replace(/_/g, " ")}
              </div>
            );
          })}
        </div>
      )}

      {/* Plate grid */}
      <div className="overflow-auto">
        <div
          className="inline-grid select-none"
          style={{
            gridTemplateColumns: `${size + 8}px repeat(${cols}, ${size}px)`,
            gridTemplateRows: `${size}px repeat(${rows}, ${size}px)`,
            gap: "1px",
          }}
        >
          {/* Top-left corner */}
          <div />

          {/* Column headers */}
          {Array.from({ length: cols }, (_, c) => (
            <div
              key={`col-${c}`}
              className={cn(
                "flex items-center justify-center",
                labelSize,
                "text-muted-foreground font-medium"
              )}
            >
              {c + 1}
            </div>
          ))}

          {/* Rows */}
          {Array.from({ length: rows }, (_, r) => {
            const rLabel = rowLabel(r);
            return (
              <Fragment key={`row-${r}`}>
                {/* Row header */}
                <div
                  className={cn(
                    "flex items-center justify-center",
                    labelSize,
                    "text-muted-foreground font-medium"
                  )}
                >
                  {rLabel}
                </div>

                {/* Wells */}
                {Array.from({ length: cols }, (_, c) => {
                  const pos = `${rLabel}${c + 1}`;
                  const well = wellMap.get(pos);
                  const style = getWellStyle(well);
                  const isHovered = hoveredWell === pos;

                  return (
                    <div
                      key={pos}
                      className="relative rounded-sm cursor-default transition-opacity"
                      style={{
                        width: size,
                        height: size,
                        background: style.background,
                        border: style.border,
                        boxSizing: "border-box",
                        opacity: isHovered ? 0.75 : 1,
                      }}
                      onMouseEnter={() => setHoveredWell(pos)}
                      onMouseLeave={() => setHoveredWell(null)}
                      title={pos}
                    >
                      {showLabel && !well && (
                        <span className="flex h-full w-full items-center justify-center text-[8px] text-muted-foreground/40 select-none">
                          {pos}
                        </span>
                      )}
                      {isHovered && well && <WellTooltip well={well} />}
                    </div>
                  );
                })}
              </Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
}
