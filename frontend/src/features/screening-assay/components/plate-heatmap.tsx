"use client";

import { cn } from "@/shared/lib/utils";
import { type PlateFormat, type WellType, WELL_TYPE_LABELS } from "../types";
import { WELL_TYPE_COLORS as VF_WELL_COLORS, WELL_EMPTY_COLOR } from "@/shared/lib/chart-colors";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface WellData {
  row: number;
  column: number;
  well_type?: WellType;
  value?: number;
}

interface PlateHeatmapProps {
  format: PlateFormat;
  wells?: WellData[];
  valueRange?: { min: number; max: number };
  className?: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const PLATE_DIMENSIONS: Record<PlateFormat, { rows: number; cols: number }> = {
  "6": { rows: 2, cols: 3 },
  "12": { rows: 3, cols: 4 },
  "24": { rows: 4, cols: 6 },
  "48": { rows: 6, cols: 8 },
  "96": { rows: 8, cols: 12 },
  "384": { rows: 16, cols: 24 },
  "1536": { rows: 32, cols: 48 },
};

const WELL_TYPE_COLORS: Record<WellType, string> = VF_WELL_COLORS as Record<WellType, string>;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getRowLabel(index: number): string {
  if (index < 26) return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[index];
  const first = Math.floor(index / 26) - 1;
  const second = index % 26;
  return `${"ABCDEFGHIJKLMNOPQRSTUVWXYZ"[first]}${"ABCDEFGHIJKLMNOPQRSTUVWXYZ"[second]}`;
}

function valueToColor(value: number, min: number, max: number): string {
  const range = max - min;
  const ratio = range === 0 ? 0.5 : Math.max(0, Math.min(1, (value - min) / range));

  // blue (low) → yellow (mid) → red (high)
  if (ratio <= 0.5) {
    const t = ratio * 2;
    const r = Math.round(59 + (234 - 59) * t);
    const g = Math.round(130 + (179 - 130) * t);
    const b = Math.round(246 + (8 - 246) * t);
    return `rgb(${r},${g},${b})`;
  } else {
    const t = (ratio - 0.5) * 2;
    const r = Math.round(234 + (239 - 234) * t);
    const g = Math.round(179 + (68 - 179) * t);
    const b = Math.round(8 + (68 - 8) * t);
    return `rgb(${r},${g},${b})`;
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function PlateHeatmap({
  format,
  wells = [],
  valueRange,
  className,
}: PlateHeatmapProps) {
  const dims = PLATE_DIMENSIONS[format];
  if (!dims) return null;

  const { rows, cols } = dims;

  // Cell sizing based on format
  const cellSize = format === "1536" ? 8 : format === "384" ? 12 : 24;
  const gap = Math.max(1, Math.floor(cellSize * 0.1));

  // Label area widths/heights
  const labelW = cellSize + 4;
  const labelH = cellSize + 4;

  // Build well lookup map: "row,col" -> WellData
  const wellMap = new Map<string, WellData>();
  for (const w of wells) {
    wellMap.set(`${w.row},${w.column}`, w);
  }

  // SVG total dimensions
  const svgWidth = labelW + cols * cellSize + (cols - 1) * gap + 4;
  const svgHeight = labelH + rows * cellSize + (rows - 1) * gap + 4;

  const wellTypeEntries = Object.entries(WELL_TYPE_COLORS) as [WellType, string][];

  return (
    <div className={cn("w-full", className)}>
      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="w-full max-w-full"
        style={{ maxHeight: 400 }}
        aria-label={`${format}-well plate heatmap`}
      >
        {/* Column labels */}
        {Array.from({ length: cols }, (_, ci) => (
          <text
            key={`col-${ci}`}
            x={labelW + ci * (cellSize + gap) + cellSize / 2}
            y={labelH - 4}
            textAnchor="middle"
            fontSize={Math.max(6, cellSize * 0.45)}
            fill="currentColor"
            className="fill-muted-foreground"
          >
            {ci + 1}
          </text>
        ))}

        {/* Row labels + wells */}
        {Array.from({ length: rows }, (_, ri) => {
          const rowLabel = getRowLabel(ri);
          const rowY = labelH + ri * (cellSize + gap);

          return (
            <g key={`row-${ri}`}>
              {/* Row label */}
              <text
                x={labelW / 2}
                y={rowY + cellSize / 2 + Math.max(4, cellSize * 0.35)}
                textAnchor="middle"
                fontSize={Math.max(6, cellSize * 0.45)}
                fill="currentColor"
                className="fill-muted-foreground"
              >
                {rowLabel}
              </text>

              {/* Wells */}
              {Array.from({ length: cols }, (_, ci) => {
                const wellKey = `${ri + 1},${ci + 1}`;
                const wellData = wellMap.get(wellKey);
                const hasData = !!wellData;

                let fillColor = WELL_EMPTY_COLOR;
                let opacity = 0.2;
                let titleText = `${rowLabel}${ci + 1}`;

                if (hasData) {
                  opacity = 1.0;
                  if (valueRange !== undefined && wellData.value !== undefined) {
                    fillColor = valueToColor(wellData.value, valueRange.min, valueRange.max);
                    titleText += ` — ${wellData.value}`;
                  } else if (wellData.well_type) {
                    fillColor = WELL_TYPE_COLORS[wellData.well_type];
                    titleText += ` — ${WELL_TYPE_LABELS[wellData.well_type]}`;
                  }
                }

                const cx = labelW + ci * (cellSize + gap);

                return (
                  <rect
                    key={`well-${ri}-${ci}`}
                    x={cx}
                    y={rowY}
                    width={cellSize}
                    height={cellSize}
                    rx={cellSize <= 8 ? 1 : 3}
                    fill={fillColor}
                    opacity={opacity}
                  >
                    <title>{titleText}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}
      </svg>

      {/* Legend (only when not using valueRange) */}
      {!valueRange && (
        <div className="mt-3 flex flex-wrap gap-3">
          {wellTypeEntries.map(([type, color]) => (
            <div key={type} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: color }}
              />
              {WELL_TYPE_LABELS[type]}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
