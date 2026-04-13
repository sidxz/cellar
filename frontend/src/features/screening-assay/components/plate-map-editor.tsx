"use client";

import { Fragment, useCallback, useRef, useState } from "react";
import { cn } from "@/shared/lib/utils";
import type { PlateFormat, WellDesignation } from "../types";
import { WELL_DESIGNATION_LABELS } from "../types";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const WELL_COLORS: Record<WellDesignation, string> = {
  compound: "bg-blue-500",
  positive_control: "bg-green-500",
  negative_control: "bg-red-500",
  empty: "bg-gray-300 dark:bg-gray-700",
};

const WELL_DOT_COLORS: Record<WellDesignation, string> = {
  compound: "bg-blue-500",
  positive_control: "bg-green-500",
  negative_control: "bg-red-500",
  empty: "bg-gray-400",
};

const DESIGNATIONS: WellDesignation[] = [
  "compound",
  "positive_control",
  "negative_control",
  "empty",
];

/** Plate dimensions: [rows, cols] */
function plateDimensions(format: PlateFormat): [number, number] {
  switch (format) {
    case "6":
      return [2, 3];
    case "12":
      return [3, 4];
    case "24":
      return [4, 6];
    case "48":
      return [6, 8];
    case "96":
      return [8, 12];
    case "384":
      return [16, 24];
    case "1536":
      return [32, 48];
    default:
      return [8, 12];
  }
}

/** Row label: A-Z, then AA-AZ, BA-BZ, etc. */
function rowLabel(index: number): string {
  if (index < 26) return String.fromCharCode(65 + index);
  return (
    String.fromCharCode(65 + Math.floor(index / 26) - 1) +
    String.fromCharCode(65 + (index % 26))
  );
}

/** Cell size in pixels based on plate format */
function cellSize(format: PlateFormat): number {
  switch (format) {
    case "6":
    case "12":
    case "24":
    case "48":
      return 28;
    case "96":
      return 28;
    case "384":
      return 18;
    case "1536":
      return 10;
    default:
      return 28;
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

interface PlateMapEditorProps {
  format: PlateFormat;
  value: Record<string, WellDesignation>;
  onChange: (map: Record<string, WellDesignation>) => void;
}

export function PlateMapEditor({
  format,
  value,
  onChange,
}: PlateMapEditorProps) {
  const [selectedDesignation, setSelectedDesignation] =
    useState<WellDesignation>("compound");
  const isMouseDownRef = useRef(false);

  const [rows, cols] = plateDimensions(format);
  const size = cellSize(format);
  const showText = size >= 18;

  const setWell = useCallback(
    (wellKey: string) => {
      const next = { ...value };
      next[wellKey] = selectedDesignation;
      onChange(next);
    },
    [value, onChange, selectedDesignation]
  );

  const fillRow = useCallback(
    (rowIndex: number) => {
      const next = { ...value };
      const rLabel = rowLabel(rowIndex);
      for (let c = 1; c <= cols; c++) {
        next[`${rLabel}${c}`] = selectedDesignation;
      }
      onChange(next);
    },
    [value, onChange, cols, selectedDesignation]
  );

  const fillCol = useCallback(
    (colIndex: number) => {
      const next = { ...value };
      for (let r = 0; r < rows; r++) {
        next[`${rowLabel(r)}${colIndex}`] = selectedDesignation;
      }
      onChange(next);
    },
    [value, onChange, rows, selectedDesignation]
  );

  const handleMouseDown = useCallback(
    (wellKey: string) => {
      isMouseDownRef.current = true;
      setWell(wellKey);
    },
    [setWell]
  );

  const handleMouseEnter = useCallback(
    (wellKey: string) => {
      if (isMouseDownRef.current) {
        setWell(wellKey);
      }
    },
    [setWell]
  );

  const handleMouseUp = useCallback(() => {
    isMouseDownRef.current = false;
  }, []);

  // Label size based on cell size
  const labelSize = size >= 28 ? "text-xs" : size >= 18 ? "text-[10px]" : "text-[8px]";

  return (
    <div className="space-y-3">
      {/* Toolbar — designation selector */}
      <div className="flex items-center gap-2 flex-wrap">
        {DESIGNATIONS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setSelectedDesignation(d)}
            className={cn(
              "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors",
              selectedDesignation === d
                ? "border-primary ring-2 ring-primary/30 bg-primary/10"
                : "border-border hover:bg-accent"
            )}
          >
            <span
              className={cn("h-3 w-3 rounded-full", WELL_DOT_COLORS[d])}
            />
            {WELL_DESIGNATION_LABELS[d]}
          </button>
        ))}
      </div>

      {/* Grid */}
      <div
        className="overflow-auto select-none"
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div
          className="inline-grid"
          style={{
            gridTemplateColumns: `${size + 8}px repeat(${cols}, ${size}px)`,
            gridTemplateRows: `${size}px repeat(${rows}, ${size}px)`,
            gap: "1px",
          }}
        >
          {/* Top-left corner — empty */}
          <div />

          {/* Column headers */}
          {Array.from({ length: cols }, (_, c) => (
            <button
              key={`col-${c}`}
              type="button"
              onClick={() => fillCol(c + 1)}
              className={cn(
                "flex items-center justify-center rounded-sm cursor-pointer hover:bg-accent transition-colors",
                labelSize,
                "text-muted-foreground font-medium"
              )}
              title={`Fill column ${c + 1}`}
            >
              {c + 1}
            </button>
          ))}

          {/* Rows */}
          {Array.from({ length: rows }, (_, r) => {
            const rLabel = rowLabel(r);
            return (
              <Fragment key={`row-${r}`}>
                {/* Row header */}
                <button
                  type="button"
                  onClick={() => fillRow(r)}
                  className={cn(
                    "flex items-center justify-center rounded-sm cursor-pointer hover:bg-accent transition-colors",
                    labelSize,
                    "text-muted-foreground font-medium"
                  )}
                  title={`Fill row ${rLabel}`}
                >
                  {rLabel}
                </button>

                {/* Wells */}
                {Array.from({ length: cols }, (_, c) => {
                  const wellKey = `${rLabel}${c + 1}`;
                  const designation = value[wellKey] ?? "empty";
                  return (
                    <div
                      key={wellKey}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        handleMouseDown(wellKey);
                      }}
                      onMouseEnter={() => handleMouseEnter(wellKey)}
                      className={cn(
                        "rounded-sm cursor-pointer transition-colors hover:opacity-80",
                        WELL_COLORS[designation]
                      )}
                      title={`${wellKey}: ${WELL_DESIGNATION_LABELS[designation]}`}
                      style={{ width: size, height: size }}
                    >
                      {showText && (
                        <span className="flex h-full w-full items-center justify-center text-[8px] text-white/70 select-none">
                          {wellKey}
                        </span>
                      )}
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
